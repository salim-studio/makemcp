"""Fast python->JSON-Schema generation using only stdlib (no pydantic).

Supports: str,int,float,bool,None,list,dict,tuple,set,
Optional[X], Union, Literal, enums, dataclasses, TypedDict,
lists/dicts nesting. Results are cached per-function for speed.
"""
from __future__ import annotations

import dataclasses
import enum
import inspect
import typing
from typing import Any, get_args, get_origin

_PY_TO_JSON = {str: "string", int: "integer", float: "number", bool: "boolean",
               bytes: "string", bytearray: "string", type(None): "null"}

_CACHE: dict[int, dict] = {}


def _ref_name(tp) -> str:
    return getattr(tp, "__name__", str(tp))


def type_to_schema(tp: Any) -> dict:
    """Convert a python annotation to JSON Schema (fast path first)."""
    if tp is inspect.Parameter.empty or tp is Any:
        return {}
    if tp in _PY_TO_JSON:
        return {"type": _PY_TO_JSON[tp]}
    if tp is dict or tp is object:
        return {"type": "object"}
    if tp is list or tp is tuple or tp is set:
        return {"type": "array"}
    origin = get_origin(tp)
    args = get_args(tp)
    # Optional / Union (typing.Union + X|Y syntax)
    import types as _types
    _UNION_ORIGINS = {typing.Union, getattr(_types, "UnionType", None)}
    if origin in _UNION_ORIGINS:
        non_none = [a for a in args if a is not type(None)]
        nullable = len(non_none) != len(args)
        if len(non_none) == 1:
            s = type_to_schema(non_none[0])
            if nullable:
                t = s.get("type")
                if t and isinstance(t, str):
                    s = dict(s, type=[t, "null"])
                elif "anyOf" not in s:
                    s = {"anyOf": [s, {"type": "null"}]}
            return s
        out: dict = {"anyOf": [type_to_schema(a) for a in non_none]}
        if nullable:
            out["anyOf"].append({"type": "null"})
        return out
    # Literal
    if origin is typing.Literal:
        vals = list(args)
        types = {type(v).__name__ for v in vals}
        return {"enum": vals}
    if origin in (list, tuple, set, frozenset):
        item = type_to_schema(args[0]) if args else {}
        return {"type": "array", "items": item}
    if origin is dict:
        vsch = type_to_schema(args[1]) if len(args) == 2 else {}
        sch: dict = {"type": "object"}
        if vsch:
            sch["additionalProperties"] = vsch
        return sch
    # Enum
    if isinstance(tp, type) and issubclass(tp, enum.Enum):
        try:
            vals = [e.value for e in tp]
        except Exception:
            vals = [e.name for e in tp]
        return {"enum": vals}
    # Dataclass
    if isinstance(tp, type) and dataclasses.is_dataclass(tp):
        props = {}
        req = []
        for f in dataclasses.fields(tp):
            props[f.name] = type_to_schema(f.type)
            if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
                req.append(f.name)
        sch = {"type": "object", "properties": props}
        if req:
            sch["required"] = req
        return sch
    # TypedDict
    if isinstance(tp, type) and hasattr(tp, "__annotations__") and hasattr(tp, "__total__"):
        try:
            hints = typing.get_type_hints(tp)
            props = {k: type_to_schema(v) for k, v in hints.items()}
            sch = {"type": "object", "properties": props}
            if getattr(tp, "__total__", True):
                sch["required"] = list(hints.keys())
            return sch
        except Exception:
            pass
    # Fallback primitives by name
    name = getattr(tp, "__name__", "")
    if name in ("str", "string"):
        return {"type": "string"}
    if name in ("int", "integer"):
        return {"type": "integer"}
    if name in ("float", "number"):
        return {"type": "number"}
    if name in ("bool", "boolean"):
        return {"type": "boolean"}
    return {"type": "object"}


def types_union():
    import types
    return types.UnionType


def _is_union_origin(origin) -> bool:
    import types
    return origin is typing.Union or origin is getattr(types, "UnionType", None)


# Patch: handle X | Y syntax
_orig_type_to_schema = type_to_schema


def func_schema(fn) -> dict:
    """Build JSON-Schema object for a function signature. Cached by fn id + qualname."""
    key = id(fn)
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    sig = inspect.signature(fn)
    try:
        hints = typing.get_type_hints(fn)
    except Exception:
        hints = {}
    props: dict = {}
    required: list = []
    for name, p in sig.parameters.items():
        if name in ("self", "cls", "ctx", "context", "_ctx"):
            continue
        if p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        ann = hints.get(name, p.annotation)
        # X | None support
        origin = get_origin(ann)
        if _is_union_origin(origin):
            sch = _union_schema(ann)
        else:
            sch = _orig_type_to_schema(ann)
        if p.default is not inspect.Parameter.empty:
            try:
                import json as _j
                _j.dumps(p.default)
                sch["default"] = p.default
            except Exception:
                sch["default"] = str(p.default)
        else:
            required.append(name)
        props[name] = sch
    out = {"type": "object", "properties": props}
    if required:
        out["required"] = required
    _CACHE[key] = out
    return out


def _union_schema(tp) -> dict:
    args = get_args(tp)
    non_none = [a for a in args if a is not type(None)]
    nullable = len(non_none) != len(args)
    if len(non_none) == 1:
        s = _orig_type_to_schema(non_none[0])
        if nullable:
            t = s.get("type")
            if isinstance(t, str):
                return dict(s, type=[t, "null"])
            return {"anyOf": [s, {"type": "null"}]}
        return s
    out: dict = {"anyOf": [_orig_type_to_schema(a) for a in non_none]}
    if nullable:
        out["anyOf"].append({"type": "null"})
    return out


def coerce(value: Any, ann: Any) -> Any:
    """Tiny fast coercion (str->int/float/bool). Returns value unchanged on failure."""
    if ann is inspect.Parameter.empty or ann is Any:
        return value
    try:
        if ann is int and isinstance(value, str):
            v = value.strip()
            return int(v, 0) if v[:2].lower() in ("0x", "0o", "0b") else int(v)
        if ann is float and isinstance(value, str):
            return float(value)
        if ann is bool and isinstance(value, str):
            lv = value.strip().lower()
            if lv in ("1", "true", "yes", "y", "on"):
                return True
            if lv in ("0", "false", "no", "n", "off"):
                return False
    except Exception:
        pass
    return value
