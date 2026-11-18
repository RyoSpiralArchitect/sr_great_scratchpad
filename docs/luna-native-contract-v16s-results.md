# GPT-6 Luna Native Contract V1.6s: Standalone 結果記録

V1.6s は V1.5s と同じ semantic contract + flag lexicon + flag scope の
組み合わせを保持し、各 scenario に `distracted` ビュー(case の全レコード=
関連+distractor)を追加した standalone 系譜(parent: null、witness なし)。
引用規律をノイズありで測る、bounded authored distractor calibration であり、
retrieval efficacy や adoption 証拠としては扱わない。

## 条件

| | 値 |
|---|---|
| spec | `scenarios/luna_native_contract_v16s.json`(semantic contract + flag lexicon + flag scope + distracted ビュー、citation enum なし) |
| fresh_seed | 26110319(非重複は seed 構成上のもの) |
| source commit | `3900c6c`(実走時点の HEAD) |
| plan digest | `27e63e64c27a040e8cd4d5f4982845b7ab9932982690d911431ecb2c4da51bd2` |
| 実行日 | 2026-11-15(50/50 完走、停止なし) |

## 結果(25 paired views)

| | native | json-mode |
|---|---:|---:|
| provider_completed | 25/25 | 25/25 |
| caller_contract_ok | 25/25 | 25/25 |
| value_correct | 25/25 | 25/25 |
| flags_faithful | 25/25 | 25/25 |
| citations_visible / relevant / proof_covered | 25/25 | 25/25 |
| contract_success | **25/25** | **25/25** |
| all_25_passed | **あり** | **あり** |

paired: both 25、mean_delta 0.0。**25/25 ゲート達成**。

## 観測

- **distractor 混在でも引用規律は崩れなかった。** 訂正（2026-11-18）:
  凍結済み plan の distracted 呼び出しは20件（10 scenarios×2群）。いずれも
  evidence は関連IDのみの部分集合に収まった。distractor を拾う失敗は0件。
- **enum なしでも散文引用は今回出なかった。** ただし distracted ビューでは
  関連レコード3件に distractor 18件を追加した合計21件で、ノイズ量は
  authored calibration の範囲。noise 負荷を上げた版は別 spec が必要。
- **意味契約+lexicon+scope の組み合わせは50/50 を通した。** V1.5s で残った
  native の散文引用失敗が今回出なかったのは、ケース差(新 seed)・
  prompt 差(契約文の組み合わせが同じでも question 構成は同型)のどちらとも
  切り分けられず、再現性の記述的観測として残す。

## 使用量

| | native | json-mode | 合計 |
|---|---:|---:|---:|
| prompt tokens | 34,220 | 32,027 | 66,247 |
| completion tokens | 2,885 | 2,637 | 5,522 |
| total tokens | 37,105 | 34,664 | 71,769 |

usage 不明0件。50 calls で逐次約135秒(速度比較の意図なし)。

## 再現情報

| ファイル | SHA-256 |
|---|---|
| `plan.json` | `475f6f69851a66d81ed39967a22e9f30a86c4de1dc10b7fdeef1a2152140a579` |
| `execution/result.json` | `7c4154319efdf66975d52001c83fdd59b59773b7e5aaa2827bc52309438a0f39` |
| `execution/attempts.jsonl` | `27e7c687284335b083614574830e2a77ad1f204f52caecfb11f1723b690e2fc2` |
| `execution/responses.jsonl` | `36494ce8909005741118438b0d8e63a486c8cba04896086ac266573a9430965e` |
| `summary.json` | `0f62fd7191946bd16a24812b010073137d63abc481425b2301a8da44d34491b6` |

run ディレクトリは `.great_scratchpad/runs/luna-native-contract-v16s-20261115`。
旧 summary の集計フラグは15件固定だったため、表の25/25は
各群25件の `contract_success` に基づく。元のファイルは変更していない。

## 次の磨き方

1. **retrieval pilot は依然として未承認。** 25/25 は authored calibration の
   ゲート通過であり、retrieval 化・adoption 化の根拠には使えない。
2. **noise 負荷の段階的上昇**: distractor 数を増やした spec(例: 1.6x/2x
   distractor ratio)は新規 spec と新 seed が必要。今回は関連:distractor が
   低いので、より重い条件での限界測定。
3. **native の散文引用の再現条件を切る**: V1.5s で出て V1.6s で出なかった
   差は、ケース・distractor・契約文のどれかに依存する。enum ありで再現
   不能になること(V1.2s)は確認済みなので、enum-なし版で distractor 数を
   上げると失敗の閾値が見える可能性がある。
