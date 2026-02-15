## Token set:
- IDENT: "bare words" and also many non-alphanumeric single characters (fallback)
- Recognized "identifier" start: [A-Za-z_]
- Recognized continuation: [A-Za-z0-9_\.\/\-']
- Numbers are also tokenized as IDENT (a "number" is read until whitespace or one of { } [ ] ( ) : ,)
- Any other single character not matched earlier becomes a one-char IDENT
- STRING (either quoted string "..." or '...', or heredoc <<TEXT ... TEXT which is converted directly into one STRING token)
- punctuation tokens: { } [ ] ( ) : , @ ->
- NL for \n (newline)
- EOF

## Meta-rule:
ScalarText(terminators) = "read token values until one of terminators is seen at nesting depth 0, where nesting counts {…}, […], (…) (and, in some collectors, also <…>)."

## Extended Backus–Naur form:
```
# BLOCKS
Schema = NL* "system{" SystemBlock "}" NL* EOF ;
SystemBlock = { NL* SystemItem } ;
SystemItem = AnnotatedService | AnnotatedAttribute ;
Service = "service" Ident "{" { NL* Attribute } NL* "}" NL* ;

# ANNOTATIONS
Annotations = { Annotation NL* } ;
Annotation = "@" Ident [ "(" AnnArgList? ")" ] ;
AnnArgList = AnnArg { "," AnnArg } ;
AnnArg = AnnArgText ;

# ATTRIBUTES
AnnotatedAttribute = Annotations? Attribute ;
Attribute = AttributeHead AttributeRhs ;
AttributeHead = Ident ;
AttributeRhs = ( ":" NL* Value )
             | ( NL* Map ) (* missing ':' allowed when next token is "{" *)
             | ( NL* List ) (* missing ':' allowed when next token is "[" and not bracket-literal *)
             | ( NL* ComponentBlockValue ) (* missing ':' allowed when lookahead is: Ident "{" after a name *) ;

# BLOCK ITEMS
ComponentBlockValue = (* only when there was no ":" and lookahead matches: Ident "{" after a name *) ComponentBlock ;
Value = Map | List | String | Scalar ;
Scalar = ScalarText(terminators = { NL, "}", "]" } at depth 0)
ComponentBlock = Ident Ident "{" InnerBlockAnnotations? { NL* Attribute } NL* "}" NL* ;
InnerBlockAnnotations = Annotations ;

# MAPS/OBJECTS
Map = "{" NL* { MapItem } NL* "}" NL* ;
MapItem = NL* ( MapEntry | RawMapLine ) ;
MapEntry = Annotations? MapKey [ ":" NL* MapValue ] NL* [ "," NL* ] ;
MapKey = Ident | String ;
MapValueOpt = ":" NL* MapValue | MapInlineRemainder ;
MapValue = Map | List | String | MapScalar ;
MapInlineRemainder = MapScalarNoColon ;
MapScalarNoColon = ScalarText(terminators = { ",", NEWLINE, "}", "]" } at depth 0) | BalancedBraceSubstringAsText ;
MapScalar = ScalarText(terminators = { ",", NL, "}", "]" } at depth 0) ;
RawMapLine = (* any line that cannot be parsed as MapEntry key/value, or a line starting with "@" not followed by Ident *) MapRawText NL* ;

# LISTS
List = "[" NL* [ ListItems ] NL* "]" NL* ;
ListItems = ListItem { ListSep ListItem } [ ListSep ] ;
ListSep = ( "," NL* ) | ( NL+ ) ;
ListItem = Annotations? ListPayload ;
ListPayload = Method (* when list context == "methods" *)
            | FieldDecl (* when list context == "fields" *)
            | EndpointLine (* when list context == "endpoints" *)
            | ComponentBlock (* when list context == "components" and matches header *)
            | Map (* if next token is "{" *)
            | ScalarInList (* everything else, including bracketed groups "[...]" which are captured as scalar text *) ;
ScalarInList = ScalarText(terminators = { ",", NL, "]" } at depth 0) ;
FieldDecl = Visibility? Ident [ ":" ] FieldType ; 
Visibility = "+" | "-" | "#"; (* tokenized as IDENT via fallback *) 
FieldType = ScalarText(terminators = { ",", NL, "]" } at depth 0) ;

# FUNCTIONS/METHODS
Method = Visibility? Ident "(" MethodParamsText ")" NL* [ "->" ] NL* MethodReturnsText [ NL* MethodBody ] ; 
MethodBody = "{" NL* { NL* Attribute } NL* "}" ;
MethodParamsText = (* raw token capture inside matching parentheses, then compacted *) ParamsText ; 
MethodReturnsText = ScalarText(terminators = { "{", ",", "]", NL } at depth 0) ;

# ENDPOINTS
## HTTP ENDPOINTS
HttpEndpoint = HttpVerb HttpPathAndMaybeRequest [ NL* "->" NL* HttpResponseSig ] HttpAttrsOpt ;
HttpVerb = "GET" | "POST" | "PUT" | "PATCH" | "DELETE" | "HEAD" | "OPTIONS" ;
HttpPath = PathText ; (* token sequence compacted; may include "/todos/{id}" JSON/TEXT/FORM or "{" *)
HttpRequestSig = SignatureText ; (* token sequence compacted, often starts with JSON/TEXT/FORM or "{" *)
HttpResponseSig = SignatureText ;
HttpAttrsOpt = [ EndpointAttrs ] ;

## GRPC ENDPOINTS
GrpcEndpoint = GrpcNameOpt GrpcRequestOpt NL* [ "->" ] NL* GrpcResponseSig GrpcAttrsOpt ;
GrpcNameOpt = Ident? ;
GrpcRequestOpt = [ "(" SignatureTextInsideParens ")" ] ;
GrpcResponseSig = TupleResponse | SignatureText ;
TupleResponse = "(" SignatureTextInsideParens ")" ;
GrpcAttrsOpt = [ EndpointAttrs ] ;
EndpointAttrs = "[" AttrPair { "," AttrPair } "]" ;
AttrPair = AttrKey ":" AttrValue ; 
(* In the implementation, AttrKey and AttrValue are token sequences compacted by joining with spaces. There is no quoting/escaping rule here beyond the base tokenizer. *)
AttrKey = AttrText ; 
AttrValue = AttrText ;
```

## Signature sublanguage

This part is not required to parse the SiMAL file, but it is the formal grammar of the signature sublanguage that `simal_endpoint.py` implements to parse from endpoint request/response strings.

### Token set: 
- Ident in signatures is strictly [A-Za-z0-9_]+ (letters/digits/underscore; must be nonempty).
- AngleBalanced is a balanced < ... > substring (may contain nested < >).
- BracketBalanced is a balanced [ ... ] substring (may contain nested [ ]).

Normalization note: the signature parser compacts whitespace just inside < > and [ ] (e.g., map < int, Todo > -> map<int, Todo>), but otherwise treats the signature as plain text.
```
Signature = TupleSig | TypeExpr ;
TupleSig = "(" ParamList? ")" ;
ParamList = Param { ( "," | WS+ ) Param } ;
Param = Ident ":" TypeExpr | Ident WS+ Ident ; (* "uuid str" form; type is a simple Ident here *)
TypeExpr = TypeBase TypeSuffix* ObjectShape? OptionalMark? ;
TypeBase = Ident ;
TypeSuffix = AngleBalanced | BracketBalanced ;
ObjectShape = "{" ObjFieldList? "}" ;
ObjFieldList = ObjField { ( "," | WS+ ) ObjField } ;
ObjField = Ident ":" TypeExpr | Ident WS+ Ident OptionalMark? ; (* "uuid str?" form *)
OptionalMark = "?" ;
```
