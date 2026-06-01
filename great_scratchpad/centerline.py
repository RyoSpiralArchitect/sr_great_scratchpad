from __future__ import annotations

import re

from .text import limit_text

CHECKPOINT_CUES = (
    "結局",
    "つまり",
    "なんなん",
    "なんだろう",
    "まとめ",
    "so what",
    "where are we",
    "what does that mean",
)
SHIFT_CUES = (
    "ところで",
    "そういえば",
    "by the way",
    "btw",
    "speaking of",
)
CORRECTION_CUES = (
    "そうじゃなく",
    "じゃなくて",
    "違った",
    "でもそれをいうなら",
    "not exactly",
    "rather",
)
ANALOGY_CUES = (
    "アナロジ",
    "比喩",
    "みたい",
    "ような",
    "というのも",
    "analog",
    "analogy",
    "like",
)
ORIGIN_CUES = (
    "発祥",
    "起源",
    "ルーツ",
    "origin",
)
QUESTION_SUFFIXES = ("?", "？")
JP_TERMS_RE = re.compile(r"[ぁ-んァ-ヶー一-龥々〆〤A-Za-z0-9_./:-]{2,24}")


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    folded = text.casefold()
    return any(needle.casefold() in folded for needle in needles)


def _recent_user_texts(history: list[dict[str, str]], limit: int = 4) -> list[str]:
    users = [msg.get("content", "") for msg in history if msg.get("role") == "user"]
    return [text for text in users[-limit:] if text.strip()]


def _short_question(text: str) -> bool:
    stripped = text.strip()
    return len(stripped) <= 18 and stripped.endswith(QUESTION_SUFFIXES)


def _extract_terms(text: str, max_terms: int = 5) -> list[str]:
    terms: list[str] = []
    for match in JP_TERMS_RE.finditer(text):
        term = match.group(0).strip("。、,.!?！？")
        if len(term) < 2 or term in terms:
            continue
        terms.append(term)
        if len(terms) >= max_terms:
            break
    return terms


def infer_active_centers(history: list[dict[str, str]], user_text: str) -> list[str]:
    recent = _recent_user_texts(history)
    joined = "\n".join(recent + [user_text])
    centers: list[str] = []

    if _contains_any(joined, ("分散", "神経叢", "クラゲ", "味噌", "多様性")):
        centers.append("distributed systems / analogy fit")
    if _contains_any(joined, ("発祥", "起源", "名古屋", "あんかけ", "モーニング", "パスタ")):
        centers.append("origin vs local recombination")
    if _contains_any(joined, ("センターピン", "center", "中心", "drift", "ずれ")):
        centers.append("center pin / drift control")

    if not centers:
        snippets = [limit_text(text.replace("\n", " "), 48) for text in recent[-2:] + [user_text]]
        centers = [snippet for snippet in snippets if snippet]

    deduped: list[str] = []
    for center in centers:
        if center not in deduped:
            deduped.append(center)
    return deduped[:4]


def analyze_centerline(user_text: str, history: list[dict[str, str]]) -> dict:
    text = user_text.strip()
    checkpoint = _contains_any(text, CHECKPOINT_CUES)
    shift = _contains_any(text, SHIFT_CUES)
    correction = _contains_any(text, CORRECTION_CUES)
    analogy = _contains_any(text, ANALOGY_CUES)
    origin = _contains_any(text, ORIGIN_CUES)
    ambiguous_short_question = _short_question(text) and bool(history) and not checkpoint

    flags: list[str] = []
    if checkpoint:
        flags.append("checkpoint")
    if shift:
        flags.append("center_shift")
    if correction:
        flags.append("correction")
    if analogy:
        flags.append("analogy")
    if origin:
        flags.append("origin")
    if ambiguous_short_question:
        flags.append("ambiguous_short_question")

    should_checkpoint = checkpoint or (correction and analogy)
    should_clarify = ambiguous_short_question
    should_queue_note = correction or (shift and analogy) or checkpoint

    guidance: list[str] = []
    if should_checkpoint:
        guidance.append("Separate the active centers before summarizing; choose or fork instead of merging every topic.")
    if should_clarify:
        guidance.append("If the referent is unclear, ask one short clarification before answering.")
    if correction:
        guidance.append("Treat the correction as a reusable trajectory anchor.")
    if shift:
        guidance.append("Name the pivot if it changes the center pin.")
    if should_queue_note:
        guidance.append("Under writer policy, consider scratchpad.add_note for this externally visible trajectory moment.")

    terms = _extract_terms(text)
    active_centers = infer_active_centers(history, text)
    return {
        "flags": flags,
        "active_centers": active_centers,
        "terms": terms,
        "should_checkpoint": should_checkpoint,
        "should_clarify": should_clarify,
        "should_queue_note": should_queue_note,
        "guidance": guidance,
    }


def render_centerline_hints(analysis: dict) -> str:
    flags = analysis.get("flags") or []
    active_centers = analysis.get("active_centers") or []
    guidance = analysis.get("guidance") or []
    terms = analysis.get("terms") or []

    lines = [
        f"flags: {', '.join(flags) if flags else '(none)'}",
        f"active_centers: {', '.join(active_centers) if active_centers else '(unknown)'}",
        f"terms: {', '.join(terms) if terms else '(none)'}",
        f"should_checkpoint: {bool(analysis.get('should_checkpoint'))}",
        f"should_clarify: {bool(analysis.get('should_clarify'))}",
        f"should_queue_note: {bool(analysis.get('should_queue_note'))}",
    ]
    if guidance:
        lines.append("guidance:")
        lines.extend(f"- {item}" for item in guidance)
    else:
        lines.append("guidance: keep the current center explicit if the user pivots.")
    return "\n".join(lines)
