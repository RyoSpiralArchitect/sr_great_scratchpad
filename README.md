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
- One-shot `smoke --profile ...` checks, run manifests, review edits, local usage estimates, provider sampling/JSON-mode params, and optional Hugging Face local profiles
