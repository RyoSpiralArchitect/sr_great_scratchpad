from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from great_scratchpad.chat import run_chat_turn
from great_scratchpad.dialogue import canonical_json_sha256
from great_scratchpad.experiments import trace_summary, write_manifest
from great_scratchpad.llm import LLMResponseError, draft_annotation
from great_scratchpad.luna_uncertainty import CONFIG, audit, build_plan, run
from great_scratchpad.storage import ensure_thread_dirs
from tests.test_luna_uncertainty import CFG_PATH, answer_for, mock_histories


def payload(state="completed", text=None, refusal=False):
    content = [{"type": "refusal", "refusal": "Cannot provide this response."}] if refusal else (
        [{"type": "output_text", "text": text}] if text is not None else [])
    return {"id": "resp_received", "model": "gpt-6-luna", "status": state,
            "output": [{"type": "message", "content": content}],
            "incomplete_details": {"reason": "max_output_tokens"} if state == "incomplete" else None,
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}}


def wire(value):
    return io.BytesIO(json.dumps(value).encode())


class ProviderFailureIntegrationTests(unittest.TestCase):
    def test_chat_stops_received_failures_without_repairing_or_accepting_partial_json(self):
        final = json.dumps({"type": "final", "message": "must not be accepted"})
        failures = [payload(s, text=t) for s in ("failed", "cancelled", "incomplete") for t in (None, final)]
        failures += [payload(refusal=True), payload()]
        for response in failures:
            with self.subTest(state=response["status"], output=response["output"]), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                tdir = ensure_thread_dirs(root, "t")
                trace = []
                with patch("great_scratchpad.llm.api_key_from_config", return_value="test-secret"), \
                        patch("great_scratchpad.llm.urllib.request.urlopen", side_effect=[wire(response), wire(payload(text=final))]) as post:
                    with self.assertRaises(LLMResponseError) as caught:
                        run_chat_turn(root, tdir, "t", CONFIG, "question", [], verbose=False,
                                      json_repair_steps=2, trace_events=trace)
                self.assertEqual(post.call_count, 1)
                self.assertEqual(caught.exception.result["usage"]["total_tokens"], 15)
                self.assertEqual(caught.exception.result["response_id"], "resp_received")
                self.assertFalse(any(e["event"] == "json_parse_error" for e in trace))
                error = next(e for e in trace if e["event"] == "error")
                self.assertEqual(error["model_calls"], 1)
                self.assertEqual(error["output_tokens_used"], 5)
                self.assertEqual(error["llm"]["usage"]["total_tokens"], 15)
                self.assertEqual(error["llm"]["response_status"], response["status"])
                self.assertEqual(trace_summary(trace)["usage"]["total_tokens"], 15)

    def test_completed_malformed_json_keeps_the_existing_protocol_repair_control(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tdir = ensure_thread_dirs(root, "t")
            final = json.dumps({"type": "final", "message": "repaired"})
            with patch("great_scratchpad.llm.api_key_from_config", return_value="test-secret"), \
                    patch("great_scratchpad.llm.urllib.request.urlopen", side_effect=[wire(payload(text="{bad")), wire(payload(text=final))]) as post:
                answer = run_chat_turn(root, tdir, "t", CONFIG, "question", [], verbose=False, json_repair_steps=1)
            self.assertEqual(answer, "repaired")
            self.assertEqual(post.call_count, 2)

    def test_annotation_stops_after_one_received_failure(self):
        for response in (payload("failed"), payload("cancelled"), payload("incomplete"), payload(refusal=True)):
            with self.subTest(state=response["status"]):
                with patch("great_scratchpad.llm.api_key_from_config", return_value="test-secret"), \
                        patch("great_scratchpad.llm.urllib.request.urlopen", return_value=wire(response)) as post:
                    with self.assertRaises(LLMResponseError):
                        draft_annotation("raw text", CONFIG, json_repair_steps=2)
                self.assertEqual(post.call_count, 1)


class CampaignReceivedFailureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = build_plan(CONFIG, mock_histories())

    def test_adapter_to_runner_retains_all_reported_usage_and_failed_outcomes(self):
        failures = ((payload(refusal=True), "refusal"), (payload(), "missing-text"),
                    (payload("incomplete"), "output-limit"), (payload("failed"), "provider-incomplete"))
        for failed, expected_status in failures:
            with self.subTest(status=expected_status), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp)
                plan = deepcopy(self.plan)
                digest = canonical_json_sha256(plan)
                write_manifest(out / "plan.json", {"plan_sha256": digest, "plan": plan})
                cells = {(c["prompt"], c["system"]): c for c in plan["cells"]}
                calls = 0

                def respond(request, **_kwargs):
                    nonlocal calls
                    calls += 1
                    if calls == 1:
                        return wire(failed)
                    body = json.loads(request.data)
                    c = cells[(body["input"], body["instructions"])]
                    case = next(case for case in plan["cases"] if case["id"] == c["case_id"])
                    return wire(payload(text=json.dumps(answer_for(case, c["visible_ids"]))))

                with patch("great_scratchpad.llm.api_key_from_config", return_value="test-secret"), \
                        patch("great_scratchpad.luna_uncertainty.api_key_from_config", return_value="test-secret"), \
                        patch("great_scratchpad.llm.urllib.request.urlopen", side_effect=respond):
                    result = run(out, digest, CFG_PATH)
                self.assertEqual(calls, 84)
                self.assertEqual(result["known_usage"]["total_tokens"], 1260)
                self.assertEqual(result["unavailable_usage_calls"], 0)
                self.assertEqual(result["cells"][0]["status"], expected_status)
                self.assertFalse(result["cells"][0]["assessment"]["contract_success"])
                received = json.loads((out / "execution/responses.jsonl").read_text().splitlines()[0])
                self.assertIsNone(received["client_error"])
                self.assertEqual(received["response_id"], "resp_received")
                self.assertEqual(received["response_status"], failed["status"])
                self.assertEqual(received["llm"]["usage"]["total_tokens"], 15)
                self.assertEqual(audit(plan, digest, out), result)


if __name__ == "__main__":
    unittest.main()
