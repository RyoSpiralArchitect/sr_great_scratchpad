# GPT-6 Luna Native Contract V1.4s: Standalone 結果記録

V1.4s は V1.3s と同じ standalone 系譜規律(parent: null、witness なし)で、
`Flag lexicon:` 1行だけを両群 question に追加した単一要因比較。
V1/V1.1/V1.3 との系譜的比較・同入力比較の主張は行わない。

## 条件

| | 値 |
|---|---|
| spec | `scenarios/luna_native_contract_v14s.json`(semantic contract + flag lexicon、citation enum なし) |
| fresh_seed | 26110316(非重複は seed 構成上のもの) |
| source commit | `75f7d0a`(実走時点の HEAD) |
| plan digest | `d6280e3a73662977c175d116cee7e6dd3ce3416ca83566a1380ae7c625e94bd3` |
| 実行日 | 2026-11-15(30/30 完走、停止なし) |

## 結果

| | native | json-mode |
|---|---:|---:|
| provider_completed | 15/15 | 15/15 |
| caller_contract_ok | 14/15 | 14/15 |
| value_correct | 15/15 | 15/15 |
| flags_faithful | 15/15 | 14/15 |
| citations_visible / relevant / proof_covered | 14/15 | 15/15 |
| contract_success | **14/15** | **14/15** |
| all_15_passed | なし | なし |

paired: both 14 / neither 1、mean_delta 0.0。15/15 ゲートは両群とも**未達**。

## 失敗分析

### V1.3s の語彙失敗は消えた

`hold-dominates source` を含め flag の unknown/unobserved 区別の miss は全30件で
再現しなかった。追加した1行が観測された区別の欠落を埋めたことと整合するが、
ケースが fresh(非同入力)なので、語彙要因の確定的証明ではなく記述的な一致として
扱う。

### 新たな失敗2件は別々の機序

両失敗は `complete-join source` ペアの**異なる**側面で起きた(ペア内差ではなく
それぞれ独立したタグ):

- **json-mode: flag 混入**(tag: schema/flag-shape/caller-contract)。distributed-join
  の flags は `{}` が契約だが `{urgent: unobserved, hold: unobserved}` を出力。
  value/citations/proof は正解。lexicon 行が urgent/hold 語彙を提示したことで
  非ルーティング家族への flag 発生を促した可能性は記録上の仮説であり、
  lexicon 追加の**負の効果候補**として残す(単一観測、因果は未確定)。
- **native: 散文修飾引用**(tag: missing-citation/invisible-citation/
  irrelevant-citation/caller-contract)。evidence が `"m001: 依頼…"` のように
  ID+本文を連結した文字列となり、供給IDの部分集合検査に不合格。flags/value/
  proof は正解。V1 の散文引用失敗と同型で、**enum なしでは再発しうる**ことを
  実測した。V1.2 の enum 版なら provider 型強制で防げるはずだが、それは未実走の
  予測であって本記録の結論ではない。

## 使用量

| | native | json-mode | 合計 |
|---|---:|---:|---:|
| prompt tokens | 13,509 | 12,208 | 25,717 |
| completion tokens | 2,085 | 2,017 | 4,102 |
| total tokens | 15,594 | 14,225 | 29,819 |

usage 不明0件。逐次呼び出し合計約98.0秒(速度比較の意図なし)。

## 再現情報

| ファイル | SHA-256 |
|---|---|
| `plan.json` | `77a23ab4350299350e050eecff873cfa7ed929832b3319bc327f874f4d227acc` |
| `execution/result.json` | `ce4b53c18adf89e0004dbf4bd351abcd96478f7ba33ffd15b8380cd71f3d25c3` |
| `execution/attempts.jsonl` | `00fd003b2294c5abf0cfc48a0daa96b5e29641547e6eccca46e45e5abb4f0dfc` |
| `execution/responses.jsonl` | `86fab0fc580a29f73c6ba6674d95992e835ba179c43874944b6c5d3e414fac9f` |
| `summary.json` | `096108fc2be78904766fd34ba24be981215011a891e9e2ea12f4273639b48c54` |

run ディレクトリは `.great_scratchpad/runs/luna-native-contract-v14s-20261115`。

## 次の磨き方

1. **非ルーティング家族への flag 抑制を意味契約に明示**(案: lexicon 行に
   「非ルーティング家族では flags は {}」を併記、または PROOF_INSTRUCTIONS に
   同旨を追記)。flag-shape 仮説を単一要因で再検証する spec が必要。
2. **distractor 混在ビュー**(未実装): 引用規律をノイズありで測る。cells 増加に
   伴い新 spec・新予算枠。
3. witnessed V1.2/V1.3 は artifact 到達待ち。V1.2s standalone をこの系譜で走る
   選択肢もある(enum 要因の非系譜測定)。
