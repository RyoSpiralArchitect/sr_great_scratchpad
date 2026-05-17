#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp_root="$(mktemp -d)"

echo "Scratchpad root: ${tmp_root}"
echo

python3 -S "${repo_root}/sr_great_scratchpad.py" --root "${tmp_root}" init
python3 -S "${repo_root}/sr_great_scratchpad.py" --root "${tmp_root}" guide >/dev/null
python3 -S "${repo_root}/sr_great_scratchpad.py" --root "${tmp_root}" new monday-meawness --title "Monday Meawness"

python3 -S "${repo_root}/sr_great_scratchpad.py" --root "${tmp_root}" add monday-meawness \
  --speaker user \
  --text "Semantic Compressionは、結論を残すが、Trajectoryを破壊する。トピック中心がぶれるとTopic Driftが始まる。agentic retrievalは、center pinが少しずつ外れる前に必要になる。" \
  --center "semantic compression と trajectory loss" \
  --trajectory "要約の便利さから、Topic Drift の実害と agentic retrieval の必要性へ移動した" \
  --anchors "Semantic Compression, Trajectory, Topic Drift, center pin, agentic retrieval" \
  --assumptions "Markdown raw files can preserve articulation better than over-structured YAML" \
  --open-questions "決定論的searchとLLM agencyをどこで接続するか" \
  --drift-risks "結論だけを保存して経緯を失う"

echo
echo "## Search: トピック中心がぶれる"
python3 -S "${repo_root}/sr_great_scratchpad.py" --root "${tmp_root}" search monday-meawness "トピック中心がぶれる" --top 3 --width 240

echo
echo "## Context pack with guide"
python3 -S "${repo_root}/sr_great_scratchpad.py" --root "${tmp_root}" pack monday-meawness "Semantic Compression Topic Drift 軌道" \
  --recent 3 \
  --top 3 \
  --include-guide \
  --out "${tmp_root}/context_pack.md"
wc -c "${tmp_root}/context_pack.md"

echo
echo "## Audit JSON"
python3 -S "${repo_root}/sr_great_scratchpad.py" --root "${tmp_root}" audit monday-meawness --json

echo
echo "## REPL smoke"
{
  printf '%s\n' "new repl-smoke REPL Smoke"
  printf '%s\n' "add user"
  printf '%s\n' "Semantic Compression preserves conclusions."
  printf '%s\n' "Trajectory loss makes Topic Drift easier to miss."
  printf '%s\n' "."
  printf '%s\n' "semantic compression and trajectory loss"
  printf '%s\n' "A pasted conversation segment becomes a trajectory-aware turn"
  printf '%s\n' "Semantic Compression, Trajectory, Topic Drift"
  printf '%s\n' "REPL is enough for the first interface"
  printf '%s\n' "Which prompts are too heavy?"
  printf '%s\n' "Premature UI structure may become compression"
  printf '%s\n' "search Topic Drift --top 3"
  printf '%s\n' "pack Semantic Compression trajectory --include-guide --out ${tmp_root}/repl_context_pack.md"
  printf '%s\n' "audit"
  printf '%s\n' "quit"
} | python3 -S "${repo_root}/sr_great_scratchpad.py" --root "${tmp_root}" repl

echo
echo "## LLM config + fake local annotation smoke"
python3 -S "${repo_root}/sr_great_scratchpad.py" --root "${tmp_root}" llm-config local \
  --profile fake-local \
  --command "python3 -S ${repo_root}/scripts/fake_llm.py" \
  --default

python3 -S "${repo_root}/sr_great_scratchpad.py" --root "${tmp_root}" smoke \
  --profile fake-local \
  --trace-out "${tmp_root}/runs/fake_local_smoke.jsonl" \
  --run-id "live-fake-local-smoke"
test -f "${tmp_root}/runs/fake_local_smoke.manifest.json"

python3 -S "${repo_root}/sr_great_scratchpad.py" --root "${tmp_root}" annotate \
  --profile fake-local \
  --text "Semantic Compression preserves the conclusion while losing the interaction trajectory." \
  --json

{
  printf '%s\n' "new llm-repl LLM REPL"
  printf '%s\n' "llm"
  printf '%s\n' "annotate user"
  printf '%s\n' "Provider APIs and local LLM commands should both draft trajectory annotations."
  printf '%s\n' "."
  printf '%s\n' "y"
  printf '%s\n' "recent 1"
  printf '%s\n' "quit"
} | python3 -S "${repo_root}/sr_great_scratchpad.py" --root "${tmp_root}" repl --llm-profile fake-local

echo
echo "## Chat runtime fake model smoke"
python3 -S "${repo_root}/sr_great_scratchpad.py" --root "${tmp_root}" llm-config local \
  --profile fake-chat \
  --command "python3 -S ${repo_root}/scripts/fake_chat_llm.py" \
  --default

python3 -S "${repo_root}/sr_great_scratchpad.py" --root "${tmp_root}" chat monday-meawness \
  --profile fake-chat \
  --text "前のSemantic CompressionとTopic Driftの話を踏まえて、runtimeの位置づけを短く見たい。" \
  --yes \
  --policy active \
  --trace-out "${tmp_root}/chat_trace.jsonl" \
  --run-id "live-chat-smoke"
wc -l "${tmp_root}/chat_trace.jsonl"
test -f "${tmp_root}/chat_trace.manifest.json"
python3 -S "${repo_root}/sr_great_scratchpad.py" --root "${tmp_root}" trace summary "${tmp_root}/chat_trace.jsonl" >/dev/null
python3 -S "${repo_root}/sr_great_scratchpad.py" --root "${tmp_root}" trace show "${tmp_root}/chat_trace.jsonl" --line 2 >/dev/null
python3 -S "${repo_root}/sr_great_scratchpad.py" --root "${tmp_root}" trace report "${tmp_root}/chat_trace.jsonl" --out "${tmp_root}/chat_report.md"
test -f "${tmp_root}/chat_report.md"

echo
echo "## Chat runtime queued write smoke"
python3 -S "${repo_root}/sr_great_scratchpad.py" --root "${tmp_root}" chat monday-meawness \
  --profile fake-chat \
  --text "同じruntimeで、memory writeをreview queueに回してみたい。" \
  --yes \
  --queue-writes \
  --quiet \
  --trace-out "${tmp_root}/chat_queue_trace.jsonl"
python3 -S "${repo_root}/sr_great_scratchpad.py" --root "${tmp_root}" review list monday-meawness --audit
queued_item="$(find "${tmp_root}/review_queue/monday-meawness" -name '*.json' -print -quit)"
python3 -S "${repo_root}/sr_great_scratchpad.py" --root "${tmp_root}" review edit monday-meawness "$(basename "${queued_item}")" \
  --text "Runtime review queue keeps external memory writes inspectable before durable memory. Runtime review queue and external memory are explicit anchors in this queued note." \
  --center "Runtime review queue for external memory" \
  --trajectory "A model-authored memory write moves through review before becoming durable" \
  --anchors "Runtime review queue, external memory" \
  --assumptions "review queue protects scratchpad memory" \
  --open-questions "which queued notes should auto-apply" \
  --drift-risks "unsafe notes becoming memory without review"
python3 -S "${repo_root}/sr_great_scratchpad.py" --root "${tmp_root}" review show monday-meawness "$(basename "${queued_item}")" >/dev/null
python3 -S "${repo_root}/sr_great_scratchpad.py" --root "${tmp_root}" review apply monday-meawness --all-safe
python3 -S "${repo_root}/sr_great_scratchpad.py" --root "${tmp_root}" review list monday-meawness --status applied

echo
echo "## Scenario experiment fake model smoke"
python3 -S "${repo_root}/sr_great_scratchpad.py" --root "${tmp_root}" experiment run "${repo_root}/scenarios/topic_drift.md" \
  --profiles fake-chat \
  --policy active \
  --queue-writes \
  --yes \
  --quiet \
  --out-dir "${tmp_root}/runs/topic_drift"
test -f "${tmp_root}/runs/topic_drift/experiment_report.md"

echo
echo "Live run complete. Inspect artifacts under: ${tmp_root}"
