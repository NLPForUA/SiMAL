# SIMAL endpoint enrichment: parse endpoint signatures and extract structured input/output param info.

import re
from dataclasses import dataclass
from typing import List, Union, Dict, Any

from ast_struct import TypeExpr, TupleSig
from ast_struct import Attribute


def _split_top_level_commas(text: str) -> List[str]:
    """Split a comma-separated list, ignoring commas inside (), [], {}, <>."""
    s = (text or "").strip()
    if not s:
        return []

    parts: List[str] = []
    buf: List[str] = []
    depth_paren = 0
    depth_brack = 0
    depth_brace = 0
    depth_angle = 0

    for ch in s:
        if ch == '(':
            depth_paren += 1
        elif ch == ')' and depth_paren > 0:
            depth_paren -= 1
        elif ch == '[':
            depth_brack += 1
        elif ch == ']' and depth_brack > 0:
            depth_brack -= 1
        elif ch == '{':
            depth_brace += 1
        elif ch == '}' and depth_brace > 0:
            depth_brace -= 1
        elif ch == '<':
            depth_angle += 1
        elif ch == '>' and depth_angle > 0:
            depth_angle -= 1

        if (
            ch == ','
            and depth_paren == 0
            and depth_brack == 0
            and depth_brace == 0
            and depth_angle == 0
        ):
            part = "".join(buf).strip()
            if part:
                parts.append(part)
            buf = []
            continue

        buf.append(ch)

    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def _parse_go_param_list(params: str) -> List[Dict[str, Any]]:
    s = (params or "").strip()
    if not s:
        return []

    segments = _split_top_level_commas(s)
    pending_names: List[str] = []
    out: List[Dict[str, Any]] = []

    def normalize_name_type(name_part: str, type_part: str):
        name_part = (name_part or "").strip()
        type_part = (type_part or "").strip()

        for token in ("[]", "*", "&", "..."):
            if name_part == token and type_part:
                name_part = ""
                type_part = f"{token}{type_part}"
                break

        for token in ("[]", "*", "&", "..."):
            if name_part.endswith(token) and name_part != token:
                name_part = name_part[: -len(token)].strip()
                type_part = f"{token}{type_part}" if type_part else token

        for token in ("[]", "*", "&", "..."):
            if type_part.startswith(token + " "):
                type_part = token + type_part[len(token) + 1 :]
        return name_part, type_part

    def emit(names: List[str], type_str: str):
        for nm in names:
            out.append({
                "name": nm,
                "type": type_str,
                "optional": False,
                "fields": None,
            })

    def split_top_level_colon(s2: str):
        depth_paren = 0
        depth_brack = 0
        depth_brace = 0
        depth_angle = 0
        for idx, ch in enumerate(s2):
            if ch == '(':
                depth_paren += 1
            elif ch == ')' and depth_paren > 0:
                depth_paren -= 1
            elif ch == '[':
                depth_brack += 1
            elif ch == ']' and depth_brack > 0:
                depth_brack -= 1
            elif ch == '{':
                depth_brace += 1
            elif ch == '}' and depth_brace > 0:
                depth_brace -= 1
            elif ch == '<':
                depth_angle += 1
            elif ch == '>' and depth_angle > 0:
                depth_angle -= 1
            if (
                ch == ':'
                and depth_paren == 0
                and depth_brack == 0
                and depth_brace == 0
                and depth_angle == 0
            ):
                return s2[:idx].strip(), s2[idx + 1:].strip()
        return None

    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue

        colon_split = split_top_level_colon(seg)
        if colon_split is not None:
            name_part, type_part = colon_split
            if pending_names:
                emit(pending_names, type_part)
                pending_names = []
            emit([name_part or ""], type_part)
            continue

        if any(ch.isspace() for ch in seg):
            last_space = seg.rstrip().rfind(' ')
            name_part = seg[:last_space].strip() if last_space != -1 else ""
            type_part = seg[last_space + 1:].strip() if last_space != -1 else seg.strip()

            name_part, type_part = normalize_name_type(name_part, type_part)

            names: List[str] = []
            if pending_names:
                names.extend(pending_names)
                pending_names = []
            if name_part:
                names.append(name_part)
            if not names:
                names = [""]

            emit(names, type_part)
        else:
            pending_names.append(seg)

    for nm in pending_names:
        out.append({
            "name": nm,
            "type": "",
            "optional": False,
            "fields": None,
        })

    return out


def _parse_go_returns(returns: str) -> List[Dict[str, Any]]:
    s = (returns or "").strip()
    if not s:
        return []

    if s.startswith('(') and s.endswith(')'):
        s = s[1:-1].strip()

    segments = _split_top_level_commas(s)
    if not segments:
        segments = [s]

    out: List[Dict[str, Any]] = []

    def normalize_name_type(name_part: str, type_part: str):
        name_part = (name_part or "").strip()
        type_part = (type_part or "").strip()

        for token in ("[]", "*", "&", "..."):
            if name_part == token and type_part:
                name_part = ""
                type_part = f"{token}{type_part}"
                break

        for token in ("[]", "*", "&", "..."):
            if name_part.endswith(token) and name_part != token:
                name_part = name_part[: -len(token)].strip()
                type_part = f"{token}{type_part}" if type_part else token

        for token in ("[]", "*", "&", "..."):
            if type_part.startswith(token + " "):
                type_part = token + type_part[len(token) + 1 :]
        return name_part, type_part

    def split_top_level_colon(s2: str):
        depth_paren = 0
        depth_brack = 0
        depth_brace = 0
        depth_angle = 0
        for idx, ch in enumerate(s2):
            if ch == '(':
                depth_paren += 1
            elif ch == ')' and depth_paren > 0:
                depth_paren -= 1
            elif ch == '[':
                depth_brack += 1
            elif ch == ']' and depth_brack > 0:
                depth_brack -= 1
            elif ch == '{':
                depth_brace += 1
            elif ch == '}' and depth_brace > 0:
                depth_brace -= 1
            elif ch == '<':
                depth_angle += 1
            elif ch == '>' and depth_angle > 0:
                depth_angle -= 1
            if (
                ch == ':'
                and depth_paren == 0
                and depth_brack == 0
                and depth_brace == 0
                and depth_angle == 0
            ):
                return s2[:idx].strip(), s2[idx + 1:].strip()
        return None

    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue

        colon_split = split_top_level_colon(seg)
        if colon_split is not None:
            name_part, type_part = colon_split
            out.append({
                "name": name_part,
                "type": type_part,
                "optional": False,
                "fields": None,
            })
            continue
        if any(ch.isspace() for ch in seg):
            last_space = seg.rstrip().rfind(' ')
            name_part = seg[:last_space].strip() if last_space != -1 else ""
            type_part = seg[last_space + 1:].strip() if last_space != -1 else seg

            name_part, type_part = normalize_name_type(name_part, type_part)
            out.append({
                "name": name_part,
                "type": type_part,
                "optional": False,
                "fields": None,
            })
        else:
            out.append({
                "name": "",
                "type": seg,
                "optional": False,
                "fields": None,
            })
    return out


def typeexpr_to_struct_desc(t: TypeExpr) -> Dict[str, Any]:
    """
    Convert TypeExpr into a nested dict representation, including fields.

    Example:
      User{name: str, email: str, verified: bool}?  ->

      {
        "type": "User",
        "optional": True,
        "fields": [
          {"name": "name",    "type": "str", "optional": False},
          {"name": "email",   "type": "str", "optional": False},
          {"name": "verified","type": "bool","optional": False},
        ]
      }
    """
    desc: Dict[str, Any] = {
        "type": t.base,
        "optional": t.optional,
    }
    if t.fields:
        fields_out = []
        for f in t.fields:
            fields_out.append({
                "name": f.name,
                "type": f.type.base,
                "optional": f.type.optional,
                # recurse further if nested object:
                "fields": [
                    {
                        "name": sf.name,
                        "type": sf.type.base,
                        "optional": sf.type.optional,
                    }
                    for sf in (f.type.fields or [])
                ] or None,
            })
        desc["fields"] = fields_out
    return desc


@dataclass
class Field:
    """
    A named argument/field with a type.
      name: str?
      user: User{...}?
      uuid str
    """
    name: str
    type: TypeExpr

class SigParseError(Exception):
    pass


class SigParser:
    def __init__(self, text: str):
        self.text = text
        self.n = len(text)
        self.i = 0

    def peek(self) -> str:
        return self.text[self.i] if self.i < self.n else ''

    def advance(self) -> str:
        ch = self.peek()
        if ch:
            self.i += 1
        return ch

    def skip_ws(self):
        while self.peek() and self.peek().isspace():
            self.i += 1

    def parse_ident(self) -> str:
        self.skip_ws()
        start = self.i
        while self.peek() and (self.peek().isalnum() or self.peek() in "_"):
            self.i += 1
        if self.i == start:
            raise SigParseError(f"Expected identifier at pos {self.i} in {self.text!r}")
        return self.text[start:self.i]

    def parse_signature(self) -> Union[TypeExpr, TupleSig]:
        """
        Top-level entry:
          - If starts with '(', parse a tuple: (user: ..., error: ...)
          - Otherwise parse a single TypeExpr: JSON{...}, User{...}, str?, ...
        """
        self.skip_ws()
        if self.peek() == '(':
            return self.parse_tuple()
        else:
            t = self.parse_type_expr()
            self.skip_ws()
            if self.i != self.n:
                # fallback trigger: unexpected trailing content
                raise SigParseError(f"Unexpected trailing content at pos {self.i}: {self.text[self.i:]}")
            return t

    def parse_tuple(self) -> TupleSig:
        self.skip_ws()
        if self.advance() != '(':
            raise SigParseError("Expected '('")
        params = self.parse_param_list()
        self.skip_ws()
        if self.advance() != ')':
            raise SigParseError("Expected ')' at end of tuple")
        self.skip_ws()
        if self.i != self.n:
            raise SigParseError("Trailing content after tuple")
        return TupleSig(params=params)

    def parse_param_list(self) -> List[Field]:
        params: List[Field] = []
        while True:
            self.skip_ws()
            if self.peek() == ')':
                break
            if not self.peek():
                break
            param = self.parse_param()
            params.append(param)
            self.skip_ws()
            if self.peek() == ',':
                self.advance()
                continue
            elif self.peek() == ')':
                break
            else:
                # allow whitespace-only separators
                continue
        return params

    def parse_param(self) -> Field:
        """
        Param examples:
          user: User{name: str}?
          error: str?
        """
        self.skip_ws()
        name = self.parse_ident()
        self.skip_ws()
        if self.peek() == ':':
            self.advance()
            t = self.parse_type_expr()
            return Field(name=name, type=t)
        else:
            # support "uuid str" shape if you ever use it in tuples
            self.skip_ws()
            type_name = self.parse_ident()
            t = TypeExpr(base=type_name, optional=False)
            return Field(name=name, type=t)

    def parse_type_expr(self) -> TypeExpr:
        """
        TypeExpr:
          SimpleType [ObjectShape] [?]
        e.g.
          str
          str?
          User{name: str, ...}?
          JSON{uuid: str?, error: str?}
        """
        self.skip_ws()

        def _compact_bracket_ws(s: str) -> str:
            # The tokenizer often produces: "map < int, Todo >".
            # Normalize to: "map<int, Todo>" (keep spaces after commas).
            s = re.sub(r"<\s+", "<", s)
            s = re.sub(r"\s+>", ">", s)
            s = re.sub(r"\[\s+", "[", s)
            s = re.sub(r"\s+\]", "]", s)
            return s

        def _parse_balanced(open_ch: str, close_ch: str) -> str:
            self.skip_ws()
            if self.peek() != open_ch:
                return ""
            start = self.i
            depth = 0
            while self.peek():
                ch = self.advance()
                if ch == open_ch:
                    depth += 1
                elif ch == close_ch:
                    depth -= 1
                    if depth == 0:
                        break
            if depth != 0:
                raise SigParseError(f"Unclosed {open_ch}{close_ch} in {self.text!r}")
            return _compact_bracket_ws(self.text[start:self.i])

        base = self.parse_ident()
        suffix = ""
        while True:
            self.skip_ws()
            if self.peek() == '<':
                suffix += _parse_balanced('<', '>')
                continue
            if self.peek() == '[':
                suffix += _parse_balanced('[', ']')
                continue
            break
        base = base + suffix
        self.skip_ws()
        fields = None
        if self.peek() == '{':
            fields = self.parse_object_fields()
            self.skip_ws()
        optional = False
        if self.peek() == '?':
            self.advance()
            optional = True
        return TypeExpr(base=base, fields=fields, optional=optional)

    def parse_object_fields(self) -> List[Field]:
        """
        ObjectShape: { Field (, Field)* }
        Field:
          name: TypeExpr
          name TypeName[?]   # "uuid str" form
        """
        if self.advance() != '{':
            raise SigParseError("Expected '{'")
        fields: List[Field] = []
        while True:
            self.skip_ws()
            if self.peek() == '}':
                self.advance()
                break
            if not self.peek():
                raise SigParseError("Unclosed '{'")
            # name
            name = self.parse_ident()
            self.skip_ws()
            if self.peek() == ':':
                # "name: TypeExpr" form
                self.advance()
                t = self.parse_type_expr()
            else:
                # "uuid str" form
                self.skip_ws()
                type_name = self.parse_ident()
                optional = False
                self.skip_ws()
                if self.peek() == '?':
                    self.advance()
                    optional = True
                t = TypeExpr(base=type_name, optional=optional)
            fields.append(Field(name=name, type=t))
            self.skip_ws()
            if self.peek() == ',':
                self.advance()
                continue
            elif self.peek() == '}':
                continue
            else:
                # allow whitespace/newline as separator
                continue
        return fields


def try_parse_signature(sig: str) -> Union[TypeExpr, TupleSig, str]:
    sig = sig.strip()
    if not sig:
        return ""
    try:
        return SigParser(sig).parse_signature()
    except SigParseError:
        # Fallback: keep raw string if it doesn't match known patterns
        return sig


PLACEHOLDER_RE = re.compile(r"\{([^}]+)\}")

def parse_http_path_inputs(path: str) -> List[Field]:
    params: List[Field] = []
    for name in PLACEHOLDER_RE.findall(path):
        params.append(Field(name=name, type=TypeExpr(base="str", optional=False)))
    return params

def signature_to_params(parsed: Union[TypeExpr, TupleSig, str]) -> List[Dict[str, Any]]:
    """
    Flatten parsed signature into a list of named parameters with type info.
    Fallback: if parsed is a raw string, return empty list.
    """
    params: List[Dict[str, Any]] = []

    if isinstance(parsed, TupleSig):
        # (user: User{...}?, error: str?)
        for f in parsed.params:
            params.append({
                "name": f.name,
                "type": f.type.base,
                "optional": f.type.optional,
                "fields": [
                    {
                        "name": sf.name,
                        "type": sf.type.base,
                        "optional": sf.type.optional,
                    }
                    for sf in (f.type.fields or [])
                ] or None,
            })
    elif isinstance(parsed, TypeExpr):
        # JSON{uuid: str?, error: str?}  or GetUserRequest{uuid: str}
        if parsed.fields:
            # multiple named fields -> treat each as a param
            for f in parsed.fields:
                params.append({
                    "name": f.name,
                    "type": f.type.base,
                    "optional": f.type.optional,
                    "fields": [
                        {
                            "name": sf.name,
                            "type": sf.type.base,
                            "optional": sf.type.optional,
                        }
                        for sf in (f.type.fields or [])
                    ] or None,
                })
        else:
            # "just a type" case if needed
            params.append({
                "name": "",
                "type": parsed.base,
                "optional": parsed.optional,
                "fields": None,
            })
    else:
        # string / unknown => no structured params
        pass

    return params

def enrich_endpoints(system) -> None:
    for svc in system.services:
        api_attr = svc.attributes.get("api")
        if not api_attr:
            continue

        for api_item in api_attr.value:
            # unwrap Attribute (for annotated API entries like @DELETED { ... })
            if isinstance(api_item, Attribute):
                api_annotations = api_item.annotations
                api_map = api_item.value
            else:
                api_annotations = []
                api_map = api_item

            # Skip anything unexpected
            if not isinstance(api_map, dict):
                continue

            eps = api_map.get("endpoints") or []
            for ep in eps:
                # ep is already Endpoint from the parser
                # parse request/response signatures
                ep.request_parsed = try_parse_signature(ep.request)
                ep.response_parsed = try_parse_signature(ep.response)

                # HTTP: path params + body
                if ep.style == "http":
                    ep.input_params = parse_http_path_inputs(ep.path or "")

                    if isinstance(ep.request_parsed, (TypeExpr, TupleSig)):
                        body_params = signature_to_params(ep.request_parsed)
                        ep.inputs = (ep.inputs or []) + [
                            {
                                "name": p["name"],
                                "type": p["type"],
                                "optional": p["optional"],
                                "fields": p["fields"],
                            }
                            for p in body_params
                        ]
                    else:
                        ep.inputs = [
                            {
                                "name": f.name,
                                "type": f.type.base,
                                "optional": f.type.optional,
                                "fields": None,
                            }
                            for f in (ep.input_params or [])
                        ]

                # gRPC: request fields
                elif ep.style == "grpc":
                    if isinstance(ep.request_parsed, TypeExpr) and ep.request_parsed.fields:
                        ep.inputs = signature_to_params(ep.request_parsed)
                    else:
                        ep.inputs = []

                # outputs from response
                if isinstance(ep.response_parsed, (TypeExpr, TupleSig)):
                    ep.outputs = signature_to_params(ep.response_parsed)
                else:
                    ep.outputs = []


def enrich_methods(system) -> None:
    from ast_struct import Block as AstBlock, Method as AstMethod, System as AstSystem

    def walk(value: Any) -> None:
        if value is None:
            return

        if isinstance(value, AstMethod):
            value.inputs = _parse_go_param_list(value.params)
            value.outputs = _parse_go_returns(value.returns)
            return

        if isinstance(value, Attribute):
            walk(value.value)
            return

        if isinstance(value, AstSystem):
            for s in value.services:
                walk(s)
            for a in value.attributes.values():
                walk(a)
            return

        if isinstance(value, AstBlock):
            for a in value.attributes.values():
                walk(a)
            return

        if isinstance(value, list):
            for item in value:
                walk(item)
            return

        if isinstance(value, dict):
            for v in value.values():
                walk(v)
            return

    walk(system)
