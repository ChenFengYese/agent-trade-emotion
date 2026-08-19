# Direct AST v0.2.2 Slice A source/selectors — blocked review report

## Immutable inputs locked

- cwd: `/Users/wt/Documents/agent-trade-emotion`
- branch: `codex/s0-research-foundation`
- HEAD: `7ca3fc4f99a57f98217e703f222b295653ace87e`
- Direct AST Profile raw SHA-256: `36369fb04693d7c06d903c8c855ca3ea909d136680e6992c126f5f1c6488fb3e`
- Semantic source raw SHA-256: `43eedbee0a10cf0254721052c1aca23baf027a90f879739ec33b48180cfd87a6`

## Result

`BLOCKED_PROFILE_P0`. No `slice_a_sources_selectors.nodes.json` was created. Producing a fragment that merely has valid JSON/NodeEnvelope shapes would falsely claim executable enforcement of source decimal validity, conflict classification, and coverage closure.

## Requested node set intentionally not emitted

Schemas: `schema/Level.v0.2.2`, `schema/ClosedMarkBar.v0.2.2`, `schema/BookSnapshot.v0.2.2`, `schema/AggTrade.v0.2.2`, `schema/OpenInterest.v0.2.2`, `schema/OrderedSourceProjection.v0.2.2`, `schema/GenerationRange.v0.2.2`, `schema/CoverageGap.v0.2.2`, `schema/CoverageSeal.v0.2.2`, `schema/VenueInstrumentSnapshot.v0.2.2`, `schema/AccountRiskSnapshot.v0.2.2`.

Algorithms: `algorithm/ValidateDecimal.v0.2.2`, `algorithm/OrderedSourceProjection.v0.2.2`, `algorithm/SourceCollision.v0.2.2`, `algorithm/ValidateCoverageSeal.v0.2.2`, `algorithm/SelectCoverageSeal.v0.2.2`, `algorithm/SelectBook.v0.2.2`, `algorithm/SelectOpenInterest.v0.2.2`, `algorithm/SelectVenueSnapshot.v0.2.2`, `algorithm/SelectAccountSnapshot.v0.2.2`, `algorithm/SelectClosedMarkBarSlot.v0.2.2`, `algorithm/SelectAggTradeWindow.v0.2.2`, `algorithm/SelectBookGrid.v0.2.2`, `algorithm/ValidateOICompleteness.v0.2.2`.

## P0 grammar issues requiring Sol profile resolution

1. `algorithm/ValidateDecimal.v0.2.2` must mechanically enforce the semantic source's `QtyBase > 0`, `Price > 0`, `oi_base > 0`, bounded venue-rule decimals, and decimal lexical restrictions (semantic source lines 542, 567-590, 793-801). The Profile provides `DECIMAL` literal construction and decimal arithmetic but no expression that converts a wire `DecimalString` obtained by `GET` into a decimal value, and it simultaneously says aliases are recursively expanded with no string/decimal coercion (Profile lines 623-631, 683-729, 815-850). A `GET` of a wire decimal has no declared executable parse/validation transition. Emitting `ValidateDecimal` as `TYPE_VALID` alone would omit required strict lower/upper bounds.

   Minimal profile decision: either declare `T_REF type/DecimalString` and the unit aliases to preserve a decimal runtime value when read from a schema field, including lexical/range validation, or add a closed `PARSE_DECIMAL`/`DECIMAL_VALID` expression with exact return/failure semantics. Counterexample: `qty_base="0"` is syntactically a DecimalString and satisfies a nonnegative QtyBase but must be rejected in `AggTrade`/`BookSnapshot`; a `TYPE_VALID`-only node would accept it.

2. `algorithm/SourceCollision.v0.2.2` and `algorithm/ValidateCoverageSeal.v0.2.2` must evaluate a source-kind-dependent object projection and prove the exact source-object set, including sequence closure (semantic source lines 622-648 and 694-736). The Profile's `GET` only takes a statically resolved path (lines 628, 530-559) and its `ROUTING` union is restricted to three fixed nodes with paths for `DecisionResult`, `ArtifactPayload`, and `ReducerPayload` (lines 1021-1069). There is no generic typed narrowing/project operation for `ClosedMarkBar|BookSnapshot|AggTrade|OpenInterest` chosen by `covered_object_kind`, nor does inventory include a source-kind union payload router.

   Minimal profile decision: add one explicit source-object routing/projection authority with a closed source-kind discriminator and exact output schema, or state an allowed multi-homogeneous-array `MATCH` encoding and provide the required algorithm parameter/result shapes. Counterexample: two same-scope `BOOK_SNAPSHOT` records with the same `(generation, source_sequence)` and different `event_id` must be `CONFLICT`, while the corresponding `AGG_TRADE` uses a different generation field; treating either as `ANY_JSON`, concatenating them, or lexicographically selecting one violates semantic source lines 633-648.

3. The required selectors distinguish `UNKNOWN`, `CONFLICT`, `RULE_SNAPSHOT_CONFLICT`, and an admissible object (semantic source lines 894-985). The requested inventory contains no dedicated selector outcome schema and Profile has no declared selector result convention. A nullable selected object cannot distinguish `UNKNOWN` from `CONFLICT`; turning conflict into `EVAL_REJECT` changes the semantic outcome.

   Minimal profile decision: give each selector an exact closed result union (selected object plus the permitted ConstRef status values) or add an inventory schema for selector outcomes and prescribe its use. Counterexample: for `SelectBook`, zero eligible records and two incompatible records at the winning identity must not collapse to the same `null` result because downstream quality handling differs.

## Outbound references / missing cross-block closure

No nodes were emitted; therefore there are no fragment digest, key set, or NodeId outbound references to report. If Sol issues a corrected Profile, expected cross-block authority includes `type/*`, `const/LiteralRegistry.v0.2.2`, source identities, and later artifact/bundle nodes; no placeholder reference was written.

---

# Exhaustive expressibility audit against Profile `4971a337...aa48`

## Audit authority and disposition

This section supersedes the earlier audit against Profile
`36369fb0...b3e`. The current immutable inputs read for this audit are:

- Profile raw SHA-256:
  `4971a337605b7d3bbfdae3657a47498c2cfeb2d055f0e861339c57e02968aa48`
  (`2252` lines, `82244` bytes).
- Semantic source raw SHA-256:
  `43eedbee0a10cf0254721052c1aca23baf027a90f879739ec33b48180cfd87a6`.
- cwd / branch / HEAD remain
  `/Users/wt/Documents/agent-trade-emotion`,
  `codex/s0-research-foundation`,
  `7ca3fc4f99a57f98217e703f222b295653ace87e`.

Profile `4971...aa48` closes the prior decimal runtime, source-union narrowing,
and selector-result-union issues. It does **not** yet permit a truthful complete
serialization of this sub-slice. The result remains
`BLOCKED_PROFILE_P0`; no nodes fragment is present.

## Consolidated grammar gaps

### P0-G1 — no executable ConstRef/member predicate

Profile lines 636-639 make `CONST` retain the exact `T_CONST_REF` type and
forbid degradation to primitive STRING. Profile line 1071 permits `EQ/NE` only
for identical static types. `MATCH` is a statement and cannot appear inside a
SCHEMA constraint, `FILTER`, `FOR_ALL`, `EXISTS`, `IF` expression, or
`IMPLIES`.

Consequently an expression cannot ask any of the following required questions:

- `quality == VALID`;
- `covered_object_kind == OPEN_INTEREST`;
- `availability_kind == SYNTHETIC`;
- `source_schema_version == the query member`;
- `lane_id == E0_SYNTHETIC_CANONICAL_V0_2_2`.

This blocks quality-conditional venue/book structural constraints and the
predicate form of source/coverage selection. It is not repaired by the new
selector status unions: those unions can be consumed by statement-level
`MATCH`, but collection and schema predicates still need a BOOLEAN expression.

Counterexample: a `VenueInstrumentSnapshot` with `quality=INVALID` and negative
`max_leverage` must remain an INVALID data-health object, while a
`quality=VALID` object with the same value must fail structural validation.
Applying the range unconditionally rejects the first object; omitting it accepts
the second; neither is the frozen semantic rule.

Minimum common repair: one closed expression such as
`["CONST_EQ",Expr,ConstRef] -> BOOLEAN`, with exact static compatibility,
resolved-value comparison, and failure rules. It must support `T_ENUM`,
`T_CONST_REF`, primitive STRING, and the nominal fixed-string types explicitly
allowed by the profile; it must not introduce implicit general coercion.

### P0-G2 — no strict ordering over scalar or computed keys

Semantic source requires:

- `CoverageSeal.covered_event_ids` strictly ordered by the homogeneous source
  order;
- `AccountRiskSnapshot.open_order_ids` deduplicated and strictly ordered by
  UTF-8 bytes;
- book `bids` strictly descending and `asks` strictly ascending by **numeric**
  Price, with duplicate price forbidden.

Profile lines 665-668 require every `OrderSpec` key to be a nonempty static
path. Profile line 1099 restricts `SORT` to arrays of objects. There is no
scalar-array sort/check, index/range quantifier, adjacent-pair fold, or
computed-key order operation. A static path to `Level.price` returns nominal
wire `Price`; Profile lines 1033-1072 prohibit comparing that wire value
numerically without `DECIMAL_PARSE`, while an `OrderSpec` cannot contain such
an expression.

Counterexamples:

- `open_order_ids=["b","a"]` is unique and type-valid but must be rejected.
- bids at wire prices `"9"` then `"10"` are lexically descending but
  numerically ascending and must be rejected.
- two levels at the same price with different quantities are distinct objects,
  so object-level uniqueness alone does not enforce unique prices.

Minimum common repair: one computed-key predicate such as
`["STRICTLY_SORTED_BY",collection,item_var,key_expr,direction] -> BOOLEAN`.
The key expression must permit primitive STRING, INTEGER, UtcUs, Sha256,
StableId, and `DecimalValue<K>`; the latter permits
`DECIMAL_PARSE(PRICE, level.price)`. Semantics must define strictness,
left-to-right input order, null rejection, and deterministic failure. This one
operation covers scalar UTF-8 arrays and numeric book ladders without adding a
general range/index language.

The existing `T_ARRAY.order_spec` also needs one explicit type-validation rule:
whether it validates the presented array order or only documents the output of
`SORT`. If the new predicate is authoritative for schema order, the profile
must say `order_spec` does not silently provide a second ordering authority.

### P0-G3 — `Sha256` lexical validity is not serializable

Immutable atomic semantics require exactly 64 lower-case hexadecimal
characters. The current grammar has no regex, character-class, hexadecimal, or
string-character quantifier. `LEN(s)==64` would accept `"g"*64`, uppercase
hex, and punctuation. `StableId` inherits this defect because it is a Sha256
value with domain-separated provenance.

This transitively affects every source schema's `payload_sha256`, object ID,
coverage digest, rule fingerprint, and snapshot ID even when the schema-local
formula is otherwise expressible.

Counterexample: a 64-character string made entirely of `g` passes a
length-only type but is not a Sha256.

Minimum common repair: one closed
`["SHA256_VALID",wire_string_expr] -> BOOLEAN` expression, with exact
lower-hex/length semantics and primitive-STRING input. Then
`type/Sha256` can be a constrained STRING and `type/StableId` can reference
that nominal type. A general regex engine is not required.

### P0-A1 — algorithm interfaces remain theory-authority choices

The Profile freezes the exact `ValidateDecimal` body and eight selector return
types, but does not freeze the parameter, local, precondition, statement, or
postcondition shapes for the other twelve requested algorithms. In particular:

- `SelectCoverageSeal` needs artifact identity to distinguish two different
  artifact IDs from repeated identical bytes; a bare `CoverageSeal` has only
  `seal_sha256`.
- `SelectAggTradeWindow` receives an explicit `seal_id` and therefore also
  needs an exact artifact-wrapper or exact ID-to-seal input convention.
- `ValidateCoverageSeal` needs the exact full heterogeneous source collection
  and its homogeneous query/scope contract.
- `ValidateOICompleteness` has semantic `UNKNOWN` behavior but no frozen exact
  return type.
- `SourceCollision` has no frozen convention for whether `true` means
  collision-free or collision-present.

All are expressible after G1-G3, but multiple incompatible AST interfaces would
satisfy the prose. Under the user-mandated theory-first role split these are Sol
theory decisions, not safe Terra implementation defaults.

Minimum repair: freeze one exact interface table for all thirteen requested
algorithms: parameters, returns, required locals, preconditions, and the status
polarity/meaning. `SelectCoverageSeal` and `SelectAggTradeWindow` should name
the exact closed-inventory artifact wrapper/ID binding rather than use aligned
parallel arrays.

## Per-node expressibility matrix

`PASS*` means the node's local semantics can be expressed after the three
shared grammar repairs; it is not a node review or global closure result.

| Node | Result | Exact reason |
|---|---|---|
| `type/MarketSourceObject` | PASS now | Profile §8.8 freezes its exact four-variant union and exhaustive `MATCH_NARROW` behavior. |
| `schema/Level` | BLOCKED G2/G3 | Positive quantity is now expressible with decimal parse; strict numeric use in book arrays is not. All digest-bearing consumers remain blocked by Sha256 type. |
| `schema/ClosedMarkBar` | PASS* | Period enum, grid modulo, safe timestamp arithmetic, nonempty strings, payload hash, and identity equality are composable; transitive Sha256 validity needs G3. |
| `schema/BookSnapshot` | BLOCKED G1/G2/G3 | Best-price/crossed-book and quantity checks are decimal-expressible, but quality gating and strict numeric bid/ask ordering are not. |
| `schema/AggTrade` | PASS* | Exact keys, positive decimals, causality time, payload hash and identity are composable; G3 remains transitive. |
| `schema/OpenInterest` | PASS* | Same as AggTrade; G3 remains transitive. |
| `schema/OrderedSourceProjection` | PASS* | Named-object construction and exact accessors are fully determined by §8.8; object-kind predicate consumers need G1. |
| `schema/GenerationRange` | PASS now | Positive count and `count=last-first+1` are integer expressions; it is an object sortable by generation ID. |
| `schema/CoverageGap` | PASS now | Bounds and reason enum are representable. Pairwise non-overlap can use nested `FOR_ALL`; no adjacency opcode is required. |
| `schema/CoverageSeal` | BLOCKED G2/G3 | Exact fields, range objects, hashes, counts and window bounds are expressible; scalar covered-ID order is not. Source-dependent completeness properly belongs to `ValidateCoverageSeal`. |
| `schema/VenueInstrumentSnapshot` | BLOCKED G1/G3 | Nominal decimal parsing and range formulas are fixed; `quality=VALID -> ranges` needs G1. Baseline fingerprint is derivable from frozen fields plus the identity formula, but Sha lexical validity needs G3. |
| `schema/AccountRiskSnapshot` | BLOCKED G2/G3 | Balance/reserve/position-null iff rules are expressible; scalar `open_order_ids` order is not. |
| `algorithm/ValidateDecimal` | PASS now | Exact body is frozen in Profile §6.3. |
| `algorithm/OrderedSourceProjection` | PASS now | Exhaustive union narrowing and four accessors are frozen in Profile §8.8. |
| `algorithm/SourceCollision` | PASS* / A1 | Projection plus nested pairwise quantification can detect same key/different ID or payload; exact interface and Boolean polarity need A1. |
| `algorithm/ValidateCoverageSeal` | PASS* / A1 | Projection, FILTER/MAP, SET_EQ, UNIQUE, ARGMIN/ARGMAX and count arithmetic can prove exact set and per-generation integer closure; enum predicates need G1 and interface needs A1. |
| `algorithm/SelectCoverageSeal` | PASS* / A1 | Zero/one/multiple status union is frozen; exact artifact-ID carrier is not. |
| `algorithm/SelectBook` | PASS* / A1 | A total object order encodes max economic time then min lane/sequence/ID. Pairwise collision checks preserve CONFLICT. Query/quality predicates need G1. |
| `algorithm/SelectOpenInterest` | PASS* / A1 | Same reasoning as SelectBook without contiguity. |
| `algorithm/SelectVenueSnapshot` | PASS* / A1 | Sort/filter by effective time, unique fingerprints, and min snapshot ID are composable; quality predicate needs G1. |
| `algorithm/SelectAccountSnapshot` | PASS* / A1 | Effective-time winner, payload conflict and min snapshot ID are composable; query/quality predicates need G1. |
| `algorithm/SelectClosedMarkBarSlot` | PASS* / A1 | Exact slot filter, canonical duplicate elimination and payload conflict are composable; query/quality predicates need G1. |
| `algorithm/SelectAggTradeWindow` | PASS* / A1 | Validated seal IDs can filter and source-order the exact trade array without nullable unwrap; exact artifact binding needs A1. |
| `algorithm/SelectBookGrid` | PASS* / A1 | It can return the exact result of `SelectBook(query,g_us,1_000_000)`; interface still needs freezing. |
| `algorithm/ValidateOICompleteness` | PASS* / A1 | Safe timestamp subtraction, exact seal checks, two selector calls, union `MATCH_NARROW`, membership and scope equality are composable; exact success/UNKNOWN return contract is not frozen. |

## Requested special-case conclusions

- Scalar ordering / strictness: **blocked by G2**.
- Adjacent-pair checks: no independent opcode is needed for gap non-overlap;
  nested all-pairs implication is sufficient. Numeric array order still needs
  G2 because item position is otherwise unavailable.
- Set equality: `SET_EQ`, `UNIQUE`, `MAP` and `FILTER` are sufficient.
- Map key order: no Slice A source object needs a dynamic map; RFC 8785 and
  `T_MAP` cover later map-shaped inputs.
- Optional/null: `T_NULLABLE`, `IS_NULL` and `IS_NOT_NULL` are sufficient.
- String/nonempty: `LEN(s)>0` is sufficient for IDs that only require
  nonempty text; Sha256 needs G3.
- Timestamp arithmetic: `SUB`, `ADD`, `MUL`, `MOD`, `FLOOR_DIV` and ordered
  left-to-right guards are sufficient. Underflow can fail closed.
- Argmin/tie-break: complete `OrderSpec` keys plus prior collision and
  canonical-duplicate checks are sufficient for all selector object winners.
- Collision statuses: Profile §8.8 now keeps generic, coverage, rule-snapshot,
  and account-snapshot conflicts distinct; exact producer interfaces need A1.
- Generation closure: per-range FILTER, UNIQUE, COUNT, ARGMIN/ARGMAX and
  `last-first+1`, plus SET_EQ of generation sets, are sufficient; GROUP_BY or
  RANGE opcodes are not required.

## Minimal common repair count and remaining unknown surface

The minimum grammar repair is **three closed expression opcodes plus one
ordering type-rule clarification**:

1. `CONST_EQ`;
2. `STRICTLY_SORTED_BY`;
3. `SHA256_VALID`;
4. explicit `T_ARRAY.order_spec` validation-authority semantics.

The minimum theory repair is **one exact 13-algorithm interface table**. No
additional RANGE, GROUP_BY, scalar SORT, nullable unwrap, general regex,
adjacent-pair, or map-order opcode is currently justified.

After those repairs, the known Slice A source/selectors constraint surface is
expressible. The remaining unknown surface is limited to integration facts
that cannot be closed locally: exact cross-slice artifact-wrapper fields,
source identity parameter signatures, sole LiteralRegistry membership, and
whole-AST reverse reachability. Those must be checked during slice
consolidation and global closure; they are not permission to emit placeholders.
