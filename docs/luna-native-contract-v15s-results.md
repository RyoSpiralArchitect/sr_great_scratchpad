# GPT-6 Luna Native Contract V1.5s: Standalone 結果記録

V1.5s は V1.4s と同じ standalone 系譜規律(parent: null、witness なし)で、
semantic contract + flag lexicon を保持したまま `Flag scope:` 1行
(非ルーティング家族では flags: {})だけを両群 question に追加した
単一要因比較。V1/V1.1/V1.3 との系譜的比較・同入力比較の主張は行わない。

## 条件

| | 値 |
|---|---|
| spec | `scenarios/luna_native_contract_v15s.json`(semantic contract + flag lexicon + flag scope、citation enum なし) |
| fresh_seed | 26110317(非重複は seed 構成上のもの) |
| source commit | `3900c6c`(実走時点の HEAD) |
| plan digest | `c15d31c56c77c4a8fc3419eb70539305b31d0e68a6bf72f26f290bcb5fb5a35d` |
| 実行日 | 2026-11-15(30/30 完走、停止なし) |

## 結果

| | native | json-mode |
|---|---:|---:|
| provider_completed | 15/15 | 15/15 |
| caller_contract_ok | 14/15 | 15/15 |
| value_correct | 15/15 | 15/15 |
| flags_faithful | 15/15 | 15/15 |
| citations_visible / relevant / proof_covered | 14/15 | 15/15 |
| contract_success | **14/15** | **15/15** |
| all_15_passed | なし | **あり** |

paired: both 14 / control-only 1、mean_delta -0.0667。

## 失敗分析

### scope 行は flag 混入を防いだ(仮説の裏付け候補)

V1.4s で json-mode が distributed-join に `{urgent, hold: unobserved}` を出力した
flag-shape 失敗は、全30件で flag 混入を含めて再現しなかった
(flags_faithful 30/30)。fresh ケースなので確定的証明ではないが、
lexicon 語彙のプライミング仮説と、scope 行による抑制仮説の両方と整合する
記述的観測として残す。

### native の散文修飾引用は3回連続で再現

`complete-join source` の native は evidence に
`"依頼 Qb5995 の担当班は Tab34c（m001）。"` のように本文+(ID)の文字列を返し、
供給ID の部分集合検査に不合格(value/flags/proof は正解)。
V1・V1.4s に続く3回目の同型失敗で、**enum なしでは散文引用が再発する**
傾向が複数観測として強まった。V1.2s の enum 版の実測が直接の対照になる。

## 使用量

| | native | json-mode | 合計 |
|---|---:|---:|---:|
| prompt tokens | 13,679 | 12,378 | 26,057 |
| completion tokens | 1,604 | 1,397 | 3,001 |
| total tokens | 15,283 | 13,775 | 29,058 |

usage 不明0件。逐次呼び出し合計約84秒(速度比較の意図なし)。

## 再現情報

| ファイル | SHA-256 |
|---|---|
| `plan.json` | `f75edbcd855b9bf8501332ed6955b75b5d7ae3053a12f44d750612fe3d038daf` |
| `execution/result.json` | `2a5037e84f8065038d3ffd86ec1f8bf06131735384b3198c7a29c537319d66a8` |
| `execution/attempts.jsonl` | `a0cf8609751ca25ebe7a9d12bc75bda815f431424a1a8877303b2ced137b5c4b` |
| `execution/responses.jsonl` | `156f4da837f30ae58bd740712bb8c784e592dff37add67ba47d922c37a08e804` |
| `summary.json` | `13cd84fa9501b298ce62d7b004f20f530bf060f0e7624613b21f3e55f50fec35` |

run ディレクトリは `.great_scratchpad/runs/luna-native-contract-v15s-20261115`。
