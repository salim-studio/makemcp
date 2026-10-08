"""Fast JSON layer: orjson > ujson > stdlib json. Zero mandatory deps."""
try:
    import orjson as _orjson

    def dumps(obj) -> bytes:
        return _orjson.dumps(obj, option=_orjson.OPT_NON_STR_KEYS)

    def loads(data):
        if isinstance(data, (bytes, bytearray, memoryview)):
            return _orjson.loads(data)
        if isinstance(data, str):
            return _orjson.loads(data.encode())
        return _orjson.loads(data)

    BACKEND = "orjson"
except ImportError:
    try:
        import ujson as _ujson

        def dumps(obj) -> bytes:
            return _ujson.dumps(obj).encode()

        def loads(data):
            if isinstance(data, (bytes, bytearray)):
                data = bytes(data).decode()
            return _ujson.loads(data)

        BACKEND = "ujson"
    except ImportError:
        import json as _json

        _dumps = _json.dumps

        def dumps(obj) -> bytes:
            return _dumps(obj, separators=(",", ":"), ensure_ascii=False).encode()

        def loads(data):
            if isinstance(data, (bytes, bytearray)):
                data = bytes(data).decode()
            return _json.loads(data)

        BACKEND = "stdlib"
