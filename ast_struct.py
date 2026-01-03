# AST structures for SIML language

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


@dataclass
class Annotation:
    name: str
    args: List[str] = field(default_factory=list)


@dataclass
class Attribute:
    key: str
    value: Any
    annotations: List[Annotation] = field(default_factory=list)


@dataclass
class Field:
    name: str
    type: str
    visibility: Optional[str]  # "+", "-", "#", or None, just like in UML
    annotations: List[Annotation] = field(default_factory=list)
    attributes: Dict[str, Attribute] = field(default_factory=dict)


@dataclass
class Method:
    name: str
    visibility: Optional[str]  # "+", "-", "#", or None, just like in UML
    params: str                # raw "(...)" content as string, go-style with type after name
    returns: str               # raw single-type return or tuple "(...)" return as string
    annotations: List[Annotation] = field(default_factory=list)
    attributes: Dict[str, Attribute] = field(default_factory=dict)



@dataclass
class TypeExpr:
    """
    A single type expression like:
      str
      User
      JSON{uuid: str?, error: str?}
      User{name: str, email: str, verified: bool}?
    """
    base: str                       # "str", "User", "JSON", "GetUserRequest"
    fields: Optional[List["Field"]] = None  # object shape for {...}, else None
    optional: bool = False          # trailing '?' means optional


@dataclass
class TupleSig:
    """
    Tuple of outputs / inputs:
      (user: User{...}?, error: str?)
    """
    params: List[Field]


@dataclass
class Endpoint:
    style: str                  # "http", "grpc", "graphql", etc.
    name: Optional[str]         # gRPC: rpc name, HTTP: short name
    method: Optional[str]       # HTTP verb: GET/POST/... (None for gRPC)
    path: Optional[str]         # "/users/{id}" for HTTP, None for gRPC
    request: str                # raw request signature, e.g. "GetUserRequest{uuid str}"
    response: str               # raw response signature, e.g. "(user: User{...}?, error: str?)" or "JSON{...}"
    annotations: List[Annotation] = field(default_factory=list)
    attributes: Dict[str, str] = field(default_factory=dict)  # additional metadata like [auth: ..., cache: ..., timeout: ...]
    raw: str = ""               # full original line for debugging

    # parsed forms (you can fill them after parsing all endpoints)
    request_parsed: Optional[Union[TypeExpr, TupleSig, str]] = None
    response_parsed: Optional[Union[TypeExpr, TupleSig, str]] = None
    # Low-level parsed fields (if you keep them)
    input_params: Optional[List[Field]] = None   # HTTP path placeholders, gRPC fields, etc.
    output_params: Optional[List[Field]] = None  # flattened from TypeExpr/TupleSig
    # High-level, LLM-friendly IO description used in simple JSON
    inputs: Optional[List[Dict[str, Any]]] = None
    outputs: Optional[List[Dict[str, Any]]] = None


@dataclass
class Block:
    kind: str
    name: Optional[str]
    annotations: List[Annotation] = field(default_factory=list)
    attributes: Dict[str, Attribute] = field(default_factory=dict)


@dataclass
class Service(Block):
    pass


@dataclass
class System(Block):
    services: List[Service] = field(default_factory=list)

