# Slice A identity fragment build report

Status: `LOCAL_FRAGMENT_WRITTEN / E0 / NOT_A_REVIEW_RECEIPT`

Authority checked before writing:

- Profile: `RSI_MTF_DRL_PM_DIRECT_AST_PROFILE_v0_2_2.md`, SHA-256 `4971a337605b7d3bbfdae3657a47498c2cfeb2d055f0e861339c57e02968aa48`, 2,252 lines, 82,244 bytes.
- Semantic source: `RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_2.md`, SHA-256 `43eedbee0a10cf0254721052c1aca23baf027a90f879739ec33b48180cfd87a6`, 3,811 lines, 136,468 bytes.

Written artifact:

- `slice_a_identities.nodes.json`: root key `nodes`; exactly the 23 and only the 23 `identity/*` keys in Profile §11.1. The Profile itself explicitly records that Slice A has 23 identities. The file is compact UTF-8 ASCII JSON and parses successfully. Its raw bytes currently include one trailing LF introduced by the mandatory patch writer, so raw SHA-256 is `f9a8708881d22776946f22faa65e3753b38d7f82bf89e8181e1cd5d8a6ca19db`; the no-LF canonical payload SHA-256 is `d14068155a1c3f7b3bdf6847fe3298851d7f4f6b78b1243b5d441c95a3f55937`. This is a local fragment fact, not an AST byte or review result.

Node keys, direct-node digests, and outbound references:

| NodeId | Direct-node digest | Outbound references |
| --- | --- | --- |
| `identity/AccountRiskSnapshot.v0.2.2` | `e249ac601e8b8491ce62e5cbe69f3f346ec1923b67f77ae2992b5f2befb2eefc` | `schema/AccountRiskSnapshot.v0.2.2`, `type/StableId` |
| `identity/AggTrade.v0.2.2` | `51bce073c131e6c5e503404e6e140f158f2f33cd8ab207b623bc079ad2db418c` | `schema/AggTrade.v0.2.2`, `type/StableId` |
| `identity/BookSnapshot.v0.2.2` | `ac5504ef8cbaf9596a4613e0e989b269c2afe9e84050261b1f0afc3f17fd90b8` | `schema/BookSnapshot.v0.2.2`, `type/StableId` |
| `identity/Candidate.v0.2.2` | `1a805fcf940c2c5b91fc1b4b75d01237044ea706ff0d04ad1b387c83821b9096` | `type/Sha256`, `type/StableId` |
| `identity/ClosedMarkBar.v0.2.2` | `b3dd148e556dfc5f48053e52d620dc4684b194695765fb9082599d6c320057e7` | `schema/ClosedMarkBar.v0.2.2`, `type/StableId` |
| `identity/CompositeTheory.v0.2.2` | `3e9e333523d37b3127042c24c80bf7517577da89cc2b37a33f4f15dab132cf3f` | `type/Sha256`, `type/StableId` |
| `identity/CostPolicy.v0.2.2` | `7bd70f1b369aee59b5740e29db9b828c1727798f412ccb296fa5d4fc0c2f5bfb` | `schema/CostPolicy.v0.2.2`, `type/Sha256` |
| `identity/CoverageCoveredEventSet.v0.2.2` | `7e9f85fd2b423178383992270a486d69190e55822ad80cb6f9bbc5792594b4e6` | `schema/CoverageSeal.v0.2.2`, `type/Sha256` |
| `identity/CoverageSeal.v0.2.2` | `b0a8e35829c2561718f33df1173695c419fc758960b96073069b19f0f8878d3e` | `schema/CoverageSeal.v0.2.2`, `type/Sha256` |
| `identity/DataRolePolicy.v0.2.2` | `b411fa79a56fe4c9c90ab8b5591d37350382a7dad326dfb1a47cd0868a7af52b` | `schema/DataRolePolicy.v0.2.2`, `type/Sha256` |
| `identity/EntryPolicy.v0.2.2` | `c22cea8e2beb298d11cc75ecfc0bd7b65f969b188a8a69abf2bedf9eaf7e6ce4` | `schema/EntryPolicy.v0.2.2`, `type/Sha256` |
| `identity/EstimatorPolicy.v0.2.2` | `4abb99348940f2267f27dd74f63dc68b7fa8f9d376ecae32c318ea13807dc40d` | `schema/EstimatorPolicy.v0.2.2`, `type/Sha256` |
| `identity/ExitPolicyTemplate.v0.2.2` | `cd8f124bc36879b96d88784966e166490721bbcf9e043d32b7718a387121d94f` | `schema/ExitPolicyTemplate.v0.2.2`, `type/Sha256` |
| `identity/LabelPolicyBinding.v0.2.2` | `e7e5811d973e795ddd472c32c55e753d71c518ea64f0d3cfe30506429376e50f` | `schema/LabelPolicyBinding.v0.2.2`, `type/Sha256` |
| `identity/OpenInterest.v0.2.2` | `1d26140cf4a2d24a745848916d8bf3eb1e1d5c97d58d225af866d0da83d09d9b` | `schema/OpenInterest.v0.2.2`, `type/StableId` |
| `identity/ParameterSet.v0.2.2` | `30ab7cb8b3cba991a0f6632f06c30f320a4a77bcc9a4630fd8eebcadaa98c221` | `schema/ParameterSet.v0.2.2`, `type/StableId` |
| `identity/PolicyBundle.v0.2.2` | `4bdea3c273282b52bf3e74b067516a67c075ab8c84a279ad2b0adc1c7b55b420` | `schema/PolicyBundle.v0.2.2`, `type/Sha256` |
| `identity/PolicyRegistry.v0.2.2` | `86bb82f86f7db5d7d85e7db5708efed58135a676d928480675aac68d086bf7c2` | `schema/PolicyRegistry.v0.2.2`, `type/Sha256` |
| `identity/RiskPolicy.v0.2.2` | `b6c926484413fc1d27bd27baa04a4ae60ddb98b19d9e86b2b9a35813d2eb843e` | `schema/RiskPolicy.v0.2.2`, `type/Sha256` |
| `identity/SourceSelectorPolicy.v0.2.2` | `e47871d88a0f15aa92e7fbefac39af4c4d01ad6b853132409463d186d060801c` | `schema/SourceSelectorPolicy.v0.2.2`, `type/Sha256` |
| `identity/UPolicy.v0.2.2` | `d24fb4f09b545781b8f390d3ab3ee6dc2a67998955733d01ecb8ae8161d0d209` | `schema/UPolicy.v0.2.2`, `type/Sha256` |
| `identity/VenueInstrumentSnapshot.v0.2.2` | `e849f8810cde32ddc4c77eabca95010dae87505af80d323278960f818b17f939` | `schema/VenueInstrumentSnapshot.v0.2.2`, `type/StableId` |
| `identity/VenueRuleFingerprint.v0.2.2` | `ac6a23f63271731ab73ec0d09247c3e82e2a2d9118ff3267492246dbb4f5e1f6` | `schema/VenueInstrumentSnapshot.v0.2.2`, `type/Sha256` |

The unique outbound reference set is 19 Slice A schemas listed in the table plus `type/Sha256` and `type/StableId`; this identity fragment has no cross-slice outbound reference. `requires` was mechanically compared with every `T_OBJECT`/`T_REF` reference in each body: 23/23 exact. `domain_ascii` values are unique: 23/23.

No market data, historical data, backtest, adapter, paper execution, OMS, contract, validator, test, Profile, semantic source, or G1 package was read or changed by this fragment write. No global closure, AST digest, contract validity, strategy validity, or review PASS is asserted.
