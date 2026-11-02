# GPT-6 Luna: 出力の型と、根拠の意味は別だった

## 結論

**今回の新ケースでは、native schemaの優位は観測されなかった。**
JSON modeは13/15、nativeは12/15の厳密通過だった。両方式とも出力の形は15/15で、
差は主に引用IDの表現とフラグの意味解釈に出た。APIによる型の強制は、根拠の
参照先や判断を確定してよい条件まで保証するものではない。

これはPR #11の契約校正であり、検索・記憶・会話能力の比較ではない。
15提示条件は10課題の投影で、独立な15標本でも一般的なモデル評価でもない。
両群とも15/15ゲートを満たさず、検索pilotは0回のまま維持した。

## 最初の停止を残す

[V1プロトコル](luna-native-contract-v1-protocol.md)を固定して実行したが、2/30で停止した。

1. nativeはAPI完了。unknown/nullとフラグは正しかったが、`evidence`に引用IDでは
   なく説明文を入れた。手元の検証が不通過にし、使用量796 tokensを保持した。
2. JSON modeはHTTP400。systemにはJSONと書いてあったが、APIは`input`本文にも
   `json`という語が必要と返した。モデル応答・usageは受け取れず、不明1件とした。

残り28枠は未実行であり、同じ枠の修復・再試行・差し替えはない。停止prefixの
保存済み集計にある差0は、対照側の生成がないためモデル同等性を意味しない。
最初の起動時にはshell設定の終了値でモデルプロセス起動前に止まった記録もあり、
これは別のlaunch noteとして保存した。実行フォルダもAPI attemptもなかった。

この停止を提示した後、協力者から新しい30回、合計32回の呼び出しについて
明示的な承諾を得た。[V1.1プロトコル](luna-native-contract-v11-protocol.md)では、
両方式の本文を`Output JSON schema`にし、新しいseed26110312を使った。
スキーマ、引用欄、根拠指示、採点、15条件、全通過ゲートは変えていない。
**V1.1は公開した互換性修正であり、事前登録済み初回実験とは呼ばない。**

## 完了したV1.1

- 指定モデル`gpt-6-luna`、Responses、高reasoning、出力上限4096、store=false。
- 新しい10課題・15提示条件を、native/JSON modeで各1回。計30回。
- 各対で同一の公開記録、JSON化した質問、schema文章、system、出力上限。
  変えるのはAPIの`text.format`だけ。nativeは実際の`call_structured_task`を使用。
- native先行8対、JSON mode先行7対。呼び出しはstateless。
- 全30応答が完了し、指定モデル・要求パラメータ・受信使用量を確認した。
  通信失敗、拒否、出力上限停止、usage欠落、追加修復・再試行は0件。
- 通常chat、旧schema、旧採点、過去のraw/result/summaryは変更していない。

| 測定 | JSON mode | native |
|---|---:|---:|
| API完了・モデル/要求一致 | 15/15 | 15/15 |
| 既存の厳密な形状・状態/値整合 | 15/15 | 15/15 |
| caller契約: 形状＋供給ID＋既知値の引用 | 15/15 | 12/15 |
| 固定参照規則での値 | 14/15 | 14/15 |
| フラグ忠実 | 15/15 | 14/15 |
| 要求されたIDの網羅 | 14/15 | 12/15 |
| 厳密通過 | **13/15** | **12/15** |

対比較は、両方通過11、JSON modeだけ2、nativeだけ1、両方不通過1。
1件差を一般化せず、native優位や通常動作への採用を主張しない。

## 失敗を意味で分ける

### 引用の表現: nativeの3件

`urgent-unknown/source`、`urgent-enabled/partial-rule`、`complete-join/source`で、
nativeはIDの配列を「IDを含む説明文」の配列にした。たとえばjoinでは次の文字列を
返した。

```json
"m001: 依頼 Qd689e の担当班は T265ae。"
```

契約が要求した要素は`"m001"`そのものだった。文章は元資料に沿っており、
**資料の捏造や参照経路を見失ったことと同一視してはいけない。** 自動診断の
`invisible-citation` / `irrelevant-citation`は、説明文が正確なID集合に属さない
という検査結果であり、必ずしも内容として架空の資料を引いたという意味ではない。

現在のAPI schemaは`evidence.items.type=string`なので、これらは型として有効。
一方、手元の供給IDチェックは3件を拒否し、rawと報告usageを保持した。
**fail-closedな境界は働いたが、正しいID表現を生成させる契約はまだ弱い。**
説明文からIDを抜き出して通過へ変える修復は行っていない。

### 不確定性の種類: nativeの1件

`urgent-unknown/source`では、記録の「緊急フラグは未確認」を`unknown`ではなく
`unobserved`と返した。valueはnullのままで、`disabled`への変換ではない。
ただし「記録はあるが未確認」と「記録にない」の区別は失われた。
この件は引用表現の失敗とも重なるため、別の4件目として加算しない。

### 分岐の根拠: JSON modeの1件

`urgent-enabled/source`では、両群ともFAST値は正しく、フラグも正しかった。
JSON modeはpolicyとrequestだけを引用し、nativeはoverrideも引用した。
固定採点は高優先の例外を除外した根拠も要求するので、JSON modeだけ不通過。
これはこの契約での引用網羅の差であり、nativeの一般的な推論改善とは呼ばない。

### 判断を確定してよいか: 両群共通の1条件

overrideを隠した`urgent-enabled/partial-rule`では、両群ともFASTを確定した。
固定参照規則はunknownを要求する。JSON modeは供給された2つのIDを正確に
引用しているためcaller契約は通るが、判断の厳密なゲートは通らない。
nativeにはこれに加えて引用表現の失敗が重なった。

ここには**評価と入力の意味契約のずれ**という留保がある。今回使ったPR #11の
最小systemは「供給記録がlicenseするときだけknown」とは述べるが、FAST/BASEに
override記録も必須であるという分岐別の義務は明示していない。以前の強い
GUARD/proof指示と同じ説明をモデルに渡した実験ではない。
したがって、このゲート違反をそのまま一般的な論理能力不足と断定できない。
欠けた意味契約を入力側へ明示する設計も必要だが、今回は採点を後から変えない。

## 保てたこと

三種類の空記録controlは両群とも通過した。routingは両フラグをunobservedで保ち、
decision/joinは空flags、空evidence、unknown/nullを返した。
proposals-only、pending-join、partial-chainでも、両群がunknownと供給済みの
接続根拠を両立した。hold-dominatesでは、urgentがunknownでも既知のHOLD値を
両群とも返せた。未知状態を一律にfalse扱いする失敗は観測されなかった。

これは狭い契約校正の成功部分であり、未知の会話や検索失敗への頑健性ではない。

## 使用量

| V1.1の報告usage | JSON mode | native |
|---|---:|---:|
| 入力tokens | 6,164 | 7,465 |
| 出力tokens | 1,544 | 1,800 |
| 合計tokens | 7,708 | 9,265 |

V1.1全体は16,973 tokens。可視プロンプトと出力上限が同じでも、nativeのschema
転送を含む入力usageは等しくならなかった。出力にはreasoning tokensも含まれる。
reasoning内訳はJSON mode984、native952で、これを推論品質の指標とは解釈しない。
各群の逐次呼び出し時間の合計はJSON mode69.804秒、native73.632秒だったが、
初回schema処理やservice状態を分離しておらず、一般的な速度比較ではない。

V1を含めた32回の報告済みusageは17,769 tokens。受信できなかったHTTP400の
1件はusage不明のままであり、これは全消費を確定した値ではない。

## 次の磨き方

1. 引用IDを自由なstringではなく、**供給された公開IDのenum**としてnative schemaに
   渡す。正解・関連性ledgerは使わず、空記録では引用配列を空に制約する。
   対照側にも同じID語彙を見せ、型の強制とヒント量を混同しない新ケース比較にする。
2. unknown/unobservedと、値を確定するための規則・例外の要件を、入力の意味契約
   として両群に明示する。これは別要因なので、ID表現の変更と混ぜずに検証する。
3. 説明も残したいなら、参照IDと根拠の説明を別フィールドにする将来の契約を検討する。
   現行4フィールドへ説明を押し込む修復や、過去の失敗を通過へ変える再採点はしない。

いずれも今回は未実行で、新たな有料呼び出しは追加していない。

## 再現情報

| | V1停止 | V1.1完了 |
|---|---|---|
| source commit | `bf05f2b291ba864650e7261dd49f48c6105feae8` | `42324ef317ea98d70b98dd8e48c066cb4d8da2fb` |
| plan digest | `275c4aeb1167950e952781c1ff5c08d0a53620478260bcf2f3fcb5abdd787a74` | `db95a99f934b7c5004d834bd678c5456c7b777e4c6bc0dae633928b70409c9c1` |
| run directory | `.great_scratchpad/runs/luna-native-contract-v1-20261103` | `.great_scratchpad/runs/luna-native-contract-v11-20261103` |

V1は元sourceの独立checkoutでruntime guardを通して停止prefix2件を監査した。
V1.1は現行の凍結sourceで30件を監査し、保存summaryをbyte-identicalに再生成できた。
Luna v3およびV1のbyte witnessも再確認した。ガードの無効化や履歴の上書きはない。

V1.1のartifact SHA-256:

| ファイル | SHA-256 |
|---|---|
| `plan.json` | `b6a4c07462a729444e07347eebbfeecd1ff9dc0cb1438e39313e08c0a9414490` |
| `execution/result.json` | `17da57be44a9aa440a589601f17c13f27728aac0380bebcc87537d94188c0bcb` |
| `execution/attempts.jsonl` | `a13d2f029e6d9d9bddfed661a4092f19d2fdfd7fc7054ac46b59e00ffc2ee860` |
| `execution/responses.jsonl` | `6e08fb988be6363615f2551f3274344036d7b21d3b8a58090090811b79354c06` |
| `summary.json` | `6a502e9d3153fb7ba17830c64c78017a5d971501df0cec3115b37dd5660c4479` |
| `audit.json` | `ddd4d1794d0445f2d705632616dd4d5b127183ab5111562dcb06c39841ad95a5` |

V1のartifact hashはrunnerの`STOPPED_V1`に固定した。rawと使用量を残した最初の
失敗も研究記録の一部であり、完了したV1.1で置き換えていない。

最終の全245テスト、対象ファイルのRuff、既存CLI/REPL/runtimeの模擬モデルsmokeを
通過した。実際のcredential値によるsource/artifact25ファイルの検査は一致0件で、
値自体は表示・保存していない。これはローカルの検証結果でありGitHub CIとは分ける。
