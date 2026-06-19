# Multi-Modal Damage Claim Evidence Review

This submission reads claim conversations, submitted images, user history, and
minimum evidence requirements. It produces one structured decision per row in
`dataset/claims.csv` and writes the required schema to `output.csv`.

## Requirements

- Python 3.10 or newer
- Pillow (installed from `code/requirements.txt`)
- A Gemini API key
- An OpenRouter API key only if the Qwen fallback should be available

Install dependencies from the repository root:

```bash
python -m pip install -r code/requirements.txt
```

## Environment variables

Create `.env` at the repository root or export the variables in the shell.
Never commit `.env` or real keys.

```text
GEMINI_API_KEY=your_gemini_key
GEMINI_MODEL=gemini-2.5-flash
OPENROUTER_API_KEY=your_openrouter_key
QWEN_FALLBACK_MODEL=qwen/qwen2.5-vl-72b-instruct
```

| Variable | Required | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | Yes | Authenticates the primary Gemini request. The legacy spelling `Gemini_API_Key` is also accepted. |
| `GEMINI_MODEL` | No | Primary model; defaults to `gemini-2.5-flash`. |
| `OPENROUTER_API_KEY` | Fallback only | Authenticates the Qwen request if Gemini fails. |
| `QWEN_FALLBACK_MODEL` | No | Fallback model; defaults to `qwen/qwen2.5-vl-72b-instruct`. |

## Run the claim pipeline

From the repository root:

```bash
python code/main.py
```

The runner reads:

- `dataset/claims.csv`
- `dataset/user_history.csv`
- `dataset/evidence_requirements.csv`
- images referenced by each claim
- `prompt.md`

It writes `output.csv` and checkpoints each completed zero-based row index in
`progress.json`. A restarted run resumes at the next unfinished claim. Each
successful row is flushed to `output.csv` before `progress.json` advances.

For a completely new run, start without an old `output.csv` or `progress.json`.
The final prediction CSV is submitted separately from `code.zip`.

## Run evaluation

Score the currently persisted sample predictions:

```bash
python code/evaluation/main.py
```

This compares `code/evaluation/sample_predictions.csv` with the labels in
`dataset/sample_claims.csv`, prints per-field accuracy and mismatches, and
writes `code/evaluation/sample_eval_results.csv`.

To regenerate sample predictions using only the four input columns and then
score them:

```bash
python code/evaluation/main.py --generate
```

This mode makes paid model calls. Its checkpoint is stored beside
`code/evaluation/sample_predictions.csv`; remove that evaluation checkpoint
and prediction file only when intentionally starting a fresh sample run.

The measured accuracy, latency, image/token counts, and costs are documented in
`code/evaluation/evaluation_report.md`.

## Architecture

1. **Deterministic input preparation.** CSV rows are loaded locally. Expected
   sample labels are projected out before model invocation. User-history flags
   and the applicable evidence requirement are added as context.
2. **Image preprocessing.** Each local image is resized to at most 1024 x 1024,
   converted to JPEG at quality 75, and base64 encoded with its image ID.
3. **One primary multimodal call per row.** Gemini receives the prompt, claim
   context, and images. Invalid JSON permits one JSON-only retry. Gemini API
   failure routes once to the configured Qwen vision fallback.
4. **Deterministic post-processing.** Enum allowlists, booleans, image IDs,
   cross-field consistency, history risk flags, and output column order are
   validated or repaired without another reasoning layer.
5. **Durable output.** Each successful result is appended and flushed before
   its checkpoint is atomically advanced.

There is no retrieval, embedding index, vector database, web search, or RAG
stage. All non-model context comes directly from the provided CSV files and
local images.

## Final repository structure

```text
.
|-- README.md
|-- prompt.md
|-- skill-enum-validation.md
|-- skill-evaluation-report.md
|-- skill-pipeline-architecture.md
|-- code/
|   |-- main.py
|   |-- requirements.txt
|   |-- README.md
|   `-- evaluation/
|       |-- main.py
|       |-- run_sample_predictions.py
|       |-- sample_predictions.csv
|       |-- sample_eval_results.csv
|       `-- evaluation_report.md
|-- dataset/
|   |-- claims.csv
|   |-- sample_claims.csv
|   |-- user_history.csv
|   |-- evidence_requirements.csv
|   `-- images/
|-- output.csv
`-- progress.json
```

### `code.zip` checklist

- [x] `code/`
- [x] `code/evaluation/`
- [x] `prompt.md`
- [x] `skill-enum-validation.md`
- [x] `skill-evaluation-report.md`
- [x] `skill-pipeline-architecture.md`
- [x] `README.md`

Exclude `.env`, API keys, Python virtual environments, `__pycache__/`, and
other generated caches from the archive.
