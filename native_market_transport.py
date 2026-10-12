"""Optional C++ HTTPS receiver. Display-only, bounded and never a price cache."""
import ctypes
import json
import threading
import time
from urllib.parse import urlsplit
import service as s

LIBRARY = s.ROOT / 'native/librally_market_transport.so'
_native = None
_rate_lock = threading.Lock()
_retry_at = {}


def receiver():
    global _native
    if _native is None:
        lib = ctypes.CDLL(str(LIBRARY))
        lib.rally_market_get.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p),
                                        ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_long),
                                        ctypes.POINTER(ctypes.c_double)]
        lib.rally_market_get.restype = ctypes.c_int
        lib.rally_market_free.argtypes = [ctypes.c_void_p]
        lib.rally_market_free.restype = None
        _native = lib
    return _native


def get(url):
    host = urlsplit(url).hostname
    with _rate_lock:
        if time.monotonic() < _retry_at.get(host, 0):
            raise s.Problem('Chart provider is cooling down. Retry shortly.', 503, 'chart_provider_rate_limit')
    try:
        lib = receiver()
    except OSError:
        # Development and unsupported hosts retain the existing safe transport.
        return s.http_json(url, timeout=4), {'transport': 'python', 'marketCache': False}
    body, length, status, duration = ctypes.c_void_p(), ctypes.c_size_t(), ctypes.c_long(), ctypes.c_double()
    code = lib.rally_market_get(url.encode(), ctypes.byref(body), ctypes.byref(length),
                               ctypes.byref(status), ctypes.byref(duration))
    try:
        if status.value == 429:
            with _rate_lock:
                _retry_at[host] = time.monotonic()+30
            raise s.Problem('Chart provider is cooling down. Retry shortly.', 503, 'chart_provider_rate_limit')
        if code or not 200 <= status.value < 300 or not body.value or length.value > 2*1024*1024:
            raise s.Problem('Chart provider temporarily unavailable', 503, 'chart_provider_unavailable')
        data = json.loads(ctypes.string_at(body, length.value))
        return data, {'transport': 'cpp-libcurl', 'upstreamMs': round(duration.value, 2),
                      'upstreamStatus': status.value, 'marketCache': False}
    finally:
        if body.value:
            lib.rally_market_free(body)
