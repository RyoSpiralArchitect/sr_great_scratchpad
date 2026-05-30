from __future__ import annotations

import json
import uuid
from pathlib import Path

from .audit import audit_turn_md, audit_turn_values
from .storage import ensure_root, ensure_thread, load_meta, now_iso, safe_id, save_meta
from .text import auto_keys, build_turn_md, first_heading, iter_markdown_files, limit_text, parse_section, score_doc, score_doc_details, snippet

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
        anchors,
        center,
        trajectory,
        open_questions,
        drift_risks,
        assumptions,
        raw,
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

def audit_review_item(item: dict, path: Path | None = None) -> dict:
    return audit_turn_values(
        raw=str(item.get("text", "")),
        center=str(item.get("center", "")),
        trajectory=str(item.get("trajectory", "")),
        anchors=str(item.get("anchors", "")),
        assumptions=str(item.get("assumptions", "")),
        open_questions=str(item.get("open_questions", "")),
        drift_risks=str(item.get("drift_risks", "")),
        path=str(path) if path else str(item.get("id", "(draft)")),
    )

def review_item_is_safe(item: dict, audit_result: dict | None = None) -> bool:
    if item.get("status") != "pending":
        return False
    audit_result = audit_result or audit_review_item(item)
    return (
        audit_result.get("status") in {"ok", "roomy"}
        and not audit_result.get("unsupported_anchors")
        and int(audit_result.get("raw_chars", 0)) > 0
    )

def render_review_item(path: Path, item: dict, include_audit: bool = True) -> str:
    lines = [
        f"# Review item {path.name}",
        "",
        f"- Status: {item.get('status', '')}",
        f"- Thread: {item.get('thread_id', '')}",
        f"- Created: {item.get('created_at', '')}",
        f"- Action: {item.get('action', '')}",
        "",
        "## Text",
        "",
        str(item.get("text", "")).strip() or "(empty)",
        "",
        "## Annotation",
        "",
        f"- Center: {inline_field(str(item.get('center', '')), '(not specified)')}",
        f"- Trajectory: {inline_field(str(item.get('trajectory', '')), '(not specified)')}",
        f"- Anchors: {inline_field(str(item.get('anchors', '')))}",
        f"- Local assumptions: {inline_field(str(item.get('assumptions', '')))}",
        f"- Open questions: {inline_field(str(item.get('open_questions', '')))}",
        f"- Drift risks: {inline_field(str(item.get('drift_risks', '')))}",
        "",
    ]
    if include_audit:
        audit = audit_review_item(item, path)
        lines.extend(
            [
                "## Audit preview",
                "",
                f"- raw_chars: {audit['raw_chars']}",
                f"- annotation_chars: {audit['annotation_chars']}",
                f"- ratio: {audit['ratio']}",
                f"- status: {audit['status']}",
                f"- safe_to_apply: {review_item_is_safe(item, audit)}",
                f"- anchor_count: {audit['anchor_count']}",
            ]
        )
        missing = audit.get("missing_fields", [])
        if missing:
            lines.append(f"- missing_fields: {', '.join(missing)}")
        unsupported = audit.get("unsupported_anchors", [])
        if unsupported:
            lines.append(f"- unsupported_anchors: {', '.join(unsupported)}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"

def edit_review_item(root: Path, thread_id: str, item_id: str, updates: dict[str, str]) -> tuple[dict, Path]:
    item, item_path = load_review_item(root, thread_id, item_id)
    if item.get("status") != "pending":
        raise SystemExit(f"Review item is not pending: {item_path.name} status={item.get('status')}")
    allowed = {
        "text",
        "center",
        "trajectory",
        "anchors",
        "assumptions",
        "open_questions",
        "drift_risks",
    }
    changed = False
    for key, value in updates.items():
        if key not in allowed:
            raise SystemExit(f"Review item field is not editable: {key}")
        if value is None:
            continue
        item[key] = str(value)
        changed = True
    if not changed:
        raise SystemExit("No review item fields were provided to edit.")
    item.setdefault("edit_history", []).append(
        {
            "edited_at": now_iso(),
            "fields": sorted(key for key, value in updates.items() if value is not None),
        }
    )
    save_review_item(item_path, item)
    return item, item_path

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

def apply_safe_review_items(root: Path, thread_id: str) -> list[tuple[int, Path, Path, dict]]:
    applied: list[tuple[int, Path, Path, dict]] = []
    for item_path, item in iter_review_items(root, thread_id, status="pending"):
        audit = audit_review_item(item, item_path)
        if not review_item_is_safe(item, audit):
            continue
        turn_no, turn_path, applied_item_path = apply_review_item(root, thread_id, item_path.name)
        applied.append((turn_no, turn_path, applied_item_path, audit))
    return applied

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

def retrieval_reason_line(query: str, path: Path, text: str, score: float | None) -> str:
    if score is None:
        return "- Selection: recent window"
    details = score_doc_details(query, text, path)
    bits: list[str] = []
    if details.get("exact_phrase"):
        bits.append("exact phrase")
    matched = details.get("matched_tokens", [])
    if matched:
        shown = ", ".join(str(token) for token in matched[:12])
        if len(matched) > 12:
            shown += f", +{len(matched) - 12} more"
        bits.append(f"matched tokens: {shown}")
    if details.get("all_query_tokens"):
        bits.append("all query tokens")
    if details.get("path_matches"):
        bits.append("path match")
    if details.get("block_bonus"):
        bits.append("trajectory block bonus")
    if not bits:
        bits.append("score-only match")
    return f"- Selection: score={score:.1f}; " + "; ".join(bits)

def source_index_lines(
    tdir: Path,
    sources: list[tuple[str, Path, str, float | None]],
    query: str = "",
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
                retrieval_reason_line(query, path, text, score),
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
            *source_index_lines(tdir, sources, query=query),
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
