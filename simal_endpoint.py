# SIMAL endpoint enrichment: parse endpoint signatures and extract structured input/output param info.

import re
from dataclasses import dataclass
from typing import List, Union, Dict, Any

from ast_struct import TypeExpr, TupleSig
from simal_parser import Attribute


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
        base = self.parse_ident()
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
