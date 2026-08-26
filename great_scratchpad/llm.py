from __future__ import annotations

import json
import math
import os
import random
import re
import shlex
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

from .constants import ANNOTATION_FIELDS, ANNOTATION_PROMPT_TEMPLATE

OPENAI_CHAT_ADAPTER = "openai-chat-completions"
OPENAI_RESPONSES_ADAPTER = "openai-responses"
COMMAND_ADAPTER = "command"
HUGGINGFACE_ADAPTER = "huggingface"


def build_annotation_prompt(raw: str) -> str:
    return ANNOTATION_PROMPT_TEMPLATE.format(raw=raw.strip())

def clip_text(text: str, max_chars: int = 4000) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n...[truncated]"

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

def estimate_token_count(text: str) -> int:
    text = text or ""
    if not text.strip():
        return 0
    cjk_chars = len(re.findall(r"[\u3040-\u30ff\u3400-\u9fff]", text))
    latin_words = len(re.findall(r"[A-Za-z0-9_]+(?:[-'][A-Za-z0-9_]+)?", text))
    other_nonspace = len(re.findall(r"[^\sA-Za-z0-9_\u3040-\u30ff\u3400-\u9fff]", text))
    # A deliberately conservative, dependency-free estimate. It is not a
    # tokenizer replacement, but it keeps local-command traces comparable.
    rough_chars = math.ceil(len(text) / 4)
    rough_pieces = cjk_chars + latin_words + math.ceil(other_nonspace / 2)
    return max(1, max(rough_chars, rough_pieces))

def estimated_usage(prompt: str, completion: str) -> dict:
    prompt_tokens = estimate_token_count(prompt)
    completion_tokens = estimate_token_count(completion)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "estimated": True,
        "estimator": "great_scratchpad_chars_words_v1",
    }

def expand_command_part(part: str, values: dict[str, str]) -> str:
    out = part
    for key, value in values.items():
        out = out.replace("{" + key + "}", value)
    return out

def normalize_adapter_name(name: str) -> str:
    adapter = name.strip().lower().replace("_", "-")
    aliases = {
        "chat": OPENAI_CHAT_ADAPTER,
        "chat-completions": OPENAI_CHAT_ADAPTER,
        "openai-compatible": OPENAI_CHAT_ADAPTER,
        "provider": OPENAI_CHAT_ADAPTER,
        "responses": OPENAI_RESPONSES_ADAPTER,
        "openai": OPENAI_RESPONSES_ADAPTER,
        "local": COMMAND_ADAPTER,
        "local-command": COMMAND_ADAPTER,
        "hf": HUGGINGFACE_ADAPTER,
        "transformers": HUGGINGFACE_ADAPTER,
    }
    return aliases.get(adapter, adapter)

def model_prefers_responses_api(model: str) -> bool:
    normalized = model.strip().lower()
    return bool(re.match(r"^gpt-5(?:\.\d+)?(?:-|$)", normalized))

def resolve_llm_adapter(cfg: dict, strict: bool = True) -> str:
    explicit = str(cfg.get("adapter", "") or cfg.get("api", "")).strip().lower()
    backend = str(cfg.get("backend", "")).strip().lower().replace("_", "-")
    model = str(cfg.get("model", "") or cfg.get("request_model", ""))

    if explicit and explicit != "auto":
        adapter = normalize_adapter_name(explicit)
    elif backend in {"command", "local", "local-command"}:
        adapter = COMMAND_ADAPTER
    elif backend in {"huggingface", "hf", "transformers"}:
        adapter = HUGGINGFACE_ADAPTER
    elif backend in {"openai-responses", "responses"}:
        adapter = OPENAI_RESPONSES_ADAPTER
    elif backend in {"openai", "openai-api"}:
        adapter = OPENAI_RESPONSES_ADAPTER if model_prefers_responses_api(model) else OPENAI_CHAT_ADAPTER
    elif backend in {"openai-compatible", "provider"}:
        adapter = OPENAI_RESPONSES_ADAPTER if explicit == "auto" and model_prefers_responses_api(model) else OPENAI_CHAT_ADAPTER
    elif explicit == "auto" and model_prefers_responses_api(model):
        adapter = OPENAI_RESPONSES_ADAPTER
    else:
        adapter = normalize_adapter_name(backend)

    known = {
        OPENAI_CHAT_ADAPTER,
        OPENAI_RESPONSES_ADAPTER,
        COMMAND_ADAPTER,
        HUGGINGFACE_ADAPTER,
    }
    if strict and adapter not in known:
        raise SystemExit(f"Unknown LLM backend/adapter: backend={cfg.get('backend')!r} adapter={cfg.get('adapter')!r}")
    return adapter

def llm_config_metadata(cfg: dict) -> dict:
    return {
        "backend": str(cfg.get("backend", "")),
        "adapter": resolve_llm_adapter(cfg, strict=False),
        "profile": str(cfg.get("profile", "")),
        "model": str(cfg.get("model", "")),
        "model_path": str(cfg.get("model_path", "")),
    }

def api_key_from_config(cfg: dict) -> str:
    api_key_env = cfg.get("api_key_env", "")
    api_key = os.environ.get(api_key_env, "") if api_key_env else cfg.get("api_key", "")
    if api_key_env and not api_key:
        raise SystemExit(f"Environment variable is not set: {api_key_env}")
    return str(api_key or "")

def endpoint_url(cfg: dict, suffix: str, default_base_url: str = "") -> str:
    url = str(cfg.get("base_url") or cfg.get("url") or default_base_url).strip()
    if not url:
        raise SystemExit(f"{cfg.get('backend', 'LLM')} config requires base_url.")
    suffix = "/" + suffix.strip("/")
    base = url.rstrip("/")
    for known_suffix in ("/chat/completions", "/responses"):
        if base.endswith(known_suffix):
            base = base[: -len(known_suffix)]
            break
    if base.endswith(suffix):
        return base
    return base + suffix

def json_mode_enabled(value: object) -> bool:
    return value is True or str(value).strip().lower() in {"json", "json_object", "true", "1"}

def optional_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    raise SystemExit(f"Expected boolean config value, got {value!r}")

def apply_sampling_params(body: dict, cfg: dict, *, max_token_field: str) -> None:
    fallback_field = "max_output_tokens" if max_token_field == "max_tokens" else "max_tokens"
    max_tokens = cfg.get(max_token_field, cfg.get(fallback_field))
    if max_tokens not in {None, ""}:
        body[max_token_field] = int(max_tokens)
    if cfg.get("temperature") not in {None, ""}:
        body["temperature"] = float(cfg.get("temperature"))
    if cfg.get("top_p") not in {None, ""}:
        body["top_p"] = float(cfg.get("top_p"))
    if cfg.get("seed") not in {None, ""}:
        body["seed"] = int(cfg.get("seed"))
    stop = cfg.get("stop")
    if isinstance(stop, list) and stop:
        body["stop"] = [str(item) for item in stop]
    elif isinstance(stop, str) and stop:
        body["stop"] = stop

def chat_response_format(cfg: dict) -> dict | None:
    response_format = cfg.get("response_format")
    if isinstance(response_format, dict):
        return response_format
    if json_mode_enabled(cfg.get("json_mode", "")):
        return {"type": "json_object"}
    return None

def responses_text_format(cfg: dict) -> dict | None:
    response_format = cfg.get("response_format")
    if isinstance(response_format, dict):
        if response_format.get("type") == "json_schema" and isinstance(response_format.get("json_schema"), dict):
            schema = response_format["json_schema"]
            return {
                "type": "json_schema",
                "name": schema.get("name", "response"),
                "schema": schema.get("schema", {}),
                "strict": bool(schema.get("strict", True)),
            }
        return response_format
    if json_mode_enabled(cfg.get("json_mode", "")):
        return {"type": "json_object"}
    return None

def responses_reasoning(cfg: dict) -> dict | None:
    reasoning = cfg.get("reasoning")
    out = dict(reasoning) if isinstance(reasoning, dict) else {}
    for cfg_key, api_key in (
        ("reasoning_effort", "effort"),
        ("reasoning_mode", "mode"),
        ("reasoning_context", "context"),
    ):
        value = cfg.get(cfg_key)
        if value not in {None, ""}:
            out[api_key] = value
    return out or None

def extract_responses_text(data: dict) -> str:
    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    chunks: list[str] = []
    output = data.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if isinstance(content, str):
                chunks.append(content)
                continue
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                text = part.get("text")
                if isinstance(text, str) and part.get("type") in {None, "text", "output_text", "summary_text"}:
                    chunks.append(text)
    text = "\n".join(chunk for chunk in chunks if chunk.strip()).strip()
    if text:
        return text
    raise SystemExit(f"Responses API response did not contain output text: {data}")

def normalize_responses_usage(usage: dict, prompt: str, completion: str) -> dict:
    if not isinstance(usage, dict) or not usage:
        return estimated_usage(prompt, completion)
    out = dict(usage)
    if "prompt_tokens" not in out and "input_tokens" in out:
        out["prompt_tokens"] = out.get("input_tokens", 0)
    if "completion_tokens" not in out and "output_tokens" in out:
        out["completion_tokens"] = out.get("output_tokens", 0)
    if "total_tokens" not in out:
        try:
            out["total_tokens"] = int(out.get("prompt_tokens", 0)) + int(out.get("completion_tokens", 0))
        except (TypeError, ValueError):
            out["total_tokens"] = 0
    return out

def call_openai_compatible_result(cfg: dict, prompt: str, system_prompt: str = "") -> dict:
    api_key = api_key_from_config(cfg)
    url = endpoint_url(cfg, "chat/completions")

    body = {
        "model": cfg.get("model", ""),
        "messages": [
            {
                "role": "system",
                "content": system_prompt or cfg.get("system_prompt", "Return the requested response."),
            },
            {"role": "user", "content": prompt},
        ],
    }
    apply_sampling_params(body, cfg, max_token_field="max_tokens")
    body.setdefault("temperature", float(cfg.get("temperature", 0.2)))
    body.setdefault("max_tokens", int(cfg.get("max_tokens", 900)))
    response_format = chat_response_format(cfg)
    if response_format:
        body["response_format"] = response_format
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
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise SystemExit(f"Provider API response did not look OpenAI-compatible: {data}") from exc

    usage = data.get("usage", {})
    if not usage:
        usage = estimated_usage(compose_text_prompt(system_prompt, prompt), str(content))

    return {
        "content": content,
        "usage": usage,
        "response_model": data.get("model", ""),
        "request_model": body["model"],
        "url": url,
        "adapter": OPENAI_CHAT_ADAPTER,
    }

def call_openai_compatible(cfg: dict, prompt: str, system_prompt: str = "") -> str:
    return str(call_openai_compatible_result(cfg, prompt, system_prompt).get("content", ""))

def call_openai_responses_result(cfg: dict, prompt: str, system_prompt: str = "") -> dict:
    api_key = api_key_from_config(cfg)
    url = endpoint_url(cfg, "responses", default_base_url="https://api.openai.com/v1")

    body = {
        "model": cfg.get("model", ""),
        "input": prompt,
        "instructions": system_prompt or cfg.get("system_prompt", "Return the requested response."),
    }
    apply_sampling_params(body, cfg, max_token_field="max_output_tokens")
    body.setdefault("max_output_tokens", int(cfg.get("max_output_tokens", cfg.get("max_tokens", 900))))
    text_format = responses_text_format(cfg)
    if text_format:
        body["text"] = {"format": text_format}
    reasoning = responses_reasoning(cfg)
    if reasoning:
        body["reasoning"] = reasoning
    if cfg.get("store") not in {None, ""}:
        body["store"] = optional_bool(cfg.get("store"))
    if cfg.get("previous_response_id") not in {None, ""}:
        body["previous_response_id"] = str(cfg.get("previous_response_id"))
    if cfg.get("safety_identifier") not in {None, ""}:
        body["safety_identifier"] = str(cfg.get("safety_identifier"))
    if not body["model"]:
        raise SystemExit("OpenAI Responses LLM config requires model.")

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
        raise SystemExit(f"Responses API returned HTTP {exc.code}: {body_text}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Responses API request failed: {exc}") from exc

    content = extract_responses_text(data)
    usage = normalize_responses_usage(
        data.get("usage", {}),
        compose_text_prompt(system_prompt, prompt),
        str(content),
    )
    return {
        "content": content,
        "usage": usage,
        "response_model": data.get("model", ""),
        "request_model": body["model"],
        "response_id": data.get("id", ""),
        "url": url,
        "adapter": OPENAI_RESPONSES_ADAPTER,
    }

def call_command_llm_result(cfg: dict, prompt: str, system_prompt: str = "") -> dict:
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
        parts = [expand_command_part(part, values) for part in raw_parts]
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

    content = proc.stdout.strip()
    return {
        "content": content,
        "usage": estimated_usage(prompt, content),
        "response_model": "",
        "request_model": str(cfg.get("model_path", "")),
        "command": parts,
        "adapter": COMMAND_ADAPTER,
    }

def call_command_llm(cfg: dict, prompt: str, system_prompt: str = "") -> str:
    return str(call_command_llm_result(cfg, prompt, system_prompt).get("content", ""))

def call_huggingface_result(cfg: dict, prompt: str, system_prompt: str = "") -> dict:
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:
        raise SystemExit(
            "Hugging Face backend requires optional dependencies: transformers and torch."
        ) from exc

    model_ref = str(cfg.get("model_path") or cfg.get("model") or "").strip()
    if not model_ref:
        raise SystemExit("huggingface LLM config requires model or model_path.")

    seed = cfg.get("seed")
    if seed not in {None, ""}:
        seed_value = int(seed)
        random.seed(seed_value)
        torch.manual_seed(seed_value)

    tokenizer = AutoTokenizer.from_pretrained(model_ref)

    model_kwargs = {}
    dtype = str(cfg.get("dtype", "")).strip()
    if dtype:
        if not hasattr(torch, dtype):
            raise SystemExit(f"Unknown torch dtype for Hugging Face backend: {dtype}")
        model_kwargs["torch_dtype"] = getattr(torch, dtype)
    model = AutoModelForCausalLM.from_pretrained(model_ref, **model_kwargs)

    device = str(cfg.get("device", "auto")).strip()
    if device and device != "auto":
        model.to(device)

    messages = [
        {
            "role": "system",
            "content": system_prompt or cfg.get("system_prompt", "Return the requested response."),
        },
        {"role": "user", "content": prompt},
    ]
    if getattr(tokenizer, "chat_template", None):
        text_prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
    else:
        text_prompt = compose_text_prompt(system_prompt, prompt)

    inputs = tokenizer(text_prompt, return_tensors="pt")
    if device and device != "auto":
        inputs = {key: value.to(device) for key, value in inputs.items()}

    temperature = float(cfg.get("temperature", 0.1))
    capture_hidden = bool(cfg.get("capture_hidden", False))
    generate_kwargs = {
        "max_new_tokens": int(cfg.get("max_new_tokens", cfg.get("max_tokens", 900))),
        "do_sample": temperature > 0,
        "temperature": temperature if temperature > 0 else None,
        "return_dict_in_generate": True,
        "output_hidden_states": capture_hidden,
    }
    if cfg.get("top_p") not in {None, ""}:
        generate_kwargs["top_p"] = float(cfg.get("top_p"))
    if tokenizer.eos_token_id is not None:
        generate_kwargs["pad_token_id"] = tokenizer.eos_token_id
    generate_kwargs = {key: value for key, value in generate_kwargs.items() if value is not None}

    with torch.no_grad():
        generated = model.generate(**inputs, **generate_kwargs)

    input_len = int(inputs["input_ids"].shape[-1])
    sequence = generated.sequences[0]
    completion_ids = sequence[input_len:]
    content = tokenizer.decode(completion_ids, skip_special_tokens=True).strip()
    usage = {
        "prompt_tokens": input_len,
        "completion_tokens": int(completion_ids.shape[-1]),
        "total_tokens": int(sequence.shape[-1]),
    }

    hidden_summary = {}
    if capture_hidden and getattr(generated, "hidden_states", None):
        hidden_states = generated.hidden_states
        last_step = hidden_states[-1] if hidden_states else []
        last_layer = last_step[-1] if last_step else None
        hidden_summary = {
            "captured": True,
            "generated_steps": len(hidden_states),
            "layers_per_step": len(last_step) if last_step else 0,
            "last_layer_shape": list(last_layer.shape) if last_layer is not None else [],
        }

    return {
        "content": content,
        "usage": usage,
        "response_model": model_ref,
        "request_model": model_ref,
        "hidden": hidden_summary,
        "adapter": HUGGINGFACE_ADAPTER,
    }

def call_llm_result(cfg: dict, prompt: str, system_prompt: str = "") -> dict:
    started = time.perf_counter()
    adapter = resolve_llm_adapter(cfg)
    if adapter == OPENAI_CHAT_ADAPTER:
        result = call_openai_compatible_result(cfg, prompt, system_prompt)
    elif adapter == OPENAI_RESPONSES_ADAPTER:
        result = call_openai_responses_result(cfg, prompt, system_prompt)
    elif adapter == COMMAND_ADAPTER:
        result = call_command_llm_result(cfg, prompt, system_prompt)
    elif adapter == HUGGINGFACE_ADAPTER:
        result = call_huggingface_result(cfg, prompt, system_prompt)
    else:
        raise SystemExit(f"Unknown LLM adapter: {adapter!r}")

    result.setdefault("usage", {})
    result.update(
        {
            "backend": str(cfg.get("backend", "")),
            "adapter": str(result.get("adapter", adapter)),
            "profile": str(cfg.get("profile", "")),
            "model": str(cfg.get("model", "") or result.get("request_model", "")),
            "model_path": str(cfg.get("model_path", "")),
            "prompt_chars": len(prompt),
            "system_prompt_chars": len(system_prompt),
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        }
    )
    return result

def call_llm(cfg: dict, prompt: str, system_prompt: str = "") -> str:
    return str(call_llm_result(cfg, prompt, system_prompt).get("content", ""))

def build_json_repair_prompt(original_prompt: str, bad_output: str, error: str, fields: list[str]) -> str:
    field_lines = "\n".join(f"- {field}" for field in fields)
    return f"""The previous model output was not valid JSON for this task.

Return only one corrected JSON object. Do not include Markdown fences or commentary.

Required fields:
{field_lines}

Parse error:
{error}

Previous output:
---
{clip_text(bad_output)}
---

Original task prompt:
---
{clip_text(original_prompt)}
---
"""

def draft_annotation(raw: str, cfg: dict, json_repair_steps: int = 1) -> dict[str, str]:
    prompt = build_annotation_prompt(raw)
    output = call_llm(cfg, prompt, "Draft Great Scratchpad annotations as strict JSON only.")
    try:
        value = extract_json_object(output)
    except (ValueError, json.JSONDecodeError) as exc:
        last_error = exc
        for _attempt in range(max(0, json_repair_steps)):
            repair_prompt = build_json_repair_prompt(prompt, output, str(last_error), ANNOTATION_FIELDS)
            output = call_llm(
                cfg,
                repair_prompt,
                "Repair the response into strict JSON only.",
            )
            try:
                value = extract_json_object(output)
                break
            except (ValueError, json.JSONDecodeError) as repair_exc:
                last_error = repair_exc
        else:
            raise SystemExit(f"Could not parse LLM annotation JSON: {last_error}\nOutput:\n{output}") from exc
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
