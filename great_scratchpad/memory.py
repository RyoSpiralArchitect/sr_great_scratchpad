from __future__ import annotations

import json
from pathlib import Path

from .audit import audit_turn_md
from .storage import ensure_root, ensure_thread, load_meta, now_iso, save_meta
from .text import auto_keys, build_turn_md, first_heading, iter_markdown_files, limit_text, parse_section, score_doc, snippet

def recent_turn_files(tdir: Path, n: int) -> list[Path]:
    turns = sorted((tdir / "turns").glob("*.md"))
    return turns[-n:] if n > 0 else []

def retrieve(tdir: Path, query: str, top: int) -> list[tuple[float, Path, str]]:
    hits: list[tuple[float, Path, str]] = []

    for path in iter_markdown_files(tdir):
        text = path.read_text(encoding="utf-8")
        score = score_doc(query, text, path)
        if score > 0:
            hits.append((score, path, text))

    hits.sort(key=lambda x: x[0], reverse=True)
    return hits[:top]

def add_turn(
    root: Path,
    thread_id: str,
    speaker: str,
    raw: str,
    center: str = "",
    trajectory: str = "",
    anchors: str = "",
    assumptions: str = "",
    open_questions: str = "",
    drift_risks: str = "",
) -> tuple[int, Path]:
    ensure_root(root)
    tdir = ensure_thread(root, thread_id)

    meta = load_meta(tdir)
    turn_no = int(meta.get("last_turn", 0)) + 1

    keys = auto_keys(
        raw,
        center,
        trajectory,
        anchors,
        assumptions,
        open_questions,
        drift_risks,
    )

    md = build_turn_md(
        turn_no=turn_no,
        speaker=speaker,
        raw=raw,
        center=center,
        trajectory=trajectory,
        anchors=anchors,
        assumptions=assumptions,
        open_questions=open_questions,
        drift_risks=drift_risks,
        retrieval_keys=keys,
    )

    filename = f"{turn_no:06d}-{speaker}.md"
    path = tdir / "turns" / filename
    path.write_text(md, encoding="utf-8")

    meta["last_turn"] = turn_no
    meta["updated_at"] = now_iso()
    save_meta(tdir, meta)

    return turn_no, path

def compact_one_range(
    tdir: Path,
    start: int,
    end: int,
    raw_excerpt_chars: int,
) -> Path:
    out = [
        f"# Trajectory block {start:06d}-{end:06d}",
        "",
        f"Created: {now_iso()}",
        "",
        "Intent: Preserve conversational trajectory, not merely final conclusions.",
        "",
        "## Turns covered",
        "",
        f"{start:06d} through {end:06d}",
        "",
        "## Trajectory ledger",
        "",
    ]

    for turn_no in range(start, end + 1):
        matches = list((tdir / "turns").glob(f"{turn_no:06d}-*.md"))
        if not matches:
            continue

        path = matches[0]
        md = path.read_text(encoding="utf-8")

        heading = first_heading(md)
        raw = parse_section(md, "Raw articulation")
        center = parse_section(md, "Center pin")
        trajectory = parse_section(md, "Trajectory")
        anchors = parse_section(md, "Anchors")
        assumptions = parse_section(md, "Local assumptions")
        open_q = parse_section(md, "Open questions")
        drift = parse_section(md, "Drift risks")
        keys = parse_section(md, "Retrieval keys")

        out.extend(
            [
                f"### {heading}",
                "",
                "#### Center pin",
                "",
                center or "(not specified)",
                "",
                "#### Trajectory",
                "",
                trajectory or "(not specified)",
                "",
                "#### Anchors",
                "",
                anchors or "(none)",
                "",
                "#### Local assumptions",
                "",
                assumptions or "(none)",
                "",
                "#### Open questions",
                "",
                open_q or "(none)",
                "",
                "#### Drift risks",
                "",
                drift or "(none)",
                "",
                "#### Retrieval keys",
                "",
                keys or "(none)",
                "",
                "#### Raw articulation excerpt",
                "",
                limit_text(raw, raw_excerpt_chars),
                "",
            ]
        )

    block_path = tdir / "blocks" / f"{start:06d}-{end:06d}.md"
    block_path.write_text("\n".join(out).strip() + "\n", encoding="utf-8")
    return block_path

def build_context_pack(
    root: Path,
    tdir: Path,
    query: str,
    recent_n: int,
    top: int,
    max_chars_per_doc: int,
    include_guide: bool = False,
) -> str:
    recent = recent_turn_files(tdir, recent_n)
    hits = retrieve(tdir, query, top)
    included: set[Path] = set()
    lines = [
        "# Great Scratchpad Context Pack",
        "",
        "Use this as external memory. It preserves observable articulation trajectory, not hidden reasoning.",
        "",
        "## Query",
        "",
        query,
        "",
    ]

    if include_guide:
        guide_path = root / "guide.md"
        if guide_path.exists():
            lines.extend(
                [
                    "## Annotation guide",
                    "",
                    guide_path.read_text(encoding="utf-8").strip(),
                    "",
                ]
            )

    lines.extend(
        [
            "## Recent turn window",
            "",
        ]
    )

    for path in recent:
        included.add(path)
        lines.extend(
            [
                f"### {path.relative_to(tdir)}",
                "",
                limit_text(path.read_text(encoding="utf-8"), max_chars_per_doc),
                "",
            ]
        )

    lines.extend(["## Retrieved trajectory anchors", ""])

    for score, path, text in hits:
        if path in included:
            continue
        included.add(path)
        lines.extend(
            [
                f"### score={score:.1f} — {path.relative_to(tdir)}",
                "",
                limit_text(text, max_chars_per_doc),
                "",
            ]
        )

    return "\n".join(lines).strip() + "\n"

def render_search_results(tdir: Path, query: str, top: int = 5, width: int = 420) -> str:
    hits = retrieve(tdir, query, top)
    if not hits:
        return "(no hits)"

    out: list[str] = []
    for i, (score, path, text) in enumerate(hits, start=1):
        out.extend(
            [
                f"## Hit {i}: score={score:.1f} path={path.relative_to(tdir)}",
                snippet(text, query, width=width),
                "",
            ]
        )
    return "\n".join(out).strip()

def render_recent_turns(tdir: Path, n: int = 5, max_chars: int = 1600) -> str:
    files = recent_turn_files(tdir, n)
    if not files:
        return "(no recent turns)"

    out: list[str] = []
    for path in files:
        out.extend(
            [
                f"--- {path.relative_to(tdir)} ---",
                limit_text(path.read_text(encoding="utf-8"), max_chars),
                "",
            ]
        )
    return "\n".join(out).strip()

def render_audit(tdir: Path, as_json: bool = True, max_flags: int = 8) -> str:
    files = sorted((tdir / "turns").glob("*.md"))
    if not files:
        return "(no turns to audit)"

    results = [audit_turn_md(path) for path in files]
    if as_json:
        return json.dumps(results, ensure_ascii=False, indent=2)

    out: list[str] = []
    for r in results:
        rel = Path(r["path"]).relative_to(tdir)
        out.extend(
            [
                str(rel),
                f"  raw_chars: {r['raw_chars']}",
                f"  annotation_chars: {r['annotation_chars']}",
                f"  ratio: {r['ratio']}",
                f"  status: {r['status']}",
            ]
        )
        flags = r["unsupported_anchors"]
        missing = r.get("missing_fields", [])
        if missing:
            out.append(f"  missing_fields: {', '.join(missing)}")
        if "anchor_count" in r:
            out.append(f"  anchor_count: {r['anchor_count']}")
        if flags:
            shown = flags[:max_flags]
            out.append(f"  unsupported_anchors: {', '.join(shown)}")
            if len(flags) > max_flags:
                out.append(f"  ...and {len(flags) - max_flags} more")
        out.append("")
    return "\n".join(out).strip()
