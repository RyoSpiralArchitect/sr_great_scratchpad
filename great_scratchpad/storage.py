from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

from .constants import ANNOTATION_GUIDE, LLM_CONFIG_DEFAULT, ROOT_DEFAULT

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
