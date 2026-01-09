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

## Examples

Runnable example schemas (plus generated JSON artifacts) live in:

- `examples/` (start with `examples/README.md`)

If you just want to try SiMAL quickly, those examples are the easiest starting point.

From the repo root:

```bash
python simal_cli.py examples/simple-ecommerce/schema.siml
```

---

## Token savings: measuring SiMAL vs JSON

This repo's main motivation is **prompt efficiency**: represent the same "system schema" content with fewer tokens so more context fits into a fixed model window.

Below are results from a controlled comparison between:

- **SiMAL** schemas (`.simal`)
- **JSON (max-simple)** converted from those same schemas (keeps some complex structures like endpoints/methods as compact strings where possible)

### Experimental setup

- **Projects:** 10 repos, spanning webapps, libraries, and microservices.
- **Iterations:** each project has multiple schema files; each iteration generates a new schema based on (optional) past schema + chunk of source code files (up to 5k lines); thus number of iterations = number of schema files.
- **Schema generation model:** `gpt-5-2025-08-07`.
- **JSON conversion:** `simal_cli.py --max-simple` (max-simplified JSON).
- **Token counting:**
  - **GPT tokenizer:** `tiktoken` (`o200k_base` used by `gpt-5` and newer models)
  - **Gemma tokenizer:** `tokenizers` loading `google/gemma-3-27b-it`

Interpretation (project-matched comparison):

- Delta = tokens_simal - tokens_json (negative is better)
- ratio = tokens_simal / tokens_json (smaller than 1.0 is better)

### Benchmarked repos (stack snapshot)

| Project | What it is | Stack highlights |
|---|---|---|
| [JuniorTest](https://github.com/niksyromyatnikov/JuniorTest) | News app + REST API | PHP/Laravel backend; Vue frontend (`composer.json`, `package.json`) |
| [OHLCFormer](https://github.com/niksyromyatnikov/OHLCFormer) | OHLC forecasting toolkit | Python ML tooling (PyPI-style project layout) |
| [dashboard-reactjs](https://github.com/luisotavio756/dashboard-reactjs) | Dashboard template | React SPA (Yarn) |
| [full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template) | Full-stack app template | FastAPI + SQLModel + Postgres; React + TypeScript + Vite; Docker Compose/Traefik |
| [microservice-app-example](https://github.com/elgris/microservice-app-example) | Polyglot microservice demo | Vue frontend; Go auth API; Node TODOs API; Java Spring Boot users API; Python worker; Redis/Zipkin |
| [otel-python-cloud-run](https://github.com/dgildeh/otel-python-cloud-run) | Observability demo | Python microservices instrumented with OpenTelemetry; Google Cloud Run |
| [spring-food-delivery-microservices](https://github.com/mehdihadeli/spring-food-delivery-microservices) | Large Java microservices example | Spring Boot; DDD/CQRS/Vertical Slice; RabbitMQ; event-driven architecture |
| [sqlmodel](https://github.com/fastapi/sqlmodel) | Python library | SQLModel (Pydantic + SQLAlchemy ecosystem) |
| [tokenizers](https://github.com/huggingface/tokenizers) | Tokenization library | Rust core; Python bindings (PyO3) + Node bindings; performance-focused |
| [wild-workouts-go-ddd-example](https://github.com/ThreeDotsLabs/wild-workouts-go-ddd-example) | DDD reference app | Go backend; gRPC/OpenAPI; Cloud Run + Firebase; Terraform; includes a web frontend |

### Global results (all projects × all iterations)

Because JSON whitespace can be tuned depending on whether you optimize for **storage** or **human readability**, the results below include two JSON baselines.

Totals across the whole corpus:

| Mode | Files/Iterations | Bytes | GPT tokens | Gemma tokens | Avg GPT tokens/file | Avg Gemma tokens/file |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| JSON (max-simple, single-line) | 394 | 23,575,158 | 6,459,374 | 7,090,717 | 16,394 | 17,997 |
| JSON (max-simple, indent=2) | 394 | 37,379,088 | 7,919,025 | 9,656,851 | 20,099 | 24,510 |
| SiMAL | 394 | 26,075,093 | 5,900,298 | 7,083,775 | 14,975 | 17,979 |

Overall delta (SiMAL vs JSON):

- **Against indent=2 JSON:** bytes −30.2%, GPT tokens −25.5%, Gemma tokens −26.6% (SiMAL is smaller across the board)
- **Against single-line JSON:** bytes +10.6% (SiMAL is larger), GPT tokens −8.7%, Gemma tokens −0.1% (near-parity)

### Per-project breakdown

All projects have identical iteration counts between JSON and SiMAL (each JSON file is derived from the corresponding SiMAL schema).

#### Baseline A — JSON (indent=2) vs SiMAL

| Project | Files/Iterations | GPT tokens (JSON → SiMAL) | GPT Δ | GPT Δ% | Gemma tokens (JSON → SiMAL) | Gemma Δ | Gemma Δ% |
|---|:---:|---|:---:|:---:|---|:---:|:---:|
| `JuniorTest` | 31 | 246,345 → 172,507 | −73,838 | −30.0% | 299,688 → 203,471 | −96,217 | −32.1% |
| `OHLCFormer` | 12 | 62,733 → 47,374 | −15,359 | −24.5% | 76,965 → 56,520 | −20,445 | −26.6% |
| `dashboard-reactjs` | 26 | 196,564 → 166,818 | −29,746 | −15.1% | 238,590 → 203,388 | −35,202 | −14.8% |
| `full-stack-fastapi-template` | 39 | 793,822 → 613,405 | −180,417 | −22.7% | 962,485 → 735,031 | −227,454 | −23.6% |
| `microservice-app-example` | 29 | 175,694 → 127,267 | −48,427 | −27.6% | 217,023 → 153,607 | −63,416 | −29.2% |
| `otel-python-cloud-run` | 14 | 61,681 → 44,746 | −16,935 | −27.5% | 76,291 → 54,636 | −21,655 | −28.4% |
| `spring-food-delivery-microservices` | 63 | 1,506,754 → 1,186,694 | −320,060 | −21.2% | 1,857,938 → 1,433,990 | −423,948 | −22.8% |
| `sqlmodel` | 41 | 870,883 → 650,840 | −220,043 | −25.3% | 1,046,047 → 768,631 | −277,416 | −26.5% |
| `tokenizers` | 78 | 2,430,922 → 1,750,332 | −680,590 | −28.0% | 2,966,844 → 2,101,913 | −864,931 | −29.2% |
| `wild-workouts-go-ddd-example` | 61 | 1,573,627 → 1,140,315 | −433,312 | −27.5% | 1,914,980 → 1,372,588 | −542,392 | −28.3% |

#### Baseline B — JSON (single-line) vs SiMAL

| Project | Files/Iterations | GPT tokens (JSON → SiMAL) | GPT Δ | GPT Δ% | Gemma tokens (JSON → SiMAL) | Gemma Δ | Gemma Δ% |
|---|:---:|---|:---:|:---:|---|:---:|:---:|
| `JuniorTest` | 31 | 194,510 → 172,507 | −22,003 | −11.3% | 207,888 → 203,471 | −4,417 | −2.1% |
| `OHLCFormer` | 12 | 53,044 → 47,374 | −5,670 | −10.7% | 59,809 → 56,520 | −3,289 | −5.5% |
| `dashboard-reactjs` | 26 | 171,773 → 166,818 | −4,955 | −2.9% | 194,509 → 203,388 | +8,879 | +4.6% |
| `full-stack-fastapi-template` | 39 | 667,027 → 613,405 | −53,622 | −8.0% | 734,920 → 735,031 | +111 | +0.0% |
| `microservice-app-example` | 29 | 138,988 → 127,267 | −11,721 | −8.4% | 153,007 → 153,607 | +600 | +0.4% |
| `otel-python-cloud-run` | 14 | 50,591 → 44,746 | −5,845 | −11.6% | 56,545 → 54,636 | −1,909 | −3.4% |
| `spring-food-delivery-microservices` | 63 | 1,253,163 → 1,186,694 | −66,469 | −5.3% | 1,411,450 → 1,433,990 | +22,540 | +1.6% |
| `sqlmodel` | 41 | 706,327 → 650,840 | −55,487 | −7.9% | 756,428 → 768,631 | +12,203 | +1.6% |
| `tokenizers` | 78 | 1,943,340 → 1,750,332 | −193,008 | −9.9% | 2,116,913 → 2,101,913 | −15,000 | −0.7% |
| `wild-workouts-go-ddd-example` | 61 | 1,280,611 → 1,140,315 | −140,296 | −11.0% | 1,399,248 → 1,372,588 | −26,660 | −1.9% |

### What these numbers mean

- The win is **consistent across stacks** (frontend-only, backend templates, polyglot microservices, and libraries).
- The win is **highly sensitive to JSON whitespace choices**, especially under the GPT tokenizer.
- Under **indent=2 JSON**, SiMAL saves roughly **~25–27% tokens** overall (both GPT and Gemma).
- Under **single-line JSON**, SiMAL still saves **~9% GPT tokens** overall, while **Gemma tokens are ~parity** (and some repos flip direction).

### Caveats / notes

- **JSON formatting is part of the baseline.** A single-line JSON is often best for storage/transport, while indented JSON is best for humans. If you copy JSON into prompts as pretty-printed text, the whitespace overhead matters.
- **Tokenizer behavior differs.** In this dataset, minifying JSON dramatically reduces GPT-token counts, but affects Gemma-token counts much less.
- This comparison isolates **representation overhead** (syntax/structure). It does not claim anything about schema *quality* or downstream task performance.

### Quality evaluation (schema correctness)

Token savings matter only if the representation stays **faithful and useful**. To sanity-check that, we also ran an LLM-as-judge evaluation where judges were asked to read:

- the **full project context** (all source-code chunks up to and including the last schema-iteration), and
- the **latest schema** for that project (JSON vs SiMAL; same iteration index)

and then:

- identify issues, incorrect statements, and missing/contradictory details, and
- produce a score (later converted into a weighted/penalized manual score per run).

Setup:

- **Judges:** Gemini 3 Pro, Claude Sonnet 4.5, GPT-5.2
- **Runs:** 3 independent runs per (judge × project × format)
- **Aggregation:** average of the 3 run scores per cell
- **Context-limit note:** GPT-5.2 has a hard input cap (~280k tokens) and could not evaluate `sqlmodel` and `tokenizers`, so GPT averages are reported over **8 projects**.

<details>
<summary>Scoring rubric (criteria, weights, and penalties)</summary>

Each evaluation run outputs strict JSON with:

- **Six subscores** (integers 0–5, or -1 for N/A):
  - `schema_coverage_score` (weight 20)
  - `schema_accuracy_score` (weight 20)
  - `api_accuracy_score` (weight 20)
  - `structure_accuracy_score` (weight 15)
  - `annotation_quality_score` (weight 10)
  - `non_hallucination_score` (weight 15)

- **Six error counters** (non-negative integers):
  - `missed_major_components`, `missed_minor_components`, `spurious_components`,
  - `incorrect_api_signatures`, `incorrect_struct_or_table_definitions`, `incorrect_visibility_flags`

N/A handling:

- A category can be N/A only if that aspect genuinely does not exist in the repo *and* the schema does not claim it exists.
- N/A subscores are excluded from the weighted-base numerator and denominator.

Overall score is computed deterministically:

1) Weighted base from subscores:

`weighted_base = round_half_up(sum((subscore/5)*weight))` (excluding N/A)

2) Penalty from counted errors:

`penalty = 7 * missed_major_components + 2 * missed_minor_components + 4 * spurious_components + 3 * incorrect_api_signatures + 3 * incorrect_struct_or_table_definitions + 1 * incorrect_visibility_flags`

`overall_score = clamp(weighted_base - penalty, 0, 100)`

Evidence rules (how judges were instructed to behave):

- Evidence-first / strict mode: schema claims must be supported by the provided files.
- Acceptable abstraction is not penalized (e.g., naming-style differences, approximate types).
- Unsupported “strong verb” behavior claims are penalized (e.g., *enforces auth*, *uses JWT*, *caches for 5m*).

</details>

Average scores (higher is better):

| Project | JSON — Gemini | JSON — Claude | JSON — GPT | SiMAL — Gemini | SiMAL — Claude | SiMAL — GPT |
| --- | :---: | :---: | :---: | :---: | :---: | :---: |
| JuniorTest | **81** | **75.33** | **69** | **100** | **85** | **82.33** |
| OHLCFormer | **97.33** | **90** | **85.67** | **100** | **95.67** | **80.33** |
| dashboard-reactjs | **100** | **88** | **80.33** | **100** | **100** | **86** |
| full-stack-fastapi-template | **100** | **86** | **82.333** | **100** | **65.67** | **63** |
| microservice-app-example | **93** | **77** | **61.33** | **97.67** | **72.67** | **76.67** |
| otel-python-cloud-run | **98.33** | **94** | **92.67** | **100** | **97.33** | **95.33** |
| spring-food-delivery-microservices | **100** | **55.33** | **62** | **100** | **88.33** | **67.67** |
| wild-workouts-go-ddd-example | **97.67** | **95.33** | **80** | **100** | **71.33** | **64** |
| **Average (8 projects, n=24)** | **95.92** | **82.62** | **76.67** | **99.71** | **84.50** | **76.92** |
| sqlmodel | **74** | **73** | **—** | **64.67** | **58.33** | **—** |
| tokenizers | **100** | **94** | **—** | **94.67** | **29.67** | **—** |
| **Average (10 projects, n=30)** | **94.13** | **82.80** | **—** | **95.70** | **76.40** | **—** |

What’s worth noting in this dataset:

- **On 8 projects, SiMAL is on par or slightly better.** Where all three judges ran (8 projects), SiMAL matches JSON overall and edges ahead for Gemini and Claude on average, with GPT-5.2 near-parity.
- **Including the largest projects, Claude gets more conservative.** Adding `sqlmodel` and `tokenizers` shifts Claude’s average to **76.40 (SiMAL) vs 82.80 (JSON)** — i.e. SiMAL is about **8.4% lower** under Claude when long-context projects are included.
- **Long-context judging can be inconsistent.** On very long inputs, differences may reflect judge long-sequence reliability (what the model notices/forgets) as much as representation quality.
- **JSON is the more “familiar” schema format for judges.** Even if models have seen pieces of SiMAL-like syntax during training, they are far more likely to have seen full JSON schemas end-to-end, so some of the scoring can be subjective.

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

## What’s allowed (and what’s not) — as implemented here

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
