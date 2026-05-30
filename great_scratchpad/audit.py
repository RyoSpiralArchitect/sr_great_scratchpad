from __future__ import annotations

import re
from pathlib import Path

from .text import parse_section, tokenize

ANNOTATION_SECTION_NAMES = [
    "Center pin",
    "Trajectory",
    "Anchors",
    "Local assumptions",
    "Open questions",
    "Drift risks",
]
PLACEHOLDER_VALUES = {"", "(none)", "(not specified)"}

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

def is_placeholder(value: str) -> bool:
    return value.strip().lower() in PLACEHOLDER_VALUES

def annotation_sections_from_md(md: str) -> dict[str, str]:
    return {name: parse_section(md, name) for name in ANNOTATION_SECTION_NAMES}

def annotation_text_from_sections(sections: dict[str, str]) -> str:
    meaningful = [
        value.strip()
        for value in sections.values()
        if not is_placeholder(value)
    ]
    return "\n".join(meaningful).strip()

def annotation_text_from_md(md: str) -> str:
    return annotation_text_from_sections(annotation_sections_from_md(md))

def classify_ratio(raw_chars: int, ratio: float) -> str:
    if raw_chars == 0:
        return "missing_raw"
    if ratio < 0.20:
        return "too_compressed"
    if ratio < 0.50:
        return "compressed_watch"
    if ratio <= 1.20:
        return "ok"

    roomy_limit = 1.50
    if raw_chars < 180:
        roomy_limit = 3.00
    elif raw_chars < 400:
        roomy_limit = 2.00

    if ratio <= roomy_limit:
        return "roomy"
    return "overgrown_watch"

def audit_turn_md(path: Path) -> dict:
    md = path.read_text(encoding="utf-8")
    raw = parse_section(md, "Raw articulation")
    sections = annotation_sections_from_md(md)
    annotation = annotation_text_from_sections(sections)
    anchors = parse_section(md, "Anchors")

    raw_chars = len(raw.strip())
    annotation_chars = len(annotation.strip())
    ratio = annotation_chars / raw_chars if raw_chars else 0.0

    status = classify_ratio(raw_chars, ratio)
    missing_fields = [
        name for name, value in sections.items()
        if is_placeholder(value)
    ]
    anchors_list = split_anchor_items(anchors)
    unsupported_anchors = [
        a for a in anchors_list
        if not anchor_supported_by_raw(a, raw)
    ]

    if unsupported_anchors and status in {"ok", "roomy"}:
        status = "check_anchors"
    if len(missing_fields) >= 4 and status in {"ok", "roomy"}:
        status = "thin_annotation"

    return {
        "path": str(path),
        "raw_chars": raw_chars,
        "annotation_chars": annotation_chars,
        "ratio": round(ratio, 3),
        "status": status,
        "missing_fields": missing_fields,
        "anchor_count": len(anchors_list),
        "unsupported_anchors": unsupported_anchors,
    }

def audit_turn_values(
    raw: str,
    center: str = "",
    trajectory: str = "",
    anchors: str = "",
    assumptions: str = "",
    open_questions: str = "",
    drift_risks: str = "",
    path: str = "(draft)",
) -> dict:
    sections = {
        "Center pin": center,
        "Trajectory": trajectory,
        "Anchors": anchors,
        "Local assumptions": assumptions,
        "Open questions": open_questions,
        "Drift risks": drift_risks,
    }
    annotation = annotation_text_from_sections(sections)
    raw_chars = len(raw.strip())
    annotation_chars = len(annotation.strip())
    ratio = annotation_chars / raw_chars if raw_chars else 0.0
    status = classify_ratio(raw_chars, ratio)
    missing_fields = [
        name for name, value in sections.items()
        if is_placeholder(value)
    ]
    anchors_list = split_anchor_items(anchors)
    unsupported_anchors = [
        a for a in anchors_list
        if not anchor_supported_by_raw(a, raw)
    ]

    if unsupported_anchors and status in {"ok", "roomy"}:
        status = "check_anchors"
    if len(missing_fields) >= 4 and status in {"ok", "roomy"}:
        status = "thin_annotation"

    return {
        "path": path,
        "raw_chars": raw_chars,
        "annotation_chars": annotation_chars,
        "ratio": round(ratio, 3),
        "status": status,
        "missing_fields": missing_fields,
        "anchor_count": len(anchors_list),
        "unsupported_anchors": unsupported_anchors,
    }
