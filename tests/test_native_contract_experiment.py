from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from great_scratchpad.dialogue import canonical_json_sha256
from great_scratchpad.experiments import write_manifest
from great_scratchpad.native_contract_experiment import (
    ARMS, COMPLETED_V11, CONFIG, FLAG_LEXICON, FLAG_SCOPE, PARENT, SPEC, SPEC_V11, SPEC_V12,
    SPEC_V12S, SPEC_V13, SPEC_V13S, SPEC_V14S, SPEC_V15S, SPEC_V16S, SPEC_V17S, SPEC_V18S,
    SPEC_V19S, SPEC_V110S, SPEC_V111S, SPEC_V112S, SYSTEM, assess, audit,
    build_plan, load_parent, load_plan, outcome, main, prepare, request_params, run, summarize,
)
from great_scratchpad.structured_tasks import native_task_format
from great_scratchpad.uncertainty_contract import CALIBRATION_CASES, make_state_case

REPO = Path(__file__).resolve().parents[1]
CFG_PATH = str(REPO / "examples/gpt-6-luna.json")
SPEC_PATH = REPO / "scenarios/luna_native_contract_v1.json"
SPEC_V11_PATH = REPO / "scenarios/luna_native_contract_v11.json"
SPEC_V12_PATH = REPO / "scenarios/luna_native_contract_v12.json"
SPEC_V13_PATH = REPO / "scenarios/luna_native_contract_v13.json"
SPEC_V13S_PATH = REPO / "scenarios/luna_native_contract_v13s.json"
SPEC_V14S_PATH = REPO / "scenarios/luna_native_contract_v14s.json"
SPEC_V12S_PATH = REPO / "scenarios/luna_native_contract_v12s.json"
SPEC_V15S_PATH = REPO / "scenarios/luna_native_contract_v15s.json"
SPEC_V16S_PATH = REPO / "scenarios/luna_native_contract_v16s.json"
SPEC_V17S_PATH = REPO / "scenarios/luna_native_contract_v17s.json"
SPEC_V18S_PATH = REPO / "scenarios/luna_native_contract_v18s.json"


def parent_fixture():
    return {"cases": [make_state_case(26110240, scenario, "luna-fresh", 18) for scenario in CALIBRATION_CASES]}


class NativeCampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = build_plan(CONFIG, parent_fixture())
        cls.plan_v11 = build_plan(
            CONFIG, {"cases": parent_fixture()["cases"] + cls.plan["cases"]}, SPEC_V11)

    def fixture(self, out, spec=SPEC):
        if spec == SPEC:
            plan = deepcopy(self.plan)
        elif spec.get("standalone"):
            plan = build_plan(CONFIG, {"cases": []}, spec)
        elif spec in (SPEC_V12, SPEC_V13):
            history = parent_fixture()["cases"] + self.plan["cases"] + self.plan_v11["cases"]
            plan = build_plan(CONFIG, {"cases": history}, spec)
        else:
            plan = build_plan(
                CONFIG, {"cases": parent_fixture()["cases"] + self.plan["cases"]}, spec)
        digest = canonical_json_sha256(plan)
        write_manifest(out / "plan.json", {"plan_sha256": digest, "plan": plan})
        return plan, digest

    def provider(self, plan, transform=None):
        lookup = {c["request_sha256"]: c for c in plan["cells"]}

        def call(req, **kwargs):
            body = json.loads(req.data)
            if plan["spec"] != SPEC:
                self.assertIn("json", body["input"].lower())
            cell = lookup[canonical_json_sha256(body)]
            self.assertEqual(body, {**cell["request_params"], "input": cell["prompt"], "instructions": SYSTEM})
            self.assertEqual(canonical_json_sha256(body), cell["request_sha256"])
            expected = cell["expected"]
            raw = json.dumps({"status": expected["status"], "value": expected["value"],
                              "evidence": expected["support"], "flags": expected["flags"]})
            payload = {"id": "resp_fixture", "status": "completed", "model": CONFIG["model"],
                       "output": [{"type": "message", "content": [{"type": "output_text", "text": raw}]}],
                       "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}}
            if transform:
                payload = transform(cell, payload)
            return io.BytesIO(json.dumps(payload).encode())
        return call

    def execute(self, out, transform=None, spec=SPEC):
        plan, digest = self.fixture(out, spec)
        with patch("great_scratchpad.llm.api_key_from_config", return_value="fake-native-secret"), \
                patch("great_scratchpad.native_contract_experiment.api_key_from_config", return_value="fake-native-secret"), \
                patch("great_scratchpad.llm.urllib.request.urlopen", side_effect=self.provider(plan, transform)) as post:
            result = run(out, digest, CFG_PATH)
        return plan, digest, result, post.call_count

    def test_spec_profiles_budget_and_source_visibility_are_frozen(self):
        self.assertEqual(json.loads(SPEC_PATH.read_text()), SPEC)
        self.assertEqual(self.plan["parent"], PARENT)
        self.assertEqual(len(self.plan["cases"]), 10)
        self.assertEqual(self.plan["budget"]["max_calls"], 30)
        self.assertEqual(self.plan["budget"]["max_output_tokens"], 122880)
        self.assertEqual(self.plan["budget"]["retries"], 0)
        self.assertEqual(self.plan["spec"]["pilot_calls"], 0)
        self.assertEqual(len({c["seed"] for c in self.plan["cases"]} &
                             {c["seed"] for c in parent_fixture()["cases"]}), 0)
        for bad in ({"model": "another-model"}, {"temperature": 0}, {"max_output_tokens": 8192}, {"api_key": "inline"}):
            with self.assertRaises(ValueError):
                build_plan({**CONFIG, **bad}, parent_fixture())
        with self.assertRaises(ValueError):
            build_plan(CONFIG, self.plan)

    def test_every_pair_differs_only_in_the_native_format_and_order_alternates(self):
        for index in range(15):
            pair = self.plan["cells"][index * 2:index * 2 + 2]
            self.assertEqual([c["arm"] for c in pair], list(ARMS[::1 if index % 2 == 0 else -1]))
            a, b = pair
            for key in ("prompt", "system", "task", "expected", "visible_ids", "input_tokens_estimated"):
                self.assertEqual(a[key], b[key])
            self.assertEqual({k: v for k, v in a["request_params"].items() if k != "text"},
                             {k: v for k, v in b["request_params"].items() if k != "text"})
            self.assertEqual(set(a["task"]), {"family", "question", "records"})
            for r in a["task"]["records"]:
                self.assertEqual(set(r), {"id", "text"})
            self.assertIn("Output schema (structure only)", a["prompt"])
        self.assertEqual(sum(c["arm"] == "native" for c in self.plan["cells"][::2]), 8)

    def test_v11_adds_json_to_input_without_changing_the_contract_or_semantic_gate(self):
        self.assertEqual(json.loads(SPEC_V11_PATH.read_text()), SPEC_V11)
        plan = build_plan(CONFIG, {"cases": parent_fixture()["cases"] + self.plan["cases"]}, SPEC_V11)
        self.assertEqual(plan["spec"]["future_gate"], self.plan["spec"]["future_gate"])
        self.assertEqual(plan["spec"]["max_calls"], 30)
        self.assertEqual(len(plan["cases"]), 10)
        for field in ("seed", "id", "target"):
            self.assertFalse({c[field] for c in plan["cases"]} & {c[field] for c in self.plan["cases"]})
        for old, new in zip(self.plan["cells"], plan["cells"]):
            self.assertEqual(old["request_params"], new["request_params"])
            self.assertEqual(old["system"], new["system"])
            self.assertEqual(old["task"]["question"].split("\n", 1)[1].replace("Output schema", "Output JSON schema"),
                             new["task"]["question"].split("\n", 1)[1])
            self.assertIn("JSON", new["prompt"])
        self.assertEqual(plan["cells"][0]["prompt"], plan["cells"][1]["prompt"])

    def test_v11_uses_the_actual_native_helper_and_json_ready_control_once_each(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, digest, result, calls = self.execute(Path(tmp), spec=SPEC_V11)
            self.assertEqual(calls, 30)
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["method"], SPEC_V11["schema"])
            self.assertEqual(audit(plan, digest, Path(tmp)), result)
            self.assertEqual(summarize(plan, result)["method"], SPEC_V11["schema"])

    def test_v12_constrains_native_citations_to_the_same_ids_both_arms_see(self):
        self.assertEqual(json.loads(SPEC_V12_PATH.read_text()), SPEC_V12)
        self.assertTrue(SPEC_V12["citation_enum"])
        history = parent_fixture()["cases"] + self.plan["cases"] + self.plan_v11["cases"]
        plan = build_plan(CONFIG, {"cases": history}, SPEC_V12)
        self.assertEqual(plan["retained_completed"], COMPLETED_V11)
        for field in ("seed", "id", "target"):
            self.assertFalse({c[field] for c in plan["cases"]} & {c[field] for c in history})
        for native in (c for c in plan["cells"] if c["arm"] == "native"):
            schema = native["request_params"]["text"]["format"]
            self.assertTrue(schema["name"].endswith("_enum_v1"))
            evidence = schema["schema"]["properties"]["evidence"]
            if native["visible_ids"]:
                self.assertEqual(evidence["items"], {"type": "string", "enum": sorted(native["visible_ids"])})
                self.assertEqual(evidence["maxItems"], 8)
            else:
                self.assertEqual(evidence["maxItems"], 0)
                self.assertNotIn("enum", evidence["items"])
            partner = next(c for c in plan["cells"]
                           if c["id"].rsplit(":", 1)[0] == native["id"].rsplit(":", 1)[0] and c["arm"] == "json-mode")
            self.assertEqual(partner["prompt"], native["prompt"])
            self.assertEqual(partner["request_params"]["text"]["format"], {"type": "json_object"})
            embedded = json.loads(native["task"]["question"].split("(structure only):\n", 1)[1])
            self.assertEqual(embedded["properties"]["evidence"], evidence)

    def test_v12_uses_the_enum_native_helper_and_control_once_each(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, digest, result, calls = self.execute(Path(tmp), spec=SPEC_V12)
            self.assertEqual(calls, 30)
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["method"], SPEC_V12["schema"])
            self.assertEqual(audit(plan, digest, Path(tmp)), result)
            self.assertEqual(summarize(plan, result)["method"], SPEC_V12["schema"])

    def test_v13_states_the_semantic_contract_to_both_arms_without_enum(self):
        from great_scratchpad.task_contract import PROOF_INSTRUCTIONS
        self.assertEqual(json.loads(SPEC_V13_PATH.read_text()), SPEC_V13)
        self.assertTrue(SPEC_V13["semantic_contract"])
        self.assertNotIn("citation_enum", SPEC_V13)
        history = parent_fixture()["cases"] + self.plan["cases"] + self.plan_v11["cases"]
        plan = build_plan(CONFIG, {"cases": history}, SPEC_V13)
        self.assertEqual(plan["retained_completed"], COMPLETED_V11)
        for native in (c for c in plan["cells"] if c["arm"] == "native"):
            fmt = native["request_params"]["text"]["format"]
            self.assertTrue(fmt["name"].endswith("_v1"))
            self.assertFalse(fmt["name"].endswith("_enum_v1"))
            self.assertNotIn("enum", fmt["schema"]["properties"]["evidence"]["items"])
            partner = next(c for c in plan["cells"]
                           if c["id"].rsplit(":", 1)[0] == native["id"].rsplit(":", 1)[0] and c["arm"] == "json-mode")
            self.assertEqual(partner["prompt"], native["prompt"])
            head, contract = native["task"]["question"].split("\nSemantic contract:\n", 1)
            self.assertEqual(head, next(c for c in plan["cases"] if c["id"] == native["case_id"])["query"])
            self.assertTrue(contract.startswith(PROOF_INSTRUCTIONS.strip()))
            self.assertIn("\nOutput JSON schema (structure only):\n", contract)

    def test_v13_uses_the_contract_bearing_native_helper_and_control_once_each(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, digest, result, calls = self.execute(Path(tmp), spec=SPEC_V13)
            self.assertEqual(calls, 30)
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["method"], SPEC_V13["schema"])
            self.assertEqual(audit(plan, digest, Path(tmp)), result)
            self.assertEqual(summarize(plan, result)["method"], SPEC_V13["schema"])

    def test_v13s_roots_a_witness_free_lineage_with_the_same_contract_content(self):
        self.assertEqual(json.loads(SPEC_V13S_PATH.read_text()), SPEC_V13S)
        self.assertTrue(SPEC_V13S["standalone"])
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_parent(Path(tmp), SPEC_V13S), {"cases": []})
        plan = build_plan(CONFIG, {"cases": []}, SPEC_V13S)
        self.assertIsNone(plan["parent"])
        self.assertIsNone(plan["retained_failed"])
        self.assertIsNone(plan["retained_completed"])
        v13 = build_plan(
            CONFIG, {"cases": parent_fixture()["cases"] + self.plan["cases"] + self.plan_v11["cases"]},
            SPEC_V13)
        for field in ("seed", "id", "target"):
            self.assertFalse({c[field] for c in plan["cases"]} & {c[field] for c in v13["cases"]})
        for native, prior in zip(
                (c for c in plan["cells"] if c["arm"] == "native"),
                (c for c in v13["cells"] if c["arm"] == "native")):
            self.assertEqual(native["request_params"], prior["request_params"])
            self.assertIn("\nSemantic contract:\n", native["task"]["question"])

    def test_v13s_uses_the_contract_bearing_helper_without_any_run_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, digest, result, calls = self.execute(Path(tmp), spec=SPEC_V13S)
            self.assertEqual(calls, 30)
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["method"], SPEC_V13S["schema"])
            self.assertEqual(audit(plan, digest, Path(tmp)), result)
            self.assertEqual(summarize(plan, result)["method"], SPEC_V13S["schema"])

    def test_v14s_adds_only_the_flag_lexicon_to_both_arms(self):
        self.assertEqual(json.loads(SPEC_V14S_PATH.read_text()), SPEC_V14S)
        self.assertTrue(SPEC_V14S["standalone"])
        self.assertTrue(SPEC_V14S["flag_lexicon"])
        plan = build_plan(CONFIG, {"cases": []}, SPEC_V14S)
        self.assertIsNone(plan["parent"])
        v13s = build_plan(CONFIG, {"cases": []}, SPEC_V13S)
        for field in ("seed", "id", "target"):
            self.assertFalse({c[field] for c in plan["cases"]} & {c[field] for c in v13s["cases"]})
        for new, old in zip(plan["cells"], v13s["cells"]):
            self.assertEqual(new["request_params"], old["request_params"])
            self.assertEqual(new["system"], old["system"])
            head, rest = new["task"]["question"].split("\nSemantic contract:\n", 1)
            self.assertIn(FLAG_LEXICON.strip(), rest)
            self.assertIn("\nOutput JSON schema (structure only):\n", rest)
            self.assertIn(FLAG_LEXICON.strip(), new["prompt"])
            self.assertNotIn(FLAG_LEXICON.strip(), old["task"]["question"])

    def test_v14s_uses_the_lexicon_bearing_helper_without_any_run_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, digest, result, calls = self.execute(Path(tmp), spec=SPEC_V14S)
            self.assertEqual(calls, 30)
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["method"], SPEC_V14S["schema"])
            self.assertEqual(audit(plan, digest, Path(tmp)), result)
            self.assertEqual(summarize(plan, result)["method"], SPEC_V14S["schema"])

    def test_v15s_appends_the_flag_scope_line_to_both_arms(self):
        self.assertEqual(json.loads(SPEC_V15S_PATH.read_text()), SPEC_V15S)
        self.assertTrue(SPEC_V15S["flag_scope"])
        plan = build_plan(CONFIG, {"cases": []}, SPEC_V15S)
        self.assertIsNone(plan["parent"])
        for cell in plan["cells"]:
            self.assertIn(FLAG_SCOPE.strip(), cell["task"]["question"])
            self.assertIn(FLAG_LEXICON.strip(), cell["task"]["question"])
        v14s = build_plan(CONFIG, {"cases": []}, SPEC_V14S)
        for field in ("seed", "id", "target"):
            self.assertFalse({c[field] for c in plan["cases"]} & {c[field] for c in v14s["cases"]})

    def test_v15s_uses_the_scope_bearing_helper_without_any_run_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, digest, result, calls = self.execute(Path(tmp), spec=SPEC_V15S)
            self.assertEqual(calls, 30)
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["method"], SPEC_V15S["schema"])
            self.assertEqual(audit(plan, digest, Path(tmp)), result)
            self.assertEqual(summarize(plan, result)["method"], SPEC_V15S["schema"])

    def test_v12s_runs_the_enum_factor_standalone_without_contract_lines(self):
        self.assertEqual(json.loads(SPEC_V12S_PATH.read_text()), SPEC_V12S)
        self.assertTrue(SPEC_V12S["citation_enum"])
        self.assertNotIn("semantic_contract", SPEC_V12S)
        plan = build_plan(CONFIG, {"cases": []}, SPEC_V12S)
        self.assertIsNone(plan["parent"])
        for native in (c for c in plan["cells"] if c["arm"] == "native"):
            self.assertTrue(native["request_params"]["text"]["format"]["name"].endswith("_enum_v1"))
            self.assertNotIn("Semantic contract:", native["task"]["question"])
            self.assertNotIn("Flag lexicon:", native["task"]["question"])
            partner = next(c for c in plan["cells"]
                           if c["id"].rsplit(":", 1)[0] == native["id"].rsplit(":", 1)[0] and c["arm"] == "json-mode")
            self.assertEqual(partner["prompt"], native["prompt"])

    def test_v12s_uses_the_enum_helper_without_any_run_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, digest, result, calls = self.execute(Path(tmp), spec=SPEC_V12S)
            self.assertEqual(calls, 30)
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["method"], SPEC_V12S["schema"])
            self.assertEqual(audit(plan, digest, Path(tmp)), result)
            self.assertEqual(summarize(plan, result)["method"], SPEC_V12S["schema"])

    def test_v16s_supplies_distractor_records_and_keeps_the_same_expected_gate(self):
        self.assertEqual(json.loads(SPEC_V16S_PATH.read_text()), SPEC_V16S)
        plan = build_plan(CONFIG, {"cases": []}, SPEC_V16S)
        self.assertEqual(len(plan["cells"]), 50)
        self.assertEqual(plan["budget"]["max_calls"], 50)
        self.assertEqual(plan["budget"]["max_output_tokens"], 50 * 4096)
        distracted = [c for c in plan["cells"] if c["condition"] == "distracted" and c["arm"] == "native"]
        self.assertEqual(len(distracted), 10)
        for cell in distracted:
            self.assertGreater(len(cell["visible_ids"]), 3)
            case = next(c for c in plan["cases"] if c["id"] == cell["case_id"])
            relevant = [r["id"] for r in case["records"] if r["kind"] != "distractor"]
            self.assertTrue(set(relevant).issubset(cell["visible_ids"]))
            source = next(c for c in plan["cells"]
                          if c["case_id"] == cell["case_id"] and c["condition"] == "source")
            self.assertEqual(cell["expected"], source["expected"])
            self.assertIn(FLAG_SCOPE.strip(), cell["task"]["question"])
            for record in cell["task"]["records"]:
                self.assertEqual(set(record), {"id", "text"})

    def test_v16s_uses_the_distracted_helper_without_any_run_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, digest, result, calls = self.execute(Path(tmp), spec=SPEC_V16S)
            self.assertEqual(calls, 50)
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["method"], SPEC_V16S["schema"])
            self.assertEqual(audit(plan, digest, Path(tmp)), result)
            self.assertEqual(summarize(plan, result)["method"], SPEC_V16S["schema"])

    def test_v17s_replicates_v15s_semantics_under_a_fresh_seed(self):
        self.assertEqual(json.loads(SPEC_V17S_PATH.read_text()), SPEC_V17S)
        self.assertEqual({k: v for k, v in SPEC_V17S.items() if k not in ("schema", "fresh_seed")},
                         {k: v for k, v in SPEC_V15S.items() if k not in ("schema", "fresh_seed")})
        plan = build_plan(CONFIG, {"cases": []}, SPEC_V17S)
        self.assertIsNone(plan["parent"])
        self.assertEqual(len(plan["cells"]), 30)
        for cell in plan["cells"]:
            self.assertIn(FLAG_SCOPE.strip(), cell["task"]["question"])
            self.assertIn(FLAG_LEXICON.strip(), cell["task"]["question"])
        for field in ("seed", "id", "target"):
            self.assertFalse({c[field] for c in plan["cases"]}
                             & {c[field] for c in build_plan(CONFIG, {"cases": []}, SPEC_V15S)["cases"]})

    def test_v17s_uses_the_replication_helper_without_any_run_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, digest, result, calls = self.execute(Path(tmp), spec=SPEC_V17S)
            self.assertEqual(calls, 30)
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["method"], SPEC_V17S["schema"])
            self.assertEqual(audit(plan, digest, Path(tmp)), result)
            self.assertEqual(summarize(plan, result)["method"], SPEC_V17S["schema"])

    def test_v18s_triples_the_distractor_load_only_on_distracted_views(self):
        self.assertEqual(json.loads(SPEC_V18S_PATH.read_text()), SPEC_V18S)
        self.assertEqual(SPEC_V18S["distractor_count"], 54)
        plan = build_plan(CONFIG, {"cases": []}, SPEC_V18S)
        self.assertEqual(len(plan["cells"]), 50)
        distracted = [c for c in plan["cells"] if c["condition"] == "distracted" and c["arm"] == "native"]
        self.assertEqual(len(distracted), 10)
        for cell in distracted:
            case = next(c for c in plan["cases"] if c["id"] == cell["case_id"])
            relevant = [r["id"] for r in case["records"] if r["kind"] != "distractor"]
            self.assertEqual(len(cell["visible_ids"]), len(relevant) + 54)
            self.assertTrue(set(relevant).issubset(cell["visible_ids"]))
            source = next(c for c in plan["cells"]
                          if c["case_id"] == cell["case_id"] and c["condition"] == "source")
            self.assertEqual(len(source["visible_ids"]), len(relevant))
            self.assertEqual(cell["expected"], source["expected"])

    def test_v18s_uses_the_heavy_distractor_helper_without_any_run_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, digest, result, calls = self.execute(Path(tmp), spec=SPEC_V18S)
            self.assertEqual(calls, 50)
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["method"], SPEC_V18S["schema"])
            self.assertEqual(audit(plan, digest, Path(tmp)), result)
            report = summarize(plan, result)
            self.assertTrue(all(a["all_25_passed"] for a in report["arms"]))
            self.assertTrue(report["scope"].startswith("25 dependent views of 10"))
            prefix = {**result, "status": "stopped", "cells": result["cells"][:30]}
            self.assertFalse(any(a["all_25_passed"] for a in summarize(plan, prefix)["arms"]))

    def test_v19s_changes_only_decoy_keys_and_preserves_disconnected_chains(self):
        self.assertEqual(json.loads((REPO / "scenarios/luna_native_contract_v19s.json").read_text()), SPEC_V19S)
        plan = build_plan(CONFIG, {"cases": []}, SPEC_V19S)
        self.assertEqual(plan["budget"]["max_output_tokens"], 49152)
        self.assertLessEqual(plan["budget"]["input_utf8_bytes"], 200000)
        for scenario in SPEC_V19S["source_scenarios"]:
            far, near = sorted((c for c in plan["cases"] if c["scenario"] == scenario), key=lambda c: c["id"])
            self.assertEqual(far["truth"], near["truth"])
            self.assertEqual(far["target"], near["target"])
            for case, distance in ((far, 5), (near, 1)):
                records = case["records"]
                assigned = {r["target"]: r["team"] for r in records if r["kind"] == "assignment"}
                links = {r["team"]: r["line"] for r in records if r["kind"] == "team-line"}
                ends = {r["line"]: r.get("pool") for r in records if r["kind"] in ("line-pool", "pending")}
                self.assertEqual(len(assigned), 7)
                self.assertEqual(set(assigned.values()), set(links))
                self.assertEqual(set(links.values()), set(ends))
                self.assertEqual(len(set(ends.values())), 7)
                target = case["target"]
                true_keys = (target, assigned[target], links[assigned[target]])
                for ticket, team in assigned.items():
                    if ticket != target:
                        for key, real in zip((ticket, team, links[team]), true_keys):
                            self.assertEqual(len(key), len(real))
                            self.assertEqual(sum(x != y for x, y in zip(key, real)), distance)
            for a, b in zip(far["records"], near["records"]):
                self.assertEqual((a["id"], a["turn"], a["kind"], a.get("pool")),
                                 (b["id"], b["turn"], b["kind"], b.get("pool")))
                if a["id"] in far["truth"]["support"]:
                    self.assertEqual(a, b)
        for a, b in zip(plan["cells"][::2], plan["cells"][1::2]):
            self.assertEqual(a["prompt"], b["prompt"])
            self.assertEqual(a["expected"], b["expected"])
            self.assertEqual(len(a["visible_ids"]), 20 if a["condition"].endswith("missing") else 21)
            self.assertEqual(len(a["expected"]["support"]), 2 if a["condition"].endswith("missing") else 3)
            self.assertEqual(a["expected"]["status"], "known" if (
                a["scenario"] == "complete-join" and a["condition"].endswith("source")) else "unknown")

    def test_v19s_rejects_a_decoy_citation_even_when_the_value_is_correct(self):
        plan = build_plan(CONFIG, {"cases": []}, SPEC_V19S)
        cell = next(c for c in plan["cells"] if c["condition"] == "near-missing")
        case = next(c for c in plan["cases"] if c["id"] == cell["case_id"])
        decoy = next(r for r in case["records"] if r["kind"] == "line-pool" and r["id"] in cell["visible_ids"])
        for value in (None, decoy["pool"]):
            raw = json.dumps({"status": "unknown" if value is None else "known", "value": value,
                              "flags": {}, "evidence": [*cell["expected"]["support"], decoy["id"]]})
            receipt = {"unsafe_response": False, "llm": {"content": raw, "response_model": CONFIG["model"],
                       "adapter": "openai-responses", "response_status": "completed", "request_params": cell["request_params"]}}
            score = assess(plan, cell, receipt)
            self.assertTrue(score["caller_contract_ok"])
            self.assertEqual(score["value_correct"], value is None)
            self.assertFalse(score["citations_relevant"])
            self.assertFalse(score["contract_success"])

    def test_v110s_only_renames_the_decoy_line_keys_at_both_ends(self):
        self.assertEqual(json.loads((REPO / "scenarios/luna_native_contract_v110s.json").read_text()), SPEC_V110S)
        old = build_plan(CONFIG, {"cases": []}, SPEC_V19S)
        plan = build_plan(CONFIG, old, SPEC_V110S)
        self.assertEqual(len(plan["cells"]), 12)
        for scenario in SPEC_V110S["source_scenarios"]:
            far, near = sorted((c for c in plan["cases"] if c["scenario"] == scenario), key=lambda c: c["id"])
            self.assertEqual(far["truth"], near["truth"])
            facts = {r["kind"]: r for r in far["records"] if r["id"] in far["truth"]["support"]}
            true_team, true_line = facts["assignment"]["team"], facts["team-line"]["line"]
            links, ends = {}, {}
            for a, b in zip(far["records"], near["records"], strict=True):
                if a["id"] in far["truth"]["support"] or a["kind"] == "assignment":
                    self.assertEqual(a, b)
                    if a["kind"] == "assignment" and a["target"] != far["target"]:
                        for val, target in ((a["team"], true_team), (a["target"], far["target"])):
                            self.assertEqual(sum(x != y for x, y in zip(val, target, strict=True)), 5)
                    continue
                fa, ne = a["line"], b["line"]
                self.assertEqual(sum(x != y for x, y in zip(fa, true_line, strict=True)), 5)
                self.assertEqual(ne[:-1], true_line[:-1])
                self.assertNotEqual(ne[-1], true_line[-1])
                self.assertIn(fa, a["text"])
                self.assertEqual(b, {**a, "line": ne, "text": a["text"].replace(fa, ne)})
                (links if a["kind"] == "team-line" else ends)[fa] = ne
            self.assertEqual(links, ends)
            self.assertEqual(len(links), 6)
            self.assertEqual(len(set(links.values())), 6)
        for a, b in zip(plan["cells"][::2], plan["cells"][1::2], strict=True):
            self.assertEqual(a["prompt"], b["prompt"])
            partner = next(c for c in plan["cells"] if c["case_id"] != a["case_id"]
                           and (c["scenario"], c["arm"], c["condition"].split("-")[1]) ==
                           (a["scenario"], a["arm"], a["condition"].split("-")[1]))
            for field in ("system", "request_params", "expected", "visible_ids"):
                self.assertEqual(a[field], partner[field])
            self.assertEqual(a["task"]["question"], partner["task"]["question"])

    def test_v111s_removes_only_the_selected_edge_and_requires_reachable_evidence(self):
        spec_file = REPO / "scenarios/luna_native_contract_v111s.json"
        self.assertEqual(json.loads(spec_file.read_text()), SPEC_V111S)
        plan = build_plan(CONFIG, build_plan(CONFIG, {"cases": []}, SPEC_V110S), SPEC_V111S)
        for distance in ("near", "far"):
            for arm in ARMS:
                cells = {c["condition"].removeprefix(distance + "-"): c for c in plan["cells"]
                         if c["arm"] == arm and c["condition"].startswith(distance + "-")}
                full = cells["source"]
                assignment, link, endpoint = full["expected"]["support"]
                self.assertEqual(len(full["visible_ids"]), 21)
                for view, omitted, support in (("missing", endpoint, [assignment, link]),
                                                ("missing-link", link, [assignment])):
                    cell = cells[view]
                    self.assertEqual(cell["task"], {**full["task"], "records": [
                        r for r in full["task"]["records"] if r["id"] != omitted]})
                    self.assertEqual(cell["expected"], {"status": "unknown", "value": None, "flags": {},
                                                        "support": support, "eligible_ids": support})
                    self.assertEqual(cell["request_params"], full["request_params"])
                gap = cells["missing-link"]
                pool = full["expected"]["value"]
                self.assertTrue(any(r["id"] == endpoint and pool in r["text"] for r in gap["task"]["records"]))
                for value in (None, pool):
                    raw = json.dumps({"status": "unknown" if value is None else "known", "value": value,
                                      "flags": {}, "evidence": [assignment, endpoint]})
                    receipt = {"unsafe_response": False, "llm": {"content": raw, "response_model": CONFIG["model"],
                               "adapter": "openai-responses", "response_status": "completed",
                               "request_params": gap["request_params"]}}
                    score = assess(plan, gap, receipt)
                    self.assertTrue(score["caller_contract_ok"] and score["citations_visible"])
                    self.assertEqual(score["value_correct"], value is None)
                    self.assertFalse(score["citations_relevant"])
                    self.assertFalse(score["contract_success"])

    def test_join_contrasts_exercise_both_adapters_without_provider_spend(self):
        for spec in (SPEC_V19S, SPEC_V110S, SPEC_V111S):
            with self.subTest(spec=spec["schema"]), tempfile.TemporaryDirectory() as tmp:
                plan, digest, result, calls = self.execute(Path(tmp), spec=spec)
                self.assertEqual(calls, 12)
                self.assertEqual(audit(plan, digest, Path(tmp)), result)
                report = summarize(plan, result)
                self.assertTrue(all(a["all_6_passed"] for a in report["arms"]))
                self.assertTrue(report["scope"].startswith(f"6 dependent views of {len(spec['source_scenarios'])}"))

    def test_v112s_pairs_differ_only_by_the_visible_id_enum(self):
        spec = json.loads((REPO / "scenarios/luna_native_contract_v112s.json").read_text())
        self.assertEqual(spec, SPEC_V112S)
        plan = build_plan(CONFIG, build_plan(CONFIG, {"cases": []}, SPEC_V111S), spec)
        self.assertEqual(len(plan["cells"]), 12)
        for i, (a, b) in enumerate(zip(plan["cells"][::2], plan["cells"][1::2], strict=True)):
            self.assertEqual([a["arm"], b["arm"]], spec["arms"][::1 if i % 2 == 0 else -1])
            enum, plain = (a, b) if a["arm"] == "native-enum" else (b, a)
            for key in ("prompt", "system", "task", "visible_ids", "expected", "case_id", "condition"):
                self.assertEqual(enum[key], plain[key])
            params = deepcopy(enum["request_params"])
            fmt = params["text"]["format"]
            self.assertTrue(fmt["strict"])
            self.assertEqual(fmt["type"], "json_schema")
            ids = fmt["schema"]["properties"]["evidence"]["items"].pop("enum")
            self.assertEqual(ids, sorted(r["id"] for r in enum["task"]["records"]))
            self.assertTrue(set(enum["expected"]["support"]) < set(ids))
            self.assertEqual(params, plain["request_params"])

    def test_v112s_audits_prose_and_unlicensed_bare_ids_without_repair(self):
        def transform(cell, payload):
            msg = payload["output"][0]["content"][0]
            answer = json.loads(msg["text"])
            if cell["condition"] == "near-missing" and cell["arm"] == "native":
                answer["evidence"][0] += ": explanation"
            if cell["condition"] == "far-missing-link" and cell["arm"] == "native-enum":
                answer["evidence"].append(next(i for i in cell["visible_ids"] if i not in answer["evidence"]))
            msg["text"] = json.dumps(answer)
            return payload

        with tempfile.TemporaryDirectory() as tmp:
            plan, digest, result, calls = self.execute(Path(tmp), transform, spec=SPEC_V112S)
            self.assertEqual(calls, 12)
            report = summarize(plan, audit(plan, digest, Path(tmp)))
            self.assertEqual(report["paired_strict"]["outcomes"], {"both": 4, "control-only": 1, "treatment-only": 1})
            enum, plain = report["arms"]
            self.assertEqual((enum["arm"], plain["arm"]), ("native-enum", "native"))
            self.assertEqual((enum["caller_contract_ok"], plain["caller_contract_ok"]), (6, 5))
            self.assertEqual((enum["value_correct"], plain["value_correct"]), (6, 6))
            self.assertEqual((enum["contract_success"], plain["contract_success"]), (5, 5))

    def test_all_task_kinds_have_empty_controls_and_partial_views_keep_uncertainty_evidence(self):
        empty = [c for c in self.plan["cells"] if c["condition"] == "empty"]
        self.assertEqual(len(empty), 6)
        self.assertEqual({c["family"] for c in empty}, {"decision-update", "scoped-exception", "distributed-join"})
        for c in empty:
            self.assertEqual(c["expected"]["value"], None)
            self.assertEqual(c["visible_ids"], [])
        partial = [c for c in self.plan["cells"] if c["condition"].startswith("partial")]
        self.assertEqual(len(partial), 4)
        for c in partial:
            self.assertIsNone(c["expected"]["value"])
            self.assertEqual(len(c["expected"]["support"]), 2)
        native = next(c for c in empty if c["family"] == "scoped-exception" and c["arm"] == "native")
        self.assertEqual(native["request_params"]["text"]["format"], native_task_format("scoped-exception"))

    def test_actual_adapter_uses_the_frozen_request_and_issues_thirty_calls_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, digest, result, calls = self.execute(Path(tmp))
            self.assertEqual(calls, 30)
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["known_usage"]["total_tokens"], 450)
            self.assertEqual(result["unavailable_usage_calls"], 0)
            self.assertEqual(audit(plan, digest, Path(tmp)), result)
            report = summarize(plan, result)
            self.assertTrue(all(arm["all_15_passed"] for arm in report["arms"]))
            self.assertEqual([a["known_usage"]["total_tokens"] for a in report["arms"]], [225, 225])
            with patch("great_scratchpad.native_contract_experiment.api_key_from_config", return_value="fake-native-secret"), \
                    patch("great_scratchpad.llm.urllib.request.urlopen") as post:
                with self.assertRaises(FileExistsError):
                    run(Path(tmp), digest, CFG_PATH)
                post.assert_not_called()

    def test_local_native_validation_failure_retains_usage_without_repair(self):
        def malformed(cell, payload):
            if cell["id"] == self.plan["cells"][0]["id"]:
                payload["output"][0]["content"][0]["text"] = '{"status":"unknown","value":null,"evidence":[],"flags":{}}'
            return payload
        with tempfile.TemporaryDirectory() as tmp:
            plan, digest, result, calls = self.execute(Path(tmp), malformed)
            self.assertEqual(calls, 30)
            self.assertEqual(result["known_usage"]["total_tokens"], 450)
            self.assertFalse(result["cells"][0]["assessment"]["caller_contract_ok"])
            receipt = json.loads((Path(tmp) / "execution/responses.jsonl").read_text().splitlines()[0])
            self.assertIsNotNone(receipt["helper_validation_error"])
            self.assertEqual(receipt["llm"]["usage"]["total_tokens"], 15)
            self.assertEqual(audit(plan, digest, Path(tmp)), result)

    def test_attempt_and_manifest_are_durable_before_each_provider_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            plan, digest = self.fixture(out)
            provider = self.provider(plan)
            seen = []

            def check(req, **kwargs):
                manifest = json.loads((out / "execution/result.json").read_text())
                attempts = [json.loads(s) for s in (out / "execution/attempts.jsonl").read_text().splitlines()]
                self.assertEqual(manifest["attempted_calls"], len(seen) + 1)
                self.assertEqual(len(attempts), len(seen) + 1)
                self.assertEqual(attempts[-1]["id"], plan["cells"][len(seen)]["id"])
                seen.append(attempts[-1]["id"])
                return provider(req, **kwargs)

            with patch("great_scratchpad.llm.api_key_from_config", return_value="fake-native-secret"), \
                    patch("great_scratchpad.native_contract_experiment.api_key_from_config", return_value="fake-native-secret"), \
                    patch("great_scratchpad.llm.urllib.request.urlopen", side_effect=check):
                result = run(out, digest, CFG_PATH)
            self.assertEqual(len(seen), 30)
            self.assertEqual(audit(plan, digest, out), result)

    def test_valid_shape_and_all_partial_ids_do_not_license_a_known_route(self):
        cell = next(c for c in self.plan["cells"] if c["condition"] == "partial-rule" and c["arm"] == "native")
        case = next(c for c in self.plan["cases"] if c["id"] == cell["case_id"])
        policy = next(r for r in case["records"] if r["kind"] == "policy")
        answer = {"status": "known", "value": policy["fast"], "evidence": cell["visible_ids"], "flags": cell["expected"]["flags"]}
        receipt = {"unsafe_response": False, "llm": {"content": json.dumps(answer), "response_model": CONFIG["model"],
                   "adapter": "openai-responses", "response_status": "completed", "request_params": cell["request_params"]}}
        score = assess(self.plan, cell, receipt)
        self.assertTrue(score["caller_contract_ok"])
        self.assertTrue(score["proof_covered"])
        self.assertFalse(score["value_correct"])
        self.assertFalse(score["contract_success"])

    def test_refusal_and_incomplete_receipts_retain_reported_usage_but_never_pass(self):
        for failure in ("refusal", "incomplete"):
            def transform(cell, payload):
                if cell["id"] == self.plan["cells"][0]["id"]:
                    if failure == "refusal":
                        payload["output"][0]["content"] = [{"type": "refusal", "refusal": "fixture refusal"}]
                    else:
                        payload["status"] = "incomplete"
                return payload
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                plan, digest, result, calls = self.execute(Path(tmp), transform)
                self.assertEqual(calls, 30)
                self.assertEqual(result["known_usage"]["total_tokens"], 450)
                self.assertFalse(result["cells"][0]["assessment"]["provider_completed"])
                self.assertFalse(result["cells"][0]["assessment"]["contract_success"])
                self.assertEqual(audit(plan, digest, Path(tmp)), result)

    def test_no_usage_is_unknown_not_estimated_as_provider_spend(self):
        def missing(cell, payload):
            if cell["id"] == self.plan["cells"][0]["id"]:
                del payload["usage"]
            return payload
        with tempfile.TemporaryDirectory() as tmp:
            _, _, result, calls = self.execute(Path(tmp), missing)
            self.assertEqual(calls, 30)
            self.assertEqual(result["known_usage"]["total_tokens"], 435)
            self.assertEqual(result["unavailable_usage_calls"], 1)
            self.assertEqual(summarize(self.plan, result)["arms"][0]["unavailable_usage_calls"], 1)

    def test_schema_or_transport_rejection_stops_without_fallback(self):
        for error in (urllib.error.HTTPError("https://fixture", 400, "unsupported schema", {}, io.BytesIO(b'{"error":"schema"}')),
                      urllib.error.URLError("fixture offline")):
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as tmp:
                plan, digest = self.fixture(Path(tmp))
                with patch("great_scratchpad.llm.api_key_from_config", return_value="fake-native-secret"), \
                        patch("great_scratchpad.native_contract_experiment.api_key_from_config", return_value="fake-native-secret"), \
                        patch("great_scratchpad.llm.urllib.request.urlopen", side_effect=error) as post:
                    result = run(Path(tmp), digest, CFG_PATH)
                self.assertEqual(post.call_count, 1)
                self.assertEqual(result["status"], "stopped")
                self.assertEqual(result["unavailable_usage_calls"], 1)
                self.assertEqual(audit(plan, digest, Path(tmp)), result)
                self.assertFalse(any(a["all_15_passed"] for a in summarize(plan, result)["arms"]))

    def test_model_mismatch_or_credential_reflection_stops_and_retains_usage(self):
        for failure in ("identity", "secret"):
            def transform(cell, payload):
                if failure == "identity":
                    payload["model"] = "a-substitute-model"
                else:
                    payload["output"][0]["content"][0]["text"] = "fake-native-secret"
                return payload
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                plan, digest, result, calls = self.execute(Path(tmp), transform)
                self.assertEqual(calls, 1)
                self.assertEqual(result["status"], "stopped")
                self.assertEqual(result["known_usage"]["total_tokens"], 15)
                self.assertEqual(result["unavailable_usage_calls"], 0)
                self.assertEqual(audit(plan, digest, Path(tmp)), result)
                for path in (Path(tmp) / "execution").glob("*"):
                    self.assertNotIn("fake-native-secret", path.read_text())

    def test_plan_runtime_and_receipt_tampering_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            plan, digest, result, _ = self.execute(out)
            with self.assertRaises(ValueError):
                load_plan(out, "wrong-digest", CFG_PATH)
            with patch("great_scratchpad.native_contract_experiment.runtime_hashes", return_value={}):
                with self.assertRaises(ValueError):
                    load_plan(out, digest, CFG_PATH)
            self.assertEqual(audit(plan, digest, out), result)
            receipt_path = out / "execution/responses.jsonl"
            receipt_path.write_text(receipt_path.read_text().replace('"total_tokens": 15', '"total_tokens": 16', 1))
            with self.assertRaises(ValueError):
                audit(plan, digest, out)

    def test_prepare_checks_all_bounds_and_never_overwrites_a_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            with patch("great_scratchpad.native_contract_experiment.load_parent", return_value=parent_fixture()), \
                    patch("great_scratchpad.native_contract_experiment.source_revision", return_value="committed-fixture"):
                for limits in ((29, 122880, 300000), (30, 122879, 300000), (30, 122880, 1)):
                    with self.assertRaises(ValueError):
                        prepare(out, Path(tmp), SPEC_V12_PATH, CFG_PATH, *limits)
                    self.assertFalse(out.exists())
                envelope = prepare(out, Path(tmp), SPEC_V12_PATH, CFG_PATH, 30, 122880, 300000)
                self.assertEqual(load_plan(out, envelope["plan_sha256"], CFG_PATH), envelope["plan"])
                with self.assertRaises(FileExistsError):
                    prepare(out, Path(tmp), SPEC_V12_PATH, CFG_PATH, 30, 122880, 300000)

    def test_retained_v1_and_v11_campaigns_cannot_be_prepared_as_new_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "not-issued"
            with self.assertRaisesRegex(ValueError, "retained stopped"):
                prepare(out, Path(tmp), SPEC_PATH, CFG_PATH, 30, 122880, 300000)
            self.assertFalse(out.exists())
            with self.assertRaisesRegex(ValueError, "retained completed"):
                prepare(out, Path(tmp), SPEC_V11_PATH, CFG_PATH, 30, 122880, 300000)
            self.assertFalse(out.exists())

    def test_audit_rejects_lost_usage_and_omitted_slots(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            plan, digest, result, _ = self.execute(out)
            for kind in ("usage", "slot"):
                changed = deepcopy(result)
                if kind == "usage":
                    changed["known_usage"]["total_tokens"] -= 15
                else:
                    changed["cells"].pop()
                write_manifest(out / "execution/result.json", changed)
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    audit(plan, digest, out)

    def test_historical_byte_witness_is_checked_without_rescoring(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "parent"
            plan = parent_fixture()
            digest = canonical_json_sha256(plan)
            write_manifest(directory / "plan.json", {"plan_sha256": digest, "plan": plan})
            from great_scratchpad.luna_uncertainty import sha
            witness = {"directory": "parent", "plan_sha256": digest, "files": {"plan.json": sha(directory / "plan.json")}}
            with patch("great_scratchpad.native_contract_experiment.PARENT", witness):
                self.assertEqual(load_parent(Path(tmp)), plan)
                (directory / "plan.json").write_text("{}")
                with self.assertRaises(ValueError):
                    load_parent(Path(tmp))

    def test_arm_params_are_explicit_and_no_model_alias_is_substituted(self):
        self.assertEqual(request_params("scoped-exception", "native")["model"], "gpt-6-luna")
        self.assertEqual(request_params("distributed-join", "json-mode")["text"]["format"], {"type": "json_object"})
        with self.assertRaises(ValueError):
            request_params("scoped-exception", "auto")
        self.assertEqual(outcome({"request_params": {}}, {"unsafe_response": True, "llm": None}), "unsafe-response")

    def test_v11_checks_both_historical_witnesses_before_using_fresh_cases(self):
        from great_scratchpad.luna_uncertainty import sha
        with tempfile.TemporaryDirectory() as tmp:
            witnesses = []
            for name, plan in (("parent", parent_fixture()), ("stopped", self.plan)):
                path = Path(tmp) / name / "plan.json"
                digest = canonical_json_sha256(plan)
                write_manifest(path, {"plan_sha256": digest, "plan": plan})
                witnesses.append({"directory": name, "plan_sha256": digest, "files": {"plan.json": sha(path)}})
            with patch("great_scratchpad.native_contract_experiment.PARENT", witnesses[0]), \
                    patch("great_scratchpad.native_contract_experiment.STOPPED_V1", witnesses[1]):
                combined = load_parent(Path(tmp), SPEC_V11)
                self.assertEqual(len(combined["cases"]), 20)
                (Path(tmp) / "stopped/plan.json").write_text("{}")
                with self.assertRaises(ValueError):
                    load_parent(Path(tmp), SPEC_V11)

    def test_v12_checks_all_three_historical_witnesses_before_using_fresh_cases(self):
        from great_scratchpad.luna_uncertainty import sha
        with tempfile.TemporaryDirectory() as tmp:
            witnesses = []
            for name, plan in (("parent", parent_fixture()), ("stopped", self.plan), ("completed", self.plan_v11)):
                path = Path(tmp) / name / "plan.json"
                digest = canonical_json_sha256(plan)
                write_manifest(path, {"plan_sha256": digest, "plan": plan})
                witnesses.append({"directory": name, "plan_sha256": digest, "files": {"plan.json": sha(path)}})
            with patch("great_scratchpad.native_contract_experiment.PARENT", witnesses[0]), \
                    patch("great_scratchpad.native_contract_experiment.STOPPED_V1", witnesses[1]), \
                    patch("great_scratchpad.native_contract_experiment.COMPLETED_V11", witnesses[2]):
                combined = load_parent(Path(tmp), SPEC_V12)
                self.assertEqual(len(combined["cases"]), 30)
                (Path(tmp) / "completed/plan.json").write_text("{}")
                with self.assertRaises(ValueError):
                    load_parent(Path(tmp), SPEC_V12)

    def test_stopped_run_cli_does_not_report_process_success(self):
        with patch("sys.argv", ["native_contract_experiment", "run", "--out-dir", "unused", "--plan-sha256", "fixture"]), \
                patch("great_scratchpad.native_contract_experiment.run", return_value={"status": "stopped"}):
            with self.assertRaises(SystemExit) as caught:
                main()
        self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
