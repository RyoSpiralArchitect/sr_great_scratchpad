# sr_great_scratchpad

Great Scratchpad is a tiny Markdown memory tool for preserving conversational trajectory, not just conclusions.

It is an experiment in thread-level interaction design: when semantic compression keeps only the answer, it can destroy the path that made the answer usable. This project keeps raw articulation, center pins, trajectory notes, anchors, open questions, and drift risks in a simple folder structure that can be searched by a human, a shell command, or an agent.

## 日本語

Great Scratchpad は、会話の「結論」だけではなく「軌道」を残すための小さな Markdown メモリです。

Thread 単位の interaction では、articulation は reasoning と切り離しにくいものです。ところが普通の semantic compression は、結論を残す一方で、経緯・ニュアンス・比喩・迷い・未確定性を落としがちです。その結果、後続の会話で center pin がずれ、少しずつ Topic Drift が起きます。

このツールは、そのズレを減らすために、会話の raw articulation と trajectory annotation をターンごとの `.md` として保存します。30ターンごとの trajectory block、grep/bigram 検索、agentic retrieval 用の context pack を組み合わせて、「未来の会話がそこへ戻れる足場」を作ることを狙います。

### 何を保存するか

- Raw articulation: そのターンで外部化された発話そのもの
- Center pin: このターンの中心軸
- Trajectory: どこからどこへ話が動いたか
- Anchors: 再利用されそうな語句、比喩、命名
- Local assumptions: その時点で有効だった前提
- Open questions: まだ閉じていない問い
- Drift risks: 将来ズレやすいポイント

### セットアップ

Python 3.10+ の標準ライブラリだけで動きます。

```bash
git clone https://github.com/RyoSpiralArchitect/sr_great_scratchpad.git
cd sr_great_scratchpad
python3 -S -m py_compile sr_great_scratchpad.py
```

### 最小の使い方

```bash
python3 -S sr_great_scratchpad.py init
python3 -S sr_great_scratchpad.py guide
python3 -S sr_great_scratchpad.py new monday-meawness --title "Monday Meawness"

python3 -S sr_great_scratchpad.py add monday-meawness \
  --speaker user \
  --text "Semantic Compressionは、結論を残すが、Trajectoryを破壊する。トピック中心がぶれるとTopic Driftが始まる。" \
  --center "semantic compression と trajectory loss" \
  --trajectory "要約の便利さから、Topic Drift の実害へ話が移動した" \
  --anchors "Semantic Compression, Trajectory, Topic Drift" \
  --open-questions "agentic retrieval をどこまで自律させるか" \
  --drift-risks "結論だけを保存して経緯を失う"
```

検索:

```bash
python3 -S sr_great_scratchpad.py search monday-meawness "トピック中心がぶれる"
```

context pack:

```bash
python3 -S sr_great_scratchpad.py pack monday-meawness "Semantic Compression Topic Drift 軌道" \
  --recent 6 \
  --top 8 \
  --include-guide \
  --out context_pack.md
```

audit:

```bash
python3 -S sr_great_scratchpad.py audit monday-meawness
python3 -S sr_great_scratchpad.py audit monday-meawness --json
```

### REPL-first workflow

別タブで会話して、一区切りついたら raw log と annotation を一緒に保存するための薄いREPLがあります。

```bash
python3 -S sr_great_scratchpad.py repl
```

例:

```text
sr> new monday-meawness Monday Meawness
sr:monday-meawness> add user
Raw articulation (finish with a single '.' line)
| ここに別タブの会話ログや一区切りの発話を貼る
| Semantic Compressionは結論を残すが、Trajectoryを破壊する。
| .
Center pin> semantic compression と trajectory loss
Trajectory> 要約の便利さからTopic Driftの実害へ話が移動した
Anchors> Semantic Compression, Trajectory, Topic Drift
Local assumptions> REPLは最初のinterfaceとして十分
Open questions> agentic retrievalをどこまで自律させるか
Drift risks> フォーム化しすぎると早すぎる圧縮になる
sr:monday-meawness> search トピック中心がぶれる
sr:monday-meawness> pack Semantic Compression Topic Drift 軌道 --include-guide --out context_pack.md
sr:monday-meawness> audit
```

最初はCLI/REPLで挙動を見ます。どのタイミングで検索したくなるか、どのannotationが効くか、どこでTopic Driftを感じるかを観測してから、TUIやフロントエンドの形を決めます。

### LLM接続

LLMはannotationの「確定者」ではなく draft producer として使います。provider APIもlocal LLMも `llm.json` のprofileとして設定し、`annotate` またはREPLの `annotate` から呼び出します。実モデル向けの詳しいprofile例は [`docs/model-profiles.md`](docs/model-profiles.md) にあります。

OpenAI GPT-5.6 / Responses API:

```bash
python3 -S sr_great_scratchpad.py llm-config openai \
  --profile openai-5.6-luna \
  --model gpt-5.6-luna \
  --reasoning-effort medium \
  --json-mode json_object \
  --default
```

`openai` profile は `adapter=auto` です。GPT-5.x / GPT-5.6 系は Responses API に向かい、既存の provider profile は従来通り Chat Completions 互換サーバーに向かいます。

OpenAI-compatible provider API:

```bash
python3 -S sr_great_scratchpad.py llm-config provider \
  --profile provider \
  --base-url "https://YOUR_PROVIDER/v1" \
  --api-key-env YOUR_PROVIDER_API_KEY \
  --model YOUR_MODEL \
  --top-p 0.9 \
  --json-mode json_object \
  --default
```

Local command-backed LLM:

```bash
python3 -S sr_great_scratchpad.py llm-config local \
  --profile local \
  --command "llama-cli -m {model_path} -p {prompt}" \
  --model-path "/path/to/model.gguf" \
  --default
```

`{prompt}` をcommandに含めない場合、promptはstdinで渡されます。`{prompt_file}` も使えます。
local command profile は provider usage が返らない代わりに、trace 内で token usage estimate を記録します。

Hugging Face transformers-backed local profile の足場もあります。`transformers` と `torch` が入った環境では、後で hidden-state shape metadata を見るための `--capture-hidden` を使えます。

```bash
python3 -S sr_great_scratchpad.py llm-config hf \
  --profile hf-local \
  --model "/path/to/hf/model" \
  --device mps \
  --capture-hidden
```

annotation draft:

```bash
python3 -S sr_great_scratchpad.py annotate \
  --profile local \
  --text-file log.md \
  --json
```

profile smoke:

```bash
python3 -S sr_great_scratchpad.py smoke \
  --profile local \
  --trace-out traces/local-smoke.jsonl
```

REPL:

```bash
python3 -S sr_great_scratchpad.py repl monday-meawness --llm-profile local

sr:monday-meawness> annotate user
Raw articulation (finish with a single '.' line)
| ここに別タブの会話ログを貼る
| .
Center pin:
...
Save this turn? [y/N]> y
```

### Chat runtime MVP

`chat` は、LLMが会話しながら scratchpad action を要求できる最小runtimeです。

```bash
python3 -S sr_great_scratchpad.py chat monday-meawness --profile local
```

1ターンだけ試す:

```bash
python3 -S sr_great_scratchpad.py chat monday-meawness \
  --profile local \
  --text "前のSemantic CompressionとTopic Driftの話を踏まえて説明して"
```

action policy を選ぶ:

```bash
python3 -S sr_great_scratchpad.py chat monday-meawness \
  --profile local \
  --policy active \
  --text "前の話とズレないように短くまとめて"
```

runtime内でモデルは、次のようなJSONを返してscratchpadを使います。

```json
{"type":"action","action":"scratchpad.search","query":"Semantic Compression Topic Drift","top":5}
```

使えるaction:

- `scratchpad.search`
- `scratchpad.recent`
- `scratchpad.pack`
- `scratchpad.audit`
- `scratchpad.add_note`

書き込みactionはデフォルトで確認されます。実験用に自動許可する場合は `--yes` を付けます。
実験ログを残す場合は `--trace-out chat_trace.jsonl` を付けると、モデル出力・tool observation・final message がJSONLで追えます。trace の親ディレクトリは自動作成され、`chat_trace.manifest.json` に `run_id`、profile、usage summary も保存されます。
実モデルでのmemory writeを即保存したくない場合は `--queue-writes` を付け、`review list/edit/apply/reject` で確認できます。
JSONが崩れるモデルには `--json-repair-steps N` で修復再試行を増やせます。
各ターンには centerline hints が入り、checkpoint・短い曖昧な質問・中心移動・memory note 候補が trace に残ります。

traceを見る:

```bash
python3 -S sr_great_scratchpad.py trace summary chat_trace.jsonl
python3 -S sr_great_scratchpad.py trace show chat_trace.jsonl --line 2
python3 -S sr_great_scratchpad.py trace centerline chat_trace.jsonl
python3 -S sr_great_scratchpad.py trace report chat_trace.jsonl --out chat_report.md
```

review queue:

```bash
python3 -S sr_great_scratchpad.py review list monday-meawness --audit
python3 -S sr_great_scratchpad.py review show monday-meawness ITEM.json
python3 -S sr_great_scratchpad.py review apply monday-meawness ITEM.json --audit-preview
python3 -S sr_great_scratchpad.py review apply monday-meawness ITEM.json --safe-only
python3 -S sr_great_scratchpad.py review apply monday-meawness --all-safe
```

scenario実験:

```bash
python3 -S sr_great_scratchpad.py experiment run scenarios/topic_drift.md \
  --profiles local,provider \
  --policy active \
  --queue-writes \
  --out-dir runs/topic-drift
```

Luna の raw API と scratchpad runtime を同じ議題・発話数・生成予算で比較する:

```bash
python3 -S sr_great_scratchpad.py experiment dialogue \
  scenarios/luna_centerline_dialogue.json \
  --profile openai-5.6-luna \
  --turns 8 \
  --turn-output-tokens 720 \
  --max-api-calls 80 \
  --max-suite-output-tokens 24000
```

既定では `raw/raw`、`raw/scratchpad`、`scratchpad/raw`、`scratchpad/scratchpad` を走らせます。混合条件を左右反転するため、先攻・後攻の影響を scratchpad の効果と取り違えにくくなります。各発話の生成token枠は、scratchpad 内部の action/final 呼び出し全体で共有されます。入力tokenは memory/runtime のコストそのものなので揃えず、条件別に report へ記録します。

各 scratchpad 話者は run 内の隔離領域を使い、書いた note を次の自分の発話から参照できます。`report.md`、sessionごとの `transcript.md` / `transcript.jsonl`、provider-visible promptを含む `trace.jsonl`、manifest、scratchpad note が同じ出力ディレクトリに保存されます。report は memory context 注入回数、複数JSONからの protocol recovery、parse error も分けて表示します。`add_note` と完全な final が同時に返った場合だけ、書き込み成功後に final を安全に再利用します。検索系actionの先書き final は採用しません。実行前には最悪 API call 数と suite 全体の生成token上限を検査します。

centerline、書き込み、再読込の寄与を分ける遅延想起アブレーション:

```bash
python3 -S sr_great_scratchpad.py experiment dialogue \
  scenarios/luna_delayed_recall_ablation.json \
  --profile openai-5.6-luna \
  --preset ablation \
  --turns 12 \
  --history-chars 700 \
  --replicates 4 \
  --alternate-starter \
  --rotate-condition-order \
  --turn-output-tokens 600 \
  --max-api-calls 384 \
  --max-suite-output-tokens 153600
```

`ablation` は `raw/raw`、`centerline-only`、`write-no-recall`、`scratchpad/scratchpad` の4条件です。`--rotate-condition-order` はreplicateごとに順序を巡回し、n=4では各条件を各実行位置へ一度ずつ置きます。全条件の通常会話履歴は最新側から同じ文字数だけ残します。`write-no-recall` は note を保存しますが、保存済みnoteの自動注入と全read actionを閉じるため、「書いたこと」自体と「後で読めたこと」を分離できます。600-token枠はvalidなaction/finalで共有し、invalid JSONは別の有界repair reserveへ計上します。literal probe は凍結turnでの語の出現だけを報告し、意味的な勝者判定には使いません。大きな反復を始める前に、`--replicates 1` と対応する低い上限で校正してください。

遅延probeだけへ選択的にnoteを注入し、top-kとfull recallを分けるmechanism校正:

```bash
python3 -S sr_great_scratchpad.py experiment dialogue \
  scenarios/luna_delayed_recall_ablation.json \
  --profile openai-5.6-luna \
  --preset mechanism \
  --turns 12 \
  --history-chars 700 \
  --replicates 1 \
  --turn-output-tokens 600 \
  --max-api-calls 144 \
  --max-suite-output-tokens 48000
```

`mechanism` は `write-no-recall`、`probe-top1`、`probe-top2`、`scratchpad/scratchpad` の4条件です。probe条件はmodelからのread actionを閉じたまま、scenarioで凍結したturnだけmoderator interventionをqueryに使い、compact化した上位1件または2件を直接注入します。traceにはquery、score、source path、元文字数、注入文字数が残ります。relation probeは単語の有無だけでなく、変更前・変更後の役割、順序、アナロジー限界を検査します。

同じnoteを全条件に同じturnで投入し、可視性とtop-kだけを変えるfrozen-note replay:

```bash
python3 -S sr_great_scratchpad.py experiment dialogue \
  scenarios/luna_delayed_recall_ablation.json \
  --profile openai-5.6-luna \
  --preset replay \
  --memory-fixture scenarios/luna_delayed_recall_frozen_notes.json \
  --turns 12 \
  --history-chars 700 \
  --replicates 1 \
  --turn-output-tokens 600 \
  --max-api-calls 144 \
  --max-suite-output-tokens 48000
```

`replay` は `replay-no-recall`、`replay-top1`、`replay-top2`、`replay-full` の4条件です。modelからの全scratchpad actionを閉じ、fixtureの4noteを完了turnの後に決めた話者へ投入します。payload hash、donor note hash、条件間のnote byte identityはpreflightとsuite完了時に検証され、fixture writeとmodel writeは別々に記録されます。

既存runのretrievalをprovider callなしで再生し、own-threadとhard-distractor stressを分けて測る:

```bash
python3 -S sr_great_scratchpad.py experiment retrieval \
  .great_scratchpad/runs/YOUR_DIALOGUE_RUN \
  --taxonomy scenarios/luna_delayed_recall_semantic_taxonomy.json \
  --distractor-limit 24
```

reportは `intervention` とfull `current-message` queryを別々に、Recall@1/2/3/5、MRR、候補数、compact注入文字数とともに出します。n=8へのpost-hoc適用、Luna n=1 mechanism校正、frozen-note replay protocolは [`docs/luna-selective-recall-mechanism.md`](docs/luna-selective-recall-mechanism.md) にあります。条件ごとのnote内容が異なる問題を、tracked fixtureとbyte-identity gateで切り離しています。

凍結済みrunの発話とnoteを、外部依存なしの文字n-gram TF-IDFと意味プロトタイプで測る:

```bash
python3 -S sr_great_scratchpad.py experiment dialogue-nlp \
  .great_scratchpad/runs/YOUR_DIALOGUE_RUN \
  --taxonomy scenarios/luna_delayed_recall_semantic_taxonomy.json
```

生成scenarioと評価taxonomyは別identityとしてSHA-256を記録します。reportは意味フレーム占有率、note内容、反復類似度、noteのprovider-visible promptへの包含、note→遅延応答類似度、paired treatment差、固定seed bootstrap区間、literalとrelationの対応表を分けて出力します。これは監査可能な語彙・意味測定であり、LLM judgeや真偽判定ではありません。反復拡張の事前計画は [`docs/luna-delayed-recall-n-plan.md`](docs/luna-delayed-recall-n-plan.md)、n=4実行結果は [`docs/luna-delayed-recall-n4.md`](docs/luna-delayed-recall-n4.md) にあります。

### Live run

挙動を見ながら育てるための小さな実行例を用意しています。

```bash
scripts/live_run.sh
```

このスクリプトは一時ディレクトリに scratchpad を作り、日本語検索、guide 付き context pack、audit JSON を一通り走らせます。

### 設計メモ

- `.md` を主形式にする: YAMLだけに押し込めると、早すぎる構造化がまた compression になります。
- grep/bigram は下層に置く: 安価で監査可能な検索面を残します。
- LLM agency は上層に置く: 「今なにを取りに行くべきか」は、会話中のモデルが判断した方がスケールします。
- pack には参照元を残す: 記憶を幻覚化させず、turn/block に戻れるようにします。
- audit は断定しない: 圧縮しすぎや anchor の怪しさを review flag として観測します。

## English

Great Scratchpad is a small Markdown-based memory tool for preserving conversational trajectory.

In thread-level interaction, articulation is not merely a transcript of reasoning. It is also the external surface that lets future reasoning re-enter the same path. Standard semantic compression often preserves the conclusion while destroying the trajectory: the metaphors, assumptions, hesitations, local definitions, and unresolved questions that made the conclusion fit.

This project treats that loss as a practical cause of Topic Drift. When the center pin of a conversation is no longer recoverable, later turns may sound fluent while gradually becoming a different conversation.

### What It Stores

- Raw articulation: the externally visible utterance for the turn
- Center pin: the center of gravity for the turn
- Trajectory: how the conversation moved
- Anchors: reusable terms, metaphors, names, and coined phrases
- Local assumptions: assumptions active at that point
- Open questions: questions not yet closed
- Drift risks: likely ways future context may slide away

### Setup

Great Scratchpad only needs Python 3.10+ and the standard library.

```bash
git clone https://github.com/RyoSpiralArchitect/sr_great_scratchpad.git
cd sr_great_scratchpad
python3 -S -m py_compile sr_great_scratchpad.py
```

### Quick Start

```bash
python3 -S sr_great_scratchpad.py init
python3 -S sr_great_scratchpad.py guide
python3 -S sr_great_scratchpad.py new monday-meawness --title "Monday Meawness"

python3 -S sr_great_scratchpad.py add monday-meawness \
  --speaker user \
  --text "Semantic Compression preserves conclusions but destroys Trajectory." \
  --center "semantic compression and trajectory loss" \
  --trajectory "The thread moved from useful summarization to Topic Drift risk." \
  --anchors "Semantic Compression, Trajectory, Topic Drift" \
  --open-questions "How autonomous should agentic retrieval be?" \
  --drift-risks "Saving the conclusion while losing the path"
```

Search:

```bash
python3 -S sr_great_scratchpad.py search monday-meawness "Topic Drift"
```

Build a context pack:

```bash
python3 -S sr_great_scratchpad.py pack monday-meawness "Semantic Compression Topic Drift trajectory" \
  --recent 6 \
  --top 8 \
  --include-guide \
  --out context_pack.md
```

Audit:

```bash
python3 -S sr_great_scratchpad.py audit monday-meawness
python3 -S sr_great_scratchpad.py audit monday-meawness --json
```

### REPL-first Workflow

There is a thin REPL for the intended early workflow: talk in another tab, then paste a meaningful segment of the interaction back into the scratchpad with lightweight trajectory annotation.

```bash
python3 -S sr_great_scratchpad.py repl
```

Example:

```text
sr> new monday-meawness Monday Meawness
sr:monday-meawness> add user
Raw articulation (finish with a single '.' line)
| Paste a conversation segment from another tab.
| Semantic Compression preserves conclusions but destroys Trajectory.
| .
Center pin> semantic compression and trajectory loss
Trajectory> The thread moved from summarization usefulness to Topic Drift risk.
Anchors> Semantic Compression, Trajectory, Topic Drift
Local assumptions> REPL is enough for the first interface.
Open questions> How autonomous should agentic retrieval be?
Drift risks> Over-formalizing the UI may become premature compression.
sr:monday-meawness> search Topic Drift
sr:monday-meawness> pack Semantic Compression Topic Drift trajectory --include-guide --out context_pack.md
sr:monday-meawness> audit
```

The plan is to learn the interaction before freezing the product surface: observe when retrieval is wanted, which annotations actually help, and where Topic Drift becomes visible.

### LLM Connection

The LLM is treated as a draft producer, not as an authority. Provider APIs and local LLM commands are both configured as profiles in `llm.json`, then used by `annotate` or the REPL `annotate` command. See [`docs/model-profiles.md`](docs/model-profiles.md) for richer real-model profile examples.

OpenAI GPT-5.6 / Responses API:

```bash
python3 -S sr_great_scratchpad.py llm-config openai \
  --profile openai-5.6-luna \
  --model gpt-5.6-luna \
  --reasoning-effort medium \
  --json-mode json_object \
  --default
```

`openai` profiles use `adapter=auto`: GPT-5.x / GPT-5.6 models route through the Responses API, while legacy-compatible provider profiles continue using Chat Completions.

OpenAI-compatible provider API:

```bash
python3 -S sr_great_scratchpad.py llm-config provider \
  --profile provider \
  --base-url "https://YOUR_PROVIDER/v1" \
  --api-key-env YOUR_PROVIDER_API_KEY \
  --model YOUR_MODEL \
  --top-p 0.9 \
  --json-mode json_object \
  --default
```

Local command-backed LLM:

```bash
python3 -S sr_great_scratchpad.py llm-config local \
  --profile local \
  --command "llama-cli -m {model_path} -p {prompt}" \
  --model-path "/path/to/model.gguf" \
  --default
```

If `{prompt}` is not included in the command, the prompt is passed on stdin. `{prompt_file}` is also available.
Local command profiles record dependency-free token usage estimates in traces when provider usage is unavailable.

There is also an optional Hugging Face transformers-backed local profile scaffold. In an environment with `transformers` and `torch`, use `--capture-hidden` to keep generated hidden-state shape metadata available for later local-model inspection.

```bash
python3 -S sr_great_scratchpad.py llm-config hf \
  --profile hf-local \
  --model "/path/to/hf/model" \
  --device mps \
  --capture-hidden
```

Draft annotations:

```bash
python3 -S sr_great_scratchpad.py annotate \
  --profile local \
  --text-file log.md \
  --json
```

Profile smoke:

```bash
python3 -S sr_great_scratchpad.py smoke \
  --profile local \
  --trace-out traces/local-smoke.jsonl
```

REPL:

```bash
python3 -S sr_great_scratchpad.py repl monday-meawness --llm-profile local

sr:monday-meawness> annotate user
Raw articulation (finish with a single '.' line)
| Paste a conversation segment from another tab.
| .
Center pin:
...
Save this turn? [y/N]> y
```

### Chat Runtime MVP

`chat` is the minimal runtime where the LLM can request scratchpad actions while talking.

```bash
python3 -S sr_great_scratchpad.py chat monday-meawness --profile local
```

Run a single turn:

```bash
python3 -S sr_great_scratchpad.py chat monday-meawness \
  --profile local \
  --text "Use the earlier Semantic Compression and Topic Drift context."
```

Inside the runtime, the model uses JSON actions such as:

```json
{"type":"action","action":"scratchpad.search","query":"Semantic Compression Topic Drift","top":5}
```

Available actions:

- `scratchpad.search`
- `scratchpad.recent`
- `scratchpad.pack`
- `scratchpad.audit`
- `scratchpad.add_note`

Write actions ask for confirmation by default. Use `--yes` for automated experiments.
Use `--trace-out chat_trace.jsonl` to append model outputs, tool observations, and final messages as JSONL experiment traces. Trace parent directories are created automatically, and `chat_trace.manifest.json` stores the `run_id`, profile, and usage summary.
Use `--queue-writes` to review and edit model-authored memory writes before applying them, and `--json-repair-steps N` to retry malformed JSON outputs.
Choose a named action policy with `--policy balanced|conservative|active|writer|read-only`.
Each turn includes centerline hints so checkpoints, ambiguous short questions, center shifts, and memory-note candidates are visible in traces.

Inspect traces:

```bash
python3 -S sr_great_scratchpad.py trace summary chat_trace.jsonl
python3 -S sr_great_scratchpad.py trace show chat_trace.jsonl --line 2
python3 -S sr_great_scratchpad.py trace centerline chat_trace.jsonl
python3 -S sr_great_scratchpad.py trace report chat_trace.jsonl --out chat_report.md
```

Review queued writes:

```bash
python3 -S sr_great_scratchpad.py review list monday-meawness --audit
python3 -S sr_great_scratchpad.py review show monday-meawness ITEM.json
python3 -S sr_great_scratchpad.py review apply monday-meawness --all-safe
```

Run a repeatable scenario across profiles:

```bash
python3 -S sr_great_scratchpad.py experiment run scenarios/topic_drift.md \
  --profiles local,provider \
  --policy active \
  --queue-writes \
  --out-dir runs/topic-drift
```

Compare raw Luna with the scratchpad runtime under a shared topic, utterance count, and generation allowance:

```bash
python3 -S sr_great_scratchpad.py experiment dialogue \
  scenarios/luna_centerline_dialogue.json \
  --profile openai-5.6-luna \
  --turns 8 \
  --turn-output-tokens 720 \
  --max-api-calls 80 \
  --max-suite-output-tokens 24000
```

The default matrix runs `raw/raw`, both orientations of `raw/scratchpad`, and `scratchpad/scratchpad`. Every utterance receives the same generated-token allowance; scratchpad action and final calls share that allowance. Input tokens are reported rather than equalized because runtime and memory overhead are part of the treatment cost. Scratchpad speakers use isolated per-run workspaces whose notes become available on their later turns. The runner freezes transcripts, provider-visible prompts, traces, manifests, usage, tool activity, memory-context injections, multi-object protocol recoveries, parse errors, and deterministic literal-anchor coverage, while leaving the quality judgment to transcript review. A complete trailing final is reused only after a successful `add_note`; search-like actions always wait for their observation.

Run the delayed-recall ablation to separate deterministic navigation, memory writing, and memory recall:

```bash
python3 -S sr_great_scratchpad.py experiment dialogue \
  scenarios/luna_delayed_recall_ablation.json \
  --profile openai-5.6-luna \
  --preset ablation \
  --turns 12 \
  --history-chars 700 \
  --replicates 4 \
  --alternate-starter \
  --rotate-condition-order \
  --turn-output-tokens 600 \
  --max-api-calls 384 \
  --max-suite-output-tokens 153600
```

The ablation conditions are `raw/raw`, `centerline-only`, `write-no-recall`, and `scratchpad/scratchpad`. `--rotate-condition-order` cycles the order by replicate, placing every condition in every execution position once at n=4. Every condition receives the same newest-first ordinary-dialogue window. Write-no-recall persists notes but disables automatic note injection and all read actions, separating the act of writing from later availability. The 600-token allowance is pooled across valid actions and finals; invalid JSON is charged to a separate bounded repair reserve. Frozen-turn literal probes report exact lexical evidence only; they do not declare a semantic winner. Calibrate with one replicate and proportionally lower caps before a larger run.

Calibrate selective recall at the delayed probe while separating top-k from full recall:

```bash
python3 -S sr_great_scratchpad.py experiment dialogue \
  scenarios/luna_delayed_recall_ablation.json \
  --profile openai-5.6-luna \
  --preset mechanism \
  --turns 12 \
  --history-chars 700 \
  --replicates 1 \
  --turn-output-tokens 600 \
  --max-api-calls 144 \
  --max-suite-output-tokens 48000
```

The `mechanism` preset runs `write-no-recall`, `probe-top1`, `probe-top2`, and `scratchpad/scratchpad`. Probe conditions keep model-requested read actions blocked and use only the frozen moderator intervention to retrieve one or two compact notes at selected turns. Traces retain the query, score, source path, source characters, and injected characters. Relation probes require the old and new levels to occupy the requested before/after roles, in order, with an explicit analogy boundary.

Hold note content and timing constant while varying only visibility and top-k:

```bash
python3 -S sr_great_scratchpad.py experiment dialogue \
  scenarios/luna_delayed_recall_ablation.json \
  --profile openai-5.6-luna \
  --preset replay \
  --memory-fixture scenarios/luna_delayed_recall_frozen_notes.json \
  --turns 12 \
  --history-chars 700 \
  --replicates 1 \
  --turn-output-tokens 600 \
  --max-api-calls 144 \
  --max-suite-output-tokens 48000
```

The `replay` preset runs `replay-no-recall`, `replay-top1`, `replay-top2`, and `replay-full`. It blocks every model-requested scratchpad action and applies the four tracked fixture notes to the current speaker after fixed completed turns. Preflight and suite-final gates validate payload hashes, donor note hashes, and byte identity across conditions. Fixture writes and model writes remain separate in traces and manifests.

Replay retrieval over a frozen run without provider calls:

```bash
python3 -S sr_great_scratchpad.py experiment retrieval \
  .great_scratchpad/runs/YOUR_DIALOGUE_RUN \
  --taxonomy scenarios/luna_delayed_recall_semantic_taxonomy.json \
  --distractor-limit 24
```

The report separates intervention-only and full-current-message queries, own-thread and hard-distractor scopes, Recall@1/2/3/5, MRR, candidate counts, and compact injection characters. See [`docs/luna-selective-recall-mechanism.md`](docs/luna-selective-recall-mechanism.md) for the post-hoc n=8 analysis, Luna n=1 mechanism calibration, and frozen-note replay protocol. The tracked fixture plus byte-identity gate removes independently generated note contents from the next visibility/cutoff comparison.

Measure utterance and note semantics in a frozen run with dependency-free character n-gram TF-IDF and frozen semantic prototypes:

```bash
python3 -S sr_great_scratchpad.py experiment dialogue-nlp \
  .great_scratchpad/runs/YOUR_DIALOGUE_RUN \
  --taxonomy scenarios/luna_delayed_recall_semantic_taxonomy.json
```

Generation scenarios and assessment taxonomies retain separate SHA-256 identities. The report separates semantic-frame occupancy, note contents, repetition similarity, provider-visible note containment, note-to-delayed-response similarity, paired treatment contrasts, a fixed-seed bootstrap interval, and paired literal and relation outcomes. This is an auditable lexical-semantic measure, not an LLM judge or factuality scorer. See [`docs/luna-delayed-recall-n-plan.md`](docs/luna-delayed-recall-n-plan.md) for the preregistered replication path, [`docs/luna-delayed-recall-n4.md`](docs/luna-delayed-recall-n4.md) for the Stage 1 pilot, and [`docs/luna-delayed-recall-n8.md`](docs/luna-delayed-recall-n8.md) for the independent confirmation.

### Live Run

Run the included smoke test:

```bash
scripts/live_run.sh
```

It creates a temporary scratchpad, adds a bilingual trajectory-oriented turn, runs Japanese search, emits a guide-included context pack, and prints audit JSON.

### Design Direction

See also: [`docs/design-principles.md`](docs/design-principles.md)

- Keep Markdown as the primary surface. Premature YAML-only structure can become another form of semantic compression.
- Keep deterministic retrieval underneath. grep/token/bigram search is cheap, auditable, and reproducible.
- Let agentic retrieval live above that. The model should be encouraged to decide when the current thread is drifting and what needs to be retrieved.
- Context packs should preserve source paths, so memory stays inspectable rather than becoming unsupported lore.
- Audit should observe compression and suspicious anchors without pretending to prove hallucination.

## Current Status

V0.2 prototype:

- Japanese-friendly CJK bigram search tokenizer
- Separate search tokens and visible retrieval keys
- Annotation guide generated at init time
- `audit` command for compression ratio and possible unsupported anchors
- `pack --include-guide` for agent/human re-entry
- Provider/local LLM profiles for draft annotation
- Minimal `chat` runtime with scratchpad action loop
- JSON repair retries for model protocol drift
- Chat runtime JSONL traces with LLM metadata and provider usage
- Review queue for model-authored memory writes
- Named action policies for different retrieval/write postures
- `trace summary/show/report` for replayable inspection
- `experiment run` for Markdown scenarios across model profiles
- Source index selection reasons in context packs
- One-shot `smoke --profile ...` checks, run manifests, review edits, local usage estimates, provider sampling/JSON-mode params, and optional Hugging Face local profiles
