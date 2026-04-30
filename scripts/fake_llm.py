#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys


def main() -> None:
    prompt = sys.stdin.read()
    m = re.search(r"Raw articulation:\n---\n(.*?)\n---", prompt, flags=re.DOTALL)
    raw = m.group(1).strip() if m else prompt.strip()
    tokens = []
    for item in re.findall(r"[A-Za-z][A-Za-z0-9_./:-]{2,}|[ぁ-んァ-ヶー一-龥々〆〤]{4,24}", raw):
        if item not in tokens:
            tokens.append(item)
    out = {
        "center": "fake local draft: trajectory preservation",
        "trajectory": "fake local draft from pasted raw articulation into Great Scratchpad annotation",
        "anchors": ", ".join(tokens[:6]) or "Great Scratchpad",
        "assumptions": "fake local LLM script is only for smoke tests",
        "open_questions": "replace fake_llm.py with a real provider or local model",
        "drift_risks": "treating draft annotation as verified memory without review",
    }
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
