# GPT-6 Luna Native Contract V1.8s: Standalone 結果記録

V1.8s は V1.6s の heavy-distractor 版。distractor_count を18→54に
パラメトリックに引き上げ、`distracted` ビューが57レコード
(関連3前後 + 54 distractor)を供給する standalone 系譜
(parent: null、witness なし)。strict 引用ゲートがどこで曲がるかを
測る authored-noise calibration であり、retrieval efficacy ではない。

## 条件

| | 値 |
|---|---|
| spec | `scenarios/luna_native_contract_v18s.json`(V1.6s + `distractor_count: 54`) |
| fresh_seed | 26110321(非重複は seed 構成上のもの) |
| source commit | `fc38ab0`(実走時点の HEAD) |
| plan digest | `142a3b36440a4e1b3b869f42eca5ccdaaca5717d87fcd58007d8743e41ae18e4` |
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

- **57レコード混在でも引用規律は曲がらなかった。** distracted の20件
  (10 scenarios×2群)すべてで evidence が関連IDのみの部分集合。
  distractor を拾う失敗・散文修飾・ID欠落は0件。
- **測定した noise 上限はまだゲート以下。** distractor 本文は
  「別依頼 X… の最終実行プールは ALT…」という定型で、関連レコードとの
  構造的類似は高いが distractor 同士は同型の繰り返し。54→さらに上げる
  より、**distractor の質(部分chainを持つ欺瞞的レコードなど)を変える**
  方向が次の有意な段階。
- prompt は distracted で約5.4万 tokens/件まで膨らむが、usage 不明0件、
  停止0件で完走。input 肥大は記録するのみで効率主張には使わない。

## 使用量

| | native | json-mode | 合計 |
|---|---:|---:|---:|
| prompt tokens | 56,336 | 54,143 | 110,479 |
| completion tokens | 2,840 | 2,550 | 5,390 |
| total tokens | 59,176 | 56,693 | 115,869 |

usage 不明0件。逐次呼び出し合計約141秒(速度比較の意図なし)。

## 再現情報

| ファイル | SHA-256 |
|---|---|
| `plan.json` | `7933359bb952200ee3a29c7d6fd416cc364d5bad8547c694e125fcc62541ab9c` |
| `execution/result.json` | `7b00497c95efd45b3bfd0430cf9cf2a75e457224db5240a658402f4844b90723` |
| `execution/attempts.jsonl` | `37f38e945598d8be60becfd0067afbd48c80ab0d8cd50e85aa492c8b34da6aa0` |
| `execution/responses.jsonl` | `ecf1192421f19da312fc8c92b3e7db99819b3aaeded52cd7c9c3bbde3efd241d` |
| `summary.json` | `1cddebaefda527aa6e4f5b6f1ea8f3f9454d7f8a7a37f0e02758a334b40c0129` |

run ディレクトリは `.great_scratchpad/runs/luna-native-contract-v18s-20261115`。

## 次の磨き方

1. **retrieval pilot は依然として未承認。** 連続ゲート通過でも authored
   calibration の範囲。
2. **量ではなく質で noise を上げる**: 関連 chain の途中の値を持つ
   distractor、同一 target の別時点レコード、ID 類似の別レコードなど、
   欺瞞性の高い distractor 型は generator 拡張 + 新 spec が必要。
3. **間欠的散文引用の発生率**: native・enum なし・complete-join source
   で5ドロー中3回。さらにドローを重ねるか、enum/構造側での対策
   (V1.2s で再現不能は確認済み)を採用判断するかは別途。
