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

### Live Run

Run the included smoke test:

```bash
scripts/live_run.sh
```

It creates a temporary scratchpad, adds a bilingual trajectory-oriented turn, runs Japanese search, emits a guide-included context pack, and prints audit JSON.

### Design Direction

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
