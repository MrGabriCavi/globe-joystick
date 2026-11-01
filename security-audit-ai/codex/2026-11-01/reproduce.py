"""Offline evidence for audit findings; assertions describe observed defects, not desired contracts."""
import importlib.util
import io
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('audit_api', ROOT / 'api/server.py')
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


def main():
    results = {}
    response = MagicMock()
    response.__enter__.return_value.read.return_value = b'{"above":[],"info":{}}'
    barrier = Barrier(2)

    def network(*args, **kwargs):
        barrier.wait(timeout=5)
        return response

    with patch.multiple(api, above_cache={}, n2yo_calls=api.deque(), N2YO_KEY='fake'), \
            patch.object(api, 'log'), patch.object(api.urllib.request, 'urlopen', side_effect=network) as upstream:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(api.above, 42, 12.5) for _ in range(2)]
            statuses = [future.result(timeout=10)[0] for future in futures]
        assert statuses == [200, 200] and upstream.call_count == 2
        results['concurrent_same_point'] = {'statuses': statuses, 'upstream_calls': upstream.call_count}

    handler = object.__new__(api.Handler)
    handler.headers = {}
    handler.client_address = ('192.0.2.1', 1)
    handler.command = 'HEAD'
    handler.path = '/api/above?lat=42&lon=12.5'
    handler.wfile = io.BytesIO()
    handler.send_response = lambda code: None
    handler.send_header = lambda *args: None
    handler.end_headers = lambda: None
    with patch.multiple(api, above_cache={}, n2yo_calls=api.deque(),
                        ip_hits=api.defaultdict(api.deque), N2YO_KEY='fake'), \
            patch.object(api, 'log'), patch.object(api.urllib.request, 'urlopen', return_value=response) as upstream:
        handler.do_HEAD()
        assert upstream.call_count == 1 and handler.wfile.getvalue() == b''
        results['head_spends_quota'] = {'upstream_calls': upstream.call_count, 'response_body_bytes': 0}

    response.__enter__.return_value.read.return_value = b'null'
    with patch.multiple(api, above_cache={}, n2yo_calls=api.deque()), \
            patch.object(api.urllib.request, 'urlopen', return_value=response):
        try:
            api.above(0, 0)
        except TypeError:
            results['upstream_null'] = 'uncaught TypeError instead of HTTP 502'
        else:
            raise AssertionError('Expected current schema-validation defect')
    return results


if __name__ == '__main__':
    print(json.dumps(main(), indent=2))
