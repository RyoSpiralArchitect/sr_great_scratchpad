from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .text import limit_text

RELATION_RENDERINGS = ("original", "prose", "roles")
RELATION_FIELDS = ("before_state", "after_state", "comparison_boundary")


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_note_relations(path: Path, fixture: dict, scenario: dict) -> dict:
    path = path.expanduser().resolve()
    try:
        raw_bytes = path.read_bytes()
        data = json.loads(raw_bytes)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Cannot read note relations: {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise SystemExit("Note relations require schema_version=1.")
    if data.get("fixture_sha256") != fixture["_sha256"]:
        raise SystemExit("Note relations fixture hash mismatch.")
    public_scenario = {key: value for key, value in scenario.items() if not key.startswith("_")}
    scenario_hash = text_sha256(
        json.dumps(public_scenario, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    if data.get("scenario_sha256") != scenario_hash:
        raise SystemExit("Note relations scenario hash mismatch.")
    if not isinstance(data.get("id"), str) or not data["id"].strip():
        raise SystemExit("Note relations require an id.")
    entries = {entry["id"]: entry for entry in fixture["entries"]}
    annotations = data.get("annotations")
    if not isinstance(annotations, list) or not annotations:
        raise SystemExit("Note relations require at least one annotation.")
    by_hash: dict[str, dict] = {}
    for item in annotations:
        if not isinstance(item, dict) or item.get("fixture_entry_id") not in entries:
            raise SystemExit("Note relation must name an existing fixture entry.")
        entry = entries[item["fixture_entry_id"]]
        note_hash = entry["source_note_sha256"]
        if item.get("note_sha256") != note_hash or note_hash in by_hash:
            raise SystemExit("Note relation source hash mismatch or duplicate annotation.")
        # A rejected alternative is not evidence that the dialogue previously adopted it.
        if item.get("before_status") != "rejected_interpretation":
            raise SystemExit("Note relation before_status must be rejected_interpretation.")
        if item.get("prior_adoption") != "unverified":
            raise SystemExit("Note relation prior_adoption must be unverified.")
        for role in RELATION_FIELDS:
            field = item.get(role)
            if not isinstance(field, dict):
                raise SystemExit(f"Note relation requires {role} and its evidence.")
            value = field.get("value")
            evidence = field.get("evidence")
            if not isinstance(value, str) or not value.strip() or "\n" in value:
                raise SystemExit(f"Note relation {role} must be a non-empty single line.")
            if not isinstance(evidence, dict):
                raise SystemExit(f"Note relation {role} requires evidence.")
            quote = evidence.get("quote")
            if not isinstance(quote, str) or not quote.strip() or value not in quote:
                raise SystemExit(f"Note relation {role} value must occur in its evidence quote.")
            if evidence.get("kind") == "note":
                source = entries.get(evidence.get("entry_id"))
                if source is None or source["after_turn"] > entry["after_turn"]:
                    raise SystemExit("Note relation cannot use missing or future note evidence.")
                source_text = source["payload"].get(evidence.get("field"), "")
            elif evidence.get("kind") == "scenario":
                if evidence.get("field") not in {"agenda", "opening"}:
                    raise SystemExit("Scenario relation evidence must come from agenda or opening.")
                source_text = scenario[evidence["field"]]
            else:
                raise SystemExit("Note relation evidence must be note or scenario.")
            if quote not in source_text:
                raise SystemExit(f"Note relation {role} evidence quote not found in source.")
        by_hash[note_hash] = item
    return {**data, "_path": str(path), "_sha256": hashlib.sha256(raw_bytes).hexdigest(), "_by_hash": by_hash}


def render_relation(annotation: dict, rendering: str) -> str:
    before, after, boundary = (annotation[field]["value"] for field in RELATION_FIELDS)
    if rendering == "prose":
        return (
            f"The correction rejects the interpretation {before} and accepts {after}. "
            f"The comparison boundary is {boundary} "
            "Whether the rejected interpretation was previously adopted is unverified."
        )
    if rendering == "roles":
        return (
            f"before_state (rejected interpretation): {before}\n"
            f"after_state (accepted interpretation): {after}\n"
            f"comparison_boundary: {boundary}\n"
            "prior_adoption: unverified"
        )
    raise ValueError(f"Unsupported relation rendering: {rendering}")


def render_memory_with_relations(
    source_text: str,
    display_text: str,
    max_chars: int,
    relations: dict[str, dict] | None = None,
    rendering: str = "original",
) -> str:
    if rendering not in RELATION_RENDERINGS:
        raise ValueError(f"Unknown relation rendering: {rendering}")
    annotation = (relations or {}).get(text_sha256(source_text))
    if rendering == "original" or annotation is None:
        return limit_text(display_text, max_chars)
    relation = render_relation(annotation, rendering)
    # Never silently truncate one role or change which notes retrieval selects.
    if len(relation) + 2 + len(display_text) > max_chars:
        raise ValueError("Relation plus note exceeds the display budget; increase max_chars.")
    return relation + "\n\n" + display_text
