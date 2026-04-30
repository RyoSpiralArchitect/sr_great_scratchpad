#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shlex
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable


ROOT_DEFAULT = ".great_scratchpad"
LATIN_RE = re.compile(r"[A-Za-z0-9_./:-]+", re.UNICODE)
CJK_RUN_RE = re.compile(r"[ぁ-んァ-ヶー一-龥々〆〤]{2,}", re.UNICODE)
COINED_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9_./:-]{2,}",
    re.UNICODE,
)
JP_PHRASE_RE = re.compile(
    r"[ぁ-んァ-ヶー一-龥々〆〤]{4,24}",
    re.UNICODE,
)

ANNOTATION_GUIDE = """# Great Scratchpad annotation guide
これはあなた、または未来の別スレッドのあなたのためのメモ帳です。
要点整理ではありません。
## 目的
このターンの推論軌道を、未来のあなたが再構成できる形で残してください。
「何が結論か」だけではなく、
「なぜそこへ向かったか」
「どの比喩・前提・違和感・脱線が効いたか」
「どの問いがまだ閉じていないか」
を残してください。
ここで保存するのは、会話中に外部化された articulation です。
非公開の思考過程を作り出したり、raw articulation にないことを勝手に足したりしないでください。
## 書く時の感覚
- 自分宛の足場メモとして書く
- きれいな議事録にしようとしない
- 短くまとめようとしない
- 迷い、違和感、未確定性を残す
- このターンで会話の重心がどう動いたかを書く
- 後で検索されそうな coined term、比喩、命名を残す
- raw articulation にないことを勝手に足さない
## 特に残すもの
- Center pin: このターンの中心軸
- Trajectory: どこからどこへ話が動いたか
- Anchors: 再利用されそうな語句、比喩、命名
- Local assumptions: その時点で有効だった前提
- Open questions: まだ閉じていない問い
- Drift risks: 将来ズレやすいポイント
## 避けること
- 議事録的要約
- 体言止めの羅列
- 結論だけの抜き出し
- 「つまり〜」だけで済ませること
- rawにない概念を、あったことにすること
"""


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def safe_id(value: str) -> str:
    value = value.strip()
    value = re.sub(r"[^\w.\-ぁ-んァ-ン一-龥]+", "-", value, flags=re.UNICODE)
    value = value.strip("-")
    if not value:
        raise ValueError("Thread id became empty after normalization.")
    return value


def root_path(args: argparse.Namespace) -> Path:
    return Path(args.root).expanduser().resolve()


def thread_path(root: Path, thread_id: str) -> Path:
    return root / "threads" / safe_id(thread_id)


def ensure_root(root: Path) -> None:
    (root / "threads").mkdir(parents=True, exist_ok=True)
    config = root / "config.json"
    if not config.exists():
        config.write_text(
            json.dumps(
                {
                    "created_at": now_iso(),
                    "format": "great-scratchpad-v0.2",
                    "principle": "Preserve trajectory, not just conclusions.",
                    "stance": "Loose, roomy, raw-ish memory. Resist over-smart compression.",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    guide = root / "guide.md"
    if not guide.exists():
        guide.write_text(ANNOTATION_GUIDE, encoding="utf-8")


def ensure_thread(root: Path, thread_id: str) -> Path:
    tdir = thread_path(root, thread_id)
    if not tdir.exists():
        raise SystemExit(f"Thread not found: {thread_id!r}. Create it with: new {thread_id!r}")
    return tdir


def load_meta(tdir: Path) -> dict:
    meta_path = tdir / "meta.json"
    if not meta_path.exists():
        return {"last_turn": 0, "created_at": now_iso()}
    return json.loads(meta_path.read_text(encoding="utf-8"))


def save_meta(tdir: Path, meta: dict) -> None:
    (tdir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_text_arg(text: str | None, text_file: str | None) -> str:
    if text_file:
        return Path(text_file).read_text(encoding="utf-8")
    if text is not None:
        return text
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("Provide --text, --text-file, or pipe text through stdin.")


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
    pattern = rf"^## {re.escape(section_name)}\s*\n(.*?)(?=^## |\Z)"
    m = re.search(pattern, md, flags=re.MULTILINE | re.DOTALL)
    if not m:
        return ""
    return m.group(1).strip()


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
    q = query.lower().strip()
    body = text.lower()
    q_tokens = tokenize(query)
    d_tokens = Counter(tokenize(text + "\n" + str(path)))

    score = 0.0

    if q and q in body:
        score += 20.0

    for token in q_tokens:
        tf = d_tokens.get(token, 0)
        if tf:
            score += min(tf, 12) * 2.0
            if token in path.name.lower():
                score += 3.0

    if q_tokens and all(token in d_tokens for token in q_tokens):
        score += 8.0

    # Prefer trajectory-preserving blocks slightly when relevant.
    if "/blocks/" in str(path).replace("\\", "/"):
        score += 1.5

    return score


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


def cmd_init(args: argparse.Namespace) -> None:
    root = root_path(args)
    ensure_root(root)
    print(f"Initialized Great Scratchpad at: {root}")


def cmd_new(args: argparse.Namespace) -> None:
    root = root_path(args)
    ensure_root(root)

    tdir = thread_path(root, args.thread)
    (tdir / "turns").mkdir(parents=True, exist_ok=True)
    (tdir / "blocks").mkdir(parents=True, exist_ok=True)

    meta_path = tdir / "meta.json"
    if not meta_path.exists():
        save_meta(
            tdir,
            {
                "thread_id": safe_id(args.thread),
                "title": args.title or args.thread,
                "created_at": now_iso(),
                "last_turn": 0,
                "principle": "Store articulation trajectory, not only conclusions.",
            },
        )

    print(f"Thread ready: {tdir}")


def cmd_list(args: argparse.Namespace) -> None:
    root = root_path(args)
    ensure_root(root)
    threads_dir = root / "threads"

    threads = sorted(p for p in threads_dir.iterdir() if p.is_dir())
    if not threads:
        print("(no threads)")
        return

    for tdir in threads:
        meta = load_meta(tdir)
        print(f"{tdir.name}\tturns={meta.get('last_turn', 0)}\ttitle={meta.get('title', '')}")


def cmd_add(args: argparse.Namespace) -> None:
    root = root_path(args)
    raw = read_text_arg(args.text, args.text_file)
    turn_no, path = add_turn(
        root=root,
        thread_id=args.thread,
        speaker=args.speaker,
        raw=raw,
        center=args.center or "",
        trajectory=args.trajectory or "",
        anchors=args.anchors or "",
        assumptions=args.assumptions or "",
        open_questions=args.open_questions or "",
        drift_risks=args.drift_risks or "",
    )

    print(f"Added turn {turn_no:06d}: {path}")


def cmd_search(args: argparse.Namespace) -> None:
    root = root_path(args)
    tdir = ensure_thread(root, args.thread)

    hits = retrieve(tdir, args.query, args.top)

    if not hits:
        print("(no hits)")
        return

    for i, (score, path, text) in enumerate(hits, start=1):
        rel = path.relative_to(tdir)
        print(f"\n## Hit {i}: score={score:.1f} path={rel}")
        print(snippet(text, args.query, width=args.width))


def cmd_recent(args: argparse.Namespace) -> None:
    root = root_path(args)
    tdir = ensure_thread(root, args.thread)

    files = recent_turn_files(tdir, args.n)
    if not files:
        print("(no recent turns)")
        return

    for path in files:
        print(f"\n--- {path.relative_to(tdir)} ---")
        print(limit_text(path.read_text(encoding="utf-8"), args.max_chars))


def cmd_audit(args: argparse.Namespace) -> None:
    root = root_path(args)
    tdir = ensure_thread(root, args.thread)

    files = sorted((tdir / "turns").glob("*.md"))
    if not files:
        print("(no turns to audit)")
        return

    results = [audit_turn_md(path) for path in files]

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    for r in results:
        rel = Path(r["path"]).relative_to(tdir)
        print(
            f"{rel}\n"
            f"  raw_chars: {r['raw_chars']}\n"
            f"  annotation_chars: {r['annotation_chars']}\n"
            f"  ratio: {r['ratio']}\n"
            f"  status: {r['status']}"
        )
        flags = r["unsupported_anchors"]
        if flags:
            shown = flags[:args.max_flags]
            print(f"  unsupported_anchors: {', '.join(shown)}")
            if len(flags) > args.max_flags:
                print(f"  ...and {len(flags) - args.max_flags} more")
        print()


def cmd_guide(args: argparse.Namespace) -> None:
    root = root_path(args)
    ensure_root(root)
    guide = root / "guide.md"
    print(guide.read_text(encoding="utf-8"))


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


def cmd_compact(args: argparse.Namespace) -> None:
    root = root_path(args)
    tdir = ensure_thread(root, args.thread)

    meta = load_meta(tdir)
    last = int(meta.get("last_turn", 0))
    if last <= 0:
        print("(no turns to compact)")
        return

    start = args.start or 1
    end = args.end or last

    if start < 1 or end > last or start > end:
        raise SystemExit(f"Invalid range: start={start}, end={end}, last_turn={last}")

    made: list[Path] = []
    cur = start

    while cur <= end:
        block_end = min(cur + args.block_size - 1, end)
        made.append(compact_one_range(tdir, cur, block_end, args.raw_excerpt_chars))
        cur = block_end + 1

    for path in made:
        print(f"Wrote block: {path.relative_to(tdir)}")


def cmd_pack(args: argparse.Namespace) -> None:
    root = root_path(args)
    ensure_root(root)
    tdir = ensure_thread(root, args.thread)

    recent = recent_turn_files(tdir, args.recent)
    hits = retrieve(tdir, args.query, args.top)

    included: set[Path] = set()
    lines = [
        "# Great Scratchpad Context Pack",
        "",
        "Use this as external memory. It preserves observable articulation trajectory, not hidden reasoning.",
        "",
        "## Query",
        "",
        args.query,
        "",
    ]

    if args.include_guide:
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
                limit_text(path.read_text(encoding="utf-8"), args.max_chars_per_doc),
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
                limit_text(text, args.max_chars_per_doc),
                "",
            ]
        )

    output = "\n".join(lines).strip() + "\n"

    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
        print(f"Wrote context pack: {args.out}")
    else:
        print(output)


REPL_HELP = """Great Scratchpad REPL commands:

  help                         Show this help.
  root                         Show active scratchpad root.
  list | threads               List threads.
  new THREAD [TITLE...]        Create or open a thread.
  use THREAD                   Set the active thread.
  thread                       Show the active thread.
  add [SPEAKER] [THREAD]       Add one turn. Raw articulation is multiline.
  note [THREAD]                Add a note turn.
  search QUERY [--top N]       Search the active thread.
  recent [N]                   Show recent turns from the active thread.
  pack QUERY [options]         Build a context pack from the active thread.
  audit [--json]               Audit the active thread.
  guide                        Print the annotation guide.
  compact [options]            Create trajectory blocks for the active thread.
  quit | exit                  Leave the REPL.

Multiline raw input ends with a single '.' line.
"""


def _input_line(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        raise KeyboardInterrupt


def _input_block(label: str) -> str:
    print(f"{label} (finish with a single '.' line)")
    lines: list[str] = []
    while True:
        line = _input_line("| ")
        if line == ".":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def _input_field(label: str) -> str:
    return _input_line(f"{label}> ").strip()


def _active_thread_or_warn(active_thread: str | None) -> str | None:
    if active_thread:
        return active_thread
    print("No active thread. Use: new THREAD or use THREAD")
    return None


def _parse_repl_args(parser: argparse.ArgumentParser, argv: list[str]) -> argparse.Namespace | None:
    try:
        return parser.parse_args(argv)
    except SystemExit:
        return None


def _repl_search_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="search", add_help=False)
    p.add_argument("query", nargs="+")
    p.add_argument("--top", type=int, default=8)
    p.add_argument("--width", type=int, default=420)
    return p


def _repl_recent_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="recent", add_help=False)
    p.add_argument("n", nargs="?", type=int, default=6)
    p.add_argument("--max-chars", type=int, default=1600)
    return p


def _repl_pack_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pack", add_help=False)
    p.add_argument("query", nargs="+")
    p.add_argument("--recent", type=int, default=6)
    p.add_argument("--top", type=int, default=6)
    p.add_argument("--max-chars-per-doc", type=int, default=2200)
    p.add_argument("--include-guide", action="store_true")
    p.add_argument("--out", default=None)
    return p


def _repl_audit_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="audit", add_help=False)
    p.add_argument("--json", action="store_true")
    p.add_argument("--max-flags", type=int, default=8)
    return p


def _repl_compact_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="compact", add_help=False)
    p.add_argument("--start", type=int, default=None)
    p.add_argument("--end", type=int, default=None)
    p.add_argument("--block-size", type=int, default=30)
    p.add_argument("--raw-excerpt-chars", type=int, default=900)
    return p


def _repl_handle_add(root: Path, active_thread: str | None, tokens: list[str]) -> str | None:
    if tokens[0] == "note":
        speaker = "note"
        thread_id = tokens[1] if len(tokens) > 1 else active_thread
    else:
        speaker = tokens[1] if len(tokens) > 1 else "note"
        thread_id = tokens[2] if len(tokens) > 2 else active_thread

    if speaker not in {"user", "assistant", "system", "tool", "note"}:
        print("Speaker must be one of: user, assistant, system, tool, note")
        return active_thread

    thread_id = _active_thread_or_warn(thread_id)
    if not thread_id:
        return active_thread

    raw = _input_block("Raw articulation")
    if not raw:
        print("No raw articulation; skipped.")
        return active_thread

    center = _input_field("Center pin")
    trajectory = _input_field("Trajectory")
    anchors = _input_field("Anchors")
    assumptions = _input_field("Local assumptions")
    open_questions = _input_field("Open questions")
    drift_risks = _input_field("Drift risks")

    turn_no, path = add_turn(
        root=root,
        thread_id=thread_id,
        speaker=speaker,
        raw=raw,
        center=center,
        trajectory=trajectory,
        anchors=anchors,
        assumptions=assumptions,
        open_questions=open_questions,
        drift_risks=drift_risks,
    )
    print(f"Added turn {turn_no:06d}: {path}")
    return thread_id


def _repl_run_command(root: Path, active_thread: str | None, line: str) -> tuple[str | None, bool]:
    try:
        tokens = shlex.split(line)
    except ValueError as exc:
        print(f"Could not parse command: {exc}")
        return active_thread, True

    if not tokens:
        return active_thread, True

    cmd = tokens[0].lower()

    if cmd in {"quit", "exit"}:
        return active_thread, False

    if cmd in {"help", "?"}:
        print(REPL_HELP)
        return active_thread, True

    if cmd == "root":
        print(root)
        return active_thread, True

    if cmd in {"list", "threads"}:
        cmd_list(argparse.Namespace(root=str(root)))
        return active_thread, True

    if cmd == "new":
        if len(tokens) < 2:
            print("Usage: new THREAD [TITLE...]")
            return active_thread, True
        thread_id = tokens[1]
        title = " ".join(tokens[2:])
        cmd_new(argparse.Namespace(root=str(root), thread=thread_id, title=title))
        return thread_id, True

    if cmd == "use":
        if len(tokens) != 2:
            print("Usage: use THREAD")
            return active_thread, True
        thread_id = tokens[1]
        ensure_thread(root, thread_id)
        print(f"Active thread: {safe_id(thread_id)}")
        return safe_id(thread_id), True

    if cmd == "thread":
        print(active_thread or "(none)")
        return active_thread, True

    if cmd in {"add", "note"}:
        return _repl_handle_add(root, active_thread, tokens), True

    if cmd == "search":
        thread_id = _active_thread_or_warn(active_thread)
        if not thread_id:
            return active_thread, True
        ns = _parse_repl_args(_repl_search_parser(), tokens[1:])
        if not ns:
            print("Usage: search QUERY [--top N] [--width N]")
            return active_thread, True
        cmd_search(
            argparse.Namespace(
                root=str(root),
                thread=thread_id,
                query=" ".join(ns.query),
                top=ns.top,
                width=ns.width,
            )
        )
        return active_thread, True

    if cmd == "recent":
        thread_id = _active_thread_or_warn(active_thread)
        if not thread_id:
            return active_thread, True
        ns = _parse_repl_args(_repl_recent_parser(), tokens[1:])
        if not ns:
            print("Usage: recent [N] [--max-chars N]")
            return active_thread, True
        cmd_recent(argparse.Namespace(root=str(root), thread=thread_id, n=ns.n, max_chars=ns.max_chars))
        return active_thread, True

    if cmd == "pack":
        thread_id = _active_thread_or_warn(active_thread)
        if not thread_id:
            return active_thread, True
        ns = _parse_repl_args(_repl_pack_parser(), tokens[1:])
        if not ns:
            print("Usage: pack QUERY [--recent N] [--top N] [--include-guide] [--out PATH]")
            return active_thread, True
        cmd_pack(
            argparse.Namespace(
                root=str(root),
                thread=thread_id,
                query=" ".join(ns.query),
                recent=ns.recent,
                top=ns.top,
                max_chars_per_doc=ns.max_chars_per_doc,
                include_guide=ns.include_guide,
                out=ns.out,
            )
        )
        return active_thread, True

    if cmd == "audit":
        thread_id = _active_thread_or_warn(active_thread)
        if not thread_id:
            return active_thread, True
        ns = _parse_repl_args(_repl_audit_parser(), tokens[1:])
        if not ns:
            print("Usage: audit [--json] [--max-flags N]")
            return active_thread, True
        cmd_audit(argparse.Namespace(root=str(root), thread=thread_id, json=ns.json, max_flags=ns.max_flags))
        return active_thread, True

    if cmd == "guide":
        cmd_guide(argparse.Namespace(root=str(root)))
        return active_thread, True

    if cmd == "compact":
        thread_id = _active_thread_or_warn(active_thread)
        if not thread_id:
            return active_thread, True
        ns = _parse_repl_args(_repl_compact_parser(), tokens[1:])
        if not ns:
            print("Usage: compact [--start N] [--end N] [--block-size N]")
            return active_thread, True
        cmd_compact(
            argparse.Namespace(
                root=str(root),
                thread=thread_id,
                start=ns.start,
                end=ns.end,
                block_size=ns.block_size,
                raw_excerpt_chars=ns.raw_excerpt_chars,
            )
        )
        return active_thread, True

    print(f"Unknown command: {tokens[0]}. Type 'help' for commands.")
    return active_thread, True


def cmd_repl(args: argparse.Namespace) -> None:
    root = root_path(args)
    ensure_root(root)

    active_thread = safe_id(args.thread) if args.thread else None
    if active_thread:
        try:
            ensure_thread(root, active_thread)
        except SystemExit as exc:
            print(exc)
            active_thread = None

    print("Great Scratchpad REPL. Type 'help' for commands, 'quit' to exit.")
    print(f"Root: {root}")
    if active_thread:
        print(f"Active thread: {active_thread}")

    while True:
        prompt = f"sr:{active_thread}> " if active_thread else "sr> "
        try:
            line = _input_line(prompt)
            active_thread, keep_running = _repl_run_command(root, active_thread, line)
        except KeyboardInterrupt:
            print()
            break
        except SystemExit as exc:
            if exc.code:
                print(exc)
            keep_running = True

        if not keep_running:
            break


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Great Scratchpad: trajectory-preserving markdown memory.",
    )
    p.add_argument(
        "--root",
        default=os.environ.get("GS_ROOT", ROOT_DEFAULT),
        help=f"Scratchpad root directory. Default: {ROOT_DEFAULT}",
    )

    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("init", help="Initialize scratchpad root.")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("guide", help="Print the Great Scratchpad annotation guide.")
    sp.set_defaults(func=cmd_guide)

    sp = sub.add_parser("repl", help="Start an interactive Great Scratchpad REPL.")
    sp.add_argument("thread", nargs="?", default=None)
    sp.set_defaults(func=cmd_repl)

    sp = sub.add_parser("new", help="Create or open a thread.")
    sp.add_argument("thread")
    sp.add_argument("--title", default="")
    sp.set_defaults(func=cmd_new)

    sp = sub.add_parser("list", help="List threads.")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("add", help="Add one turn as trajectory-aware markdown.")
    sp.add_argument("thread")
    sp.add_argument("--speaker", required=True, choices=["user", "assistant", "system", "tool", "note"])
    sp.add_argument("--text", default=None)
    sp.add_argument("--text-file", default=None)
    sp.add_argument("--center", default="", help="The center pin of this turn.")
    sp.add_argument("--trajectory", default="", help="How this turn moves the conversation.")
    sp.add_argument("--anchors", default="", help="Phrases, definitions, or metaphors worth preserving.")
    sp.add_argument("--assumptions", default="", help="Local assumptions active in this turn.")
    sp.add_argument("--open-questions", default="", help="Unresolved questions left by this turn.")
    sp.add_argument("--drift-risks", default="", help="Ways future context might drift.")
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("search", help="Search thread memory.")
    sp.add_argument("thread")
    sp.add_argument("query")
    sp.add_argument("--top", type=int, default=8)
    sp.add_argument("--width", type=int, default=420)
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("recent", help="Show recent turns.")
    sp.add_argument("thread")
    sp.add_argument("-n", type=int, default=6)
    sp.add_argument("--max-chars", type=int, default=1600)
    sp.set_defaults(func=cmd_recent)

    sp = sub.add_parser("compact", help="Create trajectory blocks from raw turns.")
    sp.add_argument("thread")
    sp.add_argument("--start", type=int, default=None)
    sp.add_argument("--end", type=int, default=None)
    sp.add_argument("--block-size", type=int, default=30)
    sp.add_argument("--raw-excerpt-chars", type=int, default=900)
    sp.set_defaults(func=cmd_compact)

    sp = sub.add_parser("pack", help="Build a retrieval context pack for pasting into an LLM thread.")
    sp.add_argument("thread")
    sp.add_argument("query")
    sp.add_argument("--recent", type=int, default=6)
    sp.add_argument("--top", type=int, default=6)
    sp.add_argument("--max-chars-per-doc", type=int, default=2200)
    sp.add_argument("--include-guide", action="store_true", help="Include annotation guide in the generated context pack.")
    sp.add_argument("--out", default=None)
    sp.set_defaults(func=cmd_pack)

    sp = sub.add_parser("audit", help="Audit annotation/raw ratio and possible anchor hallucinations.")
    sp.add_argument("thread")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--max-flags", type=int, default=8)
    sp.set_defaults(func=cmd_audit)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
