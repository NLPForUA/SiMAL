# JSON conversion for SIMAL AST structures

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from simal_parser import Annotation, Attribute, Block, Field, Method, Service, System, Endpoint


_BRACKET_ATTRS_RE = re.compile(r"\[([^\]]*)\]")


def _extract_bracket_attr_keys(signature: str) -> set[str]:
    """Extract attribute keys present in a trailing/embedded `[...]` section.

    This is intentionally forgiving (best-effort), because values may contain
    spaces/quotes. We only care about keys to avoid duplicating them outside `def`.
    """
    keys: set[str] = set()
    if not signature:
        return keys

    for m in _BRACKET_ATTRS_RE.finditer(signature):
        inside = m.group(1)
        for part in inside.split(","):
            part = part.strip()
            if not part:
                continue
            # key:value (value may contain ':'; we only split once)
            if ":" in part:
                key = part.split(":", 1)[0].strip()
            else:
                key = part.strip()
            if key:
                keys.add(key)
    return keys


def _annotation_to_dict(a: Annotation) -> dict:
    return {
        "__type__": "Annotation",
        "name": a.name,
        "args": list(a.args),
    }


def _annotation_from_dict(d: dict) -> Annotation:
    return Annotation(
        name=d["name"],
        args=list(d.get("args", [])),
    )


def _attr_to_dict(attr: Attribute) -> dict:
    return {
        "__type__": "Attribute",
        "key": attr.key,
        "value": _to_json_value(attr.value),
        "annotations": [_annotation_to_dict(a) for a in attr.annotations],
    }


def _attr_from_dict(d: dict) -> Attribute:
    return Attribute(
        key=d["key"],
        value=_from_json_value(d["value"]),
        annotations=[_annotation_from_dict(a) for a in d.get("annotations", [])],
    )


def _field_to_dict(f: Field) -> dict:
    return {
        "__type__": "Field",
        "name": f.name,
        "type": f.type,
        "visibility": f.visibility,
        "annotations": [_annotation_to_dict(a) for a in f.annotations],
        "attributes": {k: _attr_to_dict(v) for k, v in f.attributes.items()},
    }


def _field_from_dict(d: dict) -> Field:
    return Field(
        name=d["name"],
        type=d.get("type", ""),
        visibility=d.get("visibility"),
        annotations=[_annotation_from_dict(a) for a in d.get("annotations", [])],
        attributes={
            k: _attr_from_dict(v) for k, v in d.get("attributes", {}).items()
        },
    )


def _method_to_dict(m: Method) -> dict:
    return {
        "__type__": "Method",
        "name": m.name,
        "visibility": m.visibility,
        "params": m.params,
        "returns": m.returns,
        "annotations": [_annotation_to_dict(a) for a in m.annotations],
        "attributes": {k: _attr_to_dict(v) for k, v in m.attributes.items()},
    }


def _method_from_dict(d: dict) -> Method:
    return Method(
        name=d["name"],
        visibility=d.get("visibility"),
        params=d.get("params", ""),
        returns=d.get("returns", ""),
        annotations=[_annotation_from_dict(a) for a in d.get("annotations", [])],
        attributes={
            k: _attr_from_dict(v) for k, v in d.get("attributes", {}).items()
        },
    )


def _block_to_dict(b: Block, explicit_type: Optional[str] = None) -> dict:
    t = explicit_type or b.__class__.__name__  # "Block", "Service", "System"
    return {
        "__type__": t,
        "kind": b.kind,
        "name": b.name,
        "annotations": [_annotation_to_dict(a) for a in b.annotations],
        "attributes": {k: _attr_to_dict(v) for k, v in b.attributes.items()},
    }


def _block_from_dict(d: dict) -> Block:
    t = d.get("__type__", "Block")
    base_kwargs = {
        "kind": d.get("kind"),
        "name": d.get("name"),
        "annotations": [
            _annotation_from_dict(a) for a in d.get("annotations", [])
        ],
        "attributes": {
            k: _attr_from_dict(v) for k, v in d.get("attributes", {}).items()
        },
    }

    if t == "Service":
        return Service(**base_kwargs)
    elif t == "System":
        return System(**base_kwargs)
    else:
        return Block(**base_kwargs)
    
def _endpoint_to_dict(e: Endpoint) -> dict:
    return {
        "__type__": "Endpoint",
        "style": e.style,
        "name": e.name,
        "method": e.method,
        "path": e.path,
        "request": e.request,
        "response": e.response,
        "annotations": [_annotation_to_dict(a) for a in e.annotations],
        "attributes": {k: _to_json_value(v) for k, v in e.attributes.items()},
        "raw": e.raw,
        # parsed fields are derived, better to recompute than store
    }

def _endpoint_from_dict(d: dict) -> Endpoint:
    return Endpoint(
        style=d.get("style"),
        name=d.get("name"),
        method=d.get("method"),
        path=d.get("path"),
        request=d.get("request", ""),
        response=d.get("response", ""),
        annotations=[
            _annotation_from_dict(a) for a in d.get("annotations", [])
        ],
        attributes={
            k: _from_json_value(v) for k, v in d.get("attributes", {}).items()
        },
        raw=d.get("raw", ""),
    )

def _to_json_value(v: Any) -> Any:
    """
    Recursively convert AST values (System, Service, Block, Method, Attribute, Annotation,
    dicts, lists, primitives, etc.) into JSON-serializable structures with type tags.
    """
    if isinstance(v, System):
        data = _block_to_dict(v, explicit_type="System")
        data["services"] = [_block_to_dict(s, explicit_type="Service") for s in v.services]
        return data

    if isinstance(v, Service):
        return _block_to_dict(v, explicit_type="Service")

    if isinstance(v, Block):
        return _block_to_dict(v, explicit_type="Block")
    
    if isinstance(v, Field):
        return _field_to_dict(v) 

    if isinstance(v, Method):
        return _method_to_dict(v)

    if isinstance(v, Attribute):
        return _attr_to_dict(v)

    if isinstance(v, Annotation):
        return _annotation_to_dict(v)
    
    if isinstance(v, Endpoint):
        return _endpoint_to_dict(v)

    if isinstance(v, list):
        return [_to_json_value(x) for x in v]

    if isinstance(v, dict):
        return {k: _to_json_value(val) for k, val in v.items()}

    # simple types: str, int, float, bool, None
    return v


def _from_json_value(v: Any) -> Any:
    """
    Recursively reconstruct AST values from JSON-serializable structures.
    """
    if isinstance(v, list):
        return [_from_json_value(x) for x in v]

    if not isinstance(v, dict):
        return v

    t = v.get("__type__")

    if t == "Annotation":
        return _annotation_from_dict(v)
    if t == "Attribute":
        return _attr_from_dict(v)
    if t == "Field":
        return _field_from_dict(v)
    if t == "Method":
        return _method_from_dict(v)
    if t == "Endpoint":
        return _endpoint_from_dict(v)
    if t in ("Block", "Service", "System"):
        return _block_from_dict(v)

    # plain dict (map in SIMAL)
    return {k: _from_json_value(val) for k, val in v.items()}


def system_to_json_dict(system: System) -> dict:
    """
    Convert a System AST node into a JSON-serializable dict.
    """
    return _to_json_value(system)


def system_from_json_dict(data: dict) -> System:
    """
    Convert a JSON dict (previously produced by system_to_json_dict) back into a System.
    """
    if not isinstance(data, dict):
        raise ValueError("system_from_json_dict expects a dict")

    if data.get("__type__") not in ("System", None):
        # if type tag is missing or wrong, we still try but warn
        pass

    # base System block
    sys_block = _block_from_dict({**data, "__type__": "System"})
    if not isinstance(sys_block, System):
        sys_block = System(
            kind=sys_block.kind,
            name=sys_block.name,
            annotations=sys_block.annotations,
            attributes=sys_block.attributes,
        )

    # restore services
    services_data = data.get("services", [])
    sys_block.services = []
    for sdata in services_data:
        s = _from_json_value(sdata)
        if isinstance(s, Service):
            sys_block.services.append(s)
        elif isinstance(s, Block):  # fallback: upcast
            sys_block.services.append(
                Service(
                    kind=s.kind,
                    name=s.name,
                    annotations=s.annotations,
                    attributes=s.attributes,
                )
            )

    return sys_block


# -----------------------------
# SIMPLE JSON conversion: no __type__, flattened attributes, simplified values.
# Simplified JSON is good for human viewing or LLM context, but in contrast to
# the full JSON form it cannot be converted back to AST.

def _annotation_to_simple(a: Annotation) -> str:
    if not a.args:
        return a.name
    return f"{a.name}({', '.join(a.args)})"

def _method_signature(m: Method) -> str:
    vis = m.visibility or ""
    params = m.params or ""
    returns = m.returns or ""
    return f"{vis}{m.name}({params}) -> {returns}".strip()


def _endpoint_signature(e: Endpoint) -> str:
    # Prefer original line if available.
    if e.raw:
        return e.raw.strip().rstrip(",")

    # Fallback reconstruction (less faithful than `raw`).
    parts: List[str] = []
    if e.style == "http":
        if e.method:
            parts.append(e.method)
        if e.path:
            parts.append(e.path)
        if e.request:
            parts.append(e.request)
    else:
        if e.name:
            parts.append(e.name)
        if e.request:
            parts.append(f"({e.request})")
    if e.response:
        parts.append("->")
        parts.append(e.response)
    # Rule for max-simplify is: only attrs that were inside [] in the ORIGINAL
    # raw endpoint definition belong in `def`. Anything else should be separate.
    return " ".join([p for p in parts if p]).strip()


def _method_to_simple(m: Method, max_simplify: bool = False) -> Any:
    if not max_simplify:
        d: Dict[str, Any] = {
            "params": m.params,
            "returns": m.returns,
        }
        if m.visibility:
            d["visibility"] = m.visibility
        if m.annotations:
            d["annotations"] = [_annotation_to_simple(a) for a in m.annotations]
        if m.attributes:
            d["meta"] = _attrs_to_simple_dict(m.attributes, max_simplify=max_simplify)
        return d

    # Max simplified: signature string + only additional metadata.
    sig = _method_signature(m)
    out: Dict[str, Any] = {
        "def": sig,
    }
    if m.annotations:
        out["annotations"] = [_annotation_to_simple(a) for a in m.annotations]
    if m.attributes:
        out.update(_attrs_to_simple_dict(m.attributes, max_simplify=max_simplify))

    # If only signature exists, collapse to a raw string.
    if set(out.keys()) == {"def"}:
        return sig
    return out


def _field_to_simple(f: Field, max_simplify: bool = False) -> Any:
    if not max_simplify:
        d: Dict[str, Any] = {
            "type": f.type,
        }
        if f.visibility:
            d["visibility"] = f.visibility
        if f.annotations:
            d["annotations"] = [_annotation_to_simple(a) for a in f.annotations]
        if f.attributes:
            d["meta"] = _attrs_to_simple_dict(f.attributes, max_simplify=max_simplify)
        return d

    # Max simplified: move visibility into key; if only type exists, return raw type string.
    out: Dict[str, Any] = {
        "type": f.type,
    }
    if f.annotations:
        out["annotations"] = [_annotation_to_simple(a) for a in f.annotations]
    if f.attributes:
        out["meta"] = _attrs_to_simple_dict(f.attributes, max_simplify=max_simplify)

    if set(out.keys()) == {"type"}:
        return f.type
    return out


def _field_key(f: Field, max_simplify: bool = False) -> str:
    if max_simplify and f.visibility:
        return f"{f.visibility}{f.name}"
    return f.name


def _attrs_to_simple_dict(attrs: Dict[str, Attribute], max_simplify: bool = False) -> dict:
    """
    Flatten Attribute dict: drop Attribute wrapper and simplify values.
    """
    out: Dict[str, Any] = {}
    for key, attr in attrs.items():
        out[key] = _simple_value(attr.value, context=key, max_simplify=max_simplify)
    return out


def _components_list_to_simple(comps: List[Any], max_simplify: bool = False) -> Any:
    """
    Turn a list of component Blocks into a dict:
      "components": {
        "database UserRepo": { ... },
        "cache SessionCache": { ... },
        "table users": { ... },
        "hash sessions": { ... }
      }
    Assumes (kind, name) pairs are unique.
    """
    # Avoid duplicating kind/name in both key and object: emit a list of objects.
    out: List[Any] = []
    for c in comps:
        if isinstance(c, Block):
            out.append(_block_to_simple_dict(c, max_simplify=max_simplify))
        else:
            out.append(_simple_value(c, context=None, max_simplify=max_simplify))
    return out


def _simple_value(v: Any, context: Optional[str] = None, max_simplify: bool = False) -> Any:
    """
    Recursively simplify any AST value (Block/Method/Field/Attribute/Annotation/etc.)
    into a JSON-serializable "nice" form without __type__ wrappers.
    """
    # System/Service/Block will be handled by _block_to_simple_dict,
    # this is mainly for values inside attributes.
    if isinstance(v, System) or isinstance(v, Service) or isinstance(v, Block):
        return _block_to_simple_dict(v, max_simplify=max_simplify)

    if isinstance(v, Method):
        return _method_to_simple(v, max_simplify=max_simplify)

    if isinstance(v, Field):
        return _field_to_simple(v, max_simplify=max_simplify)
    
    if isinstance(v, Endpoint):
        return _endpoint_to_simple(v, max_simplify=max_simplify)

    if isinstance(v, Attribute):
        # flatten Attribute wrapper
        return _simple_value(v.value, context=context, max_simplify=max_simplify)

    if isinstance(v, Annotation):
        return _annotation_to_simple(v)

    # Lists
    if isinstance(v, list):
        # 1) special-case components list
        if context == "components":
            return _components_list_to_simple(v, max_simplify=max_simplify)

        # 2) if it's a list of Methods – keyed by name
        if v and any(isinstance(x, Method) for x in v):
            return {
                m.name: _method_to_simple(m, max_simplify=max_simplify)
                for m in v
                if isinstance(m, Method)
            }

        # 3) if it's a list of Fields – keyed by name
        if v and any(isinstance(x, Field) for x in v):
            return {
                _field_key(f, max_simplify=max_simplify): _field_to_simple(
                    f, max_simplify=max_simplify
                )
                for f in v
                if isinstance(f, Field)
            }
        
        if v and any(isinstance(x, Endpoint) for x in v):
            return [_endpoint_to_simple(x, max_simplify=max_simplify) for x in v]

        # 4) generic list – just map recursively
        return [_simple_value(x, context=None, max_simplify=max_simplify) for x in v]

    # Dicts
    if isinstance(v, dict):
        return {k: _simple_value(val, context=k, max_simplify=max_simplify) for k, val in v.items()}

    # Simple types (str, int, bool, None, etc.)
    return v


def _block_to_simple_dict(b: Block, max_simplify: bool = False) -> dict:
    """
    Flatten a Block/Service/System into a simple dict:
      - no __type__
      - attributes merged at top level
      - components/methods/fields converted to dicts
    """
    out: Dict[str, Any] = {}

    if b.kind:
        out["kind"] = b.kind
    if b.name:
        out["name"] = b.name
    if b.annotations:
        out["annotations"] = [_annotation_to_simple(a) for a in b.annotations]

    # attributes
    out.update(_attrs_to_simple_dict(b.attributes, max_simplify=max_simplify))

    # System has services; lift them into a dict services[name] = ...
    if isinstance(b, System):
        out["services"] = {
            s.name: _block_to_simple_dict(s, max_simplify=max_simplify) for s in b.services
        }

    return out


def _endpoint_to_simple(e: Endpoint, max_simplify: bool = False) -> Any:
    if max_simplify:
        # Max simplified:
        # - `def` is the original raw endpoint signature (includes [...] attrs if present)
        # - any attrs NOT present in [...] are emitted as separate keys
        definition = _endpoint_signature(e)
        d: Dict[str, Any] = {"def": definition}

        if e.attributes:
            bracket_keys = _extract_bracket_attr_keys(definition)
            for k, v in e.attributes.items():
                if k not in bracket_keys:
                    d[k] = v
        if e.annotations:
            d["annotations"] = [_annotation_to_simple(a) for a in e.annotations]
        if set(d.keys()) == {"def"}:
            return definition
        return d

    d: Dict[str, Any] = {
        "style": e.style,
    }
    if e.name:
        d["name"] = e.name
    if e.method:
        d["method"] = e.method
    if e.path:
        d["path"] = e.path
    if e.request:
        d["request"] = e.request
    if e.response:
        d["response"] = e.response
    if e.attributes:
        d["attrs"] = e.attributes
    if e.annotations:
        d["annotations"] = [_annotation_to_simple(a) for a in e.annotations]
    if e.inputs:
        d["inputs"] = e.inputs
    if e.outputs:
        d["outputs"] = e.outputs
    return d


def system_to_simple_json_dict(system: System, max_simplify: bool = False) -> dict:
    """
    Public entry-point: convert System AST into simplified JSON,
    good for human scrolling / LLM context (not guaranteed to be
    convertible back to AST).
    """
    return _block_to_simple_dict(system, max_simplify=max_simplify)

