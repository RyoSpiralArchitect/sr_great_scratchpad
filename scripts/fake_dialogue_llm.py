#!/usr/bin/env python3
from __future__ import annotations

import json
import sys


def main() -> None:
    prompt = sys.stdin.read()
    if "Great Scratchpad chat runtime" not in prompt:
        print(
            "Raw reply: 個体内の神経叢と味噌の地域差は、どちらも分散という語を使えるが、"
            "アナロジーの尺度は違う。構成要素の由来と料理様式の発祥も分けておこう。"
        )
        return

    if "Action 1: scratchpad.add_note" not in prompt:
        print(
            json.dumps(
                {
                    "type": "action",
                    "action": "scratchpad.add_note",
                    "text": "個体内の神経叢と味噌の地域差は分散の尺度が違う。発祥論は別中心として保持する。",
                    "center": "個体内分散と地域分散のアナロジー境界",
                    "trajectory": "個体内差への補正を保持し、発祥論を別論点として分けた。",
                    "anchors": "個体内, 神経叢, 味噌, アナロジー, 構成要素, 発祥",
                    "assumptions": "fake dialogue model is deterministic",
                    "open_questions": "実モデルが後続発話で境界を再利用するか",
                    "drift_risks": "全話題を一つの結論へ混ぜること"
                },
                ensure_ascii=False,
            )
        )
        return

    print(
        json.dumps(
            {
                "type": "final",
                "message": (
                    "Scratchpad reply: 個体内の神経叢という中心を維持しよう。味噌とのアナロジーは"
                    "分散だけに限定し、構成要素の由来と料理様式の発祥は別の問いとして扱える。"
                ),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
