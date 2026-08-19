# RSI-MTF-DRL-PM Direct Machine AST Profile v0.2.2

> 状态：`REVIEW_CANDIDATE / E0 / NOT_AUTHORITY`  
> 阶段：`P0-RSI-01B-DIRECT-AST-PROFILE`  
> 日期：2026-07-23  
> 范围：只定义 direct machine AST 的表示、节点清单与验收；不授权 contract implementation、数据、fixture、回测、paper、OMS 或交易

---

## 0. 路线决定

本 profile 废弃以下 C21 修复路线：

```text
v0.2.1 prose
  -> invented base ContractAST
  -> nine TransformSet
  -> direct-node overlay
  -> merge
```

原因是 immutable v0.2.1 从未冻结 AST dialect、node bytes 或 old-node
digest。把新的人工转录称为旧 base authority 会制造三套互相竞争的规范来源。

唯一允许的新路线是：

```text
immutable source authority
  -> one complete v0.2.2 direct machine AST
  -> one node digest index
  -> one reference closure
  -> one final AST digest
```

v0.2.1 只提供 semantic provenance，不提供 inherited AST bytes。九个原
successor 与所有直接节点必须在同一 v0.2.2 AST 中完整物化；不得使用
ADD/REMOVE/REPLACE patch、overlay、wildcard inheritance、`unchanged`、
section pointer、ellipsis 或未冻结默认值。

---

## 1. 单向 authority graph

### 1.1 Immutable source authority

direct AST 必须绑定：

```text
source_contract_id =
  "rsi-mtf-drl-pm-v0-2-1-outcome-free-contract"

source_contract_sha256 =
  1db68758cae0e4b79e3206221498071ced9f7720b8d8e2fa95a1bb53995a45a7
```

后者必须按 immutable v0.2.1 公式重算：

```text
ID("rsi-mtf-drl-pm-composite-theory/v0.2.1", {
  core_raw_sha256:
    "06014b2f9e2665abef55e816616661951b35cb766ab9a49aadfad6841d7f822d",
  v0_2_contract_canonical_sha256:
    "38d572453045016bbdc314d184f9be87a608ec8bc36aabaf92d8c0ce742201e5",
  addendum_raw_sha256:
    "021053480fe9a49b3902803e2d363793416a120263551fb741fb3444af6550fd"
})
```

同时逐 byte验证：

```text
CORE_TRADING_THEORY.md raw SHA =
  06014b2f9e2665abef55e816616661951b35cb766ab9a49aadfad6841d7f822d
CORE_TRADING_THEORY.md size_bytes = 110738

config/rsi_mtf_drl_pm.research_contract.v0_2.json raw SHA =
  33d84ce8fdfa7766fbce340beac9916344655c002e39ed6c8db29cefaaa6b047
config/rsi_mtf_drl_pm.research_contract.v0_2.json size_bytes = 23206

RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_1.md raw SHA =
  021053480fe9a49b3902803e2d363793416a120263551fb741fb3444af6550fd
RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_1.md size_bytes = 197800
```

### 1.2 Frozen semantic source

direct AST 的新 v0.2.2 semantic body只允许来自以下 immutable
pre-profile candidate bytes与本 profile：

```text
semantic_source_id =
  "RSI_MTF_DRL_PM_THEORY_ADDENDUM.v0.2.2-pre-profile"

semantic_source_path =
  "RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_2.md"

semantic_source_size_bytes = 136468

semantic_source_raw_sha256 =
  "43eedbee0a10cf0254721052c1aca23baf027a90f879739ec33b48180cfd87a6"
```

该 semantic source 提供 §0–§12.8、§12.10–§14 的 v0.2.2 语义；其中旧
§12.9 transform route 被本 profile §0 的 full-direct 决定完整替换，不得进入
AST node。换言之，direct AST authority source 是：

```text
immutable v0.2.1 source triple
+ exact pre-profile v0.2.2 semantic bytes
+ exact profile bytes
```

而不是未绑定的 moving Markdown。任一 source size/hash不等必须停止。

该 path 从本 profile 起永久保留为上述 43eed/136468 semantic source，不再承担
“最终理论文档”角色；任何流程不得覆盖、追加或格式化它。未来用户可读 final
theory 的唯一独立 path 是：

```text
final_release_theory_path =
  "RSI_MTF_DRL_PM_FINAL_THEORY_v0_2_2.md"
```

final release可以解释并 pin semantic source/profile/AST/receipt，但不能替换
semantic source bytes；因此 receipt按 `semantic_source_path` 永远可以重验。

### 1.3 Cycle-free direction

authority 只能沿下列方向：

```text
immutable source triple
  -> pre-profile semantic source raw SHA
  -> this profile raw SHA
  -> direct AST raw SHA + ast_sha256
  -> direct AST review receipt SHA
  -> final release theory raw SHA at final_release_theory_path
  -> future v0.2.2 serialized contract digest
  -> future implementation manifest digest
```

禁止反向引用：

- profile 不引用 direct AST digest；
- direct AST 必须引用 §1.2 pre-profile semantic source raw SHA，但不引用
  final release theory raw SHA、future contract digest或 implementation
  digest；
- final release theory必须位于独立 `final_release_theory_path`，并 pin
  semantic source raw SHA、profile raw SHA、direct AST path、exact byte
  size、raw SHA、`ast_sha256` 与 review receipt SHA；
- future contract 同时绑定 final release theory raw SHA 与 direct AST
  raw/AST/review-receipt SHA；
- receipt 不回写被 hash 的 artifact。

target literal 唯一为：

```text
target_contract_id =
  "RSI_MTF_DRL_PM_CONTRACT.v0.2.2"
```

### 1.4 Direct replacement for frozen semantic source §12.1 and §12.10

冻结 semantic source 中所有 `SchemaTransformReceipt`、
`schema_transform_receipt_sha256` 与 `AST_PATCH` authority均被本节整体替换。
它们只保留 provenance，不得进入 AST、contract、manifest、receipt或
serializer。下列 direct forms是唯一 successor。

#### 1.4.1 Shared direct authority fields

serialized contract、ContractDigestReceipt、ImplementationManifest 与
ImplementationManifestReceipt 都必须直接携带下列 exact six fields：

```text
semantic_source_raw_sha256
profile_raw_sha256
direct_ast_raw_sha256
direct_ast_sha256
direct_ast_review_receipt_sha256
final_release_theory_raw_sha256
```

全部 type为 Sha256，且逐项满足：

```text
semantic_source_raw_sha256 =
  §1.2 semantic_source_raw_sha256

profile_raw_sha256 =
  SHA256(exact immutable profile bytes)
  = DirectMachineAST.profile_raw_sha256

direct_ast_raw_sha256 =
  SHA256(exact DirectMachineAST file bytes)
  = DirectASTReviewReceipt.direct_ast_raw_sha256

direct_ast_sha256 =
  DirectMachineAST.ast_sha256
  = DirectASTReviewReceipt.direct_ast_sha256

direct_ast_review_receipt_sha256 =
  DirectASTReviewReceipt.receipt_sha256

final_release_theory_raw_sha256 =
  SHA256(exact final_release_theory_path bytes)
```

serialized contract root必须包含这 six fields，且其余 semantic body只能由
同一 direct AST生成；不得读取 transform op、patch、section pointer或
semantic source作为 runtime fallback。

#### 1.4.2 ContractDigestReceipt direct form

`ContractDigestReceipt.v0.2.2` exact keys：

```text
schema_version
contract_id
contract_relative_path
contract_size_bytes
contract_sha256
serializer_id
semantic_source_raw_sha256
profile_raw_sha256
direct_ast_raw_sha256
direct_ast_sha256
direct_ast_review_receipt_sha256
final_release_theory_raw_sha256
status
receipt_sha256
```

Exact literals/formulas：

```text
schema_version =
  "rsi-mtf-drl-pm.contract-digest-receipt.v0.2.2"
contract_id =
  "RSI_MTF_DRL_PM_CONTRACT.v0.2.2"
serializer_id =
  "RFC8785_CANONICAL_JSON_UTF8_DIRECT_AST_V1"
status = "PASS"

contract_size_bytes =
  byte length of exact immutable serialized contract

contract_sha256 =
  SHA256(exact immutable serialized contract bytes)

receipt_sha256 =
  ID("contract-digest-receipt/v0.2.2",
     entire receipt excluding receipt_sha256)
```

external verifier必须重读 `contract_relative_path`，验证 size/hash、six direct
authority fields与 contract root exact equality，并验证
`direct_ast_review_receipt_sha256` 唯一解析为 §13 对同一 AST bytes的 PASS
receipt。contract digest不等于 AST digest，二者通过 six fields显式绑定；
不存在 `result_contract_sha256` alias。

#### 1.4.3 ImplementationManifest direct form

`ImplementationManifest.v0.2.2` exact keys：

```text
schema_version
manifest_kind
contract_id
contract_sha256
composite_theory_id
contract_digest_receipt_sha256
semantic_source_raw_sha256
profile_raw_sha256
direct_ast_raw_sha256
direct_ast_sha256
direct_ast_review_receipt_sha256
final_release_theory_raw_sha256
runtime
source_roots
test_roots
entrypoints
files
file_set_sha256
capabilities
implementation_id
manifest_sha256
```

冻结 semantic source §12.10 对 runtime/source roots/test roots/entrypoints/files/
capabilities 的 exact约束继续有效；只删除 transform字段并加入上述 direct
fields。Identity formulas替换为：

```text
implementation_id =
  ID("implementation-identity/v0.2.2", {
    contract_sha256,
    composite_theory_id,
    contract_digest_receipt_sha256,
    semantic_source_raw_sha256,
    profile_raw_sha256,
    direct_ast_raw_sha256,
    direct_ast_sha256,
    direct_ast_review_receipt_sha256,
    final_release_theory_raw_sha256,
    runtime,
    entrypoints,
    file_set_sha256
  })

manifest_sha256 =
  ID("implementation-manifest/v0.2.2",
     entire manifest excluding manifest_sha256)
```

`contract_sha256` 与 six direct fields必须逐项等于同一 PASS
ContractDigestReceipt；`contract_digest_receipt_sha256` 等于该 receipt 的
receipt_sha256。`composite_theory_id` 仍按 frozen semantic source §0.1重算。

#### 1.4.4 ImplementationManifestReceipt direct form

`ImplementationManifestReceipt.v0.2.2` exact keys：

```text
schema_version
manifest_sha256
observed_file_set_sha256
contract_sha256
contract_digest_receipt_sha256
semantic_source_raw_sha256
profile_raw_sha256
direct_ast_raw_sha256
direct_ast_sha256
direct_ast_review_receipt_sha256
final_release_theory_raw_sha256
entrypoint_resolution_sha256
capability_scan_sha256
status
receipt_sha256
```

冻结 semantic source §12.10 的 file enumeration、entrypoint resolution、
capability scan与 receipt hash公式继续有效。新增 direct fields必须逐项等于
ImplementationManifest 与 ContractDigestReceipt；`manifest_sha256`、
`contract_sha256`、`contract_digest_receipt_sha256` 也必须逐项相等。任何一项
不等都不得写 PASS。

#### 1.4.5 Only valid build sequence and replaced clauses

P0-RSI-01C/P0-RSI-02 唯一顺序：

```text
1. freeze this profile bytes
2. materialize and externally PASS-review one immutable direct AST
3. write final_release_theory_path and pin source/profile/AST/review receipt
4. serialize contract from direct AST with six direct authority fields
5. compute contract bytes/hash and write PASS ContractDigestReceipt
6. build and verify ImplementationManifest/ImplementationManifestReceipt
7. runtime ledger/label bind the same PASS DirectASTReviewReceipt,
   ContractDigestReceipt and ImplementationManifestReceipt
```

receipt 不回写其 hash target。semantic source中下列 exact line byte ranges不得
标成 ENCODED/CONTEXT_ONLY；Clause disposition必须为 REPLACED，且
target set至少包含右列 exact nodes：

| semantic-source byte range | required target nodes |
|---|---|
| `[84210,84258)`, `[84258,84300)`, `[84300,84368)`, `[84368,84428)`, `[84428,84508)` | `schema/ContractDigestReceipt.v0.2.2`, `schema/DirectASTReviewReceipt.v0.2.2`, `schema/ImplementationManifestReceipt.v0.2.2` |
| `[115635,115681)`, `[116079,116131)` | `identity/DirectASTReviewReceipt.v0.2.2`, `schema/DirectASTReviewReceipt.v0.2.2` |
| `[117222,117276)`, `[117403,117469)`, `[117718,117796)` | `algorithm/ValidateContractDigestReceipt.v0.2.2`, `identity/ContractDigestReceipt.v0.2.2`, `schema/ContractDigestReceipt.v0.2.2` |
| `[118376,118440)`, `[120796,120851)` | `algorithm/ValidateImplementationManifest.v0.2.2`, `identity/ImplementationManifest.v0.2.2`, `schema/ImplementationManifest.v0.2.2` |
| `[121117,121181)` | `algorithm/ValidateImplementationManifestReceipt.v0.2.2`, `identity/ImplementationManifestReceipt.v0.2.2`, `schema/ImplementationManifestReceipt.v0.2.2` |

---

## 2. Canonical file 与原子类型

direct AST 文件唯一目标路径：

```text
config/rsi_mtf_drl_pm.direct_machine_ast.v0_2_2.json
```

文件 bytes 必须：

- UTF-8，无 BOM；
- 严格 RFC 8785 JSON Canonicalization Scheme；
- AST 中所有 object key、NodeId、field name、symbol 与 wire string literal
  必须是 ASCII；因此 RFC 8785 的 UTF-16 property sort 与 ASCII byte sort
  结果一致；
- 无空白与 trailing newline；
- AST 内 JSON integer 必须在
  `[-9007199254740991,9007199254740991]`，使用最短十进制；
- 禁止 JSON float；
- arrays 保留规范顺序；
- string content同样只允许 ASCII，不发生 Unicode normalization。

继承 immutable v0.2.1 的：

```text
UtcUs,DecimalString,QtyBase,Price,Money,Bps,Sha256,StableId,Bytes,
decimal128=34 digits,ROUND_HALF_EVEN,
ID(d,x)=SHA256(UTF8(d)||0x00||CanonicalJSON(x))
```

五种 decimal wire types都编码为 JSON STRING，而不是 JSON number或 evaluator
decimal value：

```text
DecimalKind enum{DECIMAL,QTY_BASE,PRICE,MONEY,BPS}

DECIMAL  <-> type/DecimalString
QTY_BASE <-> type/QtyBase
PRICE    <-> type/Price
MONEY    <-> type/Money
BPS      <-> type/Bps
```

所有 wire decimal首先必须匹配 immutable v0.2.1 lexical rule：

```text
^-?(0|[1-9][0-9]*)(\.[0-9]*[1-9])?$
```

并额外拒绝 `-0`、JSON number、`+`、指数、前导零、fraction尾随零、NaN、
Infinity与任何 whitespace。严格“可精确解析”算法为：

1. 从 regex groups构造 arbitrary-precision signed coefficient/scale；对非零
   coefficient移除十进制尾零并等值调整 scale；
2. 转成 IEEE 754 decimal128（precision=34、ROUND_HALF_EVEN）；
3. 若转换产生 InvalidOperation、Inexact、Rounded、Overflow、Underflow或
   Clamped flag，拒绝；
4. 用 fixed-point canonical formatter输出，若不逐 byte等于输入 string，拒绝。

range由 DecimalKind唯一决定：

```text
DECIMAL  = any finite exactly representable value
QTY_BASE = value >= 0
PRICE    = value > 0
MONEY    = value >= 0
BPS      = value >= 0
```

这五个 TYPE 是 nominal wire-string types；`T_REF` 在 assignability和 numeric
type checking时不得把它们展开成普通 STRING。evaluator中的
`DecimalValue<K>` 是非 JSON、带 DecimalKind 的 decimal128 value，只有
§5 `T_DECIMAL_VALUE` 与 §6 decimal opcodes可产生或消费。wire value与
DecimalValue之间没有隐式 coercion。

`Bytes` 是 evaluator内部不可变 byte sequence，不是 JSON string/base64/array；
`type/Bytes` 只允许 ALGORITHM local/return与
`CANONICAL_JSON -> SHA256` expression flow，禁止作为 SCHEMA property、
IDENTITY parameter/preimage value、ConstMember或 wire artifact字段。

`NodeId` 是 ASCII string，必须匹配：

```text
^(type|schema|const|algorithm|identity|routing)/[A-Za-z][A-Za-z0-9_.-]*$
```

所有 NodeId、requires、root exports 与 node digest index key 按 UTF-8
bytes严格升序且无重复。

---

## 3. Direct AST exact top schema

`DirectMachineAST.v0.2.2` exact keys：

```text
ast_schema_version
status
target_contract_id
source_authority
profile_raw_sha256
nodes
node_digest_index
root_exports
ast_sha256
```

Exact literals/types：

```text
ast_schema_version =
  "rsi-mtf-drl-pm.direct-machine-ast.v0.2.2"

status =
  "IMMUTABLE_REVIEW_BYTES"

source_authority exact keys =
  source_contract_id,source_contract_sha256,
  core_raw_sha256,v0_2_contract_raw_sha256,
  v0_2_contract_canonical_sha256,v0_2_1_addendum_raw_sha256,
  semantic_source_id,semantic_source_path,
  semantic_source_size_bytes,semantic_source_raw_sha256

profile_raw_sha256:Sha256
nodes:object<NodeId,NodeEnvelope>
node_digest_index:object<NodeId,Sha256>
root_exports:array<NodeId>
ast_sha256:Sha256
```

`source_authority` 前六项必须逐字等于 §1.1，后四项必须逐字等于 §1.2。
`nodes` 与 `node_digest_index` key set必须完全相等。AST 只生成一次上述
status 的 immutable bytes；`PASS` 是 profile 外部
`DirectASTReviewReceipt.v0.2.2` 对 exact raw/AST SHA 的结论，不得通过改
AST status 表示。

---

## 4. Node envelope

每个 `NodeEnvelope.v0.2.2` exact keys：

```text
node_version,node_id,node_kind,requires,body
```

```text
node_version = "rsi-mtf-drl-pm.direct-node.v0.2.2"
node_id = enclosing nodes map key
node_kind enum{TYPE,SCHEMA,CONST,ALGORITHM,IDENTITY,ROUTING}
requires:array<NodeId>
body = exact union selected by node_kind
```

NodeId prefix与 `node_kind` 必须 exact equality：

```text
type/      -> TYPE
schema/    -> SCHEMA
const/     -> CONST
algorithm/ -> ALGORITHM
identity/  -> IDENTITY
routing/   -> ROUTING
```

任何 prefix/body-kind错配在读取 body前即 `AST_REJECT`。

`requires` 必须恰好等于 `body` 在 §8.7 NodeId-bearing slots内出现的全部
NodeId references 的 set，去重并按 UTF-8 bytes升序。多一项、少一项、把
reference塞入普通 string或悬空 reference都拒绝；普通 STRING ConstMember
若 value匹配 NodeId regex也必须拒绝，以免制造双重解释。

禁止在任何 node body 出现以下 keys或 sentinel values：

```text
description
comment
section
line
source_pointer
unchanged
inherit
default
TODO
TBD
ellipsis
```

NodeId、field name、variable name、identity domain、grammar opcode 与 grammar
keyword 是专用语法槽位，不是 wire literal。除此以外，enum value、reason
code、policy ID、error code、schema-version value 与其他固定 wire string
只能作为 §5 的 `ConstRef` 存在于
`const/LiteralRegistry.v0.2.2`；任何 node 不得内联任意字符串作为可执行
语义或约束。

---

## 5. Type expression closed grammar

### 5.1 Names, paths and constant references

所有 name 都是 ASCII。Exact lexical forms：

```text
field_name    = ^[A-Za-z_][A-Za-z0-9_]*$
variable_name = ^[A-Za-z_][A-Za-z0-9_]*$
const_symbol  = ^[A-Z][A-Z0-9_]*$
```

`PathToken` exact union：

```text
["FIELD",field_name]
["INDEX",nonnegative_safe_integer]
```

`StaticPath = array<PathToken>`。`GET` 可以使用空 path 表示整个 root；
`SET` 与 ROUTING discriminator 必须使用非空 path。path 必须按静态
TypeExpr逐段解析，禁止 missing-key fallback、negative index、dynamic field
name或 JSON Pointer string。

`ConstRef` exact shape：

```text
["CONST_REF","const/LiteralRegistry.v0.2.2",const_symbol]
```

它必须解析到 registry 中唯一 member。禁止引用其他 CONST node、缺失 member
或把 member value直接复制进使用位置。

### 5.2 TypeExpr

`TypeExpr` 是 JSON array；第 0 项必须是下列 opcode之一。

| opcode | exact array shape |
|---|---|
| `T_REF` | `["T_REF",NodeId]` |
| `T_PRIMITIVE` | `["T_PRIMITIVE",enum{STRING,INTEGER,BOOLEAN,NULL,ANY_JSON,BYTES}]` |
| `T_DECIMAL_VALUE` | `["T_DECIMAL_VALUE",DecimalKind]` |
| `T_CONST_REF` | `["T_CONST_REF",ConstRef]` |
| `T_ENUM` | `["T_ENUM",array<ConstRef>]` |
| `T_ARRAY` | `["T_ARRAY",item_type,min_items,max_items_or_null,unique_boolean,order_spec_or_null]` |
| `T_MAP` | `["T_MAP",key_type,value_type,min_keys,max_keys_or_null,key_order]` |
| `T_OBJECT` | `["T_OBJECT",schema_NodeId]` |
| `T_UNION` | `["T_UNION",array<TypeExpr>]` |
| `T_NULLABLE` | `["T_NULLABLE",TypeExpr]` |
| `T_CONSTRAINED` | `["T_CONSTRAINED",TypeExpr,array<Expr>]` |

规则：

- `T_REF` 只能引用 TYPE；`T_OBJECT` 只能引用 SCHEMA；
- `T_DECIMAL_VALUE` 是 evaluator-only non-JSON type，只允许出现在 ALGORITHM
  parameters/returns/locals（包括这些位置的 array/map nesting）；禁止出现在
  SCHEMA、CONST、IDENTITY、ROUTING或 wire artifact；
- `["T_PRIMITIVE","BYTES"]` 只允许作为
  `type/Bytes.body.type_expr`；其他 node必须用
  `["T_REF","type/Bytes"]`，并继续受 §2 wire-use restriction约束；
- `T_CONST_REF/T_ENUM` 的每个 member必须通过 registry member type，且
  `T_ENUM` 至少一项、全部 member type相同、wire values互异，按 resolved
  value的 RFC 8785 bytes升序；
- `["CONST",r]` 的最具体 static type是 `["T_CONST_REF",r]`；
  `T_CONST_REF(r)` 只可赋给自身、包含 exact `r` 的 T_ENUM，或包含该
  T_CONST_REF/T_ENUM variant的 T_UNION；禁止反向赋值、按 resolved value把
  另一个 symbol视为同一 member、或退化成 primitive STRING；
- `T_UNION` 至少两个互异 variants，按其 CanonicalJSON bytes升序；runtime
  value必须通过且只通过一个 variant，0个或多个匹配均 EVAL_REJECT；
- 对 static `T_UNION` 的 GET只允许每个 variant都存在且 resolved TypeExpr
  canonical bytes完全相同的 common path；任何 variant-specific path必须先经
  §7 `MATCH_NARROW`，禁止 first-match、duck typing或 unchecked field access；
- nullable 只允许 `T_NULLABLE`，禁止把 NULL偷偷加入 enum；
- nested exact object 必须用独立 SCHEMA node，不得 inline object；
- `T_CONSTRAINED` 的 base type先完整验证；constraints至少一项、全部静态返回
  BOOLEAN并按 array order求值，全部 true才匹配该 type，false表示 validation
  miss，evaluation failure为 EVAL_REJECT；
- `ANY_JSON` 只允许 conflict proof 的 frozen original/incoming payload，
  且必须另有 ROUTING node按 event kind验证；其他位置禁止；
- `T_MAP key_type` 必须解析为 STRING、Sha256、StableId、T_CONST_REF或
  T_ENUM；JSON object key按该 type的 canonical string lexical form验证，
  禁止自由 regex；
- `order_spec` 必须是 `null` 或 `OrderSpec`；
- map key order唯一为 `"UTF8_BYTES_ASC"`。

`OrderSpec` exact keys：

```text
keys,directions,nulls
```

```text
keys:array<nonempty StaticPath>
directions:array<enum{ASC,DESC}>
nulls:array<enum{FIRST,LAST,FORBIDDEN}>
```

三个 arrays长度相等且非空。`ASC/DESC/FIRST/LAST/FORBIDDEN` 与
`UTF8_BYTES_ASC` 是封闭 grammar keyword，不是 wire value。

### 5.3 Exact nominal decimal TYPE bodies

`const/LiteralRegistry.v0.2.2` 必须包含下列五个 exact STRING members；
symbol、member type与 resolved value任一不同均 `AST_REJECT`：

```text
DECIMAL_KIND_BPS      -> {type:"STRING",value:"BPS"}
DECIMAL_KIND_DECIMAL  -> {type:"STRING",value:"DECIMAL"}
DECIMAL_KIND_MONEY    -> {type:"STRING",value:"MONEY"}
DECIMAL_KIND_PRICE    -> {type:"STRING",value:"PRICE"}
DECIMAL_KIND_QTY_BASE -> {type:"STRING",value:"QTY_BASE"}
```

五个 TYPE node 的 `body.type_expr` 必须分别逐字等于：

```json
["T_CONSTRAINED",["T_PRIMITIVE","STRING"],[["CALL","algorithm/ValidateDecimal.v0.2.2",{"kind":["CONST",["CONST_REF","const/LiteralRegistry.v0.2.2","DECIMAL_KIND_DECIMAL"]],"value":["GET","$self",[]]}]]]
```

上式只用于 `type/DecimalString`。其余四个 exact bodies依次为：

`type/QtyBase`：

```json
["T_CONSTRAINED",["T_PRIMITIVE","STRING"],[["CALL","algorithm/ValidateDecimal.v0.2.2",{"kind":["CONST",["CONST_REF","const/LiteralRegistry.v0.2.2","DECIMAL_KIND_QTY_BASE"]],"value":["GET","$self",[]]}]]]
```

`type/Price`：

```json
["T_CONSTRAINED",["T_PRIMITIVE","STRING"],[["CALL","algorithm/ValidateDecimal.v0.2.2",{"kind":["CONST",["CONST_REF","const/LiteralRegistry.v0.2.2","DECIMAL_KIND_PRICE"]],"value":["GET","$self",[]]}]]]
```

`type/Money`：

```json
["T_CONSTRAINED",["T_PRIMITIVE","STRING"],[["CALL","algorithm/ValidateDecimal.v0.2.2",{"kind":["CONST",["CONST_REF","const/LiteralRegistry.v0.2.2","DECIMAL_KIND_MONEY"]],"value":["GET","$self",[]]}]]]
```

`type/Bps`：

```json
["T_CONSTRAINED",["T_PRIMITIVE","STRING"],[["CALL","algorithm/ValidateDecimal.v0.2.2",{"kind":["CONST",["CONST_REF","const/LiteralRegistry.v0.2.2","DECIMAL_KIND_BPS"]],"value":["GET","$self",[]]}]]]
```

TYPE `T_CONSTRAINED` expressions的唯一 root是 `$self`，其 static type为被约束
base type。上述五段依次只属于
`type/DecimalString`、`type/QtyBase`、`type/Price`、`type/Money`、
`type/Bps`，不是可替换的 prose pattern。上述五个 T_REF保留 nominal
DecimalKind；只有各自 TYPE body内部验证时 `$self` 作为 primitive STRING
读取。任一实现把它们折叠为 STRING、直接用 lexical LT/GT比较或跳过
ValidateDecimal都必须拒绝。

---

## 6. Expression closed grammar

`Expr` 是 JSON array。第 0 项必须命中本节 opcode。任何其他裸 JSON
array/object/string都不能被解释为 expression。

### 6.1 Typed literal, source and binding

```text
["NULL"]
["BOOL",boolean]
["INT",safe_integer]
["DECIMAL",DecimalKind,DecimalString]
["CONST",ConstRef]
["GET",root_name,StaticPath]
["VAR",variable_name]
["CALL",algorithm_NodeId,ArgumentMap]
["TYPE_VALID",schema_or_type_NodeId,Expr]
["AS_SCHEMA",Expr,schema_NodeId]
```

`ArgumentMap` 是按 key的 RFC 8785顺序编码的
`object<parameter_name,Expr>`。`CALL` target必须是 ALGORITHM，argument
key set必须与 target parameters exact equality，返回 target `returns`。
`TYPE_VALID` target只允许 TYPE或 SCHEMA，返回 BOOLEAN。
`AS_SCHEMA` target只允许 SCHEMA；input static type必须是 ANY_JSON或一个包含
exact `["T_OBJECT",schema_NodeId]` variant的 T_UNION。它执行完整 exact-schema
validation并返回 named T_OBJECT；validation失败为 EVAL_REJECT，不允许 partial
object、first-match或 structural coercion。语义上需要保留失败状态时不得用
AS_SCHEMA代替 §7 MATCH_NARROW。

root visibility与结果绑定：

```text
SCHEMA constraints:
  root_name = "$self"

TYPE T_CONSTRAINED constraints:
  root_name = "$self"

ALGORITHM preconditions:
  root_name in parameters

ALGORITHM statements:
  root_name in parameters or initialized locals

ALGORITHM postconditions:
  root_name in parameters or initialized locals or "$result"

IDENTITY preimage:
  root_name in parameters
```

`VAR` 只读取 enclosing MAP/FILTER/FOR_ALL/EXISTS/COUNT/SUM/FOLD/FOR_EACH
或 MATCH_NARROW case声明的 lexical variable。`$self`、`$result` 是 reserved
root，不得出现在 parameters/locals。

### 6.2 Logic 与 comparison

```text
["EQ",Expr,Expr]
["NE",Expr,Expr]
["LT",Expr,Expr]
["LE",Expr,Expr]
["GT",Expr,Expr]
["GE",Expr,Expr]
["AND",array<Expr>]
["OR",array<Expr>]
["NOT",Expr]
["IMPLIES",Expr,Expr]
["IFF",Expr,Expr]
["IF",condition,then_expr,else_expr]
["IS_NULL",Expr]
["IS_NOT_NULL",Expr]
```

`AND/OR` 至少一项；evaluation 为 left-to-right fail closed，不得重排。

### 6.3 Decimal、integer 与 time

```text
["DECIMAL_VALID",DecimalKind,wire_string_expr]
["DECIMAL_PARSE",DecimalKind,wire_string_expr]
["DECIMAL_FORMAT",decimal_value_expr]
["ADD",array<Expr>]
["SUB",Expr,Expr]
["MUL",array<Expr>]
["DIV",Expr,Expr]
["ABS",Expr]
["MIN",array<Expr>]
["MAX",array<Expr>]
["FLOOR",Expr]
["CEIL",Expr]
["SIGN",Expr]
["FLOOR_DIV",dividend_expr,positive_integer_divisor_expr]
["CEIL_DIV",dividend_expr,positive_integer_divisor_expr]
["MOD",dividend_expr,positive_integer_divisor_expr]
["SCALE",unit_value_expr,dimensionless_factor_expr]
["NOTIONAL",price_expr,qty_base_expr]
["APPLY_BPS",money_expr,bps_expr]
["RATIO",same_unit_numerator_expr,same_unit_denominator_expr]
["DECIMAL_QUANTIZE",Expr,quantum_expr,"ROUND_HALF_EVEN"]
```

Exact conversion semantics：

```text
DECIMAL_VALID(K,wire) -> BOOLEAN
DECIMAL_PARSE(K,wire) -> DecimalValue<K>
DECIMAL_FORMAT(DecimalValue<K>) -> nominal wire type mapped from K
```

- `wire` static type只能是 primitive STRING或与 K对应的 nominal wire type；
  其他 DecimalKind、INTEGER、JSON number、ANY_JSON均为 AST_REJECT；
- DECIMAL_VALID执行 §2 lexical/exact-parse/range rules；任何 malformed或
  out-of-range wire content只返回 false，不抛出 EVAL_REJECT；
- DECIMAL_PARSE执行同一 rules；false case立即 EVAL_REJECT，不返回 null、
  zero、UNKNOWN或 rounded value；
- DECIMAL_FORMAT使用 §2 fixed-point canonical formatter，且 formatted value
  必须通过同 K的 DECIMAL_VALID；否则 EVAL_REJECT；
- `["DECIMAL",K,literal]` 先执行同一 DECIMAL_VALID，成功后产生
  DecimalValue<K>；literal不产生 wire string；
- SCHEMA先完整验证每个 property TypeExpr，再按顺序执行 constraints。因此
  schema constraint对 nominal wire field调用 DECIMAL_PARSE时，invalid wire
  已先被 property validation拒绝，不存在 parse-failure降级。

`algorithm/ValidateDecimal.v0.2.2` exact signature：

```json
{
  "parameters":{
    "kind":["T_ENUM",[
      ["CONST_REF","const/LiteralRegistry.v0.2.2","DECIMAL_KIND_BPS"],
      ["CONST_REF","const/LiteralRegistry.v0.2.2","DECIMAL_KIND_DECIMAL"],
      ["CONST_REF","const/LiteralRegistry.v0.2.2","DECIMAL_KIND_MONEY"],
      ["CONST_REF","const/LiteralRegistry.v0.2.2","DECIMAL_KIND_PRICE"],
      ["CONST_REF","const/LiteralRegistry.v0.2.2","DECIMAL_KIND_QTY_BASE"]
    ]],
    "value":["T_PRIMITIVE","STRING"]
  },
  "returns":["T_PRIMITIVE","BOOLEAN"],
  "locals":{},
  "preconditions":[],
  "statements":[
    ["MATCH",["GET","kind",[]],[
      {
        "match":["CONST_REF","const/LiteralRegistry.v0.2.2","DECIMAL_KIND_BPS"],
        "statements":[["RETURN",["DECIMAL_VALID","BPS",["GET","value",[]]]]]
      },
      {
        "match":["CONST_REF","const/LiteralRegistry.v0.2.2","DECIMAL_KIND_DECIMAL"],
        "statements":[["RETURN",["DECIMAL_VALID","DECIMAL",["GET","value",[]]]]]
      },
      {
        "match":["CONST_REF","const/LiteralRegistry.v0.2.2","DECIMAL_KIND_MONEY"],
        "statements":[["RETURN",["DECIMAL_VALID","MONEY",["GET","value",[]]]]]
      },
      {
        "match":["CONST_REF","const/LiteralRegistry.v0.2.2","DECIMAL_KIND_PRICE"],
        "statements":[["RETURN",["DECIMAL_VALID","PRICE",["GET","value",[]]]]]
      },
      {
        "match":["CONST_REF","const/LiteralRegistry.v0.2.2","DECIMAL_KIND_QTY_BASE"],
        "statements":[["RETURN",["DECIMAL_VALID","QTY_BASE",["GET","value",[]]]]]
      }
    ]]
  ],
  "postconditions":[]
}
```

五个 enum members按 resolved value
`BPS,DECIMAL,MONEY,PRICE,QTY_BASE`排序；上述 JSON object就是该 ALGORITHM
的完整 `body`，不是 signature示例。statements唯一为对 `kind` 的 exhaustive
MATCH；不得调用 TYPE_VALID形成 cycle，不得 catch/改写 false。

十进制最小 negative corpus必须至少覆盖：

```text
"01","1.0","-0","1e3","+1","NaN","Infinity",
"12345678901234567890123456789012345",
JSON number 1
```

前八个 STRING 对 `DECIMAL_VALID` 返回 false、对 `DECIMAL_PARSE` 产生
`EVAL_REJECT`；JSON number在 static checking即 `AST_REJECT`。其中最后一个
STRING含 35 个非零 significant digits，不得经 rounding接受。`QtyBase`
wire `"0"` 本身合法，但 `AggTrade.qty_base`、`Level.qty_base` 等要求
`>0` 的 schema constraint必须显式执行
`GT(DECIMAL_PARSE(QTY_BASE,field),DECIMAL(QTY_BASE,"0"))` 并拒绝它；
不得把 nominal type的 `>=0` 误当具体字段的 `>0`。对 `Money`、`BPS`、
`QTY_BASE` 或 `PRICE` 调用 `DECIMAL_FORMAT` 时若 DecimalValue不满足对应
range，必须 `EVAL_REJECT`。任何 WD<K> 禁止直接进入 `LT/LE/GT/GE`。

所有 DecimalValue运算使用 decimal128；integer/UtcUs 运算必须检查
overflow/underflow。除数为 0、空 MIN/MAX、overflow 或 type mismatch 立即
REJECT，不返回 UNKNOWN。

Dimension-aware formulas唯一为：

```text
SCALE(DecimalValue<T> value,
      Integer|DecimalValue<DECIMAL> factor) -> DecimalValue<T>
  where T in {DECIMAL,QTY_BASE,PRICE,MONEY,BPS}

NOTIONAL(DecimalValue<PRICE> price,
         DecimalValue<QTY_BASE> qty) -> DecimalValue<MONEY>
  = decimal128_multiply(price,qty)

APPLY_BPS(DecimalValue<MONEY> money,
          DecimalValue<BPS> bps) -> DecimalValue<MONEY>
  = decimal128_divide(decimal128_multiply(money,bps),"10000")

RATIO(T numerator,T denominator) -> DecimalValue<DECIMAL>
  where T is Integer or one identical DecimalValue kind
  = decimal128_divide(numerator,denominator)
```

每个显示的 decimal128 primitive operation后立即按 precision 34 /
ROUND_HALF_EVEN得到下一 operand；不得使用 fused multiply-divide。Money、
PRICE、QTY_BASE或BPS DecimalValue禁止通过 generic MUL/DIV改变维度。

`FLOOR_DIV/CEIL_DIV/MOD` dividend只能是 INTEGER或 UtcUs，divisor只能是
positive INTEGER，输出 INTEGER。令 mathematical exact rational
`r=dividend/divisor`：

```text
FLOOR_DIV = floor(r)
CEIL_DIV  = ceil(r)
MOD       = dividend - divisor * floor(r)
```

这三项覆盖非整除 UtcUs time-grid；zero/negative divisor或 safe-integer
overflow立即 EVAL_REJECT。

### 6.4 Collection

```text
["LEN",Expr]
["INDEX",Expr,index_expr]
["IN",Expr,collection_expr]
["COUNT",collection_expr,item_var,predicate_expr]
["SUM",collection_expr,item_var,value_expr]
["MAP",collection_expr,var_name,value_expr]
["FILTER",collection_expr,var_name,predicate_expr]
["FOR_ALL",collection_expr,var_name,predicate_expr]
["EXISTS",collection_expr,var_name,predicate_expr]
["UNIQUE",collection_expr]
["SORT",collection_expr,OrderSpec]
["SET_EQ",Expr,Expr]
["SUBSET",Expr,Expr]
["CONCAT",array<Expr>]
["ARGMIN",collection_expr,OrderSpec]
["ARGMAX",collection_expr,OrderSpec]
```

quantifier body 中只有声明的 `var_name` 可见。ARGMIN/ARGMAX 空集合返回
typed `null`；非空集合必须由完整 OrderSpec产生唯一首项。

### 6.5 Construction and immutable update

```text
["OBJECT",schema_NodeId,array<[field_name,Expr]>]
["PREIMAGE_OBJECT",array<[field_name,Expr]>]
["ARRAY",array<Expr>]
["FOLD",collection_expr,item_var,accumulator_var,initial_expr,body_expr]
["UPDATE",object_expr,nonempty_StaticPath,value_expr]
["APPEND",array_expr,value_expr]
```

OBJECT target必须是 SCHEMA；field pair set必须与 target `exact_keys` exact
equality，values逐项满足 properties并通过全部 constraints，输出是 named
`["T_OBJECT",schema_NodeId]`，不是 structural coercion。

PREIMAGE_OBJECT field names同样严格升序且无重复，但输出只是一份 anonymous
JSON object；它只允许作为 IDENTITY `preimage`，或作为 CANONICAL_JSON /
IDENTITY receipt-hash formula的直接输入，禁止 LET/SET/RETURN、SCHEMA property
assignment、CALL argument或转换为 T_OBJECT。OBJECT_WITHOUT/PICK 的 anonymous
结果受同一 restriction。

ARRAY 非空时所有 elements必须统一为同一 TypeExpr；空 ARRAY必须由
assignment/return parameter提供唯一 contextual item type。FOLD 的 accumulator
type由 initial_expr唯一确定，body_expr必须返回相同 type。UPDATE 只产生新
named object，不原地修改；path必须存在、value type可赋给该 path，更新后全部
schema constraints必须重验。APPEND 返回新 array且 value type必须等于 item
type。

### 6.6 Canonical bytes and identity

```text
["CANONICAL_JSON",Expr]
["SHA256",Expr]
["IDENTITY_EVAL",identity_NodeId,ArgumentMap]
["OBJECT_WITHOUT",object_expr,array<field_name>]
["OBJECT_PICK",object_expr,array<field_name>]
```

`CANONICAL_JSON` 只接受 JSON-compatible value并返回 Bytes；`SHA256` 只接受
Bytes并返回 Sha256。`IDENTITY_EVAL` target必须是 IDENTITY，argument key set
必须与 target parameters exact equality；它只使用 target的
`domain_ascii/preimage/output_type`，禁止调用方提供或覆盖 domain/preimage。
因此每次 IDENTITY_EVAL 都形成对 identity NodeId 的 `requires` edge。
`OBJECT_WITHOUT/PICK` field arrays按 ASCII严格升序且无重复，field必须存在。

### 6.7 Closed static type and failure table

对 type inference，普通 TYPE aliases先递归展开；§5.3 五个 nominal decimal
TYPE在 assignability/type inference中保留为对应 WD<K>，只在检查其自身
T_CONSTRAINED body时暴露 primitive STRING base。`type/Bytes` 同样保留 nominal
internal type。不得用 alias expansion制造隐式 string/decimal、
integer/decimal、nullable/non-null或 schema/structural coercion。记：

```text
B = BOOLEAN
I = INTEGER
WD<K> = nominal JSON STRING wire decimal for DecimalKind K
DV<K> = non-JSON DecimalValue<K>
D0 = DV<DECIMAL>
D = DV<DECIMAL>|DV<QTY_BASE>|DV<PRICE>|DV<MONEY>|DV<BPS>
U = UtcUs
S = primitive STRING, excluding nominal WD<K>
Y = Bytes
H = Sha256|StableId
A<T> = array<T>
O = exact object/schema type
J = JSON-compatible non-Bytes/non-DV value, including WD<K>
T? = nullable T
```

全部 expression opcode的输入/输出与失败类别如下；未列组合是 static
`AST_REJECT`：

| opcode | input types | output | deterministic failure |
|---|---|---|---|
| `NULL/BOOL/INT` | exact literal payload | contextual NULL/B/I | malformed/range => AST_REJECT |
| `CONST` | exact ConstRef | `T_CONST_REF(r)`, assignable only per §5.2 | member miss/type mismatch => AST_REJECT |
| `DECIMAL` | `(DecimalKind,canonical wire literal)` | DV<K> | invalid lexical/exact/range => AST_REJECT |
| `GET/VAR` | declared root/path or lexical variable | resolved declared type | bad scope/path => AST_REJECT |
| `CALL` | ALGORITHM + exact typed ArgumentMap | target returns | wrong kind/keys/types => AST_REJECT |
| `TYPE_VALID` | TYPE or SCHEMA + J | B | wrong node kind => AST_REJECT |
| `AS_SCHEMA` | `(ANY_JSON or containing union,SCHEMA)` | named T_OBJECT(schema) | illegal target/input => AST_REJECT; validation miss => EVAL_REJECT |
| `DECIMAL_VALID` | `(K,S or matching WD<K>)` | B | content failure => false; static mismatch => AST_REJECT |
| `DECIMAL_PARSE` | `(K,S or matching WD<K>)` | DV<K> | content failure => EVAL_REJECT; static mismatch => AST_REJECT |
| `DECIMAL_FORMAT` | DV<K> | WD<K> | noncanonical/out-of-range => EVAL_REJECT |
| `EQ/NE` | `(T,T)` | B | unequal static types => AST_REJECT |
| `LT/LE/GT/GE` | `(I or same DV<K> or U or S, same type)` | B | WD<K>/unordered/null/type mismatch => AST_REJECT or EVAL_REJECT |
| `AND/OR/NOT/IMPLIES/IFF` | B operands | B | non-B => AST_REJECT |
| `IF` | `(B,T,T)` | T | branch type mismatch => AST_REJECT |
| `IS_NULL/IS_NOT_NULL` | `T?` | B | non-nullable input => AST_REJECT |
| `ADD` | all I; all same exact DV<K>; or exactly one U plus I offsets | I, same DV<K>, or U | empty/overflow/type mismatch => EVAL_REJECT |
| `SUB` | `(I,I)`, `(same DV<K>,same DV<K>)`, `(U,I)` or `(U,U)` | I, same DV<K>, U or I | overflow/type mismatch => EVAL_REJECT |
| `MUL` | all I or all D0 only | I or D0 | empty/overflow/dimension mismatch => EVAL_REJECT |
| `DIV` | `(D0,D0)`; or `(I,I)` only when exactly divisible | D0 or I | zero/non-exact integer quotient/overflow => EVAL_REJECT |
| `ABS` | I or DV<K> | same type | overflow => EVAL_REJECT |
| `MIN/MAX` | non-empty values all of same I, DV<K> or U type | same type | empty/type mismatch => EVAL_REJECT |
| `FLOOR/CEIL` | DV<K> | same DV<K> with integral value | overflow => EVAL_REJECT |
| `SIGN` | I or DV<K> | I | overflow => EVAL_REJECT |
| `FLOOR_DIV/CEIL_DIV/MOD` | `(I or U,positive I)` | I | zero/negative divisor/overflow => EVAL_REJECT |
| `SCALE` | `(DV<K>,I or DV<DECIMAL>)` | same DV<K> | overflow => EVAL_REJECT |
| `NOTIONAL` | `(DV<PRICE>,DV<QTY_BASE>)` | DV<MONEY> | overflow => EVAL_REJECT |
| `APPLY_BPS` | `(DV<MONEY>,DV<BPS>)` | DV<MONEY> | overflow => EVAL_REJECT |
| `RATIO` | `(same exact I or DV<K>,same type)` | DV<DECIMAL> | zero/overflow => EVAL_REJECT |
| `DECIMAL_QUANTIZE` | `(DV<K>,DV<K>,ROUND_HALF_EVEN)` | same DV<K> | invalid quantum/overflow => EVAL_REJECT |
| `LEN` | A<T>, MAP or S | I | other type => AST_REJECT |
| `INDEX` | `(A<T>,I)` or `(S,I)` | T or S | out of range => EVAL_REJECT |
| `IN` | `(T,A<T>)` | B | item mismatch => AST_REJECT |
| `COUNT` | `(A<T>,var:T,predicate:B)` | I | overflow => EVAL_REJECT |
| `SUM` | `(A<T>,var:T,value:I or one exact DV<K>)` | value numeric type | overflow => EVAL_REJECT |
| `MAP` | `(A<T>,var:T,value:V)` | A<V> | lexical/type error => AST_REJECT |
| `FILTER` | `(A<T>,var:T,predicate:B)` | A<T> | lexical/type error => AST_REJECT |
| `FOR_ALL/EXISTS` | `(A<T>,var:T,predicate:B)` | B | lexical/type error => AST_REJECT |
| `UNIQUE` | A<T> | A<T> | non-canonical equality => AST_REJECT |
| `SORT` | `(A<O>,OrderSpec)` | A<O> | unresolved key/non-total order => EVAL_REJECT |
| `SET_EQ/SUBSET` | `(A<T>,A<T>)` | B | type mismatch => AST_REJECT |
| `CONCAT` | all A<T> or all S | A<T> or S | empty/mixed types => AST_REJECT |
| `ARGMIN/ARGMAX` | `(A<O>,OrderSpec)` | O? | unresolved/non-total order => EVAL_REJECT |
| `OBJECT` | SCHEMA + exact sorted fields with typed Expr | named T_OBJECT(schema) | wrong kind/field/type/constraint => AST_REJECT or EVAL_REJECT |
| `PREIMAGE_OBJECT` | sorted unique fields with typed Expr | anonymous J | invalid field/context escape => AST_REJECT |
| `ARRAY` | elements of one T or contextual empty | A<T> | no context/mixed types => AST_REJECT |
| `FOLD` | `(A<T>,item:T,acc:V,initial:V,body:V)` | V | lexical/type error => AST_REJECT |
| `UPDATE` | `(O,valid path,V assignable at path)` | same O | bad path/type => AST_REJECT |
| `APPEND` | `(A<T>,T)` | A<T> | mismatch => AST_REJECT |
| `CANONICAL_JSON` | J | Y | non-JSON/unsafe integer => EVAL_REJECT |
| `SHA256` | Y | Sha256 | non-Bytes => AST_REJECT |
| `IDENTITY_EVAL` | IDENTITY + exact ArgumentMap | target output_type | wrong kind/keys/types/eval => AST_REJECT or EVAL_REJECT |
| `OBJECT_WITHOUT/PICK` | `(O,existing fields)` | anonymous J | missing/duplicate/context escape => AST_REJECT |

`SUM([])` 返回与 value_expr相同 type的 typed zero；`ADD/MUL/CONCAT` 空 arrays
禁止。ADD、MUL、SUM与CONCAT都按 array/collection order执行严格
left-to-right fold，每一步完成 decimal128 rounding后才进入下一步。UNIQUE按
CanonicalJSON equality保留第一次出现的 item并保持首次出现顺序。其他
iteration同样保留 input order。`EVAL_REJECT` 是算法执行失败，不得转换成
UNKNOWN/default；`AST_REJECT` 表示 artifact 本身不合规。

---

## 7. Statement grammar

ALGORITHM 的 statement 是下列 exact array之一：

```text
["LET",name,Expr]
["SET",local_name,nonempty_StaticPath,Expr]
["ASSERT",Expr,ConstRef]
["IF",Expr,array<Statement>,array<Statement>]
["FOR_EACH",name,collection_expr,array<Statement>]
["MATCH",Expr,array<MatchCase>]
["MATCH_NARROW",Expr,array<NarrowCase>]
["RETURN",Expr]
```

`MatchCase` exact keys：

```text
match,statements
```

`match` 是 ConstRef。MATCH expression必须静态解析为 T_ENUM；case refs必须
与该 enum member set exact equality，按 resolved wire value的 RFC 8785
bytes升序，无 default branch。`ASSERT` expression必须为 BOOLEAN；error
ConstRef必须解析为 STRING member。

`NarrowCase` exact keys：

```text
bind,statements,type
```

```text
bind:variable_name
statements:array<Statement>
type:TypeExpr
```

`MATCH_NARROW` expression的 static type必须是 `T_UNION`，或是递归展开后
恰好得到 `T_UNION` 的 `T_REF`。cases必须满足：

1. case `type` set与 union variants canonical-byte exact equality，无缺失、
   重复、额外或 default；
2. cases按 `type` 的 CanonicalJSON bytes严格升序；
3. input expression只求值一次，再以完整 TypeExpr validator检查所有 variants；
4. runtime value必须恰好匹配一个 variant；0个或多个匹配均
   `EVAL_REJECT`，不得 first-match；
5. 命中 branch内 `bind` 是只读 lexical variable，其 static type正是该
   variant；它只在该 branch的 statements可见；
6. case `type` 内所有 NodeId slots都计入 enclosing node的 `requires`；
7. variant-specific `GET` 只能从 branch bind读取，禁止从原 union root
   unchecked读取。

若 union含一个 status `T_ENUM` 与一个 object/array成功 variant，consumer必须先
用 MATCH_NARROW分开二者；enum branch再用 MATCH穷尽 wire status。不得用
`AS_SCHEMA`、null、exception、duck typing或 field-presence test代替语义状态。

`LET name` 必须命中 enclosing ALGORITHM `locals`，expression type必须可赋给
该 declared type；每个 local在每条使用路径上先 LET且至多 LET一次。`SET`
只能写已经初始化的 local object，不能修改 parameter、lexical variable或
`$result`。IF/MATCH/MATCH_NARROW 每个 branch、FOR_EACH body都使用 lexical
scope；循环 variable type等于 collection item type。每条可达 execution
path恰好一个 RETURN，RETURN expression必须可赋给 `returns`；RETURN 后不得
有 statement。

---

## 8. Node body exact unions

### 8.1 TYPE

Exact keys：

```text
type_expr
```

### 8.2 SCHEMA

Exact keys：

```text
exact_keys,properties,constraints
```

```text
exact_keys:array<string>
properties:object<string,TypeExpr>
constraints:array<Expr>
```

`exact_keys` 按 UTF-8 bytes严格升序；property key set必须完全相等。所有 key
required，禁止 additional properties，只有 TypeExpr 明示 T_NULLABLE 才可
null。constraints全部必须静态返回 BOOLEAN，按 normative evaluation order
求值且全部 true才通过 schema validation；false为 validation miss，
evaluation failure为 EVAL_REJECT。constraints不按 hash排序。

### 8.3 CONST

Exact keys：

```text
members
```

`members` 是 `object<const_symbol,ConstMember>`，keys按 RFC 8785顺序且非空。
`ConstMember` exact keys：

```text
type,value
```

`type enum{STRING,INTEGER,BOOLEAN,NULL,DECIMAL_STRING}`。STRING value必须匹配
`^[!-~]{1,256}$`（printable ASCII without whitespace），以容纳 frozen
version specifier与 entrypoint token，但不得承载含 whitespace的自然语言句子；INTEGER必须是 safe integer；BOOLEAN/NULL必须是对应 JSON
scalar；DECIMAL_STRING必须满足 §2 DecimalString lexical/precision规则。不同 symbols可以指向
同一 value，但一个 T_ENUM 内 resolved values必须互异。

DECIMAL_STRING ConstMember 的 static type是 nominal
`WD<DECIMAL>`（`["T_REF","type/DecimalString"]`），不是
`T_DECIMAL_VALUE`；numeric使用前必须 DECIMAL_PARSE。

本 profile inventory只允许一个 CONST node：

```text
const/LiteralRegistry.v0.2.2
```

所有固定 wire strings均由该 node集中给出。CONST node不允许任意 object/array
payload，也不允许用 string承载表达式、约束或自然语言算法。

### 8.4 ALGORITHM

Exact keys：

```text
parameters,returns,locals,preconditions,statements,postconditions
```

`parameters/locals` 是 key按 RFC 8785顺序的 TypeExpr map，key sets不交叠。
`returns` 是唯一 TypeExpr。pre/postconditions 是 Expr array；postconditions
只能通过 `$result` 读取返回值。locals只声明类型，初始化 authority唯一来自
§7 LET。statements 使用 §7。所有输入显式传入；
禁止 filesystem、network、database、wall clock、global state、environment、
randomness或隐式 collection。

### 8.5 IDENTITY

Exact keys：

```text
domain_ascii,parameters,preimage,output_type
```

`domain_ascii` 非空 ASCII，必须在全部 IDENTITY nodes中唯一。preimage 是
JSON-compatible Expr且只读取 exact typed parameters。每个 IDENTITY_EVAL
的 argument key set必须与 parameters exact equality，且参数类型逐项相等。
执行语义唯一为：

```text
ID(domain_ascii, evaluate(preimage, parameters))
```

output_type 必须为 `["T_REF","type/StableId"]` 或
`["T_REF","type/Sha256"]`。`ID(...)` 不是 Expr opcode，不能绕过此 node。

### 8.6 ROUTING

Exact keys：

```text
input_type,discriminator,discriminator_type,value_path,cases
```

```text
input_type:TypeExpr
discriminator:nonempty StaticPath
discriminator_type:["T_ENUM",array<ConstRef>]
value_path:StaticPath
cases:array<RoutingCase>
```

`RoutingCase` exact keys：

```text
match,schema_node_id
```

`match` 是 ConstRef，`schema_node_id` 必须引用 SCHEMA。discriminator path
必须从 input_type解析到与 `discriminator_type` canonical bytes完全相等的
type；每个 case只用其 schema验证 `GET(input,value_path)` 的 routed value，
不得把整个 envelope误当 payload。case match set必须与 enum member set exact
equality，按 resolved wire value的 RFC 8785 bytes升序，互斥、穷尽且无
default。

三个 ROUTING nodes 的 paths必须 exact equality：

```text
routing/DecisionResult.v0.2.2:
  discriminator = [["FIELD","decision_kind"]]
  value_path = []

routing/ArtifactPayload.v0.2.2:
  discriminator = [["FIELD","schema_id"]]
  value_path = [["FIELD","payload"]]

routing/ReducerPayload.v0.2.2:
  discriminator = [["FIELD","event_kind"]]
  value_path = [["FIELD","payload"]]
```

空 value_path只允许 DecisionResult，表示验证整个 decision object；另两者必须
验证 payload field。discriminator/value paths都必须从 input_type静态解析，
且 case schema input type必须与 routed value type兼容。

### 8.7 Node-kind compatibility matrix

所有 NodeId-bearing slots的 target kind必须满足：

| slot | allowed node kind |
|---|---|
| `T_REF` | TYPE |
| `T_OBJECT` | SCHEMA |
| `T_CONST_REF/T_ENUM/CONST/ASSERT/MATCH/ROUTING.match` | exact `const/LiteralRegistry.v0.2.2` CONST |
| `CALL` | ALGORITHM |
| `TYPE_VALID` | TYPE or SCHEMA |
| `AS_SCHEMA` target | SCHEMA |
| `OBJECT` | SCHEMA |
| `IDENTITY_EVAL` | IDENTITY |
| `MATCH_NARROW.cases[].type` | kinds permitted by that exact TypeExpr opcode |
| `ROUTING.cases[].schema_node_id` | SCHEMA |
| `requires` | any kind, but exact body-reference equality |

ALGORITHM `parameters/returns/locals`、IDENTITY `parameters/output_type`、
ROUTING `input_type/discriminator_type` 与全部 SCHEMA properties都必须通过
同一个 TypeExpr checker；不得各自实现局部或宽松类型规则。

### 8.8 Market-source union and selector outcome closure

`type/MarketSourceObject` 是四种 heterogeneous market source的唯一 reusable
union。它的 `body.type_expr` 必须逐字等于：

```json
["T_UNION",[["T_OBJECT","schema/AggTrade.v0.2.2"],["T_OBJECT","schema/BookSnapshot.v0.2.2"],["T_OBJECT","schema/ClosedMarkBar.v0.2.2"],["T_OBJECT","schema/OpenInterest.v0.2.2"]]]
```

该 TYPE node的 `requires` 必须逐字等于下列 UTF-8 byte-sorted array：

```json
["schema/AggTrade.v0.2.2","schema/BookSnapshot.v0.2.2","schema/ClosedMarkBar.v0.2.2","schema/OpenInterest.v0.2.2"]
```

`algorithm/OrderedSourceProjection.v0.2.2`、
`algorithm/SourceCollision.v0.2.2` 与
`algorithm/ValidateCoverageSeal.v0.2.2` 中，任何可以承载多种 market source
schema的单值 parameter/local必须用
`["T_REF","type/MarketSourceObject"]`；collection必须用以该 T_REF为 item
type的 `T_ARRAY`。禁止用 ANY_JSON、structural object、四个 nullable fields
或 untyped array表达同一输入。

上述 algorithm必须对每个 heterogeneous item执行 §7 MATCH_NARROW，四个
case `type` 与本 union四个 variants exact equality；只有 branch bind可以读取
variant-specific fields。每个 branch必须依下列 accessor生成 named
`schema/OrderedSourceProjection.v0.2.2` OBJECT：

| branch schema | `object_kind` ConstRef resolved value | `economic_time_us` | `source_object_id` | `generation_id` |
|---|---|---|---|---|
| `schema/AggTrade.v0.2.2` | `AGG_TRADE` | `event_time_us` | `event_id` | `stream_generation_id` |
| `schema/BookSnapshot.v0.2.2` | `BOOK_SNAPSHOT` | `event_time_us` | `event_id` | `book_generation_id` |
| `schema/ClosedMarkBar.v0.2.2` | `CLOSED_MARK_BAR` | `bar_close_at_us` | `stable_bar_id` | `stream_generation_id` |
| `schema/OpenInterest.v0.2.2` | `OPEN_INTEREST` | `event_time_us` | `event_id` | `stream_generation_id` |

projection只构造 named schema object，不产生 anonymous map。source collision与
coverage只能比较相同 `object_kind`、Scope4、source/schema version范围内的
projection；不得拼接不同 kind后排序，不得对 generation accessor猜测或 fallback，
也不得用 lexicographic ID消解 generation/source/conflict。

`const/LiteralRegistry.v0.2.2` 还必须包含下列五个 exact STRING members：

```text
SELECTOR_ACCOUNT_SNAPSHOT_CONFLICT -> {type:"STRING",value:"ACCOUNT_SNAPSHOT_CONFLICT"}
SELECTOR_CONFLICT                  -> {type:"STRING",value:"CONFLICT"}
SELECTOR_COVERAGE_CONFLICT         -> {type:"STRING",value:"COVERAGE_CONFLICT"}
SELECTOR_RULE_SNAPSHOT_CONFLICT    -> {type:"STRING",value:"RULE_SNAPSHOT_CONFLICT"}
SELECTOR_UNKNOWN                   -> {type:"STRING",value:"UNKNOWN"}
```

下列八个 ALGORITHM 的 `body.returns` 必须分别逐字等于所示 TypeExpr。所有
T_ENUM members都按 resolved value排序；所有 T_UNION variants都按
CanonicalJSON bytes排序。

`algorithm/SelectCoverageSeal.v0.2.2`：

```json
["T_UNION",[["T_ENUM",[["CONST_REF","const/LiteralRegistry.v0.2.2","SELECTOR_COVERAGE_CONFLICT"],["CONST_REF","const/LiteralRegistry.v0.2.2","SELECTOR_UNKNOWN"]]],["T_OBJECT","schema/CoverageSeal.v0.2.2"]]]
```

`algorithm/SelectBook.v0.2.2`：

```json
["T_UNION",[["T_ENUM",[["CONST_REF","const/LiteralRegistry.v0.2.2","SELECTOR_CONFLICT"],["CONST_REF","const/LiteralRegistry.v0.2.2","SELECTOR_UNKNOWN"]]],["T_OBJECT","schema/BookSnapshot.v0.2.2"]]]
```

`algorithm/SelectOpenInterest.v0.2.2`：

```json
["T_UNION",[["T_ENUM",[["CONST_REF","const/LiteralRegistry.v0.2.2","SELECTOR_CONFLICT"],["CONST_REF","const/LiteralRegistry.v0.2.2","SELECTOR_UNKNOWN"]]],["T_OBJECT","schema/OpenInterest.v0.2.2"]]]
```

`algorithm/SelectVenueSnapshot.v0.2.2`：

```json
["T_UNION",[["T_ENUM",[["CONST_REF","const/LiteralRegistry.v0.2.2","SELECTOR_RULE_SNAPSHOT_CONFLICT"],["CONST_REF","const/LiteralRegistry.v0.2.2","SELECTOR_UNKNOWN"]]],["T_OBJECT","schema/VenueInstrumentSnapshot.v0.2.2"]]]
```

`algorithm/SelectAccountSnapshot.v0.2.2`：

```json
["T_UNION",[["T_ENUM",[["CONST_REF","const/LiteralRegistry.v0.2.2","SELECTOR_ACCOUNT_SNAPSHOT_CONFLICT"],["CONST_REF","const/LiteralRegistry.v0.2.2","SELECTOR_UNKNOWN"]]],["T_OBJECT","schema/AccountRiskSnapshot.v0.2.2"]]]
```

`algorithm/SelectClosedMarkBarSlot.v0.2.2`：

```json
["T_UNION",[["T_ENUM",[["CONST_REF","const/LiteralRegistry.v0.2.2","SELECTOR_CONFLICT"],["CONST_REF","const/LiteralRegistry.v0.2.2","SELECTOR_UNKNOWN"]]],["T_OBJECT","schema/ClosedMarkBar.v0.2.2"]]]
```

`algorithm/SelectAggTradeWindow.v0.2.2`：

```json
["T_UNION",[["T_ARRAY",["T_OBJECT","schema/AggTrade.v0.2.2"],0,null,true,{"directions":["ASC","ASC","ASC"],"keys":[[["FIELD","event_time_us"]],[["FIELD","source_sequence"]],[["FIELD","event_id"]]],"nulls":["FORBIDDEN","FORBIDDEN","FORBIDDEN"]}],["T_ENUM",[["CONST_REF","const/LiteralRegistry.v0.2.2","SELECTOR_COVERAGE_CONFLICT"],["CONST_REF","const/LiteralRegistry.v0.2.2","SELECTOR_UNKNOWN"]]]]]
```

`algorithm/SelectBookGrid.v0.2.2`：

```json
["T_UNION",[["T_ENUM",[["CONST_REF","const/LiteralRegistry.v0.2.2","SELECTOR_CONFLICT"],["CONST_REF","const/LiteralRegistry.v0.2.2","SELECTOR_UNKNOWN"]]],["T_OBJECT","schema/BookSnapshot.v0.2.2"]]]
```

成功结果不得包装、降级或转换成 nullable。语义上的零匹配或已定义 conflict必须
RETURN相应 `["CONST",ConstRef]`，不是 `EVAL_REJECT`；malformed schema、
不满足 algorithm precondition或 union 0/multiple type match仍可
`EVAL_REJECT`。consumer必须先 MATCH_NARROW成功 variant与完整 status T_ENUM，
再在 status branch用 exhaustive MATCH；不得把
`ACCOUNT_SNAPSHOT_CONFLICT`、`RULE_SNAPSHOT_CONFLICT` 或
`COVERAGE_CONFLICT` 改写成 generic `CONFLICT`。

最小 negative corpus必须拒绝：从未 narrow的 source union读取
`book_generation_id` 或 `stream_generation_id`；把 schema不匹配的 object
强制 AS_SCHEMA；同一 runtime value匹配 0个或多个 union variants；跨 source
kind concat/sort；错误 generation accessor；以 first-match、field presence、
lexicographic ID、null或 exception替代上述 exact branch/status。

---

## 9. Digest algorithms

对每个 node：

```text
node_digest_index[node_id] =
  ID("rsi-mtf-drl-pm-direct-node/v0.2.2", {
    node_id,
    node_envelope:nodes[node_id]
  })
```

AST digest：

```text
ast_sha256 =
  ID("rsi-mtf-drl-pm-direct-machine-ast/v0.2.2", {
    ast_schema_version,
    status,
    target_contract_id,
    source_authority,
    profile_raw_sha256,
    nodes,
    node_digest_index,
    root_exports
  })
```

file raw SHA-256 对 exact bytes计算，外置于 AST。Terra 一次生成
`status="IMMUTABLE_REVIEW_BYTES"` 的完整 candidate bytes并停止写入。外部
validator与 Sol reviewer只对该 exact raw SHA与 `ast_sha256` 出具 §13
receipt；任何 byte改变都创建新 candidate并使旧 receipt失效，禁止“审后改
status再重算”。`final_release_theory_path` 只可 pin收到 external PASS
receipt的同一 bytes。

---

## 10. Global closure

完整 AST 必须同时满足：

1. NodeId 全局唯一；
2. node map key、envelope.node_id、digest-index key三者完全相等；
3. NodeId prefix与 node_kind逐项满足 §4 exact mapping；
4. requires 与 body references exact set equality；
5. root_exports 非空、去重、升序，全部存在；
6. 从 root_exports 可达的 nodes恰好等于 nodes key set；无 orphan；
7. reference graph 是 DAG；发现 cycle立即 REJECT；
8. 所有 ROUTING case穷尽、互斥并按 exact value_path验证 routed value；
9. 所有 SCHEMA exact keys与 properties exact set equality；
10. 每个 IDENTITY domain唯一；
11. TypeExpr、Expr、Statement及所有 NodeId target kind通过 §5–§8 exact
    checker；
12. 所有 ConstRef存在、每个 registry member至少被 registry外一个 ConstRef
    使用，且固定 wire string没有 registry外副本；
13. expression/statement opcode全部命中本 profile，无 extension opcode；
14. 不存在自由 prose node、source pointer、patch或 overlay；
15. `node_digest_index`、`ast_sha256` 与 file raw SHA均可独立复算；
16. AST 内不存在自称 conformance authority的 validator；PASS只能来自
    profile外部 validator与独立 reviewer的 §13 receipt；
17. 每个 nominal wire decimal在进入 comparison、financial formula或 range
    constraint前都显式通过同 DecimalKind的 DECIMAL_PARSE；不存在 JSON
    number、lexical comparison、implicit coercion或 rounded parse；
18. 每个 heterogeneous T_UNION的 variant-specific access都由 exhaustive
    MATCH_NARROW支配，runtime恰好命中一个 variant；不存在 first-match、
    duck typing或 unchecked AS_SCHEMA；
19. §8.8 八个 selector的 returns exact equality通过，成功值与
    UNKNOWN/各专属 CONFLICT状态可机械区分且所有 consumer exhaustive处理。

---

## 11. Complete node inventory 与 dependency-neutral review slices

以下 exact 307 个 NodeId 是封闭 inventory。新增、删除、改名或跨 slice隐藏
依赖必须先由 Sol 发布新 profile。A–F 只是审查工作切片，不是构建顺序、
authority stage或独立 closure boundary；body可以引用其他 slice 中已经在本
封闭 inventory精确声明的 NodeId，但不得引用 placeholder digest/value。

### 11.1 Review slice A — atoms, candidate, policy, source and selectors

```text
type/UtcUs
type/DecimalString
type/QtyBase
type/Price
type/Money
type/Bps
type/Sha256
type/StableId
type/Bytes
type/Scope4
type/ControlId
type/EntryControlId
type/Side
type/AvailabilityKind
type/Quality4
type/Quality3
type/ReducerEventKind
type/LedgerState
type/ArtifactSchemaId
type/MarketSourceObject

const/LiteralRegistry.v0.2.2

schema/Scope4.v0.2.2
schema/SourceQuery.v0.2.2
schema/AccountQuery.v0.2.2
schema/ParameterSet.v0.2.2
schema/UPolicy.v0.2.2
schema/EntryPolicy.v0.2.2
schema/ExitPolicyTemplate.v0.2.2
schema/CostPolicy.v0.2.2
schema/RiskPolicy.v0.2.2
schema/LabelPolicyBinding.v0.2.2
schema/DataRolePolicy.v0.2.2
schema/EstimatorPolicy.v0.2.2
schema/SourceSelectorPolicy.v0.2.2
schema/PolicyBundle.v0.2.2
schema/PolicyRegistry.v0.2.2
schema/Level.v0.2.2
schema/ClosedMarkBar.v0.2.2
schema/BookSnapshot.v0.2.2
schema/AggTrade.v0.2.2
schema/OpenInterest.v0.2.2
schema/OrderedSourceProjection.v0.2.2
schema/GenerationRange.v0.2.2
schema/CoverageGap.v0.2.2
schema/CoverageSeal.v0.2.2
schema/VenueInstrumentSnapshot.v0.2.2
schema/AccountRiskSnapshot.v0.2.2

algorithm/ValidateDecimal.v0.2.2
algorithm/OrderedSourceProjection.v0.2.2
algorithm/SourceCollision.v0.2.2
algorithm/ValidateCoverageSeal.v0.2.2
algorithm/SelectCoverageSeal.v0.2.2
algorithm/SelectBook.v0.2.2
algorithm/SelectOpenInterest.v0.2.2
algorithm/SelectVenueSnapshot.v0.2.2
algorithm/SelectAccountSnapshot.v0.2.2
algorithm/SelectClosedMarkBarSlot.v0.2.2
algorithm/SelectAggTradeWindow.v0.2.2
algorithm/SelectBookGrid.v0.2.2
algorithm/ValidateOICompleteness.v0.2.2
algorithm/BuildPolicyRegistry.v0.2.2

identity/ParameterSet.v0.2.2
identity/CompositeTheory.v0.2.2
identity/UPolicy.v0.2.2
identity/EntryPolicy.v0.2.2
identity/ExitPolicyTemplate.v0.2.2
identity/CostPolicy.v0.2.2
identity/RiskPolicy.v0.2.2
identity/LabelPolicyBinding.v0.2.2
identity/DataRolePolicy.v0.2.2
identity/EstimatorPolicy.v0.2.2
identity/SourceSelectorPolicy.v0.2.2
identity/PolicyBundle.v0.2.2
identity/PolicyRegistry.v0.2.2
identity/Candidate.v0.2.2
identity/ClosedMarkBar.v0.2.2
identity/BookSnapshot.v0.2.2
identity/AggTrade.v0.2.2
identity/OpenInterest.v0.2.2
identity/CoverageCoveredEventSet.v0.2.2
identity/CoverageSeal.v0.2.2
identity/VenueRuleFingerprint.v0.2.2
identity/VenueInstrumentSnapshot.v0.2.2
identity/AccountRiskSnapshot.v0.2.2
```

Slice A local review必须证明：所有 primitive/type constraints、policy chain、source
scope/generation、58-domain相关 source identities、coverage exact set与全部
selector counterexamples可机械运行。

### 11.2 Review slice B — U, evidence, decision, action and artifact union

```text
schema/UObservationReceipt.v0.2.2
schema/SyntheticFixtureManifest.v0.2.2
schema/SyntheticFixtureGeneratorPolicy.v0.2.2
schema/FixtureSourceQueries.v0.2.2
schema/EVObservation.v0.2.2
schema/EVClassCounts.v0.2.2
schema/FrozenEVEvidence.v0.2.2
schema/DecisionNamedArtifactBindings.v0.2.2
schema/DecisionSelectorBindings.v0.2.2
schema/DecisionEntryResult.v0.2.2
schema/DecisionAbstainResult.v0.2.2
schema/DecisionInputBinding.v0.2.2
schema/InitialLevels.v0.2.2
schema/RiskBasis.v0.2.2
schema/SharedEntryAction.v0.2.2
schema/CostBasis.v0.2.2
schema/FrozenPolicyBindings.v0.2.2
schema/FrozenLedgerSeed.v0.2.2
schema/FrozenActionContext.v0.2.2
schema/ArtifactWrapper.v0.2.2
schema/SyntheticFundingObservation.v0.2.2
schema/SyntheticConflictProof.v0.2.2

algorithm/EvaluateMasterU.v0.2.2
algorithm/ValidateFixtureManifest.v0.2.2
algorithm/ValidateEVObservation.v0.2.2
algorithm/ValidateFrozenEVEvidence.v0.2.2
algorithm/SelectFrozenEVEvidence.v0.2.2
algorithm/CalculateEntryDecision.v0.2.2
algorithm/ValidateDecisionInputBinding.v0.2.2
algorithm/ValidateSharedEntryAction.v0.2.2
algorithm/ValidateFatalAbstain.v0.2.2
algorithm/RouteArtifactPayload.v0.2.2

routing/DecisionResult.v0.2.2
routing/ArtifactPayload.v0.2.2

identity/UObservationReceipt.v0.2.2
identity/FixtureManifest.v0.2.2
identity/EVObservation.v0.2.2
identity/EVObservationBindings.v0.2.2
identity/EVObservationSet.v0.2.2
identity/SyntheticFixtureGeneratorPolicy.v0.2.2
identity/SyntheticFixtureArtifactSet.v0.2.2
identity/FrozenEVEvidence.v0.2.2
identity/FrozenEVSelectionKey.v0.2.2
identity/DecisionSourceArtifactSet.v0.2.2
identity/DecisionResult.v0.2.2
identity/DecisionInputBinding.v0.2.2
identity/SharedEntryAction.v0.2.2
identity/FrozenLedgerSeed.v0.2.2
identity/FrozenActionContext.v0.2.2
identity/ArtifactScope.v0.2.2
identity/Artifact.v0.2.2
identity/SyntheticFunding.v0.2.2
identity/SyntheticConflictProof.v0.2.2
```

Slice B local review必须证明：current-opportunity exclusion、selector key、decision
stage closure、same-microsecond clock、ENTRY exact artifact set与 fatal no-proof
union全都机械单值；20-member artifact routing 无 fallback。

### 11.3 Review slice C — 34 payloads, canonical event and bundle

```text
schema/Payload.CONTROL_ABSTAIN.v0.2.2
schema/Payload.ENTRY_SUBMIT.v0.2.2
schema/Payload.ENTRY_ACK.v0.2.2
schema/Payload.ENTRY_REJECT.v0.2.2
schema/Payload.ENTRY_EXPIRE.v0.2.2
schema/Payload.FILL_CUMULATIVE.v0.2.2
schema/Payload.CANCEL_REQUEST.v0.2.2
schema/Payload.CANCEL_ACK.v0.2.2
schema/Payload.CANCEL_REJECT_OR_UNKNOWN.v0.2.2
schema/Payload.STOP_REQUEST.v0.2.2
schema/Payload.STOP_ACK.v0.2.2
schema/Payload.STOP_REJECT_OR_UNKNOWN.v0.2.2
schema/Payload.TARGET_REQUEST.v0.2.2
schema/Payload.TARGET_ACK.v0.2.2
schema/Payload.TARGET_REJECT_OR_UNKNOWN.v0.2.2
schema/Payload.POSITION_SNAPSHOT.v0.2.2
schema/Payload.FUNDING_DEBIT.v0.2.2
schema/Payload.PENDING_DEADLINE.v0.2.2
schema/Payload.PROTECTION_REPAIR.v0.2.2
schema/Payload.ACCOUNT_MISMATCH.v0.2.2
schema/Payload.KILL.v0.2.2
schema/Payload.STOP_HIT.v0.2.2
schema/Payload.STRUCTURE_EXIT.v0.2.2
schema/Payload.TARGET_HIT.v0.2.2
schema/Payload.HORIZON.v0.2.2
schema/Payload.BARRIER_EVALUATION.v0.2.2
schema/Payload.REDUCE_ONLY_EXIT_REQUEST.v0.2.2
schema/Payload.EXIT_FILL_CUMULATIVE.v0.2.2
schema/Payload.EXIT_ACK.v0.2.2
schema/Payload.EXIT_REJECT_OR_UNKNOWN.v0.2.2
schema/Payload.RECONCILE_OK.v0.2.2
schema/Payload.DATA_HEALTH_INVALID.v0.2.2
schema/Payload.EVENT_CONFLICT.v0.2.2
schema/Payload.NO_CHANGE.v0.2.2
schema/CandidateEvidenceBinding.v0.2.2
schema/CanonicalSyntheticEvent.v0.2.2
schema/CanonicalSyntheticCoverage.v0.2.2
schema/CanonicalSyntheticEventBundle.v0.2.2
schema/EntryTraceEvent.v0.2.2
schema/EntryTerminalProof.v0.2.2
schema/EntryCostBinding.v0.2.2
schema/EntryExecutionBinding.v0.2.2

routing/ReducerPayload.v0.2.2

algorithm/ValidateReducerPayload.v0.2.2
algorithm/AllocateCanonicalEventIdentity.v0.2.2
algorithm/ValidateEventPredecessors.v0.2.2
algorithm/OrderReadyEventSet.v0.2.2
algorithm/ValidateSubmissionDescendant.v0.2.2
algorithm/ValidateCandidateEvidenceBindings.v0.2.2
algorithm/ValidateBundleRootClosure.v0.2.2
algorithm/ValidateCanonicalCoverage.v0.2.2
algorithm/ValidateEntryExecutionBinding.v0.2.2
algorithm/ValidateC4C5EntryCohort.v0.2.2

identity/CanonicalEventPresequence.v0.2.2
identity/CanonicalEvent.v0.2.2
identity/CanonicalEventSet.v0.2.2
identity/CanonicalArtifactSet.v0.2.2
identity/CanonicalCoverage.v0.2.2
identity/CanonicalBundleScope.v0.2.2
identity/CanonicalBundle.v0.2.2
identity/TargetCandidateEvidenceBinding.v0.2.2
identity/PivotEvaluationInputs.v0.2.2
identity/TargetEvaluationInputs.v0.2.2
identity/SharedEntryRequest.v0.2.2
identity/SharedEntryOrder.v0.2.2
identity/SyntheticManagementRequest.v0.2.2
identity/SyntheticManagementOrder.v0.2.2
identity/SharedEntryEvent.v0.2.2
identity/EntryExecutionBinding.v0.2.2
identity/AccountMismatchDetails.v0.2.2
identity/SyntheticFatalDetails.v0.2.2
```

Slice C local review必须证明：34 payload schemas逐项 exact、event identity/full
event-array preimage、multiple-target evidence、fatal bundle closure、C4/C5 trace
与 coverage branch没有 inherited/prose fallback。

### 11.4 Review slice D — reducer policy and immutable management ledger

```text
schema/ReducerPriorityPolicy.v0.2.2
schema/StopUpdateRule.v0.2.2
schema/TargetUpdateRule.v0.2.2
schema/DataHealthRule.v0.2.2
schema/OperationalOverrideRule.v0.2.2
schema/PiExitPolicy.v0.2.2
schema/ManagementLedgerBindings.v0.2.2
schema/LedgerIdentity.v0.2.2
schema/LedgerTimes.v0.2.2
schema/LedgerInputDescriptor.v0.2.2
schema/LedgerInputs.v0.2.2
schema/LedgerLevels.v0.2.2
schema/LedgerQuantities.v0.2.2
schema/LedgerRisk.v0.2.2
schema/LedgerOrderRow.v0.2.2
schema/LedgerCosts.v0.2.2
schema/LedgerReconcile.v0.2.2
schema/BarrierAuthority.v0.2.2
schema/LedgerDecision.v0.2.2
schema/LedgerOperator.v0.2.2
schema/ManagementLedgerRecord.v0.2.2
schema/ManagementLedger.v0.2.2

algorithm/ReducerPriorityRank.v0.2.2
algorithm/ValidatePiExitPolicy.v0.2.2
algorithm/BuildLedgerGenesis.v0.2.2
algorithm/MapArtifactDescriptor.v0.2.2
algorithm/ValidateSnapshotOrderSet.v0.2.2
algorithm/AccountProofTime.v0.2.2
algorithm/ReduceManagementEvent.v0.2.2
algorithm/ProjectOrderRows.v0.2.2
algorithm/ProjectInventoryAndCosts.v0.2.2
algorithm/ProjectRiskInvariant.v0.2.2
algorithm/ProjectReconcile.v0.2.2
algorithm/ProjectDecision.v0.2.2
algorithm/EncodeLedgerRecord.v0.2.2
algorithm/ReplayManagementLedger.v0.2.2

identity/ReducerPriorityPolicy.v0.2.2
identity/PiExitPolicy.v0.2.2
identity/ManagementLedger.v0.2.2
identity/ManagementGenesis.v0.2.2
identity/ManagementGenesisInputs.v0.2.2
identity/ManagementEvent.v0.2.2
identity/ManagementRecordInputs.v0.2.2
identity/ManagementLedgerRecord.v0.2.2
identity/CanonicalEventEnvelope.v0.2.2
```

Slice D local review必须证明：34-kind rank、STOP_ACK complement、全部 20 descriptor
mapping、Genesis、state×event reducer、orders、risk/cost/reconcile、record hash与
replay都是 direct nodes；不得引用 v0.2.1 algorithm body。

### 11.5 Review slice E — pivot, target, path and label

```text
schema/ThreePointTargetCandidate.v0.2.2
schema/WindowExtremeTargetCandidate.v0.2.2
schema/ExitPolicyInstance.v0.2.2
schema/C4C5ExogenousPathManifest.v0.2.2
schema/PathBookPoint.v0.2.2
schema/PathReducerEvent.v0.2.2
schema/PathFundingEvent.v0.2.2
schema/PathInputBundle.v0.2.2
schema/LabelBindings.v0.2.2
schema/FirstHitLabelPolicy.v0.2.2
schema/FirstHitLabelEnvelope.v0.2.2

algorithm/EvaluatePivot.v0.2.2
algorithm/BuildTargetCandidates.v0.2.2
algorithm/SelectTargetWinner.v0.2.2
algorithm/BuildPathGrid.v0.2.2
algorithm/ValidateC4C5ExogenousPath.v0.2.2
algorithm/BuildPathInputBundle.v0.2.2
algorithm/ArbitrateFirstHit.v0.2.2
algorithm/BuildFirstHitLabel.v0.2.2

identity/RSICrossEvent.v0.2.2
identity/DGridInput.v0.2.2
identity/PressureRun.v0.2.2
identity/G0ExecutableTouch.v0.2.2
identity/MasterOpportunity.v0.2.2
identity/TargetThreePoint.v0.2.2
identity/TargetWindowExtreme.v0.2.2
identity/ExitPolicyInstance.v0.2.2
identity/C4C5ExogenousPathManifest.v0.2.2
identity/ZeroGridSharedCause.v0.2.2
identity/PathFundingEvents.v0.2.2
identity/PathInputBundle.v0.2.2
identity/FirstHitLabelPolicy.v0.2.2
identity/NoEntryExecution.v0.2.2
identity/ControlAbstainTerminal.v0.2.2
identity/LabelCensorTerminal.v0.2.2
identity/LabelRecord.v0.2.2
```

Slice E local review必须证明：G0 `(rounded_price,grid_time_us)` dedup、target实际
artifact IDs、C4/C5 path equality、zero-grid、funding/path prefix、STOP_FIRST
与 label union均为 direct semantics。

### 11.6 Review slice F — receipts and implementation identity

```text
schema/ContractDigestReceipt.v0.2.2
schema/DirectASTReviewReceipt.v0.2.2
schema/DirectASTReviewSourceArtifact.v0.2.2
schema/DirectASTReviewClause.v0.2.2
schema/ImplementationFile.v0.2.2
schema/ImplementationManifest.v0.2.2
schema/ImplementationManifestReceipt.v0.2.2

algorithm/ValidateContractDigestReceipt.v0.2.2
algorithm/ValidateImplementationManifest.v0.2.2
algorithm/ValidateImplementationManifestReceipt.v0.2.2

identity/ContractDigestReceipt.v0.2.2
identity/DirectASTReviewReceipt.v0.2.2
identity/ImplementationFileSet.v0.2.2
identity/ImplementationIdentity.v0.2.2
identity/ImplementationManifest.v0.2.2
identity/ImplementationEntrypointResolution.v0.2.2
identity/ImplementationCapabilityScan.v0.2.2
identity/ImplementationManifestReceipt.v0.2.2
```

Slice F local review必须证明：contract/AST/implementation三者单向绑定；code SHA唯一
等于 PASS manifest digest；没有 self-reference或实际 file-set逃逸。

---

## 12. Root exports

`root_exports` 必须与下列 fixed array exact equality；多一项、少一项或顺序
不同均拒绝：

```text
algorithm/BuildFirstHitLabel.v0.2.2
algorithm/CalculateEntryDecision.v0.2.2
algorithm/ReplayManagementLedger.v0.2.2
algorithm/ValidateBundleRootClosure.v0.2.2
algorithm/ValidateCanonicalCoverage.v0.2.2
algorithm/ValidateContractDigestReceipt.v0.2.2
algorithm/ValidateImplementationManifest.v0.2.2
algorithm/ValidateImplementationManifestReceipt.v0.2.2
identity/DirectASTReviewReceipt.v0.2.2
routing/ReducerPayload.v0.2.2
schema/CanonicalSyntheticCoverage.v0.2.2
schema/CanonicalSyntheticEventBundle.v0.2.2
schema/ContractDigestReceipt.v0.2.2
schema/DecisionInputBinding.v0.2.2
schema/DirectASTReviewReceipt.v0.2.2
schema/EntryExecutionBinding.v0.2.2
schema/FirstHitLabelEnvelope.v0.2.2
schema/ImplementationManifest.v0.2.2
schema/ImplementationManifestReceipt.v0.2.2
schema/ManagementLedger.v0.2.2
schema/ManagementLedgerRecord.v0.2.2
schema/PathInputBundle.v0.2.2
schema/PiExitPolicy.v0.2.2
schema/PolicyRegistry.v0.2.2
schema/SyntheticFixtureManifest.v0.2.2
```

该 array显式包含全部九个 immutable-successor roots：
EntryExecutionBinding、PathInputBundle、ManagementLedger、PiExitPolicy、
CanonicalSyntheticEventBundle、ReducerPayload、CanonicalSyntheticCoverage、
ManagementLedgerRecord、FirstHitLabelEnvelope。profile 外部 validator还必须
证明所有 nodes 从该 fixed set可达；若 inventory node不可达，应修复显式
body reference，不得增加临时 root或保留 orphan。

---

## 13. External review receipt 与 exhaustive clause trace

`DirectASTReviewReceipt.v0.2.2` 是完整 AST 生成后由 profile 外部 validator与
独立 Sol reviewer共同出具的 downstream gate。AST 内
`schema/DirectASTReviewReceipt.v0.2.2` 与
`identity/DirectASTReviewReceipt.v0.2.2` 只定义 receipt wire shape和 hash；
实际 receipt bytes、判定过程与 validator implementation均不进入 AST，不得
被 AST algorithm调用，也不提供 runtime trading semantics。

Receipt exact keys：

```text
receipt_version
semantic_source_raw_sha256
profile_raw_sha256
direct_ast_raw_sha256
direct_ast_sha256
source_artifacts
clauses
unmapped_clause_ids
untraced_node_ids
review_status
receipt_sha256
```

Exact literals：

```text
receipt_version =
  "rsi-mtf-drl-pm.direct-ast-review-receipt.v0.2.2"
semantic_source_raw_sha256 =
  "43eedbee0a10cf0254721052c1aca23baf027a90f879739ec33b48180cfd87a6"
review_status = "PASS"
```

失败审查只产生 REWORK report，不得产生带其他 status的 receipt。
Digest bindings必须同时满足：

```text
profile_raw_sha256 =
  SHA256(exact profile bytes)
  = direct AST.profile_raw_sha256

semantic_source_raw_sha256 =
  direct AST.source_authority.semantic_source_raw_sha256

direct_ast_raw_sha256 =
  SHA256(exact direct AST file bytes)

direct_ast_sha256 =
  parsed direct AST.ast_sha256
  = independently recomputed §9 digest
```

`SourceArtifact` exact keys：

```text
source_file_id,path,size_bytes,raw_sha256
```

```text
source_file_id:one of the five exact identifiers below
path:the corresponding exact ASCII path below
size_bytes:positive safe integer
raw_sha256:Sha256
```

`source_artifacts` 必须与下列五项 exact set equality，并按
`source_file_id` ASCII升序；三项 immutable v0.2.1 source与 pre-profile
semantic source的 size/hash必须由 §1固定 hash重算，profile项必须匹配
external validator实际读取的本 profile immutable bytes：

```text
ADDENDUM_V0_2_1:
  RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_1.md

CONTRACT_V0_2:
  config/rsi_mtf_drl_pm.research_contract.v0_2.json

CORE_V0_2_1:
  CORE_TRADING_THEORY.md

DIRECT_AST_PROFILE_V0_2_2:
  RSI_MTF_DRL_PM_DIRECT_AST_PROFILE_v0_2_2.md

SEMANTIC_V0_2_2_PRE_PROFILE:
  RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_2.md
```

`Clause` exact keys：

```text
clause_id
source_file_id
start_byte_inclusive
end_byte_exclusive
raw_slice_sha256
disposition
target_node_ids
```

```text
clause_id:StableId
source_file_id:SourceArtifact.source_file_id
start_byte_inclusive:nonnegative safe integer
end_byte_exclusive:positive safe integer
raw_slice_sha256:Sha256
disposition:closed enum below
target_node_ids:sorted unique array<NodeId>
```

`clauses` 不是作者抽样。对每个 SourceArtifact，external validator从 byte 0
开始，把每个 physical UTF-8 line（包括末尾 `0x0A`）建成一个 Clause；若最后
一行没有 LF，则最后的 non-empty remainder为一个 Clause。空文件拒绝。按
`(source_file_id,start_byte_inclusive)` 排序后，每个文件的 ranges必须无缝、
无重叠覆盖 `[0,size_bytes)`。公式：

```text
raw_slice_sha256 =
  SHA256(exact source bytes[start_byte_inclusive:end_byte_exclusive])

clause_id =
  ID("rsi-mtf-drl-pm-source-clause/v0.2.2", {
    source_file_id,
    start_byte_inclusive,
    end_byte_exclusive,
    raw_slice_sha256
  })
```

`disposition` 封闭为：

```text
ENCODED
REPLACED
CONTEXT_ONLY
```

本 release 的可接受规则：

- `ENCODED` 与 `REPLACED` 的 `target_node_ids` 必须非空、存在于 direct AST、
  去重并升序；
- §1.4.5 列出的 thirteen exact ranges必须为 `REPLACED`，且 target set包含表中
  required nodes；
- `CONTEXT_ONLY` 只允许 raw line去掉 LF、可选 CR及两端 ASCII space/tab后为空，
  或 trimmed ASCII bytes匹配 exact regex
  `^\x60{3}[A-Za-z0-9_-]*$`、`^---$`、
  `^\|?[ :]*-{3,}[ :|-]*\|?$` 三者之一；target必须为空；
- `SEMANTIC_V0_2_2_PRE_PROFILE` byte interval
  `[103318,116811)` 是被本 profile §0整体替换的旧 §12.9 transform route；
  其中所有非 CONTEXT_ONLY clauses都必须为 `REPLACED`并绑定至少一个
  replacement node，禁止静默删除；
- 其他所有 content line必须是 `ENCODED` 或 `REPLACED`，不能靠作者声明
  context/irrelevant逃逸。

五个 source files均不存在 `NON_NORMATIVE` disposition；该 token不属于
Clause grammar，出现即 receipt schema invalid，而不是可列入 allowlist的
violation。

external validator必须独立重算：

```text
unmapped_clause_ids =
  sorted clause_id set for any range/disposition/target rule violation

untraced_node_ids =
  sorted AST NodeIds absent from the union of target_node_ids
  over ENCODED and REPLACED clauses
```

serialized fields必须逐字等于重算结果。`review_status="PASS"` 的必要条件是：

```text
unmapped_clause_ids=[]
untraced_node_ids=[]
all source sizes and raw hashes match
all Clause raw hashes and ids match
all AST/profile/global-closure checks pass
independent Sol semantic review passes on the same exact AST bytes
```

Receipt hash：

```text
receipt_sha256 =
  ID("semantic-provenance-receipt/v0.2.2",
     entire receipt object excluding receipt_sha256)
```

`identity/DirectASTReviewReceipt.v0.2.2.domain_ascii` 必须逐字等于
`semantic-provenance-receipt/v0.2.2`，且它的 parameters/preimage必须逐字段
实现上述公式；不允许第二种 receipt identity。

receipt 只证明同一 exact AST 的 conformance/provenance gate；AST node不得通过
source range读取语义，final release theory也不得把该 receipt改写成市场
有效性证据。

---

## 14. Dependency-neutral Terra / Sol protocol

Review slices严格执行：

1. Terra high在同一个 whole-AST workspace中物化 slice nodes、外部 validator
   tests与 negative tests；不得创建 `algorithm/ValidateDirectAST`；
2. Terra 不改本 profile、pre-profile semantic source或 immutable source；
3. slice body可以 forward-reference §11封闭 inventory中的 exact NodeId，且
   external checker必须验证预期 target kind；禁止 placeholder node、
   placeholder digest、空 body、`unchanged` 或 deferred value；
4. Terra 报告 slice node key set、node-byte SHA、node digest、全部 outbound
   refs、static type-check与实际测试事实；
5. Sol ultra逐 node审查 exact fields、constraints、algorithm与 source clauses，
   只可给 `LOCAL_NODE_REVIEW_PASS` 或 `REWORK`；
6. local pass不宣称 ref closure、AST authority或 source coverage；任一 target
   node bytes变化会使全部 reverse-dependent local reviews失效并重审；
7. 所有 slices local pass后，Terra才按 §2一次性组装 single AST，固定
   `status="IMMUTABLE_REVIEW_BYTES"`，计算 node index、AST digest与 raw SHA，
   然后停止写入；
8. profile 外部 validator对该 exact bytes执行 §10 closure、§13 source
   partition与 negative tests；独立 Sol reviewer审查同一 raw/AST SHA；
9. 只有全部检查通过，external process才生成
   `DirectASTReviewReceipt.v0.2.2`；不得修改 AST status或任何 byte；
10. `final_release_theory_path` pin semantic/profile raw SHA、同一 AST
    path/size/raw/AST SHA与 receipt SHA，且 §1.2 semantic source path仍为
    43eed/136468后，才可授权 P0-RSI-01C。

因此 A/B 对 D/E 的依赖是已声明 closed-inventory reference，不是“先 PASS
再引用”的伪拓扑。任何 slice 都不能单独成为可执行 contract或 authority；
global reference closure只在完整 AST exact bytes上成立。

---

## 15. Profile acceptance

本 profile 可交 Terra 前，Sol reviewer 必须确认：

- authority graph无环，且 direct AST显式绑定
  `43eedbee0a10cf0254721052c1aca23baf027a90f879739ec33b48180cfd87a6`
  semantic-source raw SHA；
- §1.2 semantic source path永久不改，用户可读最终理论只写独立
  `final_release_theory_path`；
- frozen §12.1/§12.10 的 SchemaTransformReceipt/AST_PATCH authority已由
  §1.4 direct receipt fields、identity formulas与 build sequence完整替换；
- NodeId/NodeEnvelope/TypeExpr/Expr/Statement/body union均有 exact grammar；
- opcode registry、static type signatures、NodeId kind compatibility与
  literal registry封闭；
- BYTES primitive只物化 internal `type/Bytes`；OBJECT产生 named schema，
  ROUTING验证 exact value_path；
- 五个 decimal wire TYPE逐一绑定 exact ValidateDecimal body，wire STRING与
  evaluator DecimalValue分离，所有 numeric consumer显式 parse且 negative
  lexical/range corpus拒绝；
- `type/MarketSourceObject` 是四种 source schema的唯一 closed union，所有
  variant field access经 exhaustive MATCH_NARROW，projection accessor无
  first-match或 fallback；
- 八个 selector的 exact returns是成功 object/ordered array与各自 status
  T_ENUM的 closed union；UNKNOWN、CONFLICT、COVERAGE_CONFLICT、
  RULE_SNAPSHOT_CONFLICT与 ACCOUNT_SNAPSHOT_CONFLICT没有 nullable/exception
  collapse；
- NOTIONAL/APPLY_BPS/SCALE/RATIO、FLOOR_DIV/CEIL_DIV/MOD与 decimal
  left-fold顺序足以表达核心 ledger/path金融量纲公式；
- NodeId prefix与 node_kind exact equality；
- 无 raw ID、任意 string/json literal或自由 prose node逃逸；
- 307-node inventory 显式覆盖九个原 inherited successor、34 payload、20 artifact
  descriptor、ledger nested objects、path/label、缺失 identity与
  implementation manifest；Slice A identity inventory仍为 exact 23，新增项只有
  非 identity `type/MarketSourceObject`；
- review slices允许的 forward refs只命中封闭 inventory且不使用 placeholder；
- root_exports与 §12 fixed array exact equality；
- AST bytes在审查前一次固定，审后不改 status；conformance只由 profile外部
  validator及 exact-SHA PASS receipt授予；
- Clause universe完整覆盖五个 source files的全部 bytes，unmapped/untraced
  fields由 external validator重算，disposition不存在 NON_NORMATIVE或静默
  remove escape，receipt不进入 runtime authority；
- 用户、市场、数据、回测与交易权限没有扩大。

本 profile PASS 只表示“可以开始 direct AST transcription”；不表示任一 AST
slice、contract、implementation、synthetic system或市场理论已通过。
