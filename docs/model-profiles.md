# Model profile examples

Great Scratchpad can use either an OpenAI-compatible HTTP API profile or a
local command profile. API profiles are usually easier to observe because
provider usage can be captured in chat traces. Command profiles are useful when
you want the simplest possible local process.

The chat runtime expects the model to return JSON objects. Use low temperature
for early experiments and keep `--json-repair-steps` enabled while comparing
models.

## OpenAI-compatible HTTP profiles

### Generic provider

```bash
export PROVIDER_API_KEY="..."

python3 -S sr_great_scratchpad.py llm-config provider \
  --profile provider \
  --base-url "https://api.example.com/v1" \
  --api-key-env PROVIDER_API_KEY \
  --model "MODEL_NAME" \
  --temperature 0.1 \
  --top-p 0.9 \
  --max-tokens 900 \
  --seed 42 \
  --stop "<END_JSON>" \
  --json-mode json_object \
  --default
```

### Ollama

Ollama documents OpenAI compatibility for `/v1/chat/completions`.

```bash
ollama serve
ollama pull qwen2.5:7b-instruct

python3 -S sr_great_scratchpad.py llm-config provider \
  --profile ollama-qwen \
  --base-url "http://127.0.0.1:11434/v1" \
  --model "qwen2.5:7b-instruct" \
  --temperature 0.1 \
  --default
```

### LM Studio

Start LM Studio's local server, load a chat/instruct model, then point Great
Scratchpad at the OpenAI-compatible base URL.

```bash
python3 -S sr_great_scratchpad.py llm-config provider \
  --profile lmstudio \
  --base-url "http://127.0.0.1:1234/v1" \
  --model "local-model" \
  --temperature 0.1 \
  --default
```

### llama.cpp `llama-server`

`llama-server` provides OpenAI-compatible HTTP endpoints.

```bash
llama-server -m /path/to/model.gguf --host 127.0.0.1 --port 8080

python3 -S sr_great_scratchpad.py llm-config provider \
  --profile llama-server \
  --base-url "http://127.0.0.1:8080/v1" \
  --model "local-gguf" \
  --temperature 0.1 \
  --default
```

### llama-cpp-python server

```bash
python -m llama_cpp.server \
  --model /path/to/model.gguf \
  --host 127.0.0.1 \
  --port 8000

python3 -S sr_great_scratchpad.py llm-config provider \
  --profile llama-cpp-python \
  --base-url "http://127.0.0.1:8000/v1" \
  --model "local-gguf" \
  --temperature 0.1
```

### vLLM OpenAI-compatible server

```bash
vllm serve Qwen/Qwen2.5-7B-Instruct \
  --host 127.0.0.1 \
  --port 8000

python3 -S sr_great_scratchpad.py llm-config provider \
  --profile vllm-qwen \
  --base-url "http://127.0.0.1:8000/v1" \
  --model "Qwen/Qwen2.5-7B-Instruct" \
  --temperature 0.1
```

## Local command profiles

Command profiles pass the composed prompt through stdin unless the command
contains `{prompt}` or `{prompt_file}`.
Because command-line models usually do not return provider usage, Great
Scratchpad records a dependency-free token usage estimate in traces and smoke
reports.

### llama.cpp `llama-cli`

```bash
python3 -S sr_great_scratchpad.py llm-config local \
  --profile llama-cli \
  --command "llama-cli -m {model_path} -f {prompt_file} -n 900 --temp 0.1" \
  --model-path "/path/to/model.gguf" \
  --timeout 180
```

### Ollama command mode

```bash
python3 -S sr_great_scratchpad.py llm-config local \
  --profile ollama-run \
  --command "ollama run qwen2.5:7b-instruct" \
  --timeout 180
```

### Python wrapper script

For models with custom prompting needs, write a tiny script that reads stdin and
prints one JSON object.

```bash
python3 -S sr_great_scratchpad.py llm-config local \
  --profile my-wrapper \
  --command "python3 -S /path/to/wrapper.py" \
  --timeout 180
```

## Hugging Face transformers profile

The Hugging Face backend is optional and only loads `transformers` / `torch`
when the profile is actually used. It is meant for local experiments where you
may later want to inspect generated hidden-state metadata.

```bash
python3 -S sr_great_scratchpad.py llm-config hf \
  --profile hf-local \
  --model "/path/to/hf/model-or-repo" \
  --device mps \
  --dtype float16 \
  --temperature 0.1 \
  --top-p 0.9 \
  --max-new-tokens 900 \
  --capture-hidden \
  --default
```

If `--capture-hidden` is set, traces include shape metadata for generated
hidden states when the model/backend supports it. Tensor dumps are intentionally
not written by default.

## Experiment commands

Profile smoke:

```bash
python3 -S sr_great_scratchpad.py smoke \
  --profile ollama-qwen \
  --trace-out traces/ollama-qwen-smoke.jsonl
```

The smoke command verifies that a profile can return one parseable JSON object.
It also writes `traces/ollama-qwen-smoke.manifest.json` by default.

```bash
python3 -S sr_great_scratchpad.py annotate \
  --profile ollama-qwen \
  --text-file sample-log.md \
  --json \
  --json-repair-steps 2

python3 -S sr_great_scratchpad.py chat monday-meawness \
  --profile ollama-qwen \
  --text "Use the earlier Topic Drift context." \
  --trace-out traces/ollama-qwen.jsonl \
  --run-id ollama-qwen-topic-drift-001 \
  --json-repair-steps 2 \
  --queue-writes
```

`chat` creates trace parent directories automatically and writes a sibling
manifest by default, for example `traces/ollama-qwen.manifest.json`. The
manifest captures the run id, profile metadata, event counts, and usage totals.

Review queued memory writes:

```bash
python3 -S sr_great_scratchpad.py review list monday-meawness
python3 -S sr_great_scratchpad.py review edit monday-meawness ITEM_ID.json \
  --text "Edited note text before applying." \
  --center "reviewed memory write"
python3 -S sr_great_scratchpad.py review apply monday-meawness ITEM_ID.json
python3 -S sr_great_scratchpad.py review reject monday-meawness ITEM_ID.json
```

References:

- Ollama OpenAI compatibility: https://docs.ollama.com/openai
- LM Studio REST/OpenAI-compatible server docs: https://lmstudio.ai/docs/developer/rest/endpoints
- llama.cpp `llama-server`: https://www.mintlify.com/ggml-org/llama.cpp/inference/server
- llama-cpp-python server: https://llama-cpp-python.readthedocs.io/en/latest/server/
- vLLM OpenAI-compatible server: https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html
