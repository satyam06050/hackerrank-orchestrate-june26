# Claim Evidence Pipeline

`main.py` reads `dataset/claims.csv`, enriches each row with the Stage 1
evidence requirement and user-history context, makes one multimodal Gemini
request per row, validates the JSON response, and writes `output.csv` at the
repository root.

## Configuration

The runner uses only Python's standard library. Define these values in the
repository-root `.env` file:

```text
GEMINI_API_KEY=your-key
GEMINI_MODEL=gemini-2.5-flash
OPENROUTER_API_KEY=your-openrouter-key
QWEN_FALLBACK_MODEL=qwen/qwen2.5-vl-72b-instruct
```

`GEMINI_MODEL` is optional and defaults to `gemini-2.5-flash`. Secrets are
read only from environment variables or `.env` and must not be committed.
The legacy key spelling `Gemini_API_Key` is also accepted.
If Gemini has an HTTP, transport, or malformed-response failure (including
HTTP 429), the same multimodal request is sent once through OpenRouter using
the Qwen fallback model. `QWEN_FALLBACK_MODEL` is optional; the shown model is
the default.

## Run

From the repository root:

```text
python code/main.py
```

If Gemini returns invalid JSON, the row is retried exactly once with a JSON-only
reminder. HTTP and other runtime failures are not retried.
