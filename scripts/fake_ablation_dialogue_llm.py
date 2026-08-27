#!/usr/bin/env python3
from __future__ import annotations

import json
import sys


CORRECTION_NOTE = "個体内の異質性を種間差と取り違えない。"


def final(message: str) -> None:
    print(json.dumps({"type": "final", "message": message}, ensure_ascii=False))


def current_message(prompt: str, heading: str) -> str:
    marker = f"{heading}:\n---\n"
    if marker not in prompt:
        return ""
    return prompt.rsplit(marker, 1)[1].split("\n---", 1)[0]


def main() -> None:
    prompt = sys.stdin.read()
    runtime = "Great Scratchpad chat runtime" in prompt
    current = current_message(
        prompt,
        "Current user message" if runtime else "Current message",
    )
    delayed_probe = "遅延確認をする" in current

    if not runtime:
        if delayed_probe:
            print("PLAIN_NO_RECALL: 通常履歴だけでは序盤の補正内容を特定できない。")
        elif "Use these deterministic centerline hints silently" in prompt:
            print("CENTERLINE_ONLY: 現在の中心と枝を分けて進める。")
        else:
            print("RAW: 対応関係を一段ずつ検討する。")
        return

    correction_turn = "重要な補正を置く" in current
    already_observed = "Action 1: scratchpad.add_note" in prompt
    if correction_turn and not already_observed:
        print(
            json.dumps(
                {
                    "type": "action",
                    "action": "scratchpad.add_note",
                    "text": CORRECTION_NOTE,
                    "center": "比較単位",
                    "trajectory": "種間差から個体内差へ補正",
                    "anchors": "個体内, 種間",
                    "assumptions": "補正は明示された",
                    "open_questions": "味噌との尺度差",
                    "drift_risks": "種間差への逆戻り"
                },
                ensure_ascii=False,
            )
        )
        return

    if delayed_probe:
        if CORRECTION_NOTE in prompt:
            final(
                "MEMORY_RECALLED: 変更前は種間差、変更後は個体内の異質性。"
                "味噌とのアナロジーには尺度を同一視できない限界がある。"
            )
        else:
            final("RUNTIME_NO_RECALL: 通常履歴だけでは序盤の補正内容を特定できない。")
        return

    final("RUNTIME: 現在の中心と枝を分けて進める。")


if __name__ == "__main__":
    main()
