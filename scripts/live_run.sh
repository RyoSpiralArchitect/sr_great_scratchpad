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
echo "Live run complete. Inspect artifacts under: ${tmp_root}"
