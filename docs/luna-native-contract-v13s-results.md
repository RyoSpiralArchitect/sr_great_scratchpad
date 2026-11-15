# GPT-6 Luna Native Contract V1.3s: Standalone 結果記録

V1.3s は witness 鎖を持たない**独立系譜**の単発キャンペーンであり、V1/V1.1 との
系譜的比較・正規 V1.3 実行としての主張は一切行わない。タスク内容・両群・予算・
ゲートは V1.3 と同一で、違いは系譜だけである。

## 条件

| | 値 |
|---|---|
| spec | `scenarios/luna_native_contract_v13s.json`(semantic contract あり、citation enum なし) |
| fresh_seed | 26110315(系譜との非重複は seed 構成上のもので、byte witness による証明なし) |
| source commit | `2a4d0cc`(実走時点の HEAD) |
| plan digest | `aad57b4089cc79b3a795ded8434cbd2720973667e7038d89dd6b84739b1d69a8` |
| 実行日 | 2026-11-15(30/30 完走、停止なし) |

## 結果

| | native | json-mode |
|---|---:|---:|
| provider_completed | 15/15 | 15/15 |
| caller_contract_ok | 15/15 | 15/15 |
| value_correct | 15/15 | 15/15 |
| flags_faithful | 14/15 | 14/15 |
| citations_visible / relevant / proof_covered | 15/15 | 15/15 |
| contract_success | **14/15** | **14/15** |
| all_15_passed | なし | なし |

paired: both 14 / neither 1、mean_delta 0.0。15/15 ゲートは両群とも**未達**。

## 唯一の失敗

`hold-dominates source` が両群同一内容で失敗:期待 `urgent: "unknown"` に対し
`"unobserved"` を返した。value(HOLDP…)、evidence(m005+m009)、proof いずれも正解で、
失敗は flag 状態の unknown/unobserved 区別のみ。意味契約を明示した上でもこの区別は
1ビュー残った、という記録であって、意味契約が無効だった/有効だったとは言わない。
両群同一点での失敗はペア内差ではなく共有点であり、形式要因(native 型強制)とも
混同できない。

## 使用量

| | native | json-mode | 合計 |
|---|---:|---:|---:|
| prompt tokens | 12,997 | 11,696 | 24,693 |
| completion tokens | 1,867 | 1,683 | 3,550 |
| total tokens | 14,864 | 13,379 | 28,243 |

usage 不明の呼び出しは0件。逐次呼び出しの合計時間は約92.8秒だが、初回スキーマ
処理や service 状態を分離しておらず一般的な速度比較ではない。

## 再現情報

| ファイル | SHA-256 |
|---|---|
| `plan.json` | `72601a53ede4a7c6e59f928cd3e6e6154da3c4e2592ae46ac830fbc47f9e8231` |
| `execution/result.json` | `fd603134c0babb9fdfef5451c98bc464db3e56416195dbf32f955418525739b9` |
| `execution/attempts.jsonl` | `db0097bc7f0dd1f1a420a44808361644bf33fadf4bc6d2333b3a2496bc49acdc` |
| `execution/responses.jsonl` | `a608984b73b84c08282499944519b1da904414b769f3f521faffa406c2b3f848` |
| `summary.json` | `e5aa5cb54e00952ca03ba38a511ad68149f68852199a07ee5a2718ebda91b869` |

run ディレクトリは `.great_scratchpad/runs/luna-native-contract-v13s-20261115`。
本 runner は `audit.json` を書かないため、台帳監査は `audit()` の再評価で確認済み
(result/attempts/responses/summary の突合は report 生成時に全件一致)。

## 読み方の上限

- 30件は10ケース×条件視点の**従属ビュー**であり、検索失敗・未知会話への頑健性や
  retrieval/adoption の証拠ではない。
- standalone である以上、V1.1 との差を系譜的比較とは言えない。witness 版 V1.3 の
  実行は artifact が入手可能になった時点で別途行う。
- unknown/unobserved の失敗1件は測定された失敗であり、再採点や通過への書き換えは
  行わない。

## 走後分析(2026-11-15 追記)

1. **失敗の根本原因は意味契約の語彙未規定**。ケース生成側は `unknown` を「未確認」、
   `unobserved` をフラグ節の欠落で表現するが、その対応表は `STATE_SYSTEM` にのみ
   存在し、本 helper の SYSTEM も `Semantic contract:` ブロックも語彙対応を定義して
   いなかった。モデルは「未確認」を「未観測」と読む解釈を両群同一点で選択した。
   形式(native schema)の問題ではなく、示された意味契約の欠落であり、測定として
   残したまま次の版で分離検証する。
2. **引用頑健性は未測定**。全ビューで distractor レコードは供給されず(生成されるが
   `kind != "distractor"` で除外)、citations_relevant 15/15 はノイズなし条件での値。
   distractor 混在ビューは将来の別 spec が担う。
3. **native スキーマ転送オーバーヘッドは一様**。全ペアで native が約+104 input
   tokens/call。output は native +184 total(3,550 中)。cached_tokens・reasoning
   tokens は指標として解釈しない。

## 次の磨き方

1. **V1.4s**(実装・凍結済み): V1.3s + `Flag lexicon:` 1行(有効=enabled; 無効=disabled;
   未確認=unknown; 未記載=unobserved)を両群 question に付与。語彙要因だけを分離する
   standalone 比較。実走は別途承認。
2. distractor 混在ビューを持つ将来 spec(未実装): 引用規律をノイズあり条件で測る。
   view 追加で cells が増えるため、予算・ペア構成は新 spec で再定義する。
3. witness 版 V1.3 は artifact 到達時に本走し、V1.3s との standalone/witnessed の
   関係を結果文書で明示する。
