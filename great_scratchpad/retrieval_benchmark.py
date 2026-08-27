from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .memory import compact_memory_text
from .semantics import (
    classify_semantic_documents,
    load_dialogue_semantic_corpus,
    load_semantic_taxonomy,
    mean,
)
from .text import score_doc_details

RETRIEVAL_BENCHMARK_METHOD = "runtime-lexical-ranker-v1"
RETRIEVAL_CUTOFFS = (1, 2, 3, 5)
RETRIEVAL_QUERY_SOURCES = ("intervention", "current-message")


def extract_current_user_message(prompt: str) -> str:
    match = re.search(
        r"(?:Current user message|Current message):\n---\n(.*?)\n---(?:\n|$)",
        prompt,
        flags=re.DOTALL,
    )
    return match.group(1).strip() if match else ""


def intervention_query(suite: dict, turn: int) -> str:
    return "\n\n".join(
        str(item.get("message", "")).strip()
        for item in suite.get("scenario", {}).get("interventions", [])
        if int(item.get("before_turn", 0)) == turn
        and str(item.get("message", "")).strip()
    )


def _note_path(note: dict) -> Path:
    source_path = str(note.get("source_path", "")).strip()
    if source_path:
        return Path(source_path)
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", str(note["id"])).strip("-")
    return Path(f"{safe_name or 'note'}.md")


def _note_text(note: dict) -> str:
    path = _note_path(note)
    return (
        path.read_text(encoding="utf-8")
        if path.is_file()
        else str(note["analysis_text"])
    )


def _score_candidate(query: str, note: dict) -> dict:
    details = score_doc_details(query, _note_text(note), _note_path(note))
    return {
        "id": note["id"],
        "source_path": str(note.get("source_path", "")),
        "condition": note["condition"],
        "session_id": note["session_id"],
        "turn": note["turn"],
        "speaker": note["speaker"],
        "primary_frame": note["primary_frame"],
        "score": round(float(details["score"]), 3),
        "matched_tokens": list(details["matched_tokens"]),
    }


def _compact_chars(note: dict, max_chars: int) -> int:
    return len(compact_memory_text(_note_text(note), max_chars=max_chars))


def _evaluate_scope(
    query: str,
    source_note: dict,
    candidates: list[dict],
    scope: str,
    max_chars_per_doc: int,
    distractors_added: int,
) -> dict:
    ranked = sorted(
        (_score_candidate(query, note) for note in candidates),
        key=lambda item: (-float(item["score"]), str(item["id"])),
    )
    retrieved = [item for item in ranked if float(item["score"]) > 0.0]
    source_rank = next(
        (
            index
            for index, item in enumerate(retrieved, start=1)
            if item["id"] == source_note["id"]
        ),
        None,
    )
    note_by_id = {note["id"]: note for note in candidates}
    selected = note_by_id.get(retrieved[0]["id"]) if retrieved else None
    injected_chars_at = {
        str(cutoff): sum(
            _compact_chars(note_by_id[item["id"]], max_chars_per_doc)
            for item in retrieved[:cutoff]
        )
        for cutoff in RETRIEVAL_CUTOFFS
    }
    return {
        "scope": scope,
        "candidate_count": len(candidates),
        "retrieved_count": len(retrieved),
        "distractors_added": distractors_added,
        "source_rank": source_rank,
        "reciprocal_rank": round(1.0 / source_rank, 6) if source_rank else 0.0,
        "recall_at": {
            str(cutoff): bool(source_rank and source_rank <= cutoff)
            for cutoff in RETRIEVAL_CUTOFFS
        },
        "top1_injected_chars": (
            _compact_chars(selected, max_chars_per_doc) if selected else 0
        ),
        "injected_chars_at": injected_chars_at,
        "top_hits": retrieved[:5],
    }


def _scope_summary(cases: list[dict], query_source: str, scope: str) -> dict:
    scoped = [
        case
        for case in cases
        if case["query_source"] == query_source and case["scope"] == scope
    ]
    return {
        "query_source": query_source,
        "scope": scope,
        "cases": len(scoped),
        "recall_at": {
            str(cutoff): round(
                mean([float(case["recall_at"][str(cutoff)]) for case in scoped]),
                6,
            )
            for cutoff in RETRIEVAL_CUTOFFS
        },
        "mrr": round(mean([case["reciprocal_rank"] for case in scoped]), 6),
        "misses": sum(1 for case in scoped if case["source_rank"] is None),
        "mean_candidates": round(mean([case["candidate_count"] for case in scoped]), 3),
        "mean_distractors_added": round(
            mean([case["distractors_added"] for case in scoped]), 3
        ),
        "mean_top1_injected_chars": round(
            mean([case["top1_injected_chars"] for case in scoped]), 3
        ),
        "mean_injected_chars_at": {
            str(cutoff): round(
                mean(
                    [case["injected_chars_at"][str(cutoff)] for case in scoped]
                ),
                3,
            )
            for cutoff in RETRIEVAL_CUTOFFS
        },
    }


def retrieval_benchmark_markdown(result: dict) -> str:
    lines = [
        "# Dialogue Retrieval Benchmark",
        "",
        f"- Run id: {result['generation_identity']['run_id']}",
        f"- Method: {result['assessment_identity']['method']}",
        f"- Taxonomy: {result['taxonomy']['id']}",
        f"- Eligible targets: {result['eligible_targets']}",
        "",
        "Retrieval uses the runtime lexical scorer. The taxonomy freezes the expected source turn; semantic frame labels are used only to exclude equivalent target-frame notes from the stress distractor pool.",
        "",
        "## Summary",
        "",
        "| Query | Scope | Cases | R@1 | R@2 | R@3 | R@5 | MRR | Misses | Mean candidates | Mean distractors | Mean chars@1 | Mean chars@2 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for summary in result["summaries"]:
        lines.append(
            f"| {summary['query_source']} | {summary['scope']} | {summary['cases']} | "
            f"{summary['recall_at']['1']:.3f} | {summary['recall_at']['2']:.3f} | "
            f"{summary['recall_at']['3']:.3f} | "
            f"{summary['recall_at']['5']:.3f} | {summary['mrr']:.3f} | "
            f"{summary['misses']} | {summary['mean_candidates']:.1f} | "
            f"{summary['mean_distractors_added']:.1f} | "
            f"{summary['mean_injected_chars_at']['1']:.1f} | "
            f"{summary['mean_injected_chars_at']['2']:.1f} |"
        )
    lines.extend(
        [
            "",
            "## Cases",
            "",
            "| Session | Target | Query | Scope | Candidates | Source rank | Top hit | Query chars | Compact chars@1 |",
            "|---|---|---|---|---:|---:|---|---:|---:|",
        ]
    )
    for case in result["cases"]:
        top_hit = case["top_hits"][0]["id"] if case["top_hits"] else "-"
        source_rank = case["source_rank"] if case["source_rank"] is not None else "miss"
        lines.append(
            f"| {case['session_id']} | {case['target_id']} | {case['query_source']} | {case['scope']} | "
            f"{case['candidate_count']} | {source_rank} | {top_hit} | "
            f"{case['query_chars']} | {case['top1_injected_chars']} |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This benchmark measures whether the existing deterministic ranker surfaces the frozen source-turn note for a frozen prompt. It does not measure whether a model will use the injected note correctly.",
            "",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def benchmark_dialogue_retrieval(
    run_dir: Path,
    taxonomy_path: Path,
    out_prefix: Path | None = None,
    distractor_limit: int = 24,
    max_chars_per_doc: int = 700,
    query_sources: tuple[str, ...] | list[str] = RETRIEVAL_QUERY_SOURCES,
) -> dict:
    if distractor_limit < 0:
        raise SystemExit("distractor_limit must be non-negative.")
    if max_chars_per_doc < 1:
        raise SystemExit("max_chars_per_doc must be positive.")
    normalized_query_sources = tuple(
        dict.fromkeys(str(value).strip().lower() for value in query_sources)
    )
    if not normalized_query_sources or any(
        value not in RETRIEVAL_QUERY_SOURCES for value in normalized_query_sources
    ):
        raise SystemExit(
            "query_sources must contain intervention and/or current-message."
        )

    run_dir = run_dir.expanduser().resolve()
    taxonomy = load_semantic_taxonomy(taxonomy_path)
    suite, documents, session_context = load_dialogue_semantic_corpus(run_dir)
    classified, _ = classify_semantic_documents(documents, taxonomy)
    by_id = {document["id"]: document for document in classified}
    all_notes = [document for document in classified if document["kind"] == "note"]
    cases: list[dict] = []
    skipped: list[dict] = []
    eligible_target_keys: set[tuple[str, str]] = set()

    for suite_session in suite.get("sessions", []):
        session_id = str(suite_session["session_id"])
        context = session_context[session_id]
        utterances = [by_id[item["id"]] for item in context["utterances"]]
        notes = [by_id[item["id"]] for item in context["notes"]]
        for target in taxonomy["targets"]:
            target_document = next(
                (item for item in utterances if int(item["turn"]) == target["turn"]),
                None,
            )
            if target_document is None:
                continue
            own_notes = [
                note
                for note in notes
                if note["speaker"] == target_document["speaker"]
                and int(note["turn"]) < target["turn"]
            ]
            source_candidates = own_notes
            if target.get("source_turn") is not None:
                source_candidates = [
                    note
                    for note in own_notes
                    if int(note["turn"]) == int(target["source_turn"])
                ]
            source_note = next(
                iter(
                    sorted(
                        source_candidates,
                        key=lambda note: (
                            int(note["turn"]),
                            str(note["id"]),
                        ),
                    )
                ),
                None,
            )
            prompt = context["prompts"].get(
                (target["turn"], target_document["speaker"]), ""
            )
            if source_note is None:
                skipped.append(
                    {
                        "session_id": session_id,
                        "target_id": target["id"],
                        "reason": "no-source-note",
                    }
                )
                continue
            queries = {
                "current-message": extract_current_user_message(prompt),
                "intervention": intervention_query(suite, target["turn"]),
            }
            for query_source in normalized_query_sources:
                query = queries[query_source]
                if not query:
                    skipped.append(
                        {
                            "session_id": session_id,
                            "target_id": target["id"],
                            "query_source": query_source,
                            "reason": "no-query",
                        }
                    )
                    continue
                eligible_target_keys.add((session_id, target["id"]))
                own_note_ids = {item["id"] for item in own_notes}
                hard_distractors = [
                    note
                    for note in all_notes
                    if note["id"] not in own_note_ids
                    and note["primary_frame"] != target["frame_id"]
                ]
                hard_distractors.sort(
                    key=lambda note: (
                        -float(_score_candidate(query, note)["score"]),
                        str(note["id"]),
                    )
                )
                selected_distractors = (
                    hard_distractors
                    if distractor_limit == 0
                    else hard_distractors[:distractor_limit]
                )
                scope_candidates = {
                    "thread": own_notes,
                    "stress": [*own_notes, *selected_distractors],
                }
                for scope, candidates in scope_candidates.items():
                    evaluated = _evaluate_scope(
                        query=query,
                        source_note=source_note,
                        candidates=candidates,
                        scope=scope,
                        max_chars_per_doc=max_chars_per_doc,
                        distractors_added=(
                            0 if scope == "thread" else len(selected_distractors)
                        ),
                    )
                    cases.append(
                        {
                            "session_id": session_id,
                            "condition": str(suite_session["condition"]),
                            "replicate": int(suite_session.get("replicate", 1)),
                            "target_id": target["id"],
                            "turn": target["turn"],
                            "speaker": target_document["speaker"],
                            "frame_id": target["frame_id"],
                            "query_source": query_source,
                            "query": query,
                            "query_chars": len(query),
                            "source_note_id": source_note["id"],
                            "source_note_path": source_note.get("source_path", ""),
                            **evaluated,
                        }
                    )

    output_prefix = (
        out_prefix.expanduser().resolve()
        if out_prefix is not None
        else run_dir / "retrieval_benchmark"
    )
    result = {
        "schema_version": 1,
        "generation_identity": {
            "run_id": suite.get("run_id"),
            "scenario_sha256": suite.get("scenario_sha256"),
            "dialogue_runner_sha256": suite.get("dialogue_runner_sha256"),
            "runtime_component_sha256": suite.get("runtime_component_sha256", {}),
            "memory_fixture_sha256": suite.get("memory_fixture_sha256"),
            "frozen_note_replay": suite.get("frozen_note_replay"),
            "llm": suite.get("llm", {}),
        },
        "assessment_identity": {
            "method": RETRIEVAL_BENCHMARK_METHOD,
            "cutoffs": list(RETRIEVAL_CUTOFFS),
            "distractor_selection": "highest-runtime-score-non-target-frame",
            "distractor_limit": distractor_limit,
            "max_chars_per_doc": max_chars_per_doc,
            "query_sources": list(normalized_query_sources),
            "taxonomy_path": taxonomy["_path"],
            "taxonomy_sha256": taxonomy["_sha256"],
            "benchmark_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        },
        "taxonomy": {key: value for key, value in taxonomy.items() if not key.startswith("_")},
        "run_dir": str(run_dir),
        "eligible_targets": len(eligible_target_keys),
        "skipped": skipped,
        "summaries": [
            _scope_summary(cases, query_source, scope)
            for query_source in normalized_query_sources
            for scope in ("thread", "stress")
        ],
        "cases": cases,
        "output": {
            "json_path": str(output_prefix.with_suffix(".json")),
            "report_path": str(output_prefix.with_suffix(".md")),
        },
    }
    json_path = output_prefix.with_suffix(".json")
    report_path = output_prefix.with_suffix(".md")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(retrieval_benchmark_markdown(result), encoding="utf-8")
    return result
