from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path

from .dialogue import RELATION_PROBE_METHOD, relation_probe_evidence
from .storage import safe_id

SEMANTIC_METHOD = "char-ngram-tfidf-prototype-v1"
SEMANTIC_NGRAMS = (2, 3, 4)
SEMANTIC_SCORE_WEIGHTS = {"prototype_cosine": 0.85, "lexical_coverage": 0.15}
SEMANTIC_MIN_SCORE = 0.055
SEMANTIC_RELATIVE_LABEL_THRESHOLD = 0.68
SEMANTIC_BOOTSTRAP_SEED = 20260826
SEMANTIC_BOOTSTRAP_RESAMPLES = 10000
SEMANTIC_BOOTSTRAP_CONFIDENCE = 0.95
NOTE_FIELDS = (
    "text",
    "center",
    "trajectory",
    "anchors",
    "assumptions",
    "open_questions",
    "drift_risks",
)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize_semantic_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(text)).casefold()
    return "".join(char for char in normalized if char.isalnum() or _is_cjk(char))


def _is_cjk(char: str) -> bool:
    codepoint = ord(char)
    return (
        0x3040 <= codepoint <= 0x30FF
        or 0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0xF900 <= codepoint <= 0xFAFF
    )


def semantic_ngrams(text: str, sizes: tuple[int, ...] = SEMANTIC_NGRAMS) -> Counter[str]:
    normalized = normalize_semantic_text(text)
    counts: Counter[str] = Counter()
    for size in sizes:
        for index in range(max(0, len(normalized) - size + 1)):
            counts[f"{size}:{normalized[index:index + size]}"] += 1
    return counts


def tfidf_vectors(texts: list[str]) -> list[dict[str, float]]:
    term_counts = [semantic_ngrams(text) for text in texts]
    document_frequency: Counter[str] = Counter()
    for counts in term_counts:
        document_frequency.update(counts.keys())
    document_count = len(texts)
    vectors: list[dict[str, float]] = []
    for counts in term_counts:
        vector: dict[str, float] = {}
        for term, count in counts.items():
            tf = 1.0 + math.log(count)
            idf = math.log((1.0 + document_count) / (1.0 + document_frequency[term])) + 1.0
            vector[term] = tf * idf
        norm = math.sqrt(sum(value * value for value in vector.values()))
        if norm:
            vector = {term: value / norm for term, value in vector.items()}
        vectors.append(vector)
    return vectors


def sparse_cosine(left: dict[str, float], right: dict[str, float]) -> float:
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(term, 0.0) for term, value in left.items())


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


def sample_standard_deviation(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    center = mean(values)
    return math.sqrt(sum((value - center) ** 2 for value in values) / (len(values) - 1))


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * min(1.0, max(0.0, quantile))
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def paired_bootstrap_mean_interval(
    values: list[float],
    seed: int = SEMANTIC_BOOTSTRAP_SEED,
    resamples: int = SEMANTIC_BOOTSTRAP_RESAMPLES,
    confidence: float = SEMANTIC_BOOTSTRAP_CONFIDENCE,
) -> dict:
    if not values or resamples < 1:
        return {
            "seed": seed,
            "resamples": max(0, resamples),
            "confidence": confidence,
            "lower": 0.0,
            "upper": 0.0,
        }
    sample_count = len(values)
    means: list[float] = []
    for sample_index in range(resamples):
        sample: list[float] = []
        for draw_index in range(sample_count):
            digest = hashlib.sha256(
                f"{seed}:{sample_index}:{draw_index}".encode("ascii")
            ).digest()
            source_index = int.from_bytes(digest[:8], "big") % sample_count
            sample.append(values[source_index])
        means.append(mean(sample))
    tail = (1.0 - confidence) / 2.0
    return {
        "seed": seed,
        "resamples": resamples,
        "confidence": confidence,
        "lower": round(percentile(means, tail), 6),
        "upper": round(percentile(means, 1.0 - tail), 6),
    }


def paired_binary_outcome_table(pairs: list[tuple[bool, bool]]) -> dict:
    both_pass = sum(1 for treatment, control in pairs if treatment and control)
    treatment_only = sum(1 for treatment, control in pairs if treatment and not control)
    control_only = sum(1 for treatment, control in pairs if control and not treatment)
    neither_pass = sum(1 for treatment, control in pairs if not treatment and not control)
    return {
        "pairs": len(pairs),
        "both_pass": both_pass,
        "treatment_only": treatment_only,
        "control_only": control_only,
        "neither_pass": neither_pass,
        "discordant_pairs": treatment_only + control_only,
    }


def mean_pairwise_similarity(vectors: list[dict[str, float]]) -> float:
    values = [
        sparse_cosine(vectors[left], vectors[right])
        for left in range(len(vectors))
        for right in range(left + 1, len(vectors))
    ]
    return mean(values)


def normalized_entropy(values: list[str], category_count: int) -> float:
    if not values or category_count < 2:
        return 0.0
    counts = Counter(values)
    total = len(values)
    entropy = -sum((count / total) * math.log(count / total) for count in counts.values())
    return entropy / math.log(category_count)


def ngram_containment(needle: str, haystack: str, size: int = 3) -> float:
    needle_text = normalize_semantic_text(needle)
    haystack_text = normalize_semantic_text(haystack)
    if len(needle_text) < size:
        return float(bool(needle_text) and needle_text in haystack_text)
    needle_ngrams = {needle_text[index:index + size] for index in range(len(needle_text) - size + 1)}
    haystack_ngrams = {haystack_text[index:index + size] for index in range(len(haystack_text) - size + 1)}
    return len(needle_ngrams & haystack_ngrams) / len(needle_ngrams)


def load_semantic_taxonomy(path: Path) -> dict:
    path = path.expanduser().resolve()
    try:
        taxonomy = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"Semantic taxonomy not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Semantic taxonomy is not valid JSON: {path}: {exc}") from exc
    if not isinstance(taxonomy, dict):
        raise SystemExit("Semantic taxonomy must be one JSON object.")
    frames: list[dict] = []
    seen: set[str] = set()
    for item in taxonomy.get("frames", []):
        if not isinstance(item, dict):
            raise SystemExit("Each semantic frame must be a JSON object.")
        raw_frame_id = str(item.get("id", "")).strip()
        if not raw_frame_id:
            raise SystemExit("Semantic frames require unique ids, labels, and prototypes.")
        frame_id = safe_id(raw_frame_id)
        label = str(item.get("label", "")).strip()
        prototypes = [str(value).strip() for value in item.get("prototypes", []) if str(value).strip()]
        terms = [str(value).strip() for value in item.get("terms", []) if str(value).strip()]
        if not frame_id or not label or not prototypes or frame_id in seen:
            raise SystemExit("Semantic frames require unique ids, labels, and prototypes.")
        seen.add(frame_id)
        frames.append(
            {
                "id": frame_id,
                "label": label,
                "prototypes": prototypes,
                "terms": terms,
            }
        )
    if not frames:
        raise SystemExit("Semantic taxonomy requires at least one frame.")

    relation_probes: list[dict] = []
    for item in taxonomy.get("relation_probes", []):
        if not isinstance(item, dict):
            raise SystemExit("Each semantic relation probe must be a JSON object.")
        probe_id = safe_id(str(item.get("id", "")).strip())
        try:
            turn = int(item.get("turn"))
            max_marker_gap = int(item.get("max_marker_gap", 80))
        except (TypeError, ValueError) as exc:
            raise SystemExit(
                "Semantic relation probe turn and max_marker_gap must be integers."
            ) from exc
        before_markers = [str(value).strip() for value in item.get("before_markers", []) if str(value).strip()]
        before_terms = [str(value).strip() for value in item.get("before_terms", []) if str(value).strip()]
        after_markers = [str(value).strip() for value in item.get("after_markers", []) if str(value).strip()]
        after_terms = [str(value).strip() for value in item.get("after_terms", []) if str(value).strip()]
        boundary_terms = [str(value).strip() for value in item.get("boundary_terms", []) if str(value).strip()]
        boundary_match = str(item.get("boundary_match", "any")).strip().lower()
        if (
            not probe_id
            or turn < 1
            or max_marker_gap < 1
            or not before_markers
            or not before_terms
            or not after_markers
            or not after_terms
            or not boundary_terms
            or boundary_match not in {"all", "any"}
        ):
            raise SystemExit(
                "Semantic relation probes require id, turn >= 1, before/after markers "
                "and terms, boundary_terms, boundary_match=all|any, and max_marker_gap >= 1."
            )
        relation_probes.append(
            {
                "id": probe_id,
                "turn": turn,
                "before_markers": before_markers,
                "before_terms": before_terms,
                "after_markers": after_markers,
                "after_terms": after_terms,
                "boundary_terms": boundary_terms,
                "boundary_match": boundary_match,
                "max_marker_gap": max_marker_gap,
            }
        )

    targets: list[dict] = []
    for item in taxonomy.get("targets", []):
        if not isinstance(item, dict):
            raise SystemExit("Each semantic target must be a JSON object.")
        raw_target_id = str(item.get("id", "")).strip()
        raw_frame_id = str(item.get("frame_id", "")).strip()
        if not raw_target_id or not raw_frame_id:
            raise SystemExit("Semantic targets require id, turn >= 1, and a known frame_id.")
        target_id = safe_id(raw_target_id)
        try:
            turn = int(item.get("turn"))
        except (TypeError, ValueError) as exc:
            raise SystemExit("Semantic target turn must be an integer.") from exc
        source_turn_raw = item.get("source_turn")
        try:
            source_turn = (
                int(source_turn_raw) if source_turn_raw is not None else None
            )
        except (TypeError, ValueError) as exc:
            raise SystemExit("Semantic target source_turn must be an integer.") from exc
        frame_id = safe_id(raw_frame_id)
        if (
            not target_id
            or turn < 1
            or frame_id not in seen
            or (source_turn is not None and (source_turn < 1 or source_turn >= turn))
        ):
            raise SystemExit("Semantic targets require id, turn >= 1, and a known frame_id.")
        targets.append(
            {
                "id": target_id,
                "turn": turn,
                "frame_id": frame_id,
                "source_turn": source_turn,
            }
        )

    contrasts: list[dict] = []
    for item in taxonomy.get("contrasts", []):
        if not isinstance(item, dict):
            raise SystemExit("Each semantic contrast must be a JSON object.")
        raw_contrast_id = str(item.get("id", "")).strip()
        raw_target_id = str(item.get("target_id", "")).strip()
        if not raw_contrast_id or not raw_target_id:
            raise SystemExit("Semantic contrasts require id and a known target_id.")
        contrast_id = safe_id(raw_contrast_id)
        target_id = safe_id(raw_target_id)
        treatment = str(item.get("treatment", "")).strip()
        control = str(item.get("control", "")).strip()
        if not contrast_id or target_id not in {target["id"] for target in targets}:
            raise SystemExit("Semantic contrasts require id and a known target_id.")
        if not treatment or not control:
            raise SystemExit("Semantic contrasts require treatment and control conditions.")
        contrasts.append(
            {
                "id": contrast_id,
                "target_id": target_id,
                "treatment": treatment,
                "control": control,
            }
        )
    return {
        "schema_version": int(taxonomy.get("schema_version", 1)),
        "id": str(taxonomy.get("id", path.stem)),
        "title": str(taxonomy.get("title", taxonomy.get("id", path.stem))),
        "frames": frames,
        "relation_probes": relation_probes,
        "targets": targets,
        "contrasts": contrasts,
        "_path": str(path),
        "_sha256": file_sha256(path),
    }


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _note_source_path(session_dir: Path, speaker: str, observation: str) -> str:
    match = re.search(r"(turns/\d+-note\.md)", observation)
    if not match:
        return ""
    matches = sorted(
        session_dir.glob(f"scratchpads/speaker-{speaker.lower()}/threads/*/{match.group(1)}")
    )
    return str(matches[0]) if matches else ""


def load_dialogue_semantic_corpus(run_dir: Path) -> tuple[dict, list[dict], dict]:
    run_dir = run_dir.expanduser().resolve()
    suite_path = run_dir / "suite_manifest.json"
    try:
        suite = json.loads(suite_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"Dialogue suite manifest not found: {suite_path}") from exc
    if suite.get("status") != "ok":
        raise SystemExit(f"Dialogue semantic analysis requires an ok suite, got {suite.get('status')!r}.")

    documents: list[dict] = []
    session_context: dict[str, dict] = {}
    for suite_session in suite.get("sessions", []):
        condition = str(suite_session.get("condition", ""))
        session_id = str(suite_session.get("session_id", ""))
        session_dir = run_dir / session_id
        transcript = load_jsonl(session_dir / "transcript.jsonl")
        events = load_jsonl(session_dir / "trace.jsonl")
        prompts: dict[tuple[int, str], str] = {}
        pending_notes: dict[tuple[int, str], dict] = {}
        notes: list[dict] = []
        for event in events:
            try:
                turn = int(event.get("dialogue_turn", 0))
            except (TypeError, ValueError):
                turn = 0
            speaker = str(event.get("speaker", ""))
            key = (turn, speaker)
            if event.get("event") == "model_request" and key not in prompts:
                prompts[key] = str(event.get("prompt", ""))
            payload = event.get("payload")
            if (
                event.get("event") == "model_output"
                and isinstance(payload, dict)
                and payload.get("action") == "scratchpad.add_note"
            ):
                pending_notes[key] = payload
            observation = str(event.get("observation", ""))
            if (
                event.get("event") == "tool_observation"
                and event.get("action") == "scratchpad.add_note"
                and "wrote turn" in observation
            ):
                payload = pending_notes.pop(key, None)
                if not payload:
                    continue
                note_number_match = re.search(r"wrote turn (\d+)", observation)
                note_number = int(note_number_match.group(1)) if note_number_match else len(notes) + 1
                note_text = str(payload.get("text", "")).strip()
                analysis_text = "\n".join(
                    str(payload.get(field, "")).strip()
                    for field in NOTE_FIELDS
                    if str(payload.get(field, "")).strip()
                )
                note = {
                    "id": f"{session_id}:note:{speaker}:{note_number:06d}",
                    "kind": "note",
                    "condition": condition,
                    "session_id": session_id,
                    "turn": turn,
                    "speaker": speaker,
                    "text": note_text,
                    "analysis_text": analysis_text,
                    "fields": {field: str(payload.get(field, "")) for field in NOTE_FIELDS},
                    "source_path": _note_source_path(session_dir, speaker, observation),
                }
                notes.append(note)
                documents.append(note)

        utterances: list[dict] = []
        for item in transcript:
            if item.get("kind") != "utterance":
                continue
            turn = int(item["turn"])
            speaker = str(item["speaker"])
            utterance = {
                "id": f"{session_id}:utterance:{turn:02d}",
                "kind": "utterance",
                "condition": condition,
                "session_id": session_id,
                "turn": turn,
                "speaker": speaker,
                "text": str(item.get("message", "")),
                "analysis_text": str(item.get("message", "")),
                "source_path": str(session_dir / "transcript.jsonl"),
            }
            utterances.append(utterance)
            documents.append(utterance)
        session_context[session_id] = {
            "session_id": session_id,
            "manifest": suite_session,
            "prompts": prompts,
            "utterances": utterances,
            "notes": notes,
        }
    return suite, documents, session_context


def classify_semantic_documents(documents: list[dict], taxonomy: dict) -> tuple[list[dict], dict[str, dict[str, float]]]:
    frame_texts = [
        "\n".join(frame["prototypes"] + frame["terms"])
        for frame in taxonomy["frames"]
    ]
    texts = [document["analysis_text"] for document in documents] + frame_texts
    vectors = tfidf_vectors(texts)
    document_vectors = vectors[: len(documents)]
    frame_vectors = vectors[len(documents) :]
    vector_by_id = {document["id"]: vector for document, vector in zip(documents, document_vectors)}
    classified: list[dict] = []
    for document, vector in zip(documents, document_vectors):
        normalized = normalize_semantic_text(document["analysis_text"])
        scores: dict[str, float] = {}
        term_hits: dict[str, list[str]] = {}
        for frame, frame_vector in zip(taxonomy["frames"], frame_vectors):
            hits = [term for term in frame["terms"] if normalize_semantic_text(term) in normalized]
            lexical_coverage = min(1.0, len(hits) / 2.0)
            score = (
                SEMANTIC_SCORE_WEIGHTS["prototype_cosine"] * sparse_cosine(vector, frame_vector)
                + SEMANTIC_SCORE_WEIGHTS["lexical_coverage"] * lexical_coverage
            )
            scores[frame["id"]] = round(score, 6)
            term_hits[frame["id"]] = hits
        ranked = sorted(scores, key=lambda frame_id: (-scores[frame_id], frame_id))
        top_score = scores[ranked[0]] if ranked else 0.0
        primary = ranked[0] if top_score >= SEMANTIC_MIN_SCORE else "unclassified"
        label_floor = max(SEMANTIC_MIN_SCORE, top_score * SEMANTIC_RELATIVE_LABEL_THRESHOLD)
        labels = [frame_id for frame_id in ranked if scores[frame_id] >= label_floor]
        classified.append(
            {
                **document,
                "primary_frame": primary,
                "frames": labels,
                "frame_scores": scores,
                "term_hits": term_hits,
            }
        )
    return classified, vector_by_id


def _sequence_similarity(documents: list[dict], vector_by_id: dict[str, dict[str, float]]) -> float:
    ordered = sorted(documents, key=lambda item: int(item["turn"]))
    return mean(
        [
            sparse_cosine(vector_by_id[left["id"]], vector_by_id[right["id"]])
            for left, right in zip(ordered, ordered[1:])
        ]
    )


def _same_speaker_similarity(documents: list[dict], vector_by_id: dict[str, dict[str, float]]) -> float:
    values: list[float] = []
    for speaker in sorted({str(document["speaker"]) for document in documents}):
        ordered = sorted(
            [document for document in documents if document["speaker"] == speaker],
            key=lambda item: int(item["turn"]),
        )
        values.extend(
            sparse_cosine(vector_by_id[left["id"]], vector_by_id[right["id"]])
            for left, right in zip(ordered, ordered[1:])
        )
    return mean(values)


def _probe_results(manifest: dict, turn: int) -> list[dict]:
    evidence = manifest.get("literal_probe_evidence", {})
    results = [item for item in evidence.get("results", []) if int(item.get("turn", 0)) == turn]
    return [
        {
            "id": str(item.get("id", f"probe-{index:02d}")),
            "passed": bool(item.get("passed")),
            "match": str(item.get("match", "all")),
            "terms": [str(value) for value in item.get("terms", [])],
            "found": [str(value) for value in item.get("found", [])],
            "missing": [str(value) for value in item.get("missing", [])],
        }
        for index, item in enumerate(results, start=1)
    ]


def _probe_score(manifest: dict, turn: int) -> tuple[int, int, list[dict]]:
    results = _probe_results(manifest, turn)
    return sum(1 for item in results if item.get("passed")), len(results), results


def _relation_probe_results(manifest: dict, turn: int) -> list[dict]:
    evidence = manifest.get("relation_probe_evidence", {})
    results = [item for item in evidence.get("results", []) if int(item.get("turn", 0)) == turn]
    return [
        {
            "id": str(item.get("id", f"relation-{index:02d}")),
            "passed": bool(item.get("passed")),
            "order_passed": bool(item.get("order_passed")),
            "boundary_passed": bool(item.get("boundary_passed")),
            "reversed_roles": bool(item.get("reversed_roles")),
            "before_matches": list(item.get("before_matches", [])),
            "after_matches": list(item.get("after_matches", [])),
            "boundary_found": [str(value) for value in item.get("boundary_found", [])],
            "boundary_missing": [str(value) for value in item.get("boundary_missing", [])],
        }
        for index, item in enumerate(results, start=1)
    ]


def _relation_probe_score(manifest: dict, turn: int) -> tuple[int, int, list[dict]]:
    results = _relation_probe_results(manifest, turn)
    return sum(1 for item in results if item.get("passed")), len(results), results


def analyze_dialogue_semantics(
    run_dir: Path,
    taxonomy_path: Path,
    out_prefix: Path | None = None,
) -> dict:
    run_dir = run_dir.expanduser().resolve()
    taxonomy = load_semantic_taxonomy(taxonomy_path)
    suite, documents, session_context = load_dialogue_semantic_corpus(run_dir)
    classified, vector_by_id = classify_semantic_documents(documents, taxonomy)
    by_id = {document["id"]: document for document in classified}
    frames = [frame["id"] for frame in taxonomy["frames"]]

    session_summaries: list[dict] = []
    target_results: list[dict] = []
    for suite_session in suite.get("sessions", []):
        condition = str(suite_session["condition"])
        session_id = str(suite_session["session_id"])
        replicate = int(suite_session.get("replicate", 1))
        context = session_context[session_id]
        utterances = [by_id[document["id"]] for document in context["utterances"]]
        notes = [by_id[document["id"]] for document in context["notes"]]
        utterance_vectors = [vector_by_id[document["id"]] for document in utterances]
        session_summaries.append(
            {
                "session_id": session_id,
                "condition": condition,
                "replicate": replicate,
                "utterance_count": len(utterances),
                "note_count": len(notes),
                "mean_frame_scores": {
                    frame_id: round(mean([document["frame_scores"][frame_id] for document in utterances]), 6)
                    for frame_id in frames
                },
                "primary_frame_counts": dict(sorted(Counter(document["primary_frame"] for document in utterances).items())),
                "semantic_entropy": round(
                    normalized_entropy(
                        [document["primary_frame"] for document in utterances],
                        len(frames) + 1,
                    ),
                    6,
                ),
                "mean_pairwise_similarity": round(mean_pairwise_similarity(utterance_vectors), 6),
                "adjacent_turn_similarity": round(_sequence_similarity(utterances, vector_by_id), 6),
                "same_speaker_lag_similarity": round(_same_speaker_similarity(utterances, vector_by_id), 6),
                "note_mean_frame_scores": {
                    frame_id: round(mean([document["frame_scores"][frame_id] for document in notes]), 6)
                    for frame_id in frames
                },
                "note_primary_frame_counts": dict(
                    sorted(Counter(document["primary_frame"] for document in notes).items())
                ),
            }
        )

        for target in taxonomy["targets"]:
            target_document = next(
                (document for document in utterances if int(document["turn"]) == target["turn"]),
                None,
            )
            if target_document is None:
                continue
            candidate_notes = [
                note
                for note in notes
                if note["speaker"] == target_document["speaker"] and int(note["turn"]) < target["turn"]
            ]
            if target.get("source_turn") is not None:
                candidate_notes = [
                    note
                    for note in candidate_notes
                    if int(note["turn"]) == int(target["source_turn"])
                ]
                candidate_notes.sort(key=lambda note: str(note["id"]))
            else:
                candidate_notes.sort(
                    key=lambda note: (
                        -note["frame_scores"][target["frame_id"]],
                        int(note["turn"]),
                    )
                )
            source_note = candidate_notes[0] if candidate_notes else None
            prompt = context["prompts"].get((target["turn"], target_document["speaker"]), "")
            containment = (
                ngram_containment(source_note["text"], prompt) if source_note is not None else 0.0
            )
            probe_passed, probe_total, probe_results = _probe_score(
                context["manifest"], target["turn"]
            )
            relation_manifest = context["manifest"]
            relation_probe_source = "generation-manifest"
            if taxonomy["relation_probes"]:
                relation_probe_source = "assessment-taxonomy"
                relation_manifest = {
                    "relation_probe_evidence": relation_probe_evidence(
                        [
                            {
                                "kind": "utterance",
                                "turn": target["turn"],
                                "speaker": target_document["speaker"],
                                "message": target_document["text"],
                            }
                        ],
                        taxonomy["relation_probes"],
                    )
                }
            relation_passed, relation_total, relation_results = _relation_probe_score(
                relation_manifest, target["turn"]
            )
            target_results.append(
                {
                    "target_id": target["id"],
                    "frame_id": target["frame_id"],
                    "session_id": session_id,
                    "condition": condition,
                    "replicate": replicate,
                    "turn": target["turn"],
                    "speaker": target_document["speaker"],
                    "primary_frame": target_document["primary_frame"],
                    "frame_score": target_document["frame_scores"][target["frame_id"]],
                    "literal_probe_passed": probe_passed,
                    "literal_probe_total": probe_total,
                    "literal_probe_results": probe_results,
                    "relation_probe_passed": relation_passed,
                    "relation_probe_total": relation_total,
                    "relation_probe_results": relation_results,
                    "relation_probe_source": relation_probe_source,
                    "source_note_id": source_note["id"] if source_note else None,
                    "source_note_turn": source_note["turn"] if source_note else None,
                    "source_note_frame_score": (
                        source_note["frame_scores"][target["frame_id"]] if source_note else None
                    ),
                    "note_prompt_containment": round(containment, 6),
                    "note_visible": containment >= 0.72,
                    "note_response_similarity": (
                        round(
                            sparse_cosine(
                                vector_by_id[source_note["id"]],
                                vector_by_id[target_document["id"]],
                            ),
                            6,
                        )
                        if source_note
                        else None
                    ),
                    "response": target_document["text"],
                }
            )

    condition_summaries: list[dict] = []
    condition_order = list(dict.fromkeys(str(session["condition"]) for session in suite.get("sessions", [])))
    for condition in condition_order:
        sessions = [session for session in session_summaries if session["condition"] == condition]
        utterances = [
            document
            for document in classified
            if document["kind"] == "utterance" and document["condition"] == condition
        ]
        notes = [
            document
            for document in classified
            if document["kind"] == "note" and document["condition"] == condition
        ]
        condition_summaries.append(
            {
                "condition": condition,
                "session_count": len(sessions),
                "utterance_count": len(utterances),
                "note_count": len(notes),
                "mean_frame_scores": {
                    frame_id: round(mean([document["frame_scores"][frame_id] for document in utterances]), 6)
                    for frame_id in frames
                },
                "primary_frame_counts": dict(sorted(Counter(document["primary_frame"] for document in utterances).items())),
                "semantic_entropy": round(
                    normalized_entropy(
                        [document["primary_frame"] for document in utterances],
                        len(frames) + 1,
                    ),
                    6,
                ),
                "mean_pairwise_similarity": round(mean([session["mean_pairwise_similarity"] for session in sessions]), 6),
                "adjacent_turn_similarity": round(mean([session["adjacent_turn_similarity"] for session in sessions]), 6),
                "same_speaker_lag_similarity": round(mean([session["same_speaker_lag_similarity"] for session in sessions]), 6),
                "note_mean_frame_scores": {
                    frame_id: round(mean([document["frame_scores"][frame_id] for document in notes]), 6)
                    for frame_id in frames
                },
            }
        )

    contrast_instances: list[dict] = []
    targets_by_key = {
        (item["target_id"], item["condition"], item["replicate"]): item
        for item in target_results
    }
    for contrast in taxonomy["contrasts"]:
        replicates = sorted(
            {
                item["replicate"]
                for item in target_results
                if item["target_id"] == contrast["target_id"]
            }
        )
        for replicate in replicates:
            treatment = targets_by_key.get(
                (contrast["target_id"], contrast["treatment"], replicate)
            )
            control = targets_by_key.get(
                (contrast["target_id"], contrast["control"], replicate)
            )
            if not treatment or not control:
                continue
            contrast_instances.append(
                {
                    **contrast,
                    "replicate": replicate,
                    "frame_id": treatment["frame_id"],
                    "treatment_frame_score": treatment["frame_score"],
                    "control_frame_score": control["frame_score"],
                    "frame_score_delta": round(treatment["frame_score"] - control["frame_score"], 6),
                    "treatment_note_visible": treatment["note_visible"],
                    "control_note_visible": control["note_visible"],
                    "treatment_literal_probe_passed": treatment["literal_probe_passed"],
                    "treatment_literal_probe_total": treatment["literal_probe_total"],
                    "control_literal_probe_passed": control["literal_probe_passed"],
                    "control_literal_probe_total": control["literal_probe_total"],
                    "treatment_literal_probe_results": treatment["literal_probe_results"],
                    "control_literal_probe_results": control["literal_probe_results"],
                    "treatment_relation_probe_passed": treatment[
                        "relation_probe_passed"
                    ],
                    "treatment_relation_probe_total": treatment[
                        "relation_probe_total"
                    ],
                    "control_relation_probe_passed": control[
                        "relation_probe_passed"
                    ],
                    "control_relation_probe_total": control[
                        "relation_probe_total"
                    ],
                    "treatment_relation_probe_results": treatment[
                        "relation_probe_results"
                    ],
                    "control_relation_probe_results": control[
                        "relation_probe_results"
                    ],
                }
            )

    contrasts: list[dict] = []
    for contrast in taxonomy["contrasts"]:
        instances = [item for item in contrast_instances if item["id"] == contrast["id"]]
        if not instances:
            continue
        deltas = [item["frame_score_delta"] for item in instances]
        session_literal_pairs = [
            (
                item["treatment_literal_probe_total"] > 0
                and item["treatment_literal_probe_passed"]
                == item["treatment_literal_probe_total"],
                item["control_literal_probe_total"] > 0
                and item["control_literal_probe_passed"]
                == item["control_literal_probe_total"],
            )
            for item in instances
            if item["treatment_literal_probe_total"] > 0
            and item["control_literal_probe_total"] > 0
        ]
        item_literal_pairs: list[tuple[bool, bool]] = []
        session_relation_pairs = [
            (
                item["treatment_relation_probe_total"] > 0
                and item["treatment_relation_probe_passed"]
                == item["treatment_relation_probe_total"],
                item["control_relation_probe_total"] > 0
                and item["control_relation_probe_passed"]
                == item["control_relation_probe_total"],
            )
            for item in instances
            if item["treatment_relation_probe_total"] > 0
            and item["control_relation_probe_total"] > 0
        ]
        item_relation_pairs: list[tuple[bool, bool]] = []
        for item in instances:
            treatment_items = {
                probe["id"]: bool(probe["passed"])
                for probe in item["treatment_literal_probe_results"]
            }
            control_items = {
                probe["id"]: bool(probe["passed"])
                for probe in item["control_literal_probe_results"]
            }
            item_literal_pairs.extend(
                (treatment_items[probe_id], control_items[probe_id])
                for probe_id in sorted(treatment_items.keys() & control_items.keys())
            )
            treatment_relations = {
                probe["id"]: bool(probe["passed"])
                for probe in item["treatment_relation_probe_results"]
            }
            control_relations = {
                probe["id"]: bool(probe["passed"])
                for probe in item["control_relation_probe_results"]
            }
            item_relation_pairs.extend(
                (treatment_relations[probe_id], control_relations[probe_id])
                for probe_id in sorted(
                    treatment_relations.keys() & control_relations.keys()
                )
            )
        contrasts.append(
            {
                **contrast,
                "frame_id": instances[0]["frame_id"],
                "replicates": len(instances),
                "treatment_frame_score": round(mean([item["treatment_frame_score"] for item in instances]), 6),
                "control_frame_score": round(mean([item["control_frame_score"] for item in instances]), 6),
                "frame_score_delta": round(mean(deltas), 6),
                "frame_score_delta_median": round(median(deltas), 6),
                "frame_score_delta_sample_sd": round(sample_standard_deviation(deltas), 6),
                "frame_score_delta_bootstrap_ci": paired_bootstrap_mean_interval(deltas),
                "positive_delta_replicates": sum(1 for value in deltas if value > 0),
                "frame_score_deltas": deltas,
                "treatment_note_visible_rate": round(mean([float(item["treatment_note_visible"]) for item in instances]), 6),
                "control_note_visible_rate": round(mean([float(item["control_note_visible"]) for item in instances]), 6),
                "treatment_literal_probe": (
                    f"{sum(item['treatment_literal_probe_passed'] for item in instances)}/"
                    f"{sum(item['treatment_literal_probe_total'] for item in instances)}"
                ),
                "control_literal_probe": (
                    f"{sum(item['control_literal_probe_passed'] for item in instances)}/"
                    f"{sum(item['control_literal_probe_total'] for item in instances)}"
                ),
                "literal_session_outcomes": paired_binary_outcome_table(
                    session_literal_pairs
                ),
                "literal_item_outcomes": paired_binary_outcome_table(item_literal_pairs),
                "treatment_relation_probe": (
                    f"{sum(item['treatment_relation_probe_passed'] for item in instances)}/"
                    f"{sum(item['treatment_relation_probe_total'] for item in instances)}"
                ),
                "control_relation_probe": (
                    f"{sum(item['control_relation_probe_passed'] for item in instances)}/"
                    f"{sum(item['control_relation_probe_total'] for item in instances)}"
                ),
                "relation_session_outcomes": paired_binary_outcome_table(
                    session_relation_pairs
                ),
                "relation_item_outcomes": paired_binary_outcome_table(
                    item_relation_pairs
                ),
            }
        )

    representatives: dict[str, list[dict]] = {}
    for frame_id in frames:
        ranked = sorted(
            classified,
            key=lambda document: (-document["frame_scores"][frame_id], document["id"]),
        )
        representatives[frame_id] = [
            {
                "id": document["id"],
                "kind": document["kind"],
                "condition": document["condition"],
                "turn": document["turn"],
                "speaker": document["speaker"],
                "score": document["frame_scores"][frame_id],
                "text": document["text"],
            }
            for document in ranked[:3]
        ]

    output_prefix = (
        out_prefix.expanduser().resolve()
        if out_prefix is not None
        else run_dir / "semantic_analysis"
    )
    result: dict = {
        "schema_version": 2,
        "generation_identity": {
            "run_id": suite.get("run_id"),
            "scenario_sha256": suite.get("scenario_sha256"),
            "dialogue_runner_sha256": suite.get("dialogue_runner_sha256"),
            "llm": suite.get("llm", {}),
            "history_chars": suite.get("history_chars"),
            "budget_plan": suite.get("budget_plan", {}),
        },
        "assessment_identity": {
            "method": SEMANTIC_METHOD,
            "ngrams": list(SEMANTIC_NGRAMS),
            "score_weights": SEMANTIC_SCORE_WEIGHTS,
            "min_score": SEMANTIC_MIN_SCORE,
            "relative_label_threshold": SEMANTIC_RELATIVE_LABEL_THRESHOLD,
            "relation_probe_method": RELATION_PROBE_METHOD,
            "paired_bootstrap": {
                "seed": SEMANTIC_BOOTSTRAP_SEED,
                "resamples": SEMANTIC_BOOTSTRAP_RESAMPLES,
                "confidence": SEMANTIC_BOOTSTRAP_CONFIDENCE,
            },
            "taxonomy_path": taxonomy["_path"],
            "taxonomy_sha256": taxonomy["_sha256"],
            "analyzer_sha256": file_sha256(Path(__file__)),
        },
        "taxonomy": {key: value for key, value in taxonomy.items() if not key.startswith("_")},
        "corpus": {
            "run_dir": str(run_dir),
            "documents": len(classified),
            "utterances": sum(1 for document in classified if document["kind"] == "utterance"),
            "notes": sum(1 for document in classified if document["kind"] == "note"),
            "characters": sum(len(document["text"]) for document in classified),
        },
        "conditions": condition_summaries,
        "sessions": session_summaries,
        "targets": target_results,
        "contrasts": contrasts,
        "contrast_instances": contrast_instances,
        "representatives": representatives,
        "documents": classified,
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
    report_path.write_text(semantic_report_markdown(result), encoding="utf-8")
    return result


def _score(value: float | int | None) -> str:
    return "-" if value is None else f"{float(value):.3f}"


def semantic_report_markdown(result: dict) -> str:
    taxonomy = result["taxonomy"]
    frames = taxonomy["frames"]
    lines = [
        "# Dialogue Semantic NLP Report",
        "",
        f"- Run id: {result['generation_identity']['run_id']}",
        f"- Model: {result['generation_identity']['llm'].get('model', '')}",
        f"- Method: {result['assessment_identity']['method']}",
        f"- Taxonomy: {taxonomy['id']}",
        f"- Documents: {result['corpus']['documents']} ({result['corpus']['utterances']} utterances, {result['corpus']['notes']} notes)",
        "",
        "This report uses frozen semantic prototypes plus character 2-4 gram TF-IDF. It is an auditable lexical-semantic measurement, not an LLM quality judgment.",
        "",
        "## Frame Occupancy",
        "",
    ]
    header = ["Condition"] + [frame["id"] for frame in frames] + ["Entropy", "Pair sim", "Self-lag sim"]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(["---"] + ["---:"] * (len(header) - 1)) + "|")
    for condition in result["conditions"]:
        row = [f"{condition['condition']} (n={condition['session_count']})"]
        row.extend(_score(condition["mean_frame_scores"][frame["id"]]) for frame in frames)
        row.extend(
            [
                _score(condition["semantic_entropy"]),
                _score(condition["mean_pairwise_similarity"]),
                _score(condition["same_speaker_lag_similarity"]),
            ]
        )
        lines.append("| " + " | ".join(row) + " |")

    lines.extend(["", "## Note Contents", ""])
    lines.append("| Condition | Notes | " + " | ".join(frame["id"] for frame in frames) + " |")
    lines.append("|---|---:|" + "|".join("---:" for _ in frames) + "|")
    for condition in result["conditions"]:
        row = [condition["condition"], str(condition["note_count"])]
        row.extend(_score(condition["note_mean_frame_scores"][frame["id"]]) for frame in frames)
        lines.append("| " + " | ".join(row) + " |")

    note_documents = [document for document in result["documents"] if document["kind"] == "note"]
    if note_documents:
        lines.extend(["", "### Individual Notes", ""])
        lines.extend(
            [
                "| Condition | Turn | Speaker | Primary frame | Score | Contents |",
                "|---|---:|---|---|---:|---|",
            ]
        )
        for document in sorted(
            note_documents,
            key=lambda item: (item["condition"], int(item["turn"]), item["speaker"]),
        ):
            primary = document["primary_frame"]
            primary_score = document["frame_scores"].get(primary, 0.0)
            excerpt = str(document["text"]).replace("\n", " ").replace("|", "\\|")
            lines.append(
                f"| {document['condition']} | {document['turn']} | {document['speaker']} | "
                f"{primary} | {_score(primary_score)} | {excerpt} |"
            )

    lines.extend(["", "## Delayed Targets", ""])
    lines.extend(
        [
            "| Session | Target frame | Score | Primary | Literal | Relation | Note visible | Note-response sim |",
            "|---|---|---:|---|---:|---:|---:|---:|",
        ]
    )
    for target in result["targets"]:
        lines.append(
            "| {condition} | {frame} | {score} | {primary} | {passed}/{total} | {relation_passed}/{relation_total} | {visible} | {similarity} |".format(
                condition=f"{target['condition']}-r{target['replicate']:02d}",
                frame=target["frame_id"],
                score=_score(target["frame_score"]),
                primary=target["primary_frame"],
                passed=target["literal_probe_passed"],
                total=target["literal_probe_total"],
                relation_passed=target["relation_probe_passed"],
                relation_total=target["relation_probe_total"],
                visible="yes" if target["note_visible"] else "no",
                similarity=_score(target["note_response_similarity"]),
            )
        )

    if result["contrasts"]:
        lines.extend(["", "## Frozen Contrasts", ""])
        lines.extend(
            [
                "| Contrast | n | Treatment | Control | Mean delta | Bootstrap CI | Median | Positive | Note visibility rate | Literal probes | Relation probes | Literal discordance | Relation discordance |",
                "|---|---:|---|---|---:|---|---:|---:|---|---|---|---|---|",
            ]
        )
        for contrast in result["contrasts"]:
            lines.append(
                f"| {contrast['id']} | {contrast['replicates']} | {contrast['treatment']} | {contrast['control']} | "
                f"{_score(contrast['frame_score_delta'])} | "
                f"[{_score(contrast['frame_score_delta_bootstrap_ci']['lower'])}, {_score(contrast['frame_score_delta_bootstrap_ci']['upper'])}] | "
                f"{_score(contrast['frame_score_delta_median'])} | "
                f"{contrast['positive_delta_replicates']}/{contrast['replicates']} | "
                f"{_score(contrast['treatment_note_visible_rate'])} / {_score(contrast['control_note_visible_rate'])} | "
                f"{contrast['treatment_literal_probe']} / {contrast['control_literal_probe']} | "
                f"{contrast['treatment_relation_probe']} / {contrast['control_relation_probe']} | "
                f"{contrast['literal_session_outcomes']['treatment_only']} / {contrast['literal_session_outcomes']['control_only']} | "
                f"{contrast['relation_session_outcomes']['treatment_only']} / {contrast['relation_session_outcomes']['control_only']} |"
            )

    lines.extend(["", "## Representative Passages", ""])
    frame_labels = {frame["id"]: frame["label"] for frame in frames}
    for frame_id, examples in result["representatives"].items():
        lines.extend([f"### {frame_labels[frame_id]}", ""])
        for example in examples:
            excerpt = str(example["text"]).replace("\n", " ")
            lines.append(
                f"- `{example['condition']}` {example['kind']} turn {example['turn']} "
                f"({_score(example['score'])}): {excerpt}"
            )
        lines.append("")

    lines.extend(
        [
            "## Interpretation Boundary",
            "",
            "Prototype scores measure alignment with this frozen taxonomy, not factual correctness. Pairwise similarity measures semantic repetition under the same representation. A single run can identify provider-visible transfer plumbing and aligned behavior, but increased-n replication is required before claiming a stable treatment effect.",
            "",
        ]
    )
    return "\n".join(lines).strip() + "\n"
