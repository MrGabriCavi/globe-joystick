"""Offline API contract tests. Run: python -m unittest discover -s tests -v."""
import gzip
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    'globe_api_under_test', Path(__file__).resolve().parents[1] / 'api' / 'server.py')
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


class AboveTests(unittest.TestCase):
    def setUp(self):
        self.state = patch.multiple(api, above_cache={}, n2yo_calls=api.deque(),
                                    ip_hits=api.defaultdict(api.deque), N2YO_KEY='test-only')
        self.state.start()
        self.addCleanup(self.state.stop)
        self.clock = patch.object(api.time, 'time', return_value=10000)
        self.now = self.clock.start()
        self.addCleanup(self.clock.stop)
        self.network = patch.object(api.urllib.request, 'urlopen')
        self.urlopen = self.network.start()
        self.addCleanup(self.network.stop)
        self.urlopen.return_value.__enter__.return_value.read.return_value = (
            b'{"above":[{"satid":25544}],"info":{"transactionscount":1}}')
        self.logging = patch.object(api, 'log')
        self.logging.start()
        self.addCleanup(self.logging.stop)

    def test_nearby_coordinates_share_cache_and_only_spend_one_call(self):
        first = api.above(41.91, 12.51)
        second = api.above(41.92, 12.52)
        self.assertEqual(first, second)
        self.assertEqual(first[0], 200)
        self.assertEqual(json.loads(first[1])['lat'], 42)
        self.assertEqual(json.loads(first[1])['lon'], 12.5)
        self.assertEqual(len(api.n2yo_calls), 1)
        self.urlopen.assert_called_once()
        self.assertIn('/42.0/12.5/', self.urlopen.call_args.args[0].full_url)

    def test_cache_expires_at_exact_ttl(self):
        api.above(0, 0)
        self.now.return_value += api.ABOVE_TTL - 1
        api.above(0, 0)
        self.assertEqual(self.urlopen.call_count, 1)
        self.now.return_value += 1
        api.above(0, 0)
        self.assertEqual(self.urlopen.call_count, 2)

    def test_cache_hit_still_works_when_hourly_quota_is_full(self):
        cached = api.above(0, 0)
        api.n2yo_calls.extend([10000] * (api.N2YO_HOURLY - 1))
        self.assertEqual(api.above(0, 0), cached)
        self.assertEqual(api.above(1, 1)[0], 429)
        self.urlopen.assert_called_once()

    def test_expired_hourly_calls_no_longer_block_requests(self):
        api.n2yo_calls.extend([10000 - 3601] * api.N2YO_HOURLY)
        self.assertEqual(api.above(0, 0)[0], 200)
        self.assertEqual(len(api.n2yo_calls), 1)

    def test_network_failure_spends_quota_but_does_not_poison_cache(self):
        self.urlopen.side_effect = TimeoutError('offline test')
        self.assertEqual(api.above(0, 0)[0], 502)
        self.assertEqual(len(api.n2yo_calls), 1)
        self.assertEqual(api.above_cache, {})


class HandlerTests(unittest.TestCase):
    def handler(self, headers=None):
        handler = object.__new__(api.Handler)
        handler.headers = headers or {}
        handler.client_address = ('192.0.2.1', 1234)
        handler.command = 'GET'
        handler.wfile = io.BytesIO()
        handler.send_response = lambda code: setattr(handler, 'status', code)
        handler.send_header = lambda *_: None
        handler.end_headers = lambda: None
        return handler

    def setUp(self):
        state = patch.multiple(api, N2YO_KEY='test-only', ip_hits=api.defaultdict(api.deque))
        state.start()
        self.addCleanup(state.stop)

    def test_invalid_coordinates_never_reach_upstream(self):
        cases = [{}, {'lat': ['NaN'], 'lon': ['0']},
                 {'lat': ['inf'], 'lon': ['0']},
                 {'lat': ['90.01'], 'lon': ['0']},
                 {'lat': ['0'], 'lon': ['-180.01']},
                 {'lat': ['abc'], 'lon': ['0']}]
        with patch.object(api, 'above') as upstream:
            for query in cases:
                with self.subTest(query=query):
                    api.ip_hits.clear()
                    handler = self.handler()
                    handler.handle_above(query)
                    self.assertEqual(handler.status, 400)
            upstream.assert_not_called()

    def test_coordinate_extremes_are_valid(self):
        with patch.object(api, 'above', return_value=(200, b'{}')) as upstream:
            for lat, lon in [(-90, -180), (90, 180)]:
                handler = self.handler()
                handler.handle_above({'lat': [str(lat)], 'lon': [str(lon)]})
                self.assertEqual(handler.status, 200)
                upstream.assert_called_with(lat, lon)

    def test_cross_origin_request_does_not_spend_quota(self):
        with patch.object(api, 'above') as upstream:
            for headers in [{'Origin': 'https://example.invalid'},
                            {'Sec-Fetch-Site': 'cross-site'}]:
                handler = self.handler(headers)
                handler.handle_above({'lat': ['0'], 'lon': ['0']})
                self.assertEqual(handler.status, 403)
            upstream.assert_not_called()
            self.assertEqual(dict(api.ip_hits), {})

    def test_seventh_request_is_limited_and_recovers_after_window(self):
        with patch.object(api.time, 'time', return_value=10000) as now, \
                patch.object(api, 'above', return_value=(200, b'{}')) as upstream:
            for i in range(api.PER_IP_PER_MIN + 1):
                handler = self.handler()
                handler.handle_above({'lat': ['0'], 'lon': ['0']})
                self.assertEqual(handler.status, 200 if i < api.PER_IP_PER_MIN else 429)
            self.assertEqual(upstream.call_count, api.PER_IP_PER_MIN)
            now.return_value += 61
            handler.handle_above({'lat': ['0'], 'lon': ['0']})
            self.assertEqual(handler.status, 200)

    def test_head_returns_headers_without_body(self):
        handler = self.handler()
        handler.command = 'HEAD'
        handler.reply(200, b'{"ok":true}')
        self.assertEqual(handler.status, 200)
        self.assertEqual(handler.wfile.getvalue(), b'')

    def test_unknown_group_never_reads_a_file(self):
        handler = self.handler()
        handler.path = '/api/gp/unknown'
        with patch.object(api, 'load') as load:
            handler.do_GET()
            self.assertEqual(handler.status, 404)
            load.assert_not_called()


class FileCacheTests(unittest.TestCase):
    def test_missing_file_and_gzip_round_trip(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(api, 'files', {}):
            path = Path(directory) / 'stations.json'
            self.assertIsNone(api.load(path))
            raw = b'[{"NORAD_CAT_ID":25544}]'
            path.write_bytes(raw)
            loaded = api.load(path)
            self.assertEqual(loaded[1], raw)
            self.assertEqual(gzip.decompress(loaded[2]), raw)
            self.assertIs(api.load(path), loaded)


if __name__ == '__main__':
    unittest.main()
