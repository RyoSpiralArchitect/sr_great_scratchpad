#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
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
LLM_CONFIG_DEFAULT = "llm.json"
ANNOTATION_FIELDS = [
    "center",
    "trajectory",
    "anchors",
    "assumptions",
    "open_questions",
    "drift_risks",
]

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

ANNOTATION_PROMPT_TEMPLATE = """You are drafting Great Scratchpad annotations.

Use only the externally visible raw articulation below.
Do not invent hidden reasoning, private chain-of-thought, or facts not present in the raw articulation.
Preserve trajectory, not just conclusions.
Keep uncertainty, local wording, coined terms, metaphors, and drift risks when visible.

Return only a JSON object with these exact string fields:
- center
- trajectory
- anchors
- assumptions
- open_questions
- drift_risks

Field meanings:
- center: the center pin of this turn
- trajectory: how this turn moves the conversation
- anchors: reusable terms, metaphors, phrases, or names, comma-separated
- assumptions: local assumptions visible in this turn
- open_questions: unresolved questions left by this turn
- drift_risks: ways future context might drift

Raw articulation:
---
{raw}
---
"""

CHAT_RUNTIME_SYSTEM = """You are running inside Great Scratchpad chat runtime.

You are having a normal conversation with the user, but you may use the scratchpad
as external memory. Preserve conversational trajectory, not just conclusions.

You must return exactly one JSON object and no other text.

To use memory, return:
{"type":"action","action":"scratchpad.search","query":"...","top":5}
{"type":"action","action":"scratchpad.recent","n":5}
{"type":"action","action":"scratchpad.pack","query":"...","recent":6,"top":6,"include_guide":true}
{"type":"action","action":"scratchpad.audit","json":true}
{"type":"action","action":"scratchpad.add_note","text":"...","center":"...","trajectory":"...","anchors":"...","assumptions":"...","open_questions":"...","drift_risks":"..."}

To answer the user, return:
{"type":"final","message":"..."}

Rules:
- Use scratchpad tools when memory would help keep the topic centered.
- Do not invent memory. Use retrieved source paths when relying on scratchpad material.
- scratchpad.add_note should store externally visible trajectory notes, not hidden reasoning.
- Never reveal hidden chain-of-thought. Concise rationale is okay when useful.
"""

CHAT_PROMPT_TEMPLATE = """Thread: {thread_id}

Recent scratchpad context:
---
{recent_context}
---

Conversation so far in this runtime:
---
{history}
---

Current user message:
---
{user_text}
---

Tool observations so far:
---
{observations}
---

Return the next JSON object now.
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


def llm_config_path(root: Path, explicit_path: str | None = None) -> Path:
    if explicit_path:
        return Path(explicit_path).expanduser().resolve()
    return root / LLM_CONFIG_DEFAULT


def load_llm_config(root: Path, explicit_path: str | None = None, profile: str | None = None) -> dict:
    path = llm_config_path(root, explicit_path)
    if not path.exists():
        raise SystemExit(
            f"LLM config not found: {path}. Create one with: "
            "llm-config provider ... or llm-config local ..."
        )

    data = json.loads(path.read_text(encoding="utf-8"))
    if "profiles" not in data:
        cfg = dict(data)
        cfg.setdefault("profile", profile or "default")
        cfg["_config_path"] = str(path)
        return cfg

    profiles = data.get("profiles") or {}
    profile_name = profile or data.get("default_profile")
    if not profile_name:
        if len(profiles) == 1:
            profile_name = next(iter(profiles))
        else:
            names = ", ".join(sorted(profiles)) or "(none)"
            raise SystemExit(f"LLM profile not specified. Available profiles: {names}")

    if profile_name not in profiles:
        names = ", ".join(sorted(profiles)) or "(none)"
        raise SystemExit(f"LLM profile not found: {profile_name}. Available profiles: {names}")

    cfg = dict(profiles[profile_name])
    cfg["profile"] = profile_name
    cfg["_config_path"] = str(path)
    return cfg


def read_llm_config_document(path: Path) -> dict:
    if not path.exists():
        return {"created_at": now_iso(), "profiles": {}, "default_profile": ""}
    data = json.loads(path.read_text(encoding="utf-8"))
    if "profiles" not in data:
        profile = data.get("profile") or "default"
        data = {
            "created_at": data.get("created_at", now_iso()),
            "profiles": {profile: {k: v for k, v in data.items() if k != "profile"}},
            "default_profile": profile,
        }
    data.setdefault("profiles", {})
    data.setdefault("default_profile", "")
    return data


def write_llm_config_document(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = now_iso()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


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


def build_annotation_prompt(raw: str) -> str:
    return ANNOTATION_PROMPT_TEMPLATE.format(raw=raw.strip())


def extract_json_object(text: str) -> dict:
    text = text.strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("LLM output did not contain a JSON object.") from None
        value = json.loads(text[start:end + 1])

    if not isinstance(value, dict):
        raise ValueError("LLM output JSON must be an object.")
    return value


def normalize_annotation(value: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for field in ANNOTATION_FIELDS:
        item = value.get(field, "")
        if isinstance(item, list):
            item = ", ".join(str(x).strip() for x in item if str(x).strip())
        elif item is None:
            item = ""
        else:
            item = str(item)
        out[field] = item.strip()
    return out


def compose_text_prompt(system_prompt: str, prompt: str) -> str:
    if not system_prompt:
        return prompt
    return f"System:\n{system_prompt.strip()}\n\nUser:\n{prompt.strip()}\n"


def call_openai_compatible(cfg: dict, prompt: str, system_prompt: str = "") -> str:
    api_key_env = cfg.get("api_key_env", "")
    api_key = os.environ.get(api_key_env, "") if api_key_env else cfg.get("api_key", "")
    if api_key_env and not api_key:
        raise SystemExit(f"Environment variable is not set: {api_key_env}")

    url = cfg.get("base_url") or cfg.get("url")
    if not url:
        raise SystemExit("openai-compatible LLM config requires base_url.")
    if not url.rstrip("/").endswith("/chat/completions"):
        url = url.rstrip("/") + "/chat/completions"

    body = {
        "model": cfg.get("model", ""),
        "messages": [
            {
                "role": "system",
                "content": system_prompt or cfg.get("system_prompt", "Return the requested response."),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": float(cfg.get("temperature", 0.2)),
        "max_tokens": int(cfg.get("max_tokens", 900)),
    }
    if not body["model"]:
        raise SystemExit("openai-compatible LLM config requires model.")

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=float(cfg.get("timeout", 120))) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Provider API returned HTTP {exc.code}: {body_text}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Provider API request failed: {exc}") from exc

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise SystemExit(f"Provider API response did not look OpenAI-compatible: {data}") from exc


def call_command_llm(cfg: dict, prompt: str, system_prompt: str = "") -> str:
    command = cfg.get("command")
    if not command:
        raise SystemExit("command LLM config requires command.")

    prompt = compose_text_prompt(system_prompt, prompt)
    raw_parts = command if isinstance(command, list) else shlex.split(str(command))
    model_path = str(cfg.get("model_path", ""))
    timeout = float(cfg.get("timeout", 120))

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=True) as prompt_file:
        prompt_file.write(prompt)
        prompt_file.flush()
        values = {
            "model_path": model_path,
            "prompt": prompt,
            "prompt_file": prompt_file.name,
        }
        parts = [part.format(**values) for part in raw_parts]
        has_prompt_placeholder = any("{prompt}" in part or "{prompt_file}" in part for part in raw_parts)
        input_text = None if has_prompt_placeholder else prompt

        try:
            proc = subprocess.run(
                parts,
                input=input_text,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise SystemExit(f"Local LLM command not found: {parts[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise SystemExit(f"Local LLM command timed out after {timeout:g}s.") from exc

    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        raise SystemExit(f"Local LLM command failed with exit {proc.returncode}: {stderr}")

    return proc.stdout.strip()


def call_llm(cfg: dict, prompt: str, system_prompt: str = "") -> str:
    backend = str(cfg.get("backend", "")).lower()
    if backend in {"openai-compatible", "openai_compatible", "provider"}:
        return call_openai_compatible(cfg, prompt, system_prompt)
    if backend in {"command", "local", "local-command"}:
        return call_command_llm(cfg, prompt, system_prompt)
    raise SystemExit(f"Unknown LLM backend: {cfg.get('backend')!r}")


def draft_annotation(raw: str, cfg: dict) -> dict[str, str]:
    prompt = build_annotation_prompt(raw)
    output = call_llm(cfg, prompt, "Draft Great Scratchpad annotations as strict JSON only.")
    try:
        value = extract_json_object(output)
    except (ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Could not parse LLM annotation JSON: {exc}\nOutput:\n{output}") from exc
    return normalize_annotation(value)


def print_annotation(annotation: dict[str, str]) -> None:
    labels = {
        "center": "Center pin",
        "trajectory": "Trajectory",
        "anchors": "Anchors",
        "assumptions": "Local assumptions",
        "open_questions": "Open questions",
        "drift_risks": "Drift risks",
    }
    for field in ANNOTATION_FIELDS:
        print(f"{labels[field]}:")
        print(annotation.get(field, "") or "(none)")
        print()


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


def cmd_llm_config_show(args: argparse.Namespace) -> None:
    root = root_path(args)
    ensure_root(root)
    path = llm_config_path(root, args.config)
    if not path.exists():
        print(f"(no llm config at {path})")
        return
    print(path.read_text(encoding="utf-8"))


def cmd_llm_config_provider(args: argparse.Namespace) -> None:
    root = root_path(args)
    ensure_root(root)
    path = llm_config_path(root, args.config)
    data = read_llm_config_document(path)
    profile = args.profile
    data["profiles"][profile] = {
        "backend": "openai-compatible",
        "base_url": args.base_url,
        "api_key_env": args.api_key_env,
        "model": args.model,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "timeout": args.timeout,
    }
    if args.default or not data.get("default_profile"):
        data["default_profile"] = profile
    write_llm_config_document(path, data)
    print(f"Wrote provider LLM profile {profile!r}: {path}")


def cmd_llm_config_local(args: argparse.Namespace) -> None:
    root = root_path(args)
    ensure_root(root)
    path = llm_config_path(root, args.config)
    data = read_llm_config_document(path)
    profile = args.profile
    data["profiles"][profile] = {
        "backend": "command",
        "command": args.command,
        "model_path": args.model_path,
        "timeout": args.timeout,
    }
    if args.default or not data.get("default_profile"):
        data["default_profile"] = profile
    write_llm_config_document(path, data)
    print(f"Wrote local command LLM profile {profile!r}: {path}")


def cmd_annotate(args: argparse.Namespace) -> None:
    root = root_path(args)
    ensure_root(root)
    raw = read_text_arg(args.text, args.text_file)
    cfg = load_llm_config(root, args.llm_config, args.profile)
    annotation = draft_annotation(raw, cfg)

    if args.json:
        print(json.dumps(annotation, ensure_ascii=False, indent=2))
    else:
        print_annotation(annotation)

    if args.save_thread:
        turn_no, path = add_turn(
            root=root,
            thread_id=args.save_thread,
            speaker=args.speaker,
            raw=raw,
            center=annotation["center"],
            trajectory=annotation["trajectory"],
            anchors=annotation["anchors"],
            assumptions=annotation["assumptions"],
            open_questions=annotation["open_questions"],
            drift_risks=annotation["drift_risks"],
        )
        print(f"Saved turn {turn_no:06d}: {path}")


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


def cmd_pack(args: argparse.Namespace) -> None:
    root = root_path(args)
    ensure_root(root)
    tdir = ensure_thread(root, args.thread)

    output = build_context_pack(
        root=root,
        tdir=tdir,
        query=args.query,
        recent_n=args.recent,
        top=args.top,
        max_chars_per_doc=args.max_chars_per_doc,
        include_guide=args.include_guide,
    )

    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
        print(f"Wrote context pack: {args.out}")
    else:
        print(output)


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
        if flags:
            shown = flags[:max_flags]
            out.append(f"  unsupported_anchors: {', '.join(shown)}")
            if len(flags) > max_flags:
                out.append(f"  ...and {len(flags) - max_flags} more")
        out.append("")
    return "\n".join(out).strip()


def parse_chat_json(text: str) -> dict:
    try:
        return extract_json_object(text)
    except (ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Could not parse chat runtime JSON: {exc}\nOutput:\n{text}") from exc


def chat_history_text(history: list[dict[str, str]], max_chars: int = 4000) -> str:
    lines: list[str] = []
    for msg in history:
        lines.append(f"{msg['role']}: {msg['content']}")
    text = "\n\n".join(lines).strip()
    return limit_text(text, max_chars) if text else "(empty)"


def build_chat_prompt(
    thread_id: str,
    user_text: str,
    recent_context: str,
    history: list[dict[str, str]],
    observations: list[str],
    history_chars: int = 4000,
) -> str:
    return CHAT_PROMPT_TEMPLATE.format(
        thread_id=thread_id,
        recent_context=recent_context,
        history=chat_history_text(history, history_chars),
        user_text=user_text.strip(),
        observations="\n\n".join(observations).strip() or "(none yet)",
    )


def maybe_confirm_write(prompt: str, yes: bool) -> bool:
    if yes:
        return True
    if not sys.stdin.isatty():
        return False
    answer = input(f"{prompt} [y/N]> ").strip().lower()
    return answer in {"y", "yes"}


def run_scratchpad_action(
    root: Path,
    tdir: Path,
    thread_id: str,
    action_obj: dict,
    yes: bool = False,
    max_tool_chars: int = 6000,
) -> str:
    action = str(action_obj.get("action", "")).strip()

    if action == "scratchpad.search":
        query = str(action_obj.get("query", "")).strip()
        if not query:
            return "scratchpad.search failed: missing query"
        top = int(action_obj.get("top", 5))
        width = int(action_obj.get("width", 420))
        return limit_text(render_search_results(tdir, query, top=top, width=width), max_tool_chars)

    if action == "scratchpad.recent":
        n = int(action_obj.get("n", 5))
        max_chars = int(action_obj.get("max_chars", 1600))
        return limit_text(render_recent_turns(tdir, n=n, max_chars=max_chars), max_tool_chars)

    if action == "scratchpad.pack":
        query = str(action_obj.get("query", "")).strip()
        if not query:
            return "scratchpad.pack failed: missing query"
        output = build_context_pack(
            root=root,
            tdir=tdir,
            query=query,
            recent_n=int(action_obj.get("recent", 6)),
            top=int(action_obj.get("top", 6)),
            max_chars_per_doc=int(action_obj.get("max_chars_per_doc", 2200)),
            include_guide=bool(action_obj.get("include_guide", False)),
        )
        return limit_text(output, max_tool_chars)

    if action == "scratchpad.audit":
        return limit_text(
            render_audit(
                tdir,
                as_json=bool(action_obj.get("json", True)),
                max_flags=int(action_obj.get("max_flags", 8)),
            ),
            max_tool_chars,
        )

    if action == "scratchpad.add_note":
        raw = str(action_obj.get("text", "")).strip()
        if not raw:
            return "scratchpad.add_note failed: missing text"
        if not maybe_confirm_write("Allow scratchpad.add_note write?", yes):
            return "scratchpad.add_note skipped: write was not confirmed"
        turn_no, path = add_turn(
            root=root,
            thread_id=thread_id,
            speaker="note",
            raw=raw,
            center=str(action_obj.get("center", "")),
            trajectory=str(action_obj.get("trajectory", "")),
            anchors=str(action_obj.get("anchors", "")),
            assumptions=str(action_obj.get("assumptions", "")),
            open_questions=str(action_obj.get("open_questions", "")),
            drift_risks=str(action_obj.get("drift_risks", "")),
        )
        return f"scratchpad.add_note wrote turn {turn_no:06d}: {path.relative_to(tdir)}"

    return f"Unknown scratchpad action: {action!r}"


def run_chat_turn(
    root: Path,
    tdir: Path,
    thread_id: str,
    cfg: dict,
    user_text: str,
    history: list[dict[str, str]],
    max_steps: int = 4,
    recent_n: int = 4,
    yes: bool = False,
    max_tool_chars: int = 6000,
    verbose: bool = True,
) -> str:
    observations: list[str] = []
    recent_context = render_recent_turns(tdir, n=recent_n, max_chars=1200)

    for step in range(max_steps + 1):
        prompt = build_chat_prompt(
            thread_id=thread_id,
            user_text=user_text,
            recent_context=recent_context,
            history=history,
            observations=observations,
        )
        raw_output = call_llm(cfg, prompt, CHAT_RUNTIME_SYSTEM)
        obj = parse_chat_json(raw_output)
        kind = str(obj.get("type", "")).strip().lower()

        if kind == "final" or "message" in obj:
            message = str(obj.get("message", "")).strip()
            if not message:
                message = "(empty final message)"
            return message

        if kind != "action" and "action" not in obj:
            return f"(chat runtime stopped: expected action/final JSON, got {obj})"

        if step >= max_steps:
            return "(chat runtime stopped: max tool steps reached before final answer)"

        action_name = str(obj.get("action", "")).strip()
        if verbose:
            print(f"[tool] {action_name}")
        observation = run_scratchpad_action(
            root=root,
            tdir=tdir,
            thread_id=thread_id,
            action_obj=obj,
            yes=yes,
            max_tool_chars=max_tool_chars,
        )
        observations.append(
            f"Action {len(observations) + 1}: {action_name}\nObservation:\n{observation}"
        )
        if verbose:
            print(limit_text(observation, 800))

    return "(chat runtime stopped unexpectedly)"


def ensure_thread_dirs(root: Path, thread_id: str, title: str = "") -> Path:
    ensure_root(root)
    tdir = thread_path(root, thread_id)
    (tdir / "turns").mkdir(parents=True, exist_ok=True)
    (tdir / "blocks").mkdir(parents=True, exist_ok=True)
    meta_path = tdir / "meta.json"
    if not meta_path.exists():
        save_meta(
            tdir,
            {
                "thread_id": safe_id(thread_id),
                "title": title or thread_id,
                "created_at": now_iso(),
                "last_turn": 0,
                "principle": "Store articulation trajectory, not only conclusions.",
            },
        )
    return tdir


def cmd_chat(args: argparse.Namespace) -> None:
    root = root_path(args)
    tdir = ensure_thread_dirs(root, args.thread, title=args.thread)
    thread_id = safe_id(args.thread)
    cfg = load_llm_config(root, args.llm_config, args.profile)
    history: list[dict[str, str]] = []

    def run_one(user_text: str) -> None:
        message = run_chat_turn(
            root=root,
            tdir=tdir,
            thread_id=thread_id,
            cfg=cfg,
            user_text=user_text,
            history=history,
            max_steps=args.max_steps,
            recent_n=args.recent,
            yes=args.yes,
            max_tool_chars=args.max_tool_chars,
            verbose=not args.quiet,
        )
        print(message)
        history.extend(
            [
                {"role": "user", "content": user_text},
                {"role": "assistant", "content": message},
            ]
        )

    if args.text or args.text_file:
        run_one(read_text_arg(args.text, args.text_file))
        return

    print("Great Scratchpad chat runtime. Type /help or /quit.")
    print(f"Thread: {thread_id}")
    while True:
        try:
            user_text = input("you> ").strip()
        except EOFError:
            break
        except KeyboardInterrupt:
            print()
            break

        if not user_text:
            continue
        if user_text in {"/quit", "/exit"}:
            break
        if user_text == "/help":
            print("/quit, /exit, /recent, /audit")
            continue
        if user_text == "/recent":
            print(render_recent_turns(tdir, n=args.recent))
            continue
        if user_text == "/audit":
            print(render_audit(tdir, as_json=False))
            continue

        run_one(user_text)


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
  llm                          Show active LLM config.
  annotate [SPEAKER] [THREAD]  Draft annotations with the configured LLM.
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


def _repl_show_llm(root: Path, explicit_path: str | None, profile: str | None) -> None:
    path = llm_config_path(root, explicit_path)
    print(f"LLM config: {path}")
    if not path.exists():
        print("(not configured)")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    if "profiles" in data:
        default_profile = data.get("default_profile") or "(none)"
        profiles = ", ".join(sorted(data.get("profiles", {}))) or "(none)"
        print(f"Default profile: {default_profile}")
        print(f"REPL profile override: {profile or '(none)'}")
        print(f"Profiles: {profiles}")
    else:
        print(f"Backend: {data.get('backend', '(unknown)')}")


def _repl_handle_annotate(
    root: Path,
    active_thread: str | None,
    tokens: list[str],
    explicit_llm_config: str | None,
    llm_profile: str | None,
) -> str | None:
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

    cfg = load_llm_config(root, explicit_llm_config, llm_profile)
    annotation = draft_annotation(raw, cfg)
    print()
    print_annotation(annotation)

    answer = _input_line("Save this turn? [y/N]> ").strip().lower()
    if answer not in {"y", "yes"}:
        print("Skipped save.")
        return thread_id

    turn_no, path = add_turn(
        root=root,
        thread_id=thread_id,
        speaker=speaker,
        raw=raw,
        center=annotation["center"],
        trajectory=annotation["trajectory"],
        anchors=annotation["anchors"],
        assumptions=annotation["assumptions"],
        open_questions=annotation["open_questions"],
        drift_risks=annotation["drift_risks"],
    )
    print(f"Added turn {turn_no:06d}: {path}")
    return thread_id


def _repl_run_command(
    root: Path,
    active_thread: str | None,
    line: str,
    explicit_llm_config: str | None,
    llm_profile: str | None,
) -> tuple[str | None, bool]:
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

    if cmd == "llm":
        _repl_show_llm(root, explicit_llm_config, llm_profile)
        return active_thread, True

    if cmd == "annotate":
        return _repl_handle_annotate(root, active_thread, tokens, explicit_llm_config, llm_profile), True

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
    if args.llm_config or args.llm_profile:
        _repl_show_llm(root, args.llm_config, args.llm_profile)

    while True:
        prompt = f"sr:{active_thread}> " if active_thread else "sr> "
        try:
            line = _input_line(prompt)
            active_thread, keep_running = _repl_run_command(
                root,
                active_thread,
                line,
                args.llm_config,
                args.llm_profile,
            )
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
    sp.add_argument("--llm-config", default=None, help="Path to llm.json. Default: ROOT/llm.json")
    sp.add_argument("--llm-profile", default=None, help="LLM profile name to use in the REPL.")
    sp.set_defaults(func=cmd_repl)

    sp = sub.add_parser("annotate", help="Draft trajectory annotations with a configured LLM.")
    sp.add_argument("--text", default=None)
    sp.add_argument("--text-file", default=None)
    sp.add_argument("--llm-config", default=None, help="Path to llm.json. Default: ROOT/llm.json")
    sp.add_argument("--profile", default=None, help="LLM profile name.")
    sp.add_argument("--json", action="store_true", help="Print annotation JSON.")
    sp.add_argument("--save-thread", default=None, help="Save drafted annotation as a turn in THREAD.")
    sp.add_argument("--speaker", default="note", choices=["user", "assistant", "system", "tool", "note"])
    sp.set_defaults(func=cmd_annotate)

    sp = sub.add_parser("llm-config", help="Create or inspect LLM provider/local profiles.")
    sp.add_argument("--config", default=None, help="Path to llm.json. Default: ROOT/llm.json")
    llm_sub = sp.add_subparsers(dest="llm_cmd", required=True)

    sp2 = llm_sub.add_parser("show", help="Print LLM config.")
    sp2.set_defaults(func=cmd_llm_config_show)

    sp2 = llm_sub.add_parser("provider", help="Configure an OpenAI-compatible provider API.")
    sp2.add_argument("--profile", default="provider")
    sp2.add_argument("--base-url", required=True, help="Base URL or full /chat/completions URL.")
    sp2.add_argument("--api-key-env", default="", help="Environment variable containing the API key.")
    sp2.add_argument("--model", required=True)
    sp2.add_argument("--temperature", type=float, default=0.2)
    sp2.add_argument("--max-tokens", type=int, default=900)
    sp2.add_argument("--timeout", type=float, default=120)
    sp2.add_argument("--default", action="store_true", help="Make this the default profile.")
    sp2.set_defaults(func=cmd_llm_config_provider)

    sp2 = llm_sub.add_parser("local", help="Configure a local command-backed LLM.")
    sp2.add_argument("--profile", default="local")
    sp2.add_argument("--command", required=True, help="Command to run. Prompt is passed on stdin unless {prompt} or {prompt_file} is used.")
    sp2.add_argument("--model-path", default="", help="Optional local model path available as {model_path}.")
    sp2.add_argument("--timeout", type=float, default=120)
    sp2.add_argument("--default", action="store_true", help="Make this the default profile.")
    sp2.set_defaults(func=cmd_llm_config_local)

    sp = sub.add_parser("chat", help="Run a minimal LLM chat runtime with scratchpad actions.")
    sp.add_argument("thread")
    sp.add_argument("--text", default=None, help="Run one chat turn with this text.")
    sp.add_argument("--text-file", default=None, help="Run one chat turn with text from this file.")
    sp.add_argument("--llm-config", default=None, help="Path to llm.json. Default: ROOT/llm.json")
    sp.add_argument("--profile", default=None, help="LLM profile name.")
    sp.add_argument("--max-steps", type=int, default=4, help="Maximum scratchpad action steps per turn.")
    sp.add_argument("--recent", type=int, default=4, help="Recent scratchpad turns included in each prompt.")
    sp.add_argument("--max-tool-chars", type=int, default=6000, help="Maximum chars returned from each scratchpad action.")
    sp.add_argument("--yes", action="store_true", help="Allow runtime write actions without prompting.")
    sp.add_argument("--quiet", action="store_true", help="Do not print tool action progress.")
    sp.set_defaults(func=cmd_chat)

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
