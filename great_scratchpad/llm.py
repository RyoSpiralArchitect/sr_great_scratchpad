from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
import urllib.error
import urllib.request

from .constants import ANNOTATION_FIELDS, ANNOTATION_PROMPT_TEMPLATE

def build_annotation_prompt(raw: str) -> str:
    return ANNOTATION_PROMPT_TEMPLATE.format(raw=raw.strip())

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

def expand_command_part(part: str, values: dict[str, str]) -> str:
    out = part
    for key, value in values.items():
        out = out.replace("{" + key + "}", value)
    return out

def call_openai_compatible(cfg: dict, prompt: str, system_prompt: str = "") -> str:
    api_key_env = cfg.get("api_key_env", "")
    api_key = os.environ.get(api_key_env, "") if api_key_env else cfg.get("api_key", "")
    if api_key_env and not api_key:
        raise SystemExit(f"Environment variable is not set: {api_key_env}")

    url = cfg.get("base_url") or cfg.get("url")
    if not url:
        raise SystemExit("openai-compatible LLM config requires base_url.")
    if not url.rstrip("/").endswith("/chat/completions"):
        url = url.rstrip("/") + "/chat/completions"

    body = {
        "model": cfg.get("model", ""),
        "messages": [
            {
                "role": "system",
                "content": system_prompt or cfg.get("system_prompt", "Return the requested response."),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": float(cfg.get("temperature", 0.2)),
        "max_tokens": int(cfg.get("max_tokens", 900)),
    }
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
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise SystemExit(f"Provider API response did not look OpenAI-compatible: {data}") from exc

def call_command_llm(cfg: dict, prompt: str, system_prompt: str = "") -> str:
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

    return proc.stdout.strip()

def call_llm(cfg: dict, prompt: str, system_prompt: str = "") -> str:
    backend = str(cfg.get("backend", "")).lower()
    if backend in {"openai-compatible", "openai_compatible", "provider"}:
        return call_openai_compatible(cfg, prompt, system_prompt)
    if backend in {"command", "local", "local-command"}:
        return call_command_llm(cfg, prompt, system_prompt)
    raise SystemExit(f"Unknown LLM backend: {cfg.get('backend')!r}")

def draft_annotation(raw: str, cfg: dict) -> dict[str, str]:
    prompt = build_annotation_prompt(raw)
    output = call_llm(cfg, prompt, "Draft Great Scratchpad annotations as strict JSON only.")
    try:
        value = extract_json_object(output)
    except (ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Could not parse LLM annotation JSON: {exc}\nOutput:\n{output}") from exc
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
