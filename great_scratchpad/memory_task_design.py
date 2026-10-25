"""Offline task construction and exposure audit. No provider execution here."""

from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile

from .grounded_recall import strict_json
from .centerline import analyze_centerline, render_centerline_hints
from .chat import build_chat_prompt
from .dialogue import canonical_json_sha256, render_dialogue_context
from .experiments import write_manifest
from .memory import retrieve
from .text import build_turn_md

METHOD = "memory-task-design-v1"
FAMILIES = ("decision-update", "scoped-exception", "distributed-join")
REGIMES = ("recent", "delayed", "interference", "insufficient")
CONDITIONS = ("window-only", "archive-recent", "scratchpad-retrieve", "irrelevant-notes", "oracle-evidence", "full-history")
SYSTEM = """Answer a question about a fictional project using only supplied records.
Return one JSON object with exactly these fields:
{"value": "exact recorded answer or null", "evidence": ["source id", "source id"]}
When evidence is insufficient, use {"value": null, "evidence": []}.
Never treat a proposal as an approved decision or an absent flag as false.
Evidence must be visible original records. Resolve scoped rules and links before
answering, citing every record needed for that inference. Do not cite an unrelated
record just because it contains the same word. Use at most eight distinct ids.
"""


def validate_spec(spec: dict) -> None:
    if spec.get("schema") != METHOD or spec.get("live_calls_authorized") != 0:
        raise ValueError("This is an offline-only design specification.")
    for key, expected in (("families", FAMILIES), ("regimes", REGIMES), ("conditions", CONDITIONS)):
        if spec.get(key) != list(expected):
            raise ValueError("All predeclared families, regimes and controls must be retained.")
    pilot, heldout = spec["pilot_seeds"], spec["confirmation_seeds"]
    if (len(pilot) != 1 or len(heldout) != 2 or len(set(pilot + heldout)) != 3
            or any(type(seed) is not int or seed < 1 for seed in pilot + heldout)):
        raise ValueError("Require one pilot seed and two disjoint confirmation seeds.")
    for field, low, high in (("history_chars", 500, 1000), ("memory_chars", 1000, 1600),
                             ("retrieval_top", 3, 6), ("distractor_records", 18, 30)):
        if type(spec[field]) is not int or not low <= spec[field] <= high:
            raise ValueError("Design budget outside the declared range.")


def _ids(seed: int, family: str, regime: str) -> tuple[str, list[str]]:
    digest = hashlib.sha256(f"{METHOD}:{seed}:{family}:{regime}".encode()).hexdigest()
    return digest[:8], [prefix + digest[i * 5:i * 5 + 5] for i, prefix in enumerate(("Q", "G", "T", "L", "P", "V"))]


def make_case(seed: int, family: str, regime: str, split: str, distractors: int) -> dict:
    suffix, (ticket, group, team, line, pool, value) = _ids(seed, family, regime)
    facts: list[dict] = []

    def fact(kind: str, text: str, **fields: object) -> None:
        facts.append({"text": text, "kind": kind, **fields})

    missing = regime == "insufficient"
    if family == "decision-update":
        status = "proposal" if missing else "approved"
        word = "未承認の提案" if missing else "承認済みの決定"
        fact("decision", f"案件 {ticket} の圧縮方式。初回の{word}は OLD{value}。", target=ticket, status=status, value="OLD" + value)
        fact("decision", f"案件 {ticket} の圧縮方式。二回目の{word}は {value}。承認済みの場合に限り前の決定を置き換える。",
             target=ticket, status=status, value=value)
        fact("decision", f"案件 {ticket} の圧縮方式を NEXT{value} にする案が後から出たが、これは未承認の提案であり決定ではない。",
             target=ticket, status="proposal", value="NEXT" + value)
        query = f"案件 {ticket} について、現在承認されている圧縮方式は何か。"
    elif family == "scoped-exception":
        urgent = bool(int(suffix[:2], 16) % 2)
        held = bool(int(suffix[2:4], 16) % 3 == 0)
        fact("policy", f"対象群 {group} の配送規則。通常便は BASE{pool}。緊急フラグが有効なら FAST{pool} にする。",
             group=group, base="BASE" + pool, fast="FAST" + pool)
        fact("override", f"対象群 {group} の配送規則に例外。保留フラグが有効なら緊急フラグより優先し HOLD{pool} にする。",
             group=group, held_value="HOLD" + pool)
        held_text = "未確認" if missing else "有効" if held else "無効"
        fact("request", f"申請 {ticket} は対象群 {group}。緊急フラグは{'有効' if urgent else '無効'}、保留フラグは{held_text}。",
             target=ticket, group=group, urgent=urgent, held=None if missing else held)
        query = f"申請 {ticket} の配送先を、適用される規則と申請記録から答えて。"
    elif family == "distributed-join":
        fact("assignment", f"依頼 {ticket} の担当班は {team}。依頼名だけから実行プールを決めてはいけない。", target=ticket, team=team)
        fact("team-line", f"班 {team} が使う処理系列は {line}。班と系列は別の識別子である。", team=team, line=line)
        if missing:
            fact("pending", f"処理系列 {line} の実行プールはまだ決まっていない。予約枠は実行先の確定記録ではない。", line=line)
        else:
            fact("line-pool", f"処理系列 {line} の実行プールは {pool}。この対応が今回の確定記録である。", line=line, pool=pool)
        query = f"依頼 {ticket} の最終実行プールはどこか。記録の対応関係をたどって答えて。"
    else:
        raise ValueError("Unknown task family.")
    noise = []
    for index in range(distractors):
        other = f"X{suffix}{index:02d}"
        if regime in {"interference", "insufficient"}:
            if family == "decision-update":
                text = f"別案件 {other} の圧縮方式は REV{index:02d}。{ticket} と名前は似ていても別案件で、こちらは承認済みの決定である。"
            elif family == "scoped-exception":
                text = f"別申請 {other} は別対象群 Z{index:02d}。配送規則では緊急便は EAST{index:02d}、保留便は WEST{index:02d}。{ticket} には適用しない。"
            else:
                text = f"別依頼 {other} の最終実行プールは ALT{index:02d}。依頼 {ticket} と同じ担当窓口でも班と系列の対応は別である。"
        else:
            text = f"備品管理 {other}。展示用ラベルは版 {index + 1} に更新した。棚の配置と印刷順序を確認し、次回は用紙の種類を相談する。"
        noise.append({"text": text, "kind": "distractor", "target": other})
    if regime == "recent":
        ordered = noise + facts
    else:
        # Relevant records are spread through the old prefix, then evicted by later records.
        ordered = facts[:1] + noise[:3] + facts[1:2] + noise[3:6] + facts[2:] + noise[6:]
    records = [{"id": f"m{index:03d}", "turn": index, **record} for index, record in enumerate(ordered, start=1)]
    case = {"id": f"{family}-{regime}-{seed}", "split": split, "seed": seed, "family": family,
            "regime": regime, "target": ticket, "query": query, "records": records}
    case["truth"] = solve_case(case)
    return case


def solve_case(case: dict) -> dict:
    """Reference semantics over authored events, not over model-generated prose."""
    records, target = case["records"], case["target"]
    unknown = {"value": None, "support": []}
    if case["family"] == "decision-update":
        approved = [r for r in records if r["kind"] == "decision" and r["target"] == target and r["status"] == "approved"]
        if not approved:
            return unknown
        latest = max(approved, key=lambda r: r["turn"])
        return {"value": latest["value"], "support": [latest["id"]]}
    if case["family"] == "scoped-exception":
        request = next((r for r in records if r["kind"] == "request" and r["target"] == target), None)
        if not request or request["held"] is None:
            return unknown
        policy = next((r for r in records if r["kind"] == "policy" and r["group"] == request["group"]), None)
        override = next((r for r in records if r["kind"] == "override" and r["group"] == request["group"]), None)
        if not policy or not override:
            return unknown
        if request["held"]:
            return {"value": override["held_value"], "support": [override["id"], request["id"]]}
        return {"value": policy["fast"] if request["urgent"] else policy["base"],
                "support": [policy["id"], override["id"], request["id"]]}
    assignment = next((r for r in records if r["kind"] == "assignment" and r["target"] == target), None)
    link = next((r for r in records if assignment and r["kind"] == "team-line" and r["team"] == assignment["team"]), None)
    endpoint = next((r for r in records if link and r["kind"] == "line-pool" and r["line"] == link["line"]), None)
    if not endpoint:
        return unknown
    return {"value": endpoint["pool"], "support": [assignment["id"], link["id"], endpoint["id"]]}


def source_text(record: dict) -> str:
    return f"[{record['id']}] {record['text']}"


def assess_task_answer(raw: str, case: dict, prompt: str) -> dict:
    result = {"schema_ok": False, "answer_correct": None, "grounded_success": False,
              "safe_abstention": None, "recovered": False, "errors": []}
    try:
        answer = strict_json(raw)
        if (not isinstance(answer, dict) or set(answer) != {"value", "evidence"}
                or (answer["value"] is not None and (not isinstance(answer["value"], str) or not answer["value"].strip()))
                or not isinstance(answer["evidence"], list) or len(answer["evidence"]) > 8
                or not all(isinstance(i, str) and i for i in answer["evidence"])
                or len(answer["evidence"]) != len(set(answer["evidence"]))
                or (answer["value"] is None and answer["evidence"])):
            raise ValueError("Expected a value/null and up to eight distinct source ids; null requires empty evidence.")
    except (ValueError, TypeError, RecursionError) as exc:
        result["errors"].append(str(exc))
        return result
    truth = solve_case(case)
    visible = {r["id"] for r in case["records"] if source_text(r) in prompt}
    result["schema_ok"] = True
    result["answer_correct"] = answer["value"] == truth["value"]
    result["safe_abstention"] = answer["value"] is None
    result["citations_visible"] = set(answer["evidence"]).issubset(visible)
    result["proof_covered"] = set(truth["support"]).issubset(answer["evidence"])
    result["grounded_success"] = bool(result["answer_correct"] and result["citations_visible"] and result["proof_covered"])
    result["recovered"] = result["grounded_success"] and truth["value"] is not None
    return result


def pack_records(records: list[dict], max_chars: int) -> tuple[str, list[str]]:
    lines, ids = [], []
    for record in records:
        candidate = source_text(record)
        if len("\n".join([*lines, candidate])) > max_chars:
            continue
        lines.append(candidate)
        ids.append(record["id"])
    return "\n".join(lines) or "(no archive records)", ids


def build_conditions(case: dict, spec: dict, archive: Path) -> list[dict]:
    archive.mkdir(parents=True, exist_ok=False)
    turns = archive / "turns"
    turns.mkdir()
    records = case["records"]
    for record in records:
        text = build_turn_md(record["turn"], "user", source_text(record), "", "", "", "", "", "", [],
                             created_at=f"synthetic-turn-{record['turn']:03d}")
        (turns / f"{record['turn']:06d}-note.md").write_text(text, encoding="utf-8")
    transcript = [{"kind": "utterance", "speaker": "A", "message": source_text(r)} for r in records]
    history = render_dialogue_context(transcript, spec["history_chars"])
    full_history = render_dialogue_context(transcript, 100000)
    recent_ids = {r["id"] for r in records if source_text(r) in history}
    prior = [r for r in records if r["id"] not in recent_ids]
    hits = retrieve(archive, case["query"], spec["retrieval_top"])
    by_turn = {r["turn"]: r for r in records}
    ranked = [by_turn[int(path.name.split("-", 1)[0])] for _, path, _ in hits]
    contexts = {
        "window-only": ("(no archive records)", []),
        "archive-recent": pack_records(list(reversed(prior)), spec["memory_chars"]),
        "scratchpad-retrieve": pack_records(ranked, spec["memory_chars"]),
        "irrelevant-notes": pack_records([r for r in reversed(records) if r["kind"] == "distractor"], spec["memory_chars"]),
        "oracle-evidence": pack_records([r for r in records if r["id"] in case["truth"]["support"]], spec["memory_chars"]),
        "full-history": ("(no archive records)", []),
    }
    rows = []
    for condition in CONDITIONS:
        context, selected = contexts[condition]
        visible_history = full_history if condition == "full-history" else history
        hints = render_centerline_hints(analyze_centerline(case["query"], [{"role": "user", "content": visible_history}]))
        common = dict(thread_id="memory-task-probe", user_text=case["query"], history=[], observations=[],
                      centerline_hints=hints, history_context=visible_history)
        prompt = build_chat_prompt(recent_context=context, **common)
        visible = [r["id"] for r in records if source_text(r) in prompt]
        support = set(case["truth"]["support"])
        rows.append({"condition": condition, "prompt": prompt, "prompt_sha256": canonical_json_sha256(prompt),
                     "outside_memory_sha256": canonical_json_sha256(build_chat_prompt(recent_context="", **common)),
                     "context_chars": len(context), "history_chars": len(visible_history),
                     "selected_ids": selected, "visible_ids": visible,
                     "support_visible": bool(support) and support.issubset(visible),
                     "retrieval_hits": [{"id": by_turn[int(p.name.split('-', 1)[0])]["id"], "score": score} for score, p, _ in hits]
                     if condition == "scratchpad-retrieve" else []})
    return rows


def validate_constructed_case(case: dict, rows: list[dict], spec: dict) -> None:
    truth = case["truth"]
    by_condition = {row["condition"]: row for row in rows}
    if truth != solve_case(case) or len(by_condition) != len(CONDITIONS):
        raise ValueError("Reference answer or condition set drifted.")
    if (truth["value"] is None) != (case["regime"] == "insufficient"):
        raise ValueError("Answerability stratum was constructed incorrectly.")
    if truth["value"] is not None:
        if not by_condition["full-history"]["support_visible"] or not by_condition["oracle-evidence"]["support_visible"]:
            raise ValueError("Oracle evidence is missing or over budget.")
        recent = by_condition["window-only"]["support_visible"]
        if recent != (case["regime"] == "recent"):
            raise ValueError("The intended recent/delayed manipulation failed.")
    normal = [row for row in rows if row["condition"] != "full-history"]
    if len({row["outside_memory_sha256"] for row in normal}) != 1:
        raise ValueError("Condition-specific information leaked outside memory.")
    if any(row["context_chars"] > spec["memory_chars"] for row in normal):
        raise ValueError("Memory budget exceeded.")


def design_memory_tasks(spec: dict, out_dir: Path) -> dict:
    validate_spec(spec)
    if out_dir.exists():
        raise FileExistsError("Task design requires a fresh output directory.")
    cases, audits = [], []
    with tempfile.TemporaryDirectory(prefix="scratchpad-task-design-") as temporary:
        for split, seeds in (("pilot", spec["pilot_seeds"]), ("confirmation", spec["confirmation_seeds"])):
            for seed in seeds:
                for family in FAMILIES:
                    for regime in REGIMES:
                        case = make_case(seed, family, regime, split, spec["distractor_records"])
                        rows = build_conditions(case, spec, Path(temporary) / case["id"])
                        validate_constructed_case(case, rows, spec)
                        cases.append(case)
                        audits.append({"id": case["id"], "split": split, "family": family, "regime": regime,
                                       "answerable": case["truth"]["value"] is not None, "conditions": rows})
    result = {"method": METHOD, "status": "OFFLINE_DESIGN_ONLY", "live_calls": 0,
              "model_difficulty": "NOT_MEASURED", "writer_quality": "NOT_TESTED",
              "assessment_method": "exact-task-answer-plus-visible-proof-v1",
              "memory_mode": "query-blind verbatim archive; no answer annotations or model-authored notes",
              "spec": spec, "spec_sha256": canonical_json_sha256(spec),
              "cases": cases, "cases_sha256": canonical_json_sha256(cases),
              "audits": audits, "system_prompt": SYSTEM,
              "runtime_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in sorted(Path(__file__).parent.glob("*.py"))}}
    out_dir.mkdir(parents=True, exist_ok=False)
    envelope = {"design_sha256": canonical_json_sha256(result), "design": result}
    write_manifest(out_dir / "design.json", envelope)
    return envelope
