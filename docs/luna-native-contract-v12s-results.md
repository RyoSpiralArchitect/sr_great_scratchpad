# GPT-6 Luna Native Contract V1.2s: Standalone 結果記録

V1.2s は citation enum 要因だけを両群 question の埋め込みスキーマで
切り分けた standalone 系譜(parent: null、witness なし)。
semantic contract・flag lexicon・flag scope は**いずれも付けない**。
V1/V1.1 との系譜的比較・同入力比較の主張は行わない。

## 条件

| | 値 |
|---|---|
| spec | `scenarios/luna_native_contract_v12s.json`(citation_enum のみ) |
| fresh_seed | 26110318(非重複は seed 構成上のもの) |
| source commit | `3900c6c`(実走時点の HEAD) |
| plan digest | `183df250d2c97910786f2cc797c1e9eeb4a837b7b912ccbacce110f3ef13b1df` |
| 実行日 | 2026-11-15(30/30 完走、停止なし) |

## 結果

| | native | json-mode |
|---|---:|---:|
| provider_completed | 15/15 | 15/15 |
| caller_contract_ok | 14/15 | 14/15 |
| value_correct | 14/15 | 14/15 |
| flags_faithful | 15/15 | 15/15 |
| citations_visible / relevant / proof_covered | 15/15 | 15/15 |
| contract_success | **14/15** | **14/15** |
| all_15_passed | なし | なし |

paired: both 14 / neither 1、mean_delta 0.0。

## 失敗分析

### enum は引用失敗を完全に防いだ

`complete-join source` を含め全30件で引用が供給IDの正確な部分集合だった
(citations_visible/relevant 30/30)。V1・V1.4s・V1.5s で3回再現した
散文修飾引用は、native 側の provider 型強制で物理的に不可能になり、
json-mode 側も enum を見たまま従った。引用規律に関しては
**enum は有効に見える**が、non-enum 実走との同ケース対照ではないので
記述的的観測として扱う。

### 新たな失敗は両群同型の誤収束

`urgent-enabled partial-rule` で両群とも
`status: known, value: FASTPd04da` を返したが、期待は
`status: unknown, value: null`(rule が途中で切れた partial ビュー)。
tag は wrong-value のみで、citation/flag/proof は全て正解。
**意味契約なしの素面では、partial chain を known として誤収束する**
観測であり、semantic contract が同種ビューを守っていた可能性を
逆方向から示唆する(こちらも同ケース対照ではないので仮説止まり)。

## 使用量

| | native | json-mode | 合計 |
|---|---:|---:|---:|
| prompt tokens | 7,784 | 6,330 | 14,114 |
| completion tokens | 1,569 | 1,566 | 3,135 |
| total tokens | 9,353 | 7,896 | 17,249 |

usage 不明0件。契約文を外した分 V1.4s/V1.5s より input が小さい
(約17k vs 29k tokens)が、入力差は契約条件の差であり速度・効率の
主張には使わない。逐次呼び出し合計約93秒。

## 再現情報

| ファイル | SHA-256 |
|---|---|
| `plan.json` | `37d148e86539716d7d3469c075f4cad45ef0748121a6a5068edd649339817496` |
| `execution/result.json` | `da5bdf7ca51ed2a1d6ba737167f837ef155e11ff256e03eee1087298de053c76` |
| `execution/attempts.jsonl` | `59a544d2ae08c50d86e01a9884e9dc2cce8058f5e63609a87f5626cc7a11a52e` |
| `execution/responses.jsonl` | `ee6f5a94bdd38aee896df94dfde1759fb8bbeb244a9a584fdffc8254e9516f13` |
| `summary.json` | `fb3f9a4b311dd74423f0f200e7ffc84a081d445db413fcab36f3b7f978107678` |

run ディレクトリは `.great_scratchpad/runs/luna-native-contract-v12s-20261115`。
