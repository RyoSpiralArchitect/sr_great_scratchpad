from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Iterable

from .constants import CJK_RUN_RE, COINED_RE, JP_PHRASE_RE, LATIN_RE, TURN_SECTION_NAMES
from .storage import now_iso

def cjk_bigrams(s: str) -> list[str]:
    runs = CJK_RUN_RE.findall(s)
    out: list[str] = []
    for run in runs:
        out.extend(run[i:i + 2] for i in range(len(run) - 1))
    return out

def tokenize(text: str) -> list[str]:
    """
    Search tokenizer.
    - Latin / JP-EN technical terms are kept as word-ish tokens.
    - CJK continuous runs are decomposed into character bigrams.
    This is intentionally cheap. The goal is not perfect Japanese NLP.
    The goal is: do not let Japanese retrieval die like a tragic little search hamster.
    """
    latin = [t.lower() for t in LATIN_RE.findall(text) if len(t.strip()) > 1]
    cjk = cjk_bigrams(text)
    return latin + cjk

def auto_keys(*parts: str, max_keys: int = 18) -> list[str]:
    """
    Visible retrieval keys.
    Important:
    - This is NOT the same as tokenize().
    - tokenize() may produce ugly CJK bigrams for scoring.
    - auto_keys() should produce human/LLM-readable anchors.
    """
    text = "\n".join(p for p in parts if p)
    stop = {
        "the", "and", "for", "with", "this", "that", "from", "into",
        "are", "was", "were", "have", "has", "had", "not", "but",
        "する", "ある", "これ", "それ", "ため", "という", "として",
        "こと", "もの", "よう", "かなり", "つまり", "だから",
    }
    candidates: list[str] = []

    # Prefer explicit phrase-like fragments first.
    for part in re.split(r"[,、;\n]+", text):
        item = part.strip()
        if 3 <= len(item) <= 48:
            # Avoid turning whole sentences into keys.
            if not re.search(r"[。！？!?]{1,}", item):
                candidates.append(item)

    # Then collect English / mixed coined terms.
    candidates.extend(COINED_RE.findall(text))

    # Then collect readable Japanese phrases.
    candidates.extend(JP_PHRASE_RE.findall(text))

    seen: set[str] = set()
    out: list[str] = []
    for item in candidates:
        item = item.strip()
        if not item:
            continue
        key = item.lower()
        if key in stop:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= max_keys:
            break

    # Fallback: use frequent tokens, but avoid exposing too many ugly bigrams.
    if not out:
        counts = Counter(tokenize(text))
        for token, _ in counts.most_common():
            if token in stop or token.isdigit():
                continue
            out.append(token)
            if len(out) >= max_keys:
                break

    return out

def build_turn_md(
    turn_no: int,
    speaker: str,
    raw: str,
    center: str,
    trajectory: str,
    anchors: str,
    assumptions: str,
    open_questions: str,
    drift_risks: str,
    retrieval_keys: list[str],
) -> str:
    keys = ", ".join(retrieval_keys) if retrieval_keys else "(none)"

    return f"""# Turn {turn_no:06d} — {speaker}

Date: {now_iso()}
Speaker: {speaker}

## Raw articulation

{raw.strip()}

## Center pin

{center.strip() or "(not specified)"}

## Trajectory

{trajectory.strip() or "(not specified)"}

## Anchors

{anchors.strip() or "(none)"}

## Local assumptions

{assumptions.strip() or "(none)"}

## Open questions

{open_questions.strip() or "(none)"}

## Drift risks

{drift_risks.strip() or "(none)"}

## Retrieval keys

{keys}
"""

def parse_section(md: str, section_name: str) -> str:
    pattern = rf"^## {re.escape(section_name)}[ \t]*\r?\n"
    m = re.search(pattern, md, flags=re.MULTILINE)
    if not m:
        return ""

    known_sections = list(TURN_SECTION_NAMES)
    if section_name not in known_sections:
        known_sections.append(section_name)
    next_sections = [s for s in known_sections if s != section_name]
    next_pattern = "|".join(re.escape(s) for s in next_sections)
    next_m = re.search(
        rf"^## (?:{next_pattern})[ \t]*\r?\n",
        md[m.end():],
        flags=re.MULTILINE,
    )
    end = m.end() + next_m.start() if next_m else len(md)
    return md[m.end():end].strip()

def first_heading(md: str) -> str:
    for line in md.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return "(untitled)"

def iter_markdown_files(tdir: Path) -> Iterable[Path]:
    for sub in ("turns", "blocks"):
        d = tdir / sub
        if d.exists():
            yield from sorted(d.glob("*.md"))

def score_doc(query: str, text: str, path: Path) -> float:
    return score_doc_details(query, text, path)["score"]

def score_doc_details(query: str, text: str, path: Path) -> dict:
    q = query.lower().strip()
    body = text.lower()
    q_tokens = tokenize(query)
    d_tokens = Counter(tokenize(text + "\n" + str(path)))

    score = 0.0
    exact_phrase = bool(q and q in body)
    matched_tokens: list[str] = []
    path_matches: list[str] = []

    if exact_phrase:
        score += 20.0

    for token in q_tokens:
        tf = d_tokens.get(token, 0)
        if tf:
            matched_tokens.append(token)
            score += min(tf, 12) * 2.0
            if token in path.name.lower():
                path_matches.append(token)
                score += 3.0

    all_query_tokens = bool(q_tokens and all(token in d_tokens for token in q_tokens))
    if all_query_tokens:
        score += 8.0

    # Prefer trajectory-preserving blocks slightly when relevant.
    block_bonus = "/blocks/" in str(path).replace("\\", "/")
    if block_bonus:
        score += 1.5

    return {
        "score": score,
        "exact_phrase": exact_phrase,
        "query_tokens": q_tokens,
        "matched_tokens": matched_tokens,
        "path_matches": path_matches,
        "all_query_tokens": all_query_tokens,
        "block_bonus": block_bonus,
    }

def snippet(text: str, query: str, width: int = 360) -> str:
    lower = text.lower()
    q = query.lower().strip()

    idx = lower.find(q) if q else -1

    if idx < 0:
        for token in tokenize(query):
            idx = lower.find(token.lower())
            if idx >= 0:
                break

    if idx < 0:
        idx = 0

    start = max(0, idx - width // 2)
    end = min(len(text), idx + width // 2)

    s = text[start:end].strip()
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s

def limit_text(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n...[truncated]"
