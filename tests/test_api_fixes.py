"""Test delle correzioni ai rilievi della revisione di sicurezza (F2-F5) e dell'IP falsificabile.
Senza rete: N2YO è sostituito da finte risposte. Run: python -B -m unittest discover -s tests -v."""
import importlib.util
import io
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import MagicMock, patch


spec = importlib.util.spec_from_file_location(
    'globe_api_fixes_under_test', Path(__file__).resolve().parents[1] / 'api' / 'server.py')
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


def upstream_answer(body):
    res = MagicMock()
    res.__enter__.return_value.read.return_value = body
    return res


def make_handler(headers=None, command='GET', path='/'):
    h = object.__new__(api.Handler)
    h.headers = headers or {}
    h.client_address = ('10.0.1.8', 40000)   # Traefik, nella rete interna
    h.command, h.path = command, path
    h.wfile = io.BytesIO()
    h.send_response = lambda code: setattr(h, 'status', code)
    h.send_header = lambda *_: None
    h.end_headers = lambda: None
    return h


class FixTests(unittest.TestCase):
    def setUp(self):
        state = patch.multiple(api, above_cache={}, above_inflight={}, n2yo_calls=api.deque(),
                               ip_hits=api.defaultdict(api.deque), ip_pruned_at=0.0, N2YO_KEY='test-only')
        state.start()
        self.addCleanup(state.stop)
        quiet = patch.object(api, 'log')
        quiet.start()
        self.addCleanup(quiet.stop)

    def test_f2_concurrent_requests_for_one_point_make_one_call(self):
        release, started = threading.Event(), threading.Event()

        def slow_upstream(*_args, **_kwargs):
            started.set()
            release.wait(timeout=5)
            return upstream_answer(b'{"above":[{"satid":1}],"info":{}}')

        with patch.object(api.urllib.request, 'urlopen', side_effect=slow_upstream) as upstream:
            results = []
            first = threading.Thread(target=lambda: results.append(api.above(42, 12.5)))
            first.start()
            started.wait(timeout=5)
            second = threading.Thread(target=lambda: results.append(api.above(42.1, 12.4)))
            second.start()
            release.set()
            first.join(5)
            second.join(5)
        self.assertEqual([code for code, _ in results], [200, 200])
        self.assertEqual(results[0][1], results[1][1])
        self.assertEqual(upstream.call_count, 1)
        self.assertEqual(len(api.n2yo_calls), 1)
        self.assertEqual(api.above_inflight, {})

    def test_f2_waiting_request_gets_502_if_the_call_fails(self):
        release, started = threading.Event(), threading.Event()

        def failing_upstream(*_args, **_kwargs):
            started.set()
            release.wait(timeout=5)
            raise TimeoutError('offline test')

        with patch.object(api.urllib.request, 'urlopen', side_effect=failing_upstream):
            results = []
            first = threading.Thread(target=lambda: results.append(api.above(0, 0)))
            first.start()
            started.wait(timeout=5)
            second = threading.Thread(target=lambda: results.append(api.above(0, 0)))
            second.start()
            release.set()
            first.join(5)
            second.join(5)
        self.assertEqual(sorted(code for code, _ in results), [502, 502])
        self.assertEqual(api.above_inflight, {})

    def test_f4_malformed_upstream_answers_become_502(self):
        for body in [b'null', b'[]', b'"text"', b'{"above":"no"}', b'{"above":null,"info":3}']:
            with self.subTest(body=body):
                api.above_cache.clear()
                api.n2yo_calls.clear()
                with patch.object(api.urllib.request, 'urlopen', return_value=upstream_answer(body)):
                    code, payload = api.above(0, 0)
                if body == b'{"above":null,"info":3}':   # "above" assente o vuoto è un elenco vuoto valido
                    self.assertEqual(code, 200)
                    self.assertEqual(json.loads(payload)['above'], [])
                else:
                    self.assertEqual(code, 502)

    def test_f4_non_object_entries_are_dropped(self):
        body = b'{"above":[{"satid":1},null,7,"x"],"info":{"transactionscount":1}}'
        with patch.object(api.urllib.request, 'urlopen', return_value=upstream_answer(body)):
            code, payload = api.above(0, 0)
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(payload)['above'], [{'satid': 1}])

    def test_f5_head_on_above_never_calls_n2yo(self):
        h = make_handler(command='HEAD', path='/api/above?lat=42&lon=12.5')
        with patch.object(api.urllib.request, 'urlopen') as upstream:
            h.do_HEAD()
        self.assertEqual(h.status, 405)
        self.assertEqual(h.wfile.getvalue(), b'')
        upstream.assert_not_called()

    def test_f5_head_on_data_still_works(self):
        h = make_handler(command='HEAD', path='/api/gp/visual')
        with patch.object(api, 'load', return_value=(0, b'[1]', b'gz')):
            h.do_HEAD()
        self.assertEqual(h.status, 200)
        self.assertEqual(h.wfile.getvalue(), b'')

    def test_f3_idle_visitors_leave_the_table(self):
        with patch.object(api, 'above', return_value=(200, b'{}')), \
                patch.object(api.time, 'time', return_value=10000) as now:
            for i in range(50):
                make_handler({'X-Forwarded-For': f'198.51.100.{i}'}).handle_above({'lat': ['0'], 'lon': ['0']})
            self.assertEqual(len(api.ip_hits), 50)
            now.return_value += 61
            make_handler({'X-Forwarded-For': '203.0.113.5'}).handle_above({'lat': ['0'], 'lon': ['0']})
        self.assertEqual(list(api.ip_hits), ['203.0.113.5'])

    def test_spoofed_cf_header_is_ignored_when_not_from_cloudflare(self):
        h = make_handler({'X-Forwarded-For': '87.15.142.102', 'CF-Connecting-IP': '203.0.113.77'})
        self.assertEqual(h.client_ip(), '87.15.142.102')

    def test_cf_header_is_used_when_the_connection_comes_from_cloudflare(self):
        for edge in ['162.158.10.20', '2a06:98c1:3120::7']:
            with self.subTest(edge=edge):
                h = make_handler({'X-Forwarded-For': edge, 'CF-Connecting-IP': '87.15.142.102'})
                self.assertEqual(h.client_ip(), '87.15.142.102')

    def test_spoofed_ip_cannot_dodge_the_per_ip_limit(self):
        with patch.object(api, 'above', return_value=(200, b'{}')):
            codes = []
            for i in range(api.PER_IP_PER_MIN + 1):
                h = make_handler({'X-Forwarded-For': '87.15.142.102', 'CF-Connecting-IP': f'203.0.113.{i}'})
                h.handle_above({'lat': ['0'], 'lon': ['0']})
                codes.append(h.status)
        self.assertEqual(codes[-1], 429)


if __name__ == '__main__':
    unittest.main()
