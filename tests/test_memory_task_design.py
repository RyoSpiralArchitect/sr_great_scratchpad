from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from great_scratchpad.memory_task_design import (
    CONDITIONS, FAMILIES, REGIMES, assess_task_answer, build_conditions, design_memory_tasks,
    make_case, solve_case, source_text, validate_constructed_case, validate_spec,
)

REPO = Path(__file__).resolve().parents[1]
SPEC = json.loads((REPO / "scenarios" / "memory_task_design_v1.json").read_text())


class TaskDesignTests(unittest.TestCase):
    def case(self, family="distributed-join", regime="delayed", seed=260101):
        return make_case(seed, family, regime, "pilot", SPEC["distractor_records"])

    def test_all_predeclared_cells_are_kept_with_disjoint_seeds(self):
        with tempfile.TemporaryDirectory() as temp, patch("great_scratchpad.llm.call_llm_result", side_effect=AssertionError("No live calls")):
            envelope = design_memory_tasks(SPEC, Path(temp) / "design")
        design = envelope["design"]
        self.assertEqual(design["live_calls"], 0)
        self.assertEqual(design["model_difficulty"], "NOT_MEASURED")
        self.assertEqual(len(design["cases"]), 36)
        self.assertEqual(len({c["id"] for c in design["cases"]}), 36)
        for split, count in (("pilot", 12), ("confirmation", 24)):
            self.assertEqual(sum(c["split"] == split for c in design["cases"]), count)
        self.assertEqual(sum(not a["answerable"] for a in design["audits"]), 9)
        self.assertTrue(all(len(a["conditions"]) == 6 for a in design["audits"]))

    def test_design_reproducible_and_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            a = design_memory_tasks(SPEC, root / "first")
            b = design_memory_tasks(SPEC, root / "second")
            self.assertEqual(a, b)
            with self.assertRaises(FileExistsError):
                design_memory_tasks(SPEC, root / "first")

    def test_no_result_based_family_or_control_removal(self):
        for field in ("families", "regimes", "conditions", "confirmation_seeds"):
            spec = deepcopy(SPEC)
            spec[field].pop()
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_spec(spec)
        with self.assertRaises(ValueError):
            validate_spec({**SPEC, "live_calls_authorized": 1})

    def test_recent_exposure_old_eviction_and_oracle_access(self):
        with tempfile.TemporaryDirectory() as temp:
            for family in FAMILIES:
                for regime in REGIMES:
                    case = self.case(family, regime)
                    rows = build_conditions(case, SPEC, Path(temp) / case["id"])
                    validate_constructed_case(case, rows, SPEC)
                    by_arm = {r["condition"]: r for r in rows}
                    self.assertEqual(by_arm["window-only"]["support_visible"], regime == "recent")
                    self.assertEqual(by_arm["oracle-evidence"]["support_visible"], regime != "insufficient")
                    normal = [r for r in rows if r["condition"] != "full-history"]
                    self.assertEqual(len({r["outside_memory_sha256"] for r in normal}), 1)

    def test_ground_truth_never_enters_nonoracle_selection(self):
        case = self.case()
        altered = deepcopy(case)
        altered["truth"] = {"value": "FORGEDANSWER", "support": [case["records"][-1]["id"]]}
        with tempfile.TemporaryDirectory() as temp:
            left = build_conditions(case, SPEC, Path(temp) / "left")
            right = build_conditions(altered, SPEC, Path(temp) / "right")
            for a, b in zip(left, right):
                if a["condition"] != "oracle-evidence":
                    self.assertEqual(a["prompt"], b["prompt"])
                    self.assertEqual(a["selected_ids"], b["selected_ids"])
            for path in (Path(temp) / "left").rglob("*.md"):
                note = path.read_text()
                self.assertNotIn("FORGEDANSWER", note)
                self.assertNotIn('"support"', note)
                self.assertNotIn('"truth"', note)
                self.assertNotIn('"kind"', note)

    def test_reference_ignores_later_unapproved_proposals(self):
        case = self.case("decision-update")
        actual = solve_case(case)
        latest_proposal = next(r for r in case["records"] if r["kind"] == "decision" and r["status"] == "proposal")
        self.assertNotEqual(actual["value"], latest_proposal["value"])
        latest_proposal["status"] = "approved"
        self.assertEqual(solve_case(case)["value"], latest_proposal["value"])

    def test_unknown_hold_flag_is_not_false_and_exception_precedes_urgent(self):
        case = self.case("scoped-exception")
        request = next(r for r in case["records"] if r["kind"] == "request")
        request["held"] = None
        self.assertIsNone(solve_case(case)["value"])
        request.update(held=True, urgent=True)
        override = next(r for r in case["records"] if r["kind"] == "override")
        self.assertEqual(solve_case(case)["value"], override["held_value"])
        request["held"] = False
        policy = next(r for r in case["records"] if r["kind"] == "policy")
        self.assertEqual(solve_case(case)["value"], policy["fast"])

    def test_distributed_join_requires_each_link(self):
        case = self.case()
        self.assertEqual(len(solve_case(case)["support"]), 3)
        for kind in ("assignment", "team-line", "line-pool"):
            altered = deepcopy(case)
            altered["records"] = [r for r in altered["records"] if r["kind"] != kind]
            self.assertIsNone(solve_case(altered)["value"])

    def test_distractors_and_questions_do_not_supply_missing_facts(self):
        for family in FAMILIES:
            case = self.case(family, "insufficient")
            self.assertEqual(solve_case(case), {"value": None, "support": []})
            self.assertNotIn("support", case["query"])
            self.assertNotIn("truth", case["query"])

    def test_actual_runtime_ranker_used_and_failures_retained(self):
        case = self.case()
        with tempfile.TemporaryDirectory() as temp, patch("great_scratchpad.memory_task_design.retrieve", return_value=[]) as retrieve:
            rows = build_conditions(case, SPEC, Path(temp) / "archive")
        retrieve.assert_called_once()
        self.assertEqual(retrieve.call_args.args[1], case["query"])
        self.assertEqual(retrieve.call_args.args[2], SPEC["retrieval_top"])
        retrieval = next(r for r in rows if r["condition"] == "scratchpad-retrieve")
        self.assertFalse(retrieval["support_visible"])
        self.assertEqual(retrieval["selected_ids"], [])
        validate_constructed_case(case, rows, SPEC)

    def test_irrelevant_control_never_contains_gold_support_in_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            case = self.case("scoped-exception", "interference")
            rows = build_conditions(case, SPEC, Path(temp) / "archive")
        row = next(r for r in rows if r["condition"] == "irrelevant-notes")
        self.assertFalse(set(row["selected_ids"]) & set(case["truth"]["support"]))
        self.assertFalse(row["support_visible"])

    def test_source_ids_and_exposure_are_whole_record_bound(self):
        case = self.case()
        self.assertEqual(len({r["id"] for r in case["records"]}), len(case["records"]))
        self.assertTrue(all(source_text(r).startswith("[" + r["id"] + "] ") for r in case["records"]))
        self.assertEqual(set(CONDITIONS), set(SPEC["conditions"]))

    def test_assessor_separates_exact_answer_grounding_and_abstention(self):
        case = self.case()
        truth = case["truth"]
        raw = json.dumps({"value": truth["value"], "evidence": truth["support"]})
        full = "\n".join(source_text(r) for r in case["records"])
        self.assertTrue(assess_task_answer(raw, case, full)["recovered"])
        hidden = assess_task_answer(raw, case, "no records")
        self.assertTrue(hidden["answer_correct"])
        self.assertFalse(hidden["grounded_success"])
        without_proof = json.dumps({"value": truth["value"], "evidence": []})
        self.assertFalse(assess_task_answer(without_proof, case, full)["grounded_success"])
        abstained = assess_task_answer('{"value":null,"evidence":[]}', case, "no records")
        self.assertTrue(abstained["safe_abstention"])
        self.assertFalse(abstained["grounded_success"])
        self.assertFalse(abstained["recovered"])

    def test_assessor_missing_fact_success_is_not_recovered_memory(self):
        case = self.case(regime="insufficient")
        result = assess_task_answer('{"value":null,"evidence":[]}', case, "")
        self.assertTrue(result["grounded_success"])
        self.assertFalse(result["recovered"])
        self.assertTrue(result["safe_abstention"])

    def test_assessor_rejects_unknown_duplicate_sources_and_extra_prose(self):
        case = self.case()
        raw = json.dumps({"value": case["truth"]["value"], "evidence": [*case["truth"]["support"], "fake"]})
        full = "\n".join(source_text(r) for r in case["records"])
        self.assertFalse(assess_task_answer(raw, case, full)["grounded_success"])
        for raw in ('{"value":null,"evidence":["m001"]}',
                    '{"value":"guess","evidence":["m001","m001"]}',
                    '{"value":null,"evidence":[],"message":"guess"}',
                    '{"value":null,"value":"guess","evidence":[]}'):
            self.assertFalse(assess_task_answer(raw, case, full)["schema_ok"])

    def test_all_reference_answers_are_solvable_with_full_evidence(self):
        for seed in SPEC["pilot_seeds"] + SPEC["confirmation_seeds"]:
            for family in FAMILIES:
                for regime in REGIMES:
                    case = self.case(family, regime, seed)
                    full = "\n".join(source_text(r) for r in case["records"])
                    raw = json.dumps({"value": case["truth"]["value"], "evidence": case["truth"]["support"]})
                    self.assertTrue(assess_task_answer(raw, case, full)["grounded_success"])


if __name__ == "__main__":
    unittest.main()
