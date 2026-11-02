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
    ARMS, CONFIG, PARENT, SPEC, SPEC_V11, SYSTEM, assess, audit, build_plan, load_parent, load_plan, outcome,
    main, prepare, request_params, run, summarize,
)
from great_scratchpad.structured_tasks import native_task_format
from great_scratchpad.uncertainty_contract import CALIBRATION_CASES, make_state_case

REPO = Path(__file__).resolve().parents[1]
CFG_PATH = str(REPO / "examples/gpt-6-luna.json")
SPEC_PATH = REPO / "scenarios/luna_native_contract_v1.json"
SPEC_V11_PATH = REPO / "scenarios/luna_native_contract_v11.json"


def parent_fixture():
    return {"cases": [make_state_case(26110240, scenario, "luna-fresh", 18) for scenario in CALIBRATION_CASES]}


class NativeCampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = build_plan(CONFIG, parent_fixture())

    def fixture(self, out, spec=SPEC):
        plan = deepcopy(self.plan) if spec == SPEC else build_plan(
            CONFIG, {"cases": parent_fixture()["cases"] + self.plan["cases"]}, spec)
        digest = canonical_json_sha256(plan)
        write_manifest(out / "plan.json", {"plan_sha256": digest, "plan": plan})
        return plan, digest

    def provider(self, plan, transform=None):
        lookup = {(c["prompt"], c["request_params"]["text"]["format"]["type"]): c for c in plan["cells"]}

        def call(req, **kwargs):
            body = json.loads(req.data)
            if plan["spec"] == SPEC_V11:
                self.assertIn("json", body["input"].lower())
            cell = lookup[(body["input"], body["text"]["format"]["type"])]
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
                        prepare(out, Path(tmp), SPEC_V11_PATH, CFG_PATH, *limits)
                    self.assertFalse(out.exists())
                envelope = prepare(out, Path(tmp), SPEC_V11_PATH, CFG_PATH, 30, 122880, 300000)
                self.assertEqual(load_plan(out, envelope["plan_sha256"], CFG_PATH), envelope["plan"])
                with self.assertRaises(FileExistsError):
                    prepare(out, Path(tmp), SPEC_V11_PATH, CFG_PATH, 30, 122880, 300000)

    def test_stopped_v1_cannot_be_prepared_as_a_new_current_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "not-issued"
            with self.assertRaisesRegex(ValueError, "retained stopped"):
                prepare(out, Path(tmp), SPEC_PATH, CFG_PATH, 30, 122880, 300000)
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

    def test_stopped_run_cli_does_not_report_process_success(self):
        with patch("sys.argv", ["native_contract_experiment", "run", "--out-dir", "unused", "--plan-sha256", "fixture"]), \
                patch("great_scratchpad.native_contract_experiment.run", return_value={"status": "stopped"}):
            with self.assertRaises(SystemExit) as caught:
                main()
        self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
