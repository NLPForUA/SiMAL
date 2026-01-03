# SIMAL parser implementation

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

from ast_struct import Annotation, Attribute, Block, Endpoint, Field, Method, Service, System
from simal_endpoint import enrich_endpoints

# -----------------------------
# Tokenization

class TokType(Enum):
    IDENT   = auto()
    STRING  = auto()
    LBRACE  = auto()   # {
    RBRACE  = auto()   # }
    LBRACK  = auto()   # [
    RBRACK  = auto()   # ]
    LPAREN  = auto()   # (
    RPAREN  = auto()   # )
    COLON   = auto()   # :
    COMMA   = auto()   # ,
    ARROW   = auto()   # ->
    AT      = auto()   # @
    NEWLINE = auto()
    EOF     = auto()


@dataclass
class Token:
    type: TokType
    value: str
    line: int
    col: int


def tokenize(text: str) -> List[Token]:
    """
    Tokenizer for the SIMAL subset.

    Important trick: heredocs like

        <<TEXT
          ...
        TEXT

    are converted directly into a single STRING token, so the parser
    just sees `description: <STRING>` and doesn't have to reason
    about <<LABEL / LABEL matching.
    """
    import re

    tokens: List[Token] = []
    i = 0
    line = 1
    col = 1
    n = len(text)

    def add(tt: TokType, v: str = ""):
        tokens.append(Token(tt, v, line, col))

    WHITESPACE = " \t"

    while i < n:
        ch = text[i]

        # newline
        if ch == "\n":
            add(TokType.NEWLINE, "\n")
            i += 1
            line += 1
            col = 1
            continue

        # spaces / tabs
        if ch in WHITESPACE:
            i += 1
            col += 1
            continue

        # heredoc: <<LABEL
        if ch == "<" and i + 1 < n and text[i + 1] == "<":
            # consume the two '<'
            i += 2
            col += 2

            # read label (non-whitespace up to end of token)
            start_label = i
            while i < n and not text[i].isspace():
                i += 1
                col += 1
            label = text[start_label:i].strip()

            # skip the rest of the line (after LABEL)
            while i < n and text[i] != "\n":
                i += 1
                col += 1
            if i < n and text[i] == "\n":
                i += 1
                line += 1
                col = 1

            # collect lines until a line whose stripped text == label
            raw_lines: List[str] = []
            while i < n:
                line_start_i = i
                while i < n and text[i] != "\n":
                    i += 1
                line_str = text[line_start_i:i]
                if i < n and text[i] == "\n":
                    i += 1
                    line += 1
                    col = 1

                if line_str.strip() == label:
                    break
                raw_lines.append(line_str)

            # dedent the collected lines
            # 1) drop leading/trailing completely blank lines
            while raw_lines and raw_lines[0].strip() == "":
                raw_lines.pop(0)
            while raw_lines and raw_lines[-1].strip() == "":
                raw_lines.pop()

            # 2) compute minimal indentation of non-blank lines
            indent = 0
            for ln in raw_lines:
                stripped = ln.lstrip()
                if stripped:
                    indent = len(ln) - len(stripped)
                    break
            # 3) remove that indentation
            if indent is None:
                dedented_lines = raw_lines
            else:
                dedented_lines = [ln[indent:] if len(ln) >= indent else "" for ln in raw_lines]

            add(TokType.STRING, "\n".join(dedented_lines))
            continue


        # single-character tokens
        if ch == "{":
            add(TokType.LBRACE, ch)
            i += 1
            col += 1
            continue
        if ch == "}":
            add(TokType.RBRACE, ch)
            i += 1
            col += 1
            continue
        if ch == "[":
            add(TokType.LBRACK, ch)
            i += 1
            col += 1
            continue
        if ch == "]":
            add(TokType.RBRACK, ch)
            i += 1
            col += 1
            continue
        if ch == "(":
            add(TokType.LPAREN, ch)
            i += 1
            col += 1
            continue
        if ch == ")":
            add(TokType.RPAREN, ch)
            i += 1
            col += 1
            continue
        if ch == ":":
            add(TokType.COLON, ch)
            i += 1
            col += 1
            continue
        if ch == ",":
            add(TokType.COMMA, ch)
            i += 1
            col += 1
            continue
        if ch == "@":
            add(TokType.AT, ch)
            i += 1
            col += 1
            continue

        # arrow ->
        if ch == "-" and i + 1 < n and text[i + 1] == ">":
            add(TokType.ARROW, "->")
            i += 2
            col += 2
            continue

        # quoted string "..."
        if ch in ('"', "'"):
            quote = ch
            i += 1
            col += 1
            buf: List[str] = []
            while i < n and text[i] != quote:
                buf.append(text[i])
                i += 1
                col += 1
            if i < n and text[i] == quote:
                i += 1
                col += 1
            add(TokType.STRING, "".join(buf))
            continue

        # identifiers / bare words
        if re.match(r"[A-Za-z_]", ch):
            start = i
            while i < n and re.match(r"[A-Za-z0-9_\.\/\-']", text[i]):
                i += 1
                col += 1
            add(TokType.IDENT, text[start:i])
            continue

        # numbers (we treat them as IDENT for now)
        if re.match(r"[0-9]", ch):
            start = i
            while (
                i < n
                and not text[i].isspace()
                and text[i] not in "{}[]():,"
            ):
                i += 1
                col += 1
            add(TokType.IDENT, text[start:i])
            continue

        # fallback: treat as IDENT
        add(TokType.IDENT, ch)
        i += 1
        col += 1

    tokens.append(Token(TokType.EOF, "", line, col))
    return tokens


# -----------------------------
# Normalize Tokenization

# punctuation we want to "stick" to the left
_STICK_LEFT = {")", "]", "}", ",", ":", ";", "?", "]"}

# punctuation / symbols that we want to "stick" to the right (no space after)
_STICK_RIGHT = {"(", "[", "{", "/", ".",}

def compact_token_values(tokens: List[Token]) -> str:
    """
    Join tokens into a compact string without extra spaces around punctuation.

    Examples:
      ['GET', '/', 'users', '/', '{', 'id', '}', '->',
       'JSON', '{', 'user', ':', 'User', '}', '[', ...]  ->

      'GET /users/{id} -> JSON{user: User}[...]'
    """
    out_parts: List[str] = []
    prev_val: Optional[str] = None

    for t in tokens:
        v = t.value

        if prev_val is None:
            # first token
            out_parts.append(v)
            prev_val = v
            continue

        if v in _STICK_LEFT:
            # attach to previous token, no extra space
            out_parts[-1] = out_parts[-1].rstrip() + v
        elif prev_val in _STICK_RIGHT:
            # previous token sticks to the right (e.g. "JSON", "(", "/", "{")
            out_parts[-1] = out_parts[-1] + v
        else:
            # normal word boundary
            out_parts.append(" " + v)

        prev_val = v

    return "".join(out_parts)


# -----------------------------
# Parser

class ParseError(Exception):
    pass


class Parser:
    def __init__(self, tokens: List[Token], merge_duplicate_attrs: bool = True):
        self.tokens = tokens
        self.pos = 0
        self.merge_duplicate_attrs = merge_duplicate_attrs

    def _merge_attr_values(self, existing: Attribute, new: Attribute) -> Attribute:
        """Merge duplicate attribute keys when configured.

        - list + list => concatenation (preserve order)
        - dict + dict => shallow merge (new wins on key conflicts)
        - anything else => replace (new wins)

        Annotations are concatenated when merging.
        """
        if isinstance(existing.value, list) and isinstance(new.value, list):
            return Attribute(
                key=existing.key,
                value=list(existing.value) + list(new.value),
                annotations=list(existing.annotations) + list(new.annotations),
            )
        if isinstance(existing.value, dict) and isinstance(new.value, dict):
            merged = dict(existing.value)
            merged.update(new.value)
            return Attribute(
                key=existing.key,
                value=merged,
                annotations=list(existing.annotations) + list(new.annotations),
            )
        return new

    def _set_attr(self, attrs: Dict[str, Attribute], key: str, attr: Attribute) -> None:
        if self.merge_duplicate_attrs and key in attrs:
            attrs[key] = self._merge_attr_values(attrs[key], attr)
        else:
            attrs[key] = attr

    # basic utilities
    def peek(self, offset: int = 0) -> Token:
        idx = self.pos + offset
        if idx < len(self.tokens):
            return self.tokens[idx]
        return self.tokens[-1]

    def eat(self, ttype: TokType) -> Token:
        tok = self.peek()
        if tok.type != ttype:
            raise ParseError(
                f"Expected {ttype}, got {tok.type} ({tok.value!r}) "
                f"at line {tok.line}, col {tok.col}"
            )
        self.pos += 1
        return tok

    def maybe_eat(self, ttype: TokType) -> Optional[Token]:
        if self.peek().type == ttype:
            return self.eat(ttype)
        return None

    def skip_newlines(self):
        while self.peek().type == TokType.NEWLINE:
            self.pos += 1

    # top-level system / service
    def parse_system(self) -> System:
        self.skip_newlines()
        if not (self.peek().type == TokType.IDENT and self.peek().value == "system"):
            raise ParseError("Expected 'system' at start of file")

        self.eat(TokType.IDENT)   # system
        self.eat(TokType.LBRACE)  # {

        base = Block(kind="system", name=None)
        services: List[Service] = []

        while self.peek().type != TokType.RBRACE:
            self.skip_newlines()
            if self.peek().type == TokType.RBRACE:
                break
            if self.peek().type == TokType.EOF:
                raise ParseError("Unexpected EOF inside system body")

            # 1) collect any leading annotations
            leading_anns = self.parse_annotations()
            self.skip_newlines()

            # 2) if the next token is 'service', those annotations belong to the service
            if self.peek().type == TokType.IDENT and self.peek().value == "service":
                services.append(self.parse_service(leading_annotations=leading_anns))
            else:
                key, attr = self.parse_attribute()
                if leading_anns:
                    attr.annotations = leading_anns + list(attr.annotations)
                self._set_attr(base.attributes, key, attr)

        self.eat(TokType.RBRACE)
        self.skip_newlines()

        return System(
            kind="system",
            name=None,
            annotations=base.annotations,
            attributes=base.attributes,
            services=services,
        )
    
    def parse_service(self, leading_annotations: Optional[List[Annotation]] = None) -> Service:
        """
        Parse:

          @PATH(...)
          @CALLS(...)
          service user_service {
            ...
          }

        'leading_annotations' are those that were already parsed by parse_system()
        before seeing the 'service' keyword.
        """
        if leading_annotations is None:
            leading_annotations = []

        self.eat(TokType.IDENT)  # 'service'
        name = self.eat(TokType.IDENT).value
        self.eat(TokType.LBRACE)

        attrs: Dict[str, Attribute] = {}

        while self.peek().type != TokType.RBRACE:
            self.skip_newlines()
            if self.peek().type == TokType.RBRACE:
                break
            key, attr = self.parse_attribute()
            self._set_attr(attrs, key, attr)

        self.eat(TokType.RBRACE)
        self.skip_newlines()

        return Service(
            kind="service",
            name=name,
            annotations=leading_annotations,
            attributes=attrs,
        )

    # annotations
    def parse_annotations(self) -> List[Annotation]:
        anns: List[Annotation] = []
        self.skip_newlines()

        while self.peek().type == TokType.AT:
            self.eat(TokType.AT)
            # If '@' is not followed by an IDENT, treat it as non-annotation and stop.
            if self.peek().type != TokType.IDENT:
                # rewind one step to let caller handle the '@' as data
                self.pos -= 1
                break

            name = self.eat(TokType.IDENT).value
            args: List[str] = []

            if self.maybe_eat(TokType.LPAREN):
                # collect arguments, split only on top-level commas
                groups: List[List[str]] = []
                cur: List[str] = []
                depth = 1  # we are already inside one '('

                while depth > 0:
                    t = self.peek()
                    if t.type in (TokType.EOF, TokType.NEWLINE):
                        raise ParseError(f"Unclosed annotation @{name}")

                    if t.type == TokType.LPAREN:
                        depth += 1
                        cur.append(t.value)
                        self.pos += 1
                        continue

                    if t.type == TokType.RPAREN:
                        depth -= 1
                        self.pos += 1
                        if depth == 0:
                            break
                        cur.append(t.value)
                        continue

                    # top-level comma => end of current argument
                    if t.type == TokType.COMMA and depth == 1:
                        groups.append(cur)
                        cur = []
                        self.pos += 1
                        continue

                    # normal token inside current argument
                    cur.append(t.value)
                    self.pos += 1

                if cur:
                    groups.append(cur)

                # turn each group of tokens into a single string argument
                args = [" ".join(g).strip() for g in groups if g]

            self.skip_newlines()
            anns.append(Annotation(name=name, args=args))

        return anns


    # attributes
    def parse_attribute(self):
        self.skip_newlines()
        anns = self.parse_annotations()  # parsed but not used yet (you can attach them later)

        key_tok = self.eat(TokType.IDENT)
        key = key_tok.value

        self.skip_newlines()

        colon_consumed = False
        if self.peek().type == TokType.COLON:
            self.eat(TokType.COLON)
            colon_consumed = True
        else:
            if self.peek().type == TokType.NEWLINE:
                self.skip_newlines()
                if self.peek().type == TokType.COLON:
                    self.eat(TokType.COLON)
                    colon_consumed = True

        if colon_consumed:
            self.skip_newlines()
        else:
            t = self.peek()
            # Tolerate component-like entries without a colon: "kind Name { ... }"
            if t.type == TokType.IDENT and self.peek(1).type == TokType.LBRACE:
                comp_block = self.parse_component_block(kind=key, leading_annotations=anns)
                self.skip_newlines()
                return key, Attribute(key=key, value=comp_block, annotations=anns)
            if t.type not in (TokType.LBRACE, TokType.LBRACK):
                raise ParseError(
                    f"Expected ':' after attribute '{key}', got {t.type.name} ({t.value!r})"
                )
        
        t = self.peek()

        t = self.peek()

        if t.type == TokType.LBRACE:
            value = self.parse_map()
        elif t.type == TokType.LBRACK and not self._bracket_value_is_literal():
            value = self.parse_list(key)
        elif t.type == TokType.STRING:
            value = self.eat(TokType.STRING).value
        else:
            # simple scalar until end-of-line / block / list
            parts: List[str] = []
            bracket_depth = 0
            paren_depth = 0
            brace_depth = 0

            while True:
                tok = self.peek()
                if tok.type == TokType.EOF:
                    break
                if tok.type == TokType.NEWLINE and bracket_depth == 0 and paren_depth == 0 and brace_depth == 0:
                    break
                if tok.type == TokType.RBRACE and brace_depth == 0 and bracket_depth == 0 and paren_depth == 0:
                    break
                if tok.type == TokType.RBRACK and bracket_depth == 0 and paren_depth == 0 and brace_depth == 0:
                    break

                # track nested delimiters so constructs like meta[name=...] keep their closing tokens
                if tok.type == TokType.LBRACK:
                    bracket_depth += 1
                elif tok.type == TokType.RBRACK and bracket_depth > 0:
                    bracket_depth -= 1
                elif tok.type == TokType.LPAREN:
                    paren_depth += 1
                elif tok.type == TokType.RPAREN and paren_depth > 0:
                    paren_depth -= 1
                elif tok.type == TokType.LBRACE:
                    brace_depth += 1
                elif tok.type == TokType.RBRACE and brace_depth > 0:
                    brace_depth -= 1

                parts.append(tok.value)
                self.pos += 1

                # if we just consumed the closing token that brought depth to zero, continue so outer loop can stop next iteration

            value = " ".join(parts).strip()

        self.skip_newlines()
        return key, Attribute(key=key, value=value, annotations=anns)

    # maps and lists
    def parse_map(self) -> Dict[str, Any]:
        obj: Dict[str, Any] = {}
        self.eat(TokType.LBRACE)
        self.skip_newlines()

        def consume_raw_line():
            raw_parts = self._collect_tokens_until((TokType.NEWLINE, TokType.RBRACE))
            if raw_parts:
                raw_line = " ".join(raw_parts).strip()
                obj.setdefault("__raw__", []).append(raw_line)

        while self.peek().type != TokType.RBRACE:
            self.skip_newlines()
            if self.peek().type == TokType.RBRACE:
                break
            if self.peek().type == TokType.EOF:
                raise ParseError("Unexpected EOF inside map")

            # If we see a stray '@' not followed by IDENT, treat the rest of the line as raw text.
            if self.peek().type == TokType.AT and self.peek(1).type != TokType.IDENT:
                consume_raw_line()
                continue

            entry_anns = self.parse_annotations()

            # Be tolerant: if the next token cannot start a key, treat the rest of the line as raw text and skip.
            if self.peek().type not in (TokType.IDENT, TokType.STRING):
                consume_raw_line()
                continue

            # Allow quoted keys (e.g., "@testing_library_dom") in maps
            if self.peek().type == TokType.IDENT:
                key = self.eat(TokType.IDENT).value
            else:  # STRING
                key = self.eat(TokType.STRING).value

            # If there is no colon, treat the rest of the line as a scalar value.
            if self.peek().type == TokType.COLON:
                self.eat(TokType.COLON)
                self.skip_newlines()

                t = self.peek()
                if t.type == TokType.LBRACE:
                    val = self.parse_map()
                elif t.type == TokType.LBRACK and not self._bracket_value_is_literal():
                    val = self.parse_list(key)
                elif t.type == TokType.STRING:
                    val = self.eat(TokType.STRING).value
                else:
                    parts = self._collect_tokens_until(
                        (TokType.NEWLINE, TokType.RBRACE, TokType.RBRACK)
                    )
                    val = " ".join(parts).strip()
            else:
                # No colon after key: treat the entire remainder (including any braces) as a raw string.
                if self.peek().type == TokType.LBRACE:
                    # collect balanced braces so we don't stop at the first newline
                    depth = 0
                    buf: List[str] = []
                    while True:
                        tok = self.peek()
                        if tok.type == TokType.EOF:
                            break
                        if tok.type == TokType.LBRACE:
                            depth += 1
                        elif tok.type == TokType.RBRACE:
                            depth -= 1
                        buf.append(tok.value)
                        self.pos += 1
                        if depth == 0 and tok.type == TokType.RBRACE:
                            break
                    val = " ".join(buf).strip()
                else:
                    parts = self._collect_tokens_until((TokType.NEWLINE, TokType.RBRACE, TokType.RBRACK))
                    val = " ".join(parts).strip()

            self.skip_newlines()

            # allow optional comma after an entry
            if self.peek().type == TokType.COMMA:
                self.pos += 1
                self.skip_newlines()

            # if there were annotations, store an Attribute
            if entry_anns:
                obj[key] = Attribute(key=key, value=val, annotations=entry_anns)
            else:
                obj[key] = val

        self.eat(TokType.RBRACE)
        self.skip_newlines()
        # If this "map" only captured raw text (no real key/value pairs), collapse to a string.
        if len(obj) == 1 and "__raw__" in obj:
            raw_val = obj["__raw__"]
            if isinstance(raw_val, list):
                return "\n".join(raw_val)
            return str(raw_val)

        return obj
    
    def parse_field(self, leading_annotations: List[Annotation]) -> Field:
        """
        Parse one field in fields: [ ... ] context.

        Examples it should support:

        -database: UserRepo
        + Name: string
        Email: string
        # InternalID: UUID

        We parse:
        visibility: '+', '-', '#', or None, just like in UML
        name: IDENT
        type: everything after ':' up to comma/newline/RBRACK
        """
        self.skip_newlines()

        visibility = None
        first = self.peek()
        if first.type == TokType.IDENT and first.value in ("+", "-", "#"):
            visibility = first.value
            self.pos += 1

        name = self.eat(TokType.IDENT).value  # e.g. "database", "Name"

        if self.peek().type == TokType.COLON:
            self.eat(TokType.COLON)

        type_parts = self._collect_tokens_until(
            (TokType.COMMA, TokType.NEWLINE, TokType.RBRACK)
        )
        type_str = " ".join(type_parts).strip()

        self.skip_newlines()

        return Field(
            name=name,
            type=type_str,
            visibility=visibility,
            annotations=leading_annotations,
            attributes={},
        )
    
    def parse_method(self, leading_annotations: List[Annotation]) -> Method:
        """        
        Parse one method inside `methods: [ ... ]`.
        Supports:
        +user() -> BelongsTo  (header-only)
        +user() -> BelongsTo {
            description: ...
            effects: { hashing_driver: bcrypt, hashing_rounds: 4 }
        }  (with body containing arbitrary attributes)
        """
        self.skip_newlines()
        start_pos = self.pos

        # visibility: + / - /
        visibility = None
        tok = self.peek()
        if tok.type == TokType.IDENT and tok.value in ("+", "-", "#"):
            visibility = tok.value
            self.pos += 1

        # name
        name_tok = self.eat(TokType.IDENT)
        name = name_tok.value

        # (params)
        self.eat(TokType.LPAREN)
        param_tokens: List[str] = []
        paren_depth = 1
        while paren_depth > 0:
            t = self.peek()
            if t.type == TokType.EOF:
                raise ParseError(f"Unclosed parameter list in method {name}")
            if t.type == TokType.LPAREN:
                paren_depth += 1
                self.pos += 1
            elif t.type == TokType.RPAREN:
                paren_depth -= 1
                self.pos += 1
                if paren_depth == 0:
                    break
            else:
                param_tokens.append(t.value)
                self.pos += 1
        params_str = " ".join(param_tokens).strip()

        self.skip_newlines()

        # -> return type
        self.eat(TokType.ARROW)
        self.skip_newlines()

        ret_tokens = self._collect_tokens_until(
            (TokType.LBRACE, TokType.COMMA, TokType.RBRACK, TokType.NEWLINE)
        )
        returns_str = " ".join(ret_tokens).strip()

        # decide if the method has a body
        self.skip_newlines()
        next_tok = self.peek()

        # Header-only variant (without {}):
        #   +user() -> BelongsTo
        if next_tok.type != TokType.LBRACE:
            return Method(
                name=name,
                visibility=visibility,
                params=params_str,
                returns=returns_str,
                annotations=leading_annotations,
                attributes={},  # empty body
            )

        # method with body
        self.eat(TokType.LBRACE)
        self.skip_newlines()

        body_attrs: Dict[str, Attribute] = {}
        while self.peek().type != TokType.RBRACE:
            self.skip_newlines()
            if self.peek().type == TokType.RBRACE:
                break
            key, attr = self.parse_attribute()
            body_attrs[key] = attr
            self.skip_newlines()

        self.eat(TokType.RBRACE)

        return Method(
            name=name,
            visibility=visibility,
            params=params_str,
            returns=returns_str,
            annotations=leading_annotations,
            attributes=body_attrs,
        )

    def parse_endpoint_tokens(
        self,
        tokens: List[Token],
        leading_annotations: List[Annotation],
    ) -> Endpoint:
        """
        Interpret the collected tokens as either a gRPC or HTTP endpoint.
        """
        HTTP_VERBS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}

        # local cursor
        p = 0

        def pt(offset: int = 0) -> "Token":
            if p + offset < len(tokens):
                return tokens[p + offset]
            return Token(TokType.EOF, "", -1, -1)

        def advance() -> "Token":
            nonlocal p
            t = pt(0)
            p += 1
            return t

        def skip_newlines_local():
            nonlocal p
            while p < len(tokens) and tokens[p].type == TokType.NEWLINE:
                p += 1

        raw = compact_token_values(tokens)
        skip_newlines_local()
        first = pt(0)

        # HTTP style
        if first.type == TokType.IDENT and first.value in HTTP_VERBS:
            method = advance().value
            skip_newlines_local()

            # split into path_tokens and body_tokens
            path_tokens: List["Token"] = []
            body_tokens: List["Token"] = []
            seen_body = False

            # collect up to '->'
            while pt().type not in (TokType.ARROW, TokType.EOF):
                t = pt()

                # Heuristic: request body starts when we see 'JSON' or '{'
                if not seen_body and (
                    (t.type == TokType.IDENT and t.value == "JSON")
                    or t.type == TokType.LBRACE
                ):
                    seen_body = True

                if seen_body:
                    body_tokens.append(t)
                else:
                    path_tokens.append(t)

                advance()

            # compact join for path and body
            path = compact_token_values(path_tokens)
            request_sig = compact_token_values(body_tokens) if body_tokens else ""

            if pt().type == TokType.ARROW:
                advance()
            skip_newlines_local()

            # response signature until '[' (attrs) or end
            resp_tokens: List[Token] = []
            while pt().type not in (TokType.EOF, TokType.LBRACK):
                resp_tokens.append(advance())
            response_sig = compact_token_values(resp_tokens)

            attrs: Dict[str, str] = {}
            skip_newlines_local()
            if pt().type == TokType.LBRACK:
                advance()  # '['
                key_parts: List[str] = []
                val_parts: List[str] = []
                reading_key = True
                while pt().type not in (TokType.EOF, TokType.RBRACK):
                    t = advance()
                    if t.type == TokType.COLON and reading_key:
                        reading_key = False
                        continue
                    if t.type == TokType.COMMA:
                        key = " ".join(key_parts).strip()
                        val = " ".join(val_parts).strip()
                        if key:
                            attrs[key] = val
                        key_parts, val_parts = [], []
                        reading_key = True
                        continue
                    (key_parts if reading_key else val_parts).append(t.value)
                if pt().type == TokType.RBRACK:
                    advance()
                key = " ".join(key_parts).strip()
                val = " ".join(val_parts).strip()
                if key:
                    attrs[key] = val

            return Endpoint(
                style="http",
                name=None,
                method=method,
                path=path,
                request=request_sig,
                response=response_sig,
                annotations=leading_annotations,
                attributes=attrs,
                raw=raw,
            )

        # gRPC style
        name = None
        if pt().type == TokType.IDENT:
            name = advance().value

        skip_newlines_local()

        # request in parentheses
        request_parts: List[Token] = []
        if pt().type == TokType.LPAREN:
            advance()
            paren_depth = 1
            while paren_depth > 0 and pt().type != TokType.EOF:
                t = advance()
                if t.type == TokType.LPAREN:
                    paren_depth += 1
                elif t.type == TokType.RPAREN:
                    paren_depth -= 1
                    if paren_depth == 0:
                        break
                request_parts.append(t)

        request_sig = compact_token_values(request_parts).strip()

        skip_newlines_local()

        if pt().type == TokType.ARROW:
            advance()
        skip_newlines_local()

        # response may be parenthesized as well
        response_tokens: List[Token] = []
        wrapped_as_tuple = False

        if pt().type == TokType.LPAREN:
            advance()
            wrapped_as_tuple = True
            paren_depth = 1
            while paren_depth > 0 and pt().type != TokType.EOF:
                t = advance()
                if t.type == TokType.LPAREN:
                    paren_depth += 1
                elif t.type == TokType.RPAREN:
                    paren_depth -= 1
                    if paren_depth == 0:
                        break
                response_tokens.append(t)
        else:
            while pt().type not in (TokType.EOF, TokType.LBRACK):
                response_tokens.append(advance())

        inner = compact_token_values(response_tokens).strip()
        response_sig = f"({inner})" if wrapped_as_tuple else inner

        attrs: Dict[str, str] = {}
        skip_newlines_local()
        if pt().type == TokType.LBRACK:
            advance()
            key_parts: List[str] = []
            val_parts: List[str] = []
            reading_key = True
            while pt().type not in (TokType.EOF, TokType.RBRACK):
                t = advance()
                if t.type == TokType.COLON and reading_key:
                    reading_key = False
                    continue
                if t.type == TokType.COMMA:
                    key = " ".join(key_parts).strip()
                    val = " ".join(val_parts).strip()
                    if key:
                        attrs[key] = val
                    key_parts, val_parts = [], []
                    reading_key = True
                    continue
                (key_parts if reading_key else val_parts).append(t.value)
            if pt().type == TokType.RBRACK:
                advance()
            key = " ".join(key_parts).strip()
            val = " ".join(val_parts).strip()
            if key:
                attrs[key] = val

        return Endpoint(
            style="grpc",
            name=name,
            method=None,
            path=None,
            request=request_sig,
            response=response_sig,
            annotations=leading_annotations,
            attributes=attrs,
            raw=raw,
        )

    def parse_component_block(self, kind: str, leading_annotations: List[Annotation]) -> Block:
        """
        Parse a component block like:

          database UserRepo {
            @PATH(...)
            engine: postgres-12
            ...
          }

        'kind' is 'database'/'cache'/'struct', already consumed.
        """
        # 'kind' IDENT was already read by caller
        name = self.eat(TokType.IDENT).value
        self.eat(TokType.LBRACE)

        # annotations immediately inside the block (before first field)
        inner_block_anns = self.parse_annotations()

        attrs: Dict[str, Attribute] = {}

        while self.peek().type != TokType.RBRACE:
            self.skip_newlines()
            if self.peek().type == TokType.RBRACE:
                break
            key, attr = self.parse_attribute()
            attrs[key] = attr

        self.eat(TokType.RBRACE)
        self.skip_newlines()

        all_anns = leading_annotations + inner_block_anns

        return Block(
            kind=kind,
            name=name,
            annotations=all_anns,
            attributes=attrs,
        )

    def parse_list(self, context: Optional[str] = None) -> List[Any]:
        items: List[Any] = []
        self.eat(TokType.LBRACK)
        self.skip_newlines()

        while self.peek().type != TokType.RBRACK:
            self.skip_newlines()
            if self.peek().type == TokType.RBRACK:
                break
            if self.peek().type == TokType.EOF:
                raise ParseError("Unexpected EOF inside list")

            # annotations before list items (e.g. @DELETED { ... })
            anns = self.parse_annotations()

            t = self.peek()

            # 1) methods: [ ... ]
            if context == "methods":
                method = self.parse_method(anns)
                items.append(method)

            # 2) fields
            elif context == "fields":
                field = self.parse_field(anns)
                items.append(field)

            elif context == "endpoints":
                # parse a single endpoint line robustly
                tokens = self._collect_endpoint_tokens()
                if not tokens:
                    pass
                else:
                    ep = self.parse_endpoint_tokens(tokens, anns)
                    items.append(ep)
            
            # 2) Special handling for components: [ database X { ... } ... ]
            elif (
                context == "components"
                and self.peek(0).type == TokType.IDENT
                and self.peek(1).type == TokType.IDENT
                and self.peek(2).type == TokType.LBRACE
            ):
                kind_raw = self.eat(TokType.IDENT).value   # e.g. "db", "class"
                comp_block = self.parse_component_block(kind_raw, anns)
                items.append(comp_block)

            # 3) Generic map element in a list: { ... }
            elif t.type == TokType.LBRACE:
                val = self.parse_map()
                if anns:
                    # wrap this list element so we don't lose @DELETED / @IGNORE
                    val = Attribute(key=None, value=val, annotations=anns)
                items.append(val)
            # 4) Scalar item (API endpoint sig, field name, etc.)
            else:
                parts: List[str] = []
                bracket_depth = 0  # for nested [ ... ] inside scalars
                paren_depth = 0    # for nested ( ... ) inside scalars
                brace_depth = 0    # for nested { ... } inside scalars

                while True:
                    tok = self.peek()

                    if tok.type == TokType.EOF:
                        break

                    if tok.type == TokType.LBRACK:
                        bracket_depth += 1
                    elif tok.type == TokType.RBRACK:
                        if bracket_depth > 0:
                            bracket_depth -= 1
                        elif paren_depth == 0 and brace_depth == 0:
                            # end of THIS list
                            break
                    elif tok.type == TokType.LPAREN:
                        paren_depth += 1
                    elif tok.type == TokType.RPAREN:
                        if paren_depth > 0:
                            paren_depth -= 1
                    elif tok.type == TokType.LBRACE:
                        brace_depth += 1
                    elif tok.type == TokType.RBRACE:
                        if brace_depth > 0:
                            brace_depth -= 1

                    if (
                        bracket_depth == 0
                        and paren_depth == 0
                        and brace_depth == 0
                        and tok.type in (TokType.COMMA, TokType.NEWLINE)
                    ):
                        break

                    parts.append(tok.value)
                    self.pos += 1

                scalar = " ".join(parts).strip()
                if scalar:
                    items.append(scalar)

            # optional comma between list items
            if self.peek().type == TokType.COMMA:
                self.pos += 1
            self.skip_newlines()

        self.eat(TokType.RBRACK)
        self.skip_newlines()
        return items
    
    def _collect_endpoint_tokens(self) -> List[Token]:
        """
        Collect tokens for ONE endpoint "line".

        Stop at:
        - a COMMA, when not inside any (), {}, [] nesting
        - a NEWLINE, when not inside nesting
        - the closing RBRACK of the endpoints list (when not nested)

        Do NOT stop at commas/line breaks inside:
        - ( ... )
        - { ... }
        - [ ... ]  (e.g. [auth: ..., cache: ...])
        """
        tokens: List[Token] = []
        depth = 0  # unified nesting depth over (), {}, []

        while True:
            tok = self.peek()
            if tok.type == TokType.EOF:
                break

            # Opening brackets / parens / braces
            if tok.type in (TokType.LBRACK, TokType.LPAREN, TokType.LBRACE):
                depth += 1
                tokens.append(tok)
                self.pos += 1
                continue

            # Closing brackets / parens / braces
            if tok.type in (TokType.RBRACK, TokType.RPAREN, TokType.RBRACE):
                if depth > 0:
                    depth -= 1
                    tokens.append(tok)
                    self.pos += 1
                    continue
                # depth == 0 and RBRACK: this is the endpoints list closing
                if tok.type == TokType.RBRACK:
                    break
                # depth == 0 and RPAREN/RBRACE is syntactically weird,
                # but we'll just consume it as normal
                tokens.append(tok)
                self.pos += 1
                continue

            # Separator between endpoints: only when not nested
            if depth == 0 and tok.type in (TokType.COMMA, TokType.NEWLINE):
                # don't consume here; let parse_list handle comma/newline
                break

            tokens.append(tok)
            self.pos += 1

        return tokens
    
    def _parse_method_with_body(self, leading_annotations: List[Annotation]) -> Method:
        """
        Collect a chunk from the start of the method to its closing '}' and parse it locally.
        """

        # 1) Collect the chunk of tokens (header + body)
        start_pos = self.pos
        brace_depth = 0
        seen_lbrace = False

        while True:
            tok = self.peek()
            if tok.type == TokType.EOF:
                raise ParseError("Unexpected EOF while parsing method body")

            if tok.type == TokType.LBRACE:
                brace_depth += 1
                seen_lbrace = True
            elif tok.type == TokType.RBRACE:
                if seen_lbrace:
                    brace_depth -= 1
                    if brace_depth == 0:
                        # include this RBRACE
                        self.pos += 1
                        break

            self.pos += 1

        end_pos = self.pos
        chunk_tokens = self.tokens[start_pos:end_pos]

        # 2) Local parser over the chunk
        header_parser = Parser(chunk_tokens)
        header_parser.skip_newlines()

        # visibility
        visibility = None
        first = header_parser.peek()
        if first.type == TokType.IDENT and first.value in ("+", "-", "#"):
            visibility = first.value
            header_parser.pos += 1

        # name
        name = header_parser.eat(TokType.IDENT).value

        # (params)
        header_parser.eat(TokType.LPAREN)
        param_tokens: List[str] = []
        paren_depth = 1
        while paren_depth > 0:
            t = header_parser.peek()
            if t.type == TokType.EOF:
                raise ParseError(f"Unclosed parameter list in method {name}")

            if t.type == TokType.LPAREN:
                paren_depth += 1
                header_parser.pos += 1
            elif t.type == TokType.RPAREN:
                paren_depth -= 1
                header_parser.pos += 1
                if paren_depth == 0:
                    break
            else:
                param_tokens.append(t.value)
                header_parser.pos += 1

        params_str = " ".join(param_tokens).strip()
        header_parser.skip_newlines()

        # ->
        header_parser.eat(TokType.ARROW)
        header_parser.skip_newlines()

        # return type - read until '{', skipping NEWLINEs
        ret_tokens: List[str] = []
        while True:
            t = header_parser.peek()
            if t.type == TokType.LBRACE:
                break
            if t.type == TokType.EOF:
                raise ParseError(f"Method {name} missing body '{{' after '-> returns'")
            if t.type == TokType.NEWLINE:
                header_parser.pos += 1
                continue
            ret_tokens.append(t.value)
            header_parser.pos += 1

        returns_str = " ".join(ret_tokens).strip()

        # now we're at the '{'
        header_parser.eat(TokType.LBRACE)
        header_parser.skip_newlines()

        # body is a mini-map of attributes
        body_attrs: Dict[str, Attribute] = {}
        while header_parser.peek().type != TokType.RBRACE:
            header_parser.skip_newlines()
            if header_parser.peek().type == TokType.RBRACE:
                break
            key, attr = header_parser.parse_attribute()
            body_attrs[key] = attr

        header_parser.eat(TokType.RBRACE)

        return Method(
            name=name,
            visibility=visibility,
            params=params_str,
            returns=returns_str,
            annotations=leading_annotations,
            attributes=body_attrs,
        )

    def _collect_tokens_until(self, terminators: Tuple[TokType, ...]) -> List[str]:
        """Collect tokens until reaching one of `terminators` at top-level nesting."""
        parts: List[str] = []
        bracket_depth = 0
        paren_depth = 0
        brace_depth = 0
        angle_depth = 0

        while True:
            tok = self.peek()
            if tok.type == TokType.EOF:
                break

            if (
                tok.type in terminators
                and bracket_depth == 0
                and paren_depth == 0
                and brace_depth == 0
                and angle_depth == 0
            ):
                break

            parts.append(tok.value)
            self.pos += 1

            if tok.type == TokType.LBRACK:
                bracket_depth += 1
            elif tok.type == TokType.RBRACK and bracket_depth > 0:
                bracket_depth -= 1
            elif tok.type == TokType.LPAREN:
                paren_depth += 1
            elif tok.type == TokType.RPAREN and paren_depth > 0:
                paren_depth -= 1
            elif tok.type == TokType.LBRACE:
                brace_depth += 1
            elif tok.type == TokType.RBRACE and brace_depth > 0:
                brace_depth -= 1
            elif tok.type == TokType.IDENT and tok.value == "<":
                angle_depth += 1
            elif tok.type == TokType.IDENT and tok.value == ">" and angle_depth > 0:
                angle_depth -= 1

        return parts

    def _bracket_value_is_literal(self) -> bool:
        """Peek ahead to see if a leading '[' denotes a literal (not a real list)."""
        idx = self.pos
        depth = 0

        while idx < len(self.tokens):
            tok = self.tokens[idx]
            if tok.type == TokType.LBRACK:
                depth += 1
            elif tok.type == TokType.RBRACK:
                depth -= 1
                if depth == 0:
                    idx += 1
                    saw_newline = False
                    while idx < len(self.tokens) and self.tokens[idx].type == TokType.NEWLINE:
                        saw_newline = True
                        idx += 1
                    if idx >= len(self.tokens):
                        return False
                    if saw_newline:
                        return False
                    next_tok = self.tokens[idx]
                    return next_tok.type not in (
                        TokType.COMMA,
                        TokType.RBRACE,
                        TokType.RBRACK,
                        TokType.EOF,
                    )
            elif tok.type == TokType.EOF:
                break
            idx += 1

        return False

# -----------------------------
# Public entry

def parse_dsl(text: str, parse_endpoints: bool = True, merge_duplicate_attrs: bool = True) -> System:
    tokens = tokenize(text)
    parser = Parser(tokens, merge_duplicate_attrs=merge_duplicate_attrs)
    system = parser.parse_system()
    if parse_endpoints:
        enrich_endpoints(system)
    return system
