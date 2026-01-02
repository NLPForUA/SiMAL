# SiMAL - a system internals modeling and annotation language for LLM-driven software engineering

SiMAL ("System Internals Modeling and Annotation Language") is a lightweight DSL for describing software systems (services, APIs, components, runtime/config) of any scale in a way that is:

- **Readable for humans** (closer to architecture notes + config than a large JSON blob)
- **Friendly for LLM prompts** (compact syntax + fewer structural tokens)
- **Convertible to JSON** for downstream tooling

A core motivation is **token efficiency**: compared to typical structured JSON schemas, SiMAL tends to spend fewer tokens on quotes, commas, braces, and repeated key names. So you can fit more system context into the same prompt budget.

---

## Quickstart

Convert a SiMAL file (`.simal` or `.siml`) to JSON:

```bash
python simal_cli.py path/to/schema.simal
```

By default this writes:

- `<name>.json` (full JSON with type tags that can be converted back to SiMAL)
- `<name>_simple.json` (flattened and prompt-friendly JSON)

Optional flags:

```bash
python simal_cli.py path/to/schema.simal --json
python simal_cli.py path/to/schema.simal --simple
python simal_cli.py path/to/schema.simal --max-simple
```

`max-simple` emits a more compact JSON that keeps method/endpoint definitions as strings when possible. That was mainly used for fair comparison of token counts vs SiMAL while using SiMAL-like syntax for endpoints/methods and other structures.

---

## Core syntax

SiMAL is a **block + attributes** language:

- A file starts with a top-level `system { ... }` block
- Inside you can define attributes (`key: value`) and `service` blocks
- Values can be scalars, maps, lists, or heredoc strings

### 1) Blocks

Top-level:

```simal
system {
  type: microservices
  domain: ecommerce

  service user_service {
    langs: [go]
  }
}
```

A `service` has a name and a `{ ... }` body. Many other *component-like* blocks exist, typically inside `components: [ ... ]` lists.

### 2) Attributes (`key: value`)

Attributes look like YAML-ish key/value pairs, but are parsed as SiMAL tokens:

```simal
name: JuniorTest News App
cpu_limit: 2000m
autoscaling: cpu_target=70%
```

Important: **scalars are parsed as strings** by default (numbers/booleans like `true`, `120`, `1.0` are not automatically typed).

### 3) Maps (`{ ... }`)

Maps are dicts:

```simal
runtime: {
  development: {
    backend: k8s
    replicas: 1
  }
}
```

Map entries are separated by newlines; commas are not required but allowed.

### 4) Lists (`[ ... ]`)

Lists use brackets. Commas are allowed but optional; newlines can also separate items:

```simal
langs: [go, protobuf, yaml]
  or 
langs: ["go lang", protobuf, yaml]

ports_exposed: [50051]

issues_found: [
  { id: ISSUE-1, type: security },
  { id: ISSUE-2, type: perf }
]
```

Trailing commas are tolerated.

### 5) Strings

You can write:

- **Bare strings**: `domain: news`
- **Quoted strings** (single or double quotes): `php: "7.1.3"`

Quoted strings in the current tokenizer are simple (no robust escape handling). For multi-line text, use heredocs.

### 6) Heredoc strings (`<<LABEL ... LABEL`)

For descriptions, algorithms, long notes:

```simal
description: <<TEXT
This is a multi-line description.
It can include punctuation, colons, braces, etc.
TEXT
```

The tokenizer converts the entire heredoc into a single `STRING` token, which keeps parsing simple and avoids JSON escaping.

### 7) Annotations (`@NAME(...)`)

Annotations can appear before services, components, list items, and attributes:

```simal
@PATH(github.com/org/ecommerce/user-service/)
@CALLS(system.verification_service)
service user_service { ... }

@DELETED(timestamp: 2024-05-01T12:00:00Z, reason: "Migrated")
{ type: http, endpoints: [ ... ] }
```

Annotations are stored on the AST nodes and can be used for tooling (review filters, dependency graphs, etc.). There is no pre-defined set of annotations; you can invent your own as needed.

---

## Modeling richer structures (realistic examples)

The following sections demonstrate endpoints, methods, and field visibility. The examples are adapted from the real schema files in this repo (notably `schema_final.siml` and `schema_codex_5-1_mini.siml`).

### Components blocks (`components: [ ... ]`)

Inside `components: [ ... ]`, the parser supports component blocks of the form:

```simal
components: [
  database UserRepo {
    engine: postgres-12
    description: Manages user data in Postgres.
    queries: [GetByID, Insert, Update, Delete]
  }
  cache SessionCache {
    engine: redis-6
  }
  struct User {
    fields: [ ... ]
  }
]
```

The keyword (such as `database`, `cache`, `struct`, `config`, `table`, `hash`, etc.) is treated as the **component kind**, followed by an identifier name, followed by a normal block body. Kinds are not pre-defined; you can invent your own as needed.

You can annotate components:

```simal
components: [
  @CRITICAL
  @PATH(github.com/org/ecommerce/user-service/internal/db/)
  database UserRepo { ... }
]
```

### Fields with visibility (`fields: [ ... ]`)

In a `fields: [ ... ]` list, each field can start with a UML-like visibility marker:

- `+` public
- `-` private
- `#` protected/internal

Example:

```simal
struct User {
  fields: [
    +ID: UUID
    +Email: string
    -PasswordHash: string
    #InternalFlags: JSON
    FlexibleType: any string type definition is allowed here
  ]
}
```

Field syntax (as implemented):

- Optional visibility marker (`+`, `-`, `#`)
- Field name (identifier)
- A mandatory colon `:`
- A "type" string (token-joined until end-of-item)

Types are not validated by a type system - they’re primarily for compact documentation and LLM consumption.

### Methods (`methods: [ ... ]`)

In a `methods: [ ... ]` list, methods are parsed as:

- Optional visibility (`+`, `-`, `#`)
- Method name
- Go-like parameter list in parentheses `(...)` (kept as a raw string)
- `->` return signature (kept as a raw string)
- Method body `{ ... }` containing arbitrary attributes

Example:

```simal
struct UserService {
  methods: [
    +GetUser(uuid string) -> User {
      description: Retrieves user by UUID.
    }

    +CreateUser(name, email, password string) -> User {
      description: Registers a new user.
      algo: <<TEXT
1. Validate input
2. Hash password
3. Insert into database
4. Trigger verification workflow
TEXT
      analysis: {
        security: [PASSWORD_COMPLEXITY_WEAK]
        linter: [UNHANDLED_ERROR]
      }
    }

    -validateUserInput(name, email, password string) -> bool {
      description: Validates user input fields.
    }

    method_without_body() -> BelongsTo
  ]
}
```

This is one of the places SiMAL saves tokens vs JSON heavily: signatures are compact and bodies reuse the standard attribute syntax.

### API endpoints (`api: [...]` with `endpoints: [...]`)

Endpoints are parsed specially inside an `endpoints: [ ... ]` list.

#### HTTP-style endpoints

Pattern:

```
VERB <path> [<request-signature>] -> <response-signature> [<optional attrs>]
```

Example:

```simal
endpoints: [
  GET /api/comments/{id} -> JSON{comments: list?, error: str?} [auth:false, description:"List comments"],
  POST /api/comments JSON{token: str, article_id: int, text: str} -> JSON{comment_id: int?, error: str?} [auth:token]
]
```

Notes:

- The request signature is optional.
- The parser tries to split path vs request by heuristics (`JSON` or `{` begins the body).
- `{id}` placeholders in the path are interpreted as inputs during endpoint enrichment.

#### gRPC-style endpoints

Fallback pattern (when the line doesn’t start with an HTTP verb):

```
RpcName(<request>) -> (<response tuple>) [<attrs>]
```

Example:

```simal
endpoints: [
  GetUser(GetUserRequest{uuid: str}) -> (user: User{name: str, email: str, verified: bool}?, error: str?) [auth: user_or_admin, cache: 5m],
  CreateUser(CreateUserRequest{name: str, email: str, password: str}) -> (uuid: str?, error: str?) [auth: none, rate_limit: 10/m]
]
```

The request/response signatures are parsed into a structured form when possible (object shapes like `User{...}`, tuples like `(user: ..., error: ...)`, optional `?` markers). This enrichment is what allows simplified JSON output to include `inputs`/`outputs` fields.

---

## JSON vs SiMAL: side-by-side comparison


| Concept | JSON (idiomatic / “simple”) | SiMAL syntax | Comment (parser-aligned behavior) |
|---|---|---|---|
| Top-level container | `{ "kind": "system", "services": [...] }` | `system { ... }` | Parser requires `system { ... }` at file start and builds a `System` (top-level attributes + `services`). |
| Token kinds | n/a | `{ } [ ] ( ) : , @ ->` | Tokenizer has explicit tokens for these plus `NEWLINE`; most other characters fall back to `IDENT` tokens (e.g. `+`, `#`). |
| Key/value attributes | `"domain": "news"` | `domain: news` | Attribute syntax is `key: value`; scalar values are joined from tokens and typically remain strings. |
| Lists/arrays | `"langs": ["go", "yaml"]` | `langs: [go, yaml]` | In lists, commas are optional; newlines also separate items; trailing commas tolerated. |
| Map / object | `{ "driver": "smtp", "port": 587 }` | `mail: { driver: smtp, port: 587 }` | Structured maps are `{ ... }` (either as an attribute value or as `{ ... }` list items). Commas after entries are optional. |
| Optional commas in maps | commas required | `{ a: b, c: d, }` | `parse_map` accepts an optional comma after each entry (including trailing). |
| Map “raw lines” support | (usually avoided) | lines inside `{ ... }` without `key:` | Inside maps, non `key: value` lines are captured under `__raw__`; if a map contains only raw lines it collapses to a string. |
| Quoted map keys | `{"@x": 1}` | `{ "@x": 1 }` | Map keys can be bare identifiers **or** quoted strings. |
| Heredoc multi-line text | `"description": "...\n..."` | `description: <<TEXT ... TEXT` | `<<LABEL` becomes a single `STRING` token; lines are collected until a line whose stripped text equals `LABEL`, then dedented. |
| Quoted strings | `"value with spaces"` | `key: "value"` or `key: 'value'` | Tokenizer supports both quotes but does not implement robust escaping; prefer heredocs for complex text. |
| Bare identifiers (allowed chars) | n/a | `root: storage_path('app')` | Identifiers start with `[A-Za-z_]` and may include digits plus `_. / - '`. Tokens like `(`, `)` are separate, so scalars may be re-joined with spaces. |
| “Weird” characters / CSS selectors | `"meta[name=csrf-token]"` | `csrf_token_source: meta[name=csrf-token]` | `[` / `]` are real tokens. Scalars are reconstructed with spaces, so for exact text fidelity (selectors/code), quote the value. |
| Attribute with annotations | `{ "key": {"value": ..., "annotations": [...] } }` | `@PATH(x)\nkey: value` | Attributes have an `annotations` list in the AST; annotations directly preceding an attribute are attached to the resulting `Attribute`. |
| Annotations (general) | `"annotations": [{"name":"PATH","args":["x"]}]` | `@PATH(x)` | Syntax: `@` + IDENT + optional `(args...)`. Args are split on commas at the top level of the parentheses. |
| Service definition | `{ "services": {"auth": { ... }}}` | `service auth_api { ... }` | Services are parsed only as `service <name> { ... }` within `system { ... }`. |
| Component blocks (generic Block) | `{ "kind": "database", "name": "UserRepo", ... }` | `database UserRepo { engine: postgres-12 }` | Component blocks are `Block(kind, name, annotations, attributes)`.
| Components list special-case | `components: [ {...}, {...} ]` | `components: [ database X { ... } cache Y { ... } ]` | Only the `components: [...]` list treats `kind name { ... }` as a component block; elsewhere it’s just scalar tokens unless wrapped in `{ ... }`. |
| Nested inline objects in lists | `channels: [{"name":"stack"}]` | `channels: [ { name: stack, driver: stack } ]` | Lists accept `{ ... }` items via `parse_map()`.
| Fields list (UML visibility) | `"fields": [{"vis":"-","name":"x","type":"T"}]` | `fields: [ -dontFlash: array ]` | In `fields: [...]` items, optional visibility `+`/`-`/`#` is supported, then `name: type` (type is a raw token-joined string). |
| Methods list (with body) | `"methods": [{"name":"render","params":"...","returns":"...","attrs":{...}}]` | `methods: [ +render(req T) -> R { description: ... } ]` | Method parsing reads `name(params) -> returns` then optionally a `{ ... }` body parsed as normal attributes. |
| Methods list (header-only) | `"methods": [{"def":"+user() -> BelongsTo"}]` | `methods: [ +user() -> BelongsTo ]` | Supported: if no `{` follows, method is emitted with an empty `attributes` dict. |
| Endpoint node (AST) | `{ "style":"http", "method":"GET", "path":"/x", ... }` | `GET /x -> JSON{...} [auth: ...]` | `endpoints: [...]` list items are parsed into `Endpoint` objects; trailing `[k:v,...]` becomes `attributes`.
| Endpoint styles | `{ "type": "http" }` / `{ "type": "grpc" }` | `GET ...` vs `RpcName(...) -> ...` | Endpoint style is detected by a verb-first heuristic (`GET/POST/...`). Non-verb lines fall back to gRPC-style parsing. |
| Type signatures inside endpoints | JSON Schema-like nested objects | `JSON{user: User{name: str}?, error: str?}` | Endpoint enrichment parses nested `{...}` shapes, tuples `(a: T, b: U)`, and optional `?` markers when possible. |
| HTTP path params extraction | `"inputs": [{"name":"id","type":"str"}]` | `GET /users/{id} -> ...` | Enrichment extracts `{id}` placeholders from HTTP paths and adds them to `inputs` (default type `str`). |
| Annotated API groups | `api: [ {"type":"http",...} ]` + wrapper | `@DELETED(...)\n{ type: http, endpoints: [...] }` | Lists wrap annotated `{ ... }` items as `Attribute(value=<map>, annotations=[...])` so annotations aren’t lost. |
| Full JSON (round-trippable) | `{ "__type__": "System", ... }` | n/a | Full conversion uses `__type__` tags for reliable reconstruction. |
| Simple JSON (LLM-friendly, lossy) | flattened objects, fewer tags | n/a | Simple conversion is smaller for prompts but may lose some fidelity (e.g., raw scalar spacing). |
| “Max simplify” JSON | compact `def` strings | n/a | Max-simplify may keep compact `def` strings (e.g., endpoints/methods) while emitting non-duplicated attrs separately. |
| List separators (commas) | commas required | optional `,` between items | List parsing treats commas as optional separators; endpoint/method/field parsers stop on commas only when not nested. |

---

## What’s allowed (and what’s not) - as implemented here

### Allowed

- File starts with `system { ... }`.
- Blocks: `system`, `service`, and component blocks like `database Name { ... }` inside `components: [ ... ]`.
- Attributes: `key: value` where `value` is scalar, `{...}`, `[...]`, or heredoc.
- Map keys can be bare identifiers or quoted strings.
- Lists: commas optional; newlines can separate items; trailing commas tolerated.
- Quoted strings: `'...'` or `"..."` (simple).
- Heredocs: `<<LABEL` then lines until a line equal to `LABEL`.
- Annotations: `@NAME(...)` before blocks/items.
- Field visibility markers in `fields: [...]`: `+`, `-`, `#`.
- Methods in `methods: [...]` can be either header-only or have a `{ ... }` body.
- Endpoint lines in `endpoints: [...]`:
  - HTTP verbs trigger HTTP parsing
  - everything else is treated as gRPC-style
  - bracket attrs supported: `[key: value, ...]`

### Not supported / limitations (current)

- Comments are not a first-class feature in the tokenizer.
- Scalars are typically kept as strings (no strict boolean/int parsing).
- Complex escaping inside quoted strings is limited; prefer heredocs.
- Keys/names with spaces are not supported as identifiers.

---

## Token savings: measuring SiMAL vs JSON

This repo includes a notebook that computes token-count statistics over the schema corpora:

- `notebooks/calculate_tokens_stats.ipynb`

It scans:

- `/schemas/json`
- `/schemas/simal`

and writes CSVs to:

- `/notebooks/_outputs/`

---

## Citation

If you use SiMAL in your research or projects, please cite:

```
@misc{syromiatnikov2026simal,
  author = {Syromiatnikov, Mykyta},
  title = {SiMAL: A System Internals Modeling and Annotation Language for LLM-Driven Software Engineering},
  year = {2026},
  publisher = {GitHub},
  journal = {GitHub repository},
  howpublished = {\url{https://github.com/NLPForUA/SiMAL}},
}
```
