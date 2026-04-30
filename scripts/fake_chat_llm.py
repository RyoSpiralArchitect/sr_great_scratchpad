#!/usr/bin/env python3
from __future__ import annotations

import json
import sys


def main() -> None:
    prompt = sys.stdin.read()

    if "Action 1: scratchpad.search" not in prompt:
        out = {
            "type": "action",
            "action": "scratchpad.search",
            "query": "Semantic Compression Topic Drift center pin",
            "top": 3,
        }
    elif "Action 2: scratchpad.add_note" not in prompt:
        out = {
            "type": "action",
            "action": "scratchpad.add_note",
            "text": "Runtime noticed that the current chat turn benefits from scratchpad retrieval before answering.",
            "center": "chat runtime uses scratchpad as external memory",
            "trajectory": "The runtime moved from direct chat toward search-backed response and memory update.",
            "anchors": "chat runtime, scratchpad.search, scratchpad.add_note, external memory",
            "assumptions": "fake_chat_llm.py is only a deterministic smoke model",
            "open_questions": "which tool actions should become stable contract",
            "drift_risks": "letting the model write memory without review or audit",
        }
    else:
        out = {
            "type": "final",
            "message": (
                "Fake chat final: I searched the scratchpad, wrote a trajectory note, "
                "and can now answer with retrieved context in view."
            ),
        }

    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
