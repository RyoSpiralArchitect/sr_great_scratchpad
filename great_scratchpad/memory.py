from __future__ import annotations

import json
import uuid
from pathlib import Path

from .audit import audit_turn_md
from .storage import ensure_root, ensure_thread, load_meta, now_iso, safe_id, save_meta
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

def review_queue_dir(root: Path, thread_id: str) -> Path:
    return root / "review_queue" / safe_id(thread_id)

def review_item_path(root: Path, thread_id: str, item_id: str) -> Path:
    item_id = Path(item_id).name
    if not item_id.endswith(".json"):
        item_id += ".json"
    return review_queue_dir(root, thread_id) / item_id

def queue_add_note(root: Path, thread_id: str, action_obj: dict) -> Path:
    ensure_root(root)
    ensure_thread(root, thread_id)
    qdir = review_queue_dir(root, thread_id)
    qdir.mkdir(parents=True, exist_ok=True)
    item_id = f"{now_iso().replace(':', '').replace('+', '-')}-{uuid.uuid4().hex[:8]}.json"
    item = {
        "id": item_id,
        "status": "pending",
        "created_at": now_iso(),
        "thread_id": safe_id(thread_id),
        "action": "scratchpad.add_note",
        "text": str(action_obj.get("text", "")),
        "center": str(action_obj.get("center", "")),
        "trajectory": str(action_obj.get("trajectory", "")),
        "anchors": str(action_obj.get("anchors", "")),
        "assumptions": str(action_obj.get("assumptions", "")),
        "open_questions": str(action_obj.get("open_questions", "")),
        "drift_risks": str(action_obj.get("drift_risks", "")),
    }
    path = qdir / item_id
    path.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
    return path

def load_review_item(root: Path, thread_id: str, item_id: str) -> tuple[dict, Path]:
    path = review_item_path(root, thread_id, item_id)
    if not path.exists():
        raise SystemExit(f"Review item not found: {path}")
    return json.loads(path.read_text(encoding="utf-8")), path

def save_review_item(path: Path, item: dict) -> None:
    item["updated_at"] = now_iso()
    path.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")

def iter_review_items(root: Path, thread_id: str | None = None, status: str = "pending") -> list[tuple[Path, dict]]:
    base = root / "review_queue"
    if not base.exists():
        return []
    roots = [review_queue_dir(root, thread_id)] if thread_id else [p for p in sorted(base.iterdir()) if p.is_dir()]
    out: list[tuple[Path, dict]] = []
    for qdir in roots:
        if not qdir.exists():
            continue
        for path in sorted(qdir.glob("*.json")):
            item = json.loads(path.read_text(encoding="utf-8"))
            if status and item.get("status") != status:
                continue
            out.append((path, item))
    return out

def apply_review_item(root: Path, thread_id: str, item_id: str) -> tuple[int, Path, Path]:
    item, item_path = load_review_item(root, thread_id, item_id)
    if item.get("status") != "pending":
        raise SystemExit(f"Review item is not pending: {item_path.name} status={item.get('status')}")
    turn_no, turn_path = add_turn(
        root=root,
        thread_id=thread_id,
        speaker="note",
        raw=str(item.get("text", "")),
        center=str(item.get("center", "")),
        trajectory=str(item.get("trajectory", "")),
        anchors=str(item.get("anchors", "")),
        assumptions=str(item.get("assumptions", "")),
        open_questions=str(item.get("open_questions", "")),
        drift_risks=str(item.get("drift_risks", "")),
    )
    item["status"] = "applied"
    item["applied_at"] = now_iso()
    item["turn_path"] = str(turn_path)
    save_review_item(item_path, item)
    return turn_no, turn_path, item_path

def reject_review_item(root: Path, thread_id: str, item_id: str) -> Path:
    item, item_path = load_review_item(root, thread_id, item_id)
    if item.get("status") != "pending":
        raise SystemExit(f"Review item is not pending: {item_path.name} status={item.get('status')}")
    item["status"] = "rejected"
    item["rejected_at"] = now_iso()
    save_review_item(item_path, item)
    return item_path

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

def inline_field(value: str, fallback: str = "(none)", max_chars: int = 220) -> str:
    value = value.strip() or fallback
    value = limit_text(value, max_chars)
    return " / ".join(line.strip() for line in value.splitlines() if line.strip())

def source_index_lines(
    tdir: Path,
    sources: list[tuple[str, Path, str, float | None]],
) -> list[str]:
    if not sources:
        return ["(no sources selected)", ""]

    lines: list[str] = []
    for kind, path, text, score in sources:
        score_label = f", score={score:.1f}" if score is not None else ""
        lines.extend(
            [
                f"### {kind}: {path.relative_to(tdir)}{score_label}",
                "",
                f"- Center: {inline_field(parse_section(text, 'Center pin'), '(not specified)')}",
                f"- Trajectory: {inline_field(parse_section(text, 'Trajectory'), '(not specified)')}",
                f"- Anchors: {inline_field(parse_section(text, 'Anchors'))}",
                f"- Open questions: {inline_field(parse_section(text, 'Open questions'))}",
                f"- Drift risks: {inline_field(parse_section(text, 'Drift risks'))}",
                "",
            ]
        )
    return lines

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
    sources: list[tuple[str, Path, str, float | None]] = []

    for path in recent:
        text = path.read_text(encoding="utf-8")
        included.add(path)
        sources.append(("recent", path, text, None))

    for score, path, text in hits:
        if path in included:
            continue
        included.add(path)
        sources.append(("retrieved", path, text, score))

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
            "## Source trajectory index",
            "",
            *source_index_lines(tdir, sources),
        ]
    )

    lines.extend(
        [
            "## Recent turn window",
            "",
        ]
    )

    for kind, path, text, _score in sources:
        if kind != "recent":
            continue
        lines.extend(
            [
                f"### {path.relative_to(tdir)}",
                "",
                limit_text(text, max_chars_per_doc),
                "",
            ]
        )

    lines.extend(["## Retrieved trajectory anchors", ""])

    for kind, path, text, score in sources:
        if kind != "retrieved" or score is None:
            continue
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
