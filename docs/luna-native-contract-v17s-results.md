# GPT-6 Luna Native Contract V1.7s: Standalone 結果記録

V1.7s は V1.5s と全く同じ入力条件(semantic contract + flag lexicon +
flag scope、citation enum なし、distracted なし)を新 seed で引き直した
standalone 系譜(parent: null、witness なし)の replication 走行。
V1.5s で3回目の再現となった native 散文修飾引用が、ケース差なのか
ビュー構成差なのかを測る第2ドロー。

## 条件

| | 値 |
|---|---|
| spec | `scenarios/luna_native_contract_v17s.json`(V1.5s と同一、seed のみ差分) |
| fresh_seed | 26110320(非重複は seed 構成上のもの) |
| source commit | `fc38ab0`(実走時点の HEAD) |
| plan digest | `ddb4f0c6b824d77d338d2c6d41328a864ca51e452124af38d96e9c699ff153d6` |
| 実行日 | 2026-11-15(30/30 完走、停止なし) |

## 結果

| | native | json-mode |
|---|---:|---:|
| provider_completed | 15/15 | 15/15 |
| caller_contract_ok | 15/15 | 15/15 |
| value_correct | 15/15 | 15/15 |
| flags_faithful | 15/15 | 15/15 |
| citations_visible / relevant / proof_covered | 15/15 | 15/15 |
| contract_success | **15/15** | **15/15** |
| all_15_passed | **あり** | **あり** |

paired: both 15、mean_delta 0.0。**15/15 ゲート達成**。

## 観測

- **散文修飾引用は再現しなかった。** complete-join source を含め全30件の
  evidence が供給IDの正確な部分集合。V1・V1.4s・V1.5s の3回の失敗と
  V1.6s・V1.7s の2回の成功を合わせると、enum なし条件での発生は
  **間欠的**(5ドロー中3回、いずれも native・complete-join source)という
  記述的整理が現在の限界。distractor 有無や契約文では切り分けられない。
- flag 混入・誤収束・語彙 miss は0件。意味契約+lexicon+scope の
  組み合わせは V1.6s・V1.7s・V1.8s(後続)で連続して全通しを記録した。

## 使用量

| | native | json-mode | 合計 |
|---|---:|---:|---:|
| prompt tokens | 13,666 | 12,365 | 26,031 |
| completion tokens | 1,613 | 1,405 | 3,018 |
| total tokens | 15,279 | 13,770 | 29,049 |

usage 不明0件。逐次呼び出し合計約84秒(速度比較の意図なし)。

## 再現情報

| ファイル | SHA-256 |
|---|---|
| `plan.json` | `3ea45ce105ef7e9130821b4e3716d23c2eb075e57a398d1b32f3805e045d6ac7` |
| `execution/result.json` | `d70d94033a5f54720bca42c5fbfbb61472308cb69169b0138800302a9a37a38e` |
| `execution/attempts.jsonl` | `7ba9d4699a2d9bc181a557b83c71ab3343d0d1b857862a517130646422ebb282` |
| `execution/responses.jsonl` | `163a98792d5430a1a92d350604914f5cabb0557169ab15377a3a60c52e2398cd` |
| `summary.json` | `f85e4af1174f7e3f8b7abde632f8570e8688689ec25bc97506264431008d7635` |

run ディレクトリは `.great_scratchpad/runs/luna-native-contract-v17s-20261115`。
