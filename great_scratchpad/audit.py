from __future__ import annotations

import re
from pathlib import Path

from .text import parse_section, tokenize

def contains_cjk(s: str) -> bool:
    return bool(re.search(r"[ぁ-んァ-ヶー一-龥々〆〤]", s))

def split_anchor_items(text: str) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for part in re.split(r"[,、;\n]+", text):
        item = part.strip()
        if not item:
            continue
        if item in {"(none)", "(not specified)"}:
            continue
        if len(item) < 3:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(item)
    return items

def anchor_supported_by_raw(anchor: str, raw: str) -> bool:
    """
    Cheap hallucination/review detector.
    This is not a proof. It is a flag.
    Exact raw match is accepted.
    Otherwise, token overlap is used to reduce false positives for Japanese.
    """
    anchor = anchor.strip()
    if not anchor:
        return True
    raw_lower = raw.lower()
    anchor_lower = anchor.lower()
    if anchor_lower in raw_lower:
        return True
    anchor_tokens = tokenize(anchor)
    raw_tokens = set(tokenize(raw))
    if not anchor_tokens:
        return True
    if not raw_tokens:
        return False
    overlap = sum(1 for tok in anchor_tokens if tok in raw_tokens) / len(anchor_tokens)
    if contains_cjk(anchor):
        return overlap >= 0.66
    return overlap >= 0.50

def annotation_text_from_md(md: str) -> str:
    sections = [
        "Center pin",
        "Trajectory",
        "Anchors",
        "Local assumptions",
        "Open questions",
        "Drift risks",
    ]
    return "\n".join(parse_section(md, s) for s in sections).strip()

def audit_turn_md(path: Path) -> dict:
    md = path.read_text(encoding="utf-8")
    raw = parse_section(md, "Raw articulation")
    annotation = annotation_text_from_md(md)
    anchors = parse_section(md, "Anchors")

    raw_chars = len(raw.strip())
    annotation_chars = len(annotation.strip())
    ratio = annotation_chars / raw_chars if raw_chars else 0.0

    if raw_chars == 0:
        status = "missing_raw"
    elif ratio < 0.20:
        status = "too_compressed"
    elif ratio < 0.50:
        status = "compressed_watch"
    elif ratio <= 1.20:
        status = "ok"
    elif ratio <= 1.50:
        status = "roomy"
    else:
        status = "overgrown_watch"

    unsupported_anchors = [
        a for a in split_anchor_items(anchors)
        if not anchor_supported_by_raw(a, raw)
    ]

    if unsupported_anchors and status == "ok":
        status = "check_anchors"

    return {
        "path": str(path),
        "raw_chars": raw_chars,
        "annotation_chars": annotation_chars,
        "ratio": round(ratio, 3),
        "status": status,
        "unsupported_anchors": unsupported_anchors,
    }
