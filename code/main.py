import csv
import os
from typing import Dict, List, Tuple, Set, Any
import json
import base64
import logging
from io import BytesIO
from PIL import Image
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATASET_DIR = os.path.join(REPO_ROOT, "dataset")


def _load_env_file(path: str) -> None:
    """Load simple KEY=VALUE entries without overwriting process env vars."""
    if not os.path.isfile(path):
        return
    with open(path, 'r', encoding='utf-8') as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip()
            if value[:1] == value[-1:] and value.startswith(('"', "'")):
                value = value[1:-1]
            if key:
                os.environ.setdefault(key, value)


_load_env_file(os.path.join(REPO_ROOT, ".env"))

# Enum constants from skill-enum-validation.md / problem_statement.md
CLAIM_STATUS = {"supported", "contradicted", "not_enough_information"}

ISSUE_TYPE = {
    "dent", "scratch", "crack", "glass_shatter", "broken_part",
    "missing_part", "torn_packaging", "crushed_packaging",
    "water_damage", "stain", "none", "unknown",
}

OBJECT_PART = {
    "car": {"front_bumper","rear_bumper","door","hood","windshield",
            "side_mirror","headlight","taillight","fender",
            "quarter_panel","body","unknown"},
    "laptop": {"screen","keyboard","trackpad","hinge","lid","corner",
               "port","base","body","unknown"},
    "package": {"box","package_corner","package_side","seal","label",
                "contents","item","unknown"},
}

RISK_FLAGS = {
    "none","blurry_image","cropped_or_obstructed","low_light_or_glare",
    "wrong_angle","wrong_object","wrong_object_part","damage_not_visible",
    "claim_mismatch","possible_manipulation","non_original_image",
    "text_instruction_present","user_history_risk","manual_review_required",
}

SEVERITY = {"none","low","medium","high","unknown"}
INPUT_COLUMNS = ('user_id', 'image_paths', 'user_claim', 'claim_object')
OUTPUT_COLUMNS = [
    'user_id', 'image_paths', 'user_claim', 'claim_object',
    'evidence_standard_met', 'evidence_standard_met_reason', 'risk_flags',
    'issue_type', 'object_part', 'claim_status',
    'claim_status_justification', 'supporting_image_ids', 'valid_image',
    'severity',
]


class PipelineData:
    def __init__(self, dataset_dir: str = DATASET_DIR):
        self.dataset_dir = dataset_dir
        self.claims = []  # list of dicts
        self.evidence_requirements = []
        self.user_history = {}  # keyed by user_id
        self.repair_counters = {}

    def incr(self, key: str):
        self.repair_counters[key] = self.repair_counters.get(key, 0) + 1


def _read_csv_rows(path: str) -> List[Dict[str, str]]:
    rows = []
    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    return rows


def load_csvs(
    dataset_dir: str = DATASET_DIR,
    claims_filename: str = 'claims.csv',
) -> PipelineData:
    pd = PipelineData(dataset_dir)
    pd.claims = _read_csv_rows(os.path.join(dataset_dir, claims_filename))
    pd.evidence_requirements = _read_csv_rows(os.path.join(dataset_dir, 'evidence_requirements.csv'))
    user_rows = _read_csv_rows(os.path.join(dataset_dir, 'user_history.csv'))
    for r in user_rows:
        # coerce numeric fields
        for k in ('past_claim_count','accept_claim','manual_review_claim','rejected_claim','last_90_days_claim_count'):
            if k in r:
                try:
                    r[k] = int(r[k])
                except Exception:
                    r[k] = 0
        pd.user_history[r.get('user_id')] = r
    return pd


def lookup_evidence_requirement(pipeline: PipelineData, claim_object: str, issue_family: str) -> Dict[str, str]:
    # Normalize inputs
    co = (claim_object or '').strip().lower()
    if issue_family is None:
        issue_family = ''
    if isinstance(issue_family, str):
        if issue_family.strip() == '':
            issue_family_norm = ''
        else:
            issue_family_norm = issue_family.strip().lower()
    else:
        issue_family_norm = str(issue_family).lower()

    def applies_tokens(s: str):
        s = (s or '').lower()
        # split on common separators
        for sep in [',', ' or ', ';', '/']:
            if sep in s:
                parts = [p.strip() for p in s.split(sep) if p.strip()]
                return parts
        return [s.strip()] if s.strip() else []

    # First prefer exact object-specific matches
    for row in pipeline.evidence_requirements:
        if (row.get('claim_object') or '').strip().lower() != co:
            continue
        applies = row.get('applies_to') or ''
        if applies.strip().lower() == issue_family_norm:
            return row
        # token or substring match
        tokens = applies_tokens(applies)
        if issue_family_norm in tokens:
            return row
        if any(issue_family_norm in t for t in tokens):
            return row

    # Then try 'all' entries
    for row in pipeline.evidence_requirements:
        if (row.get('claim_object') or '').strip().lower() != 'all':
            continue
        applies = row.get('applies_to') or ''
        if applies.strip().lower() == issue_family_norm:
            return row
        tokens = applies_tokens(applies)
        if issue_family_norm in tokens:
            return row
        if any(issue_family_norm in t for t in tokens):
            return row

    # As a last resort, return the first 'all' general rule
    for row in pipeline.evidence_requirements:
        if (row.get('claim_object') or '').strip().lower() == 'all' and (row.get('applies_to') or '').strip().lower() == 'general claim review':
            return row
    return {}


def build_history_note(pipeline: PipelineData, user_id: str) -> Tuple[str, Set[str]]:
    row = pipeline.user_history.get(user_id)
    if not row:
        return (f"User history note: no record for {user_id}.", set())
    flags = set()
    past = row.get('past_claim_count', 0)
    rejected_rate = row.get('rejected_claim', 0) / max(past, 1)
    if row.get('history_flags') and str(row.get('history_flags')).strip().lower() not in ("", "none"):
        flags.add('user_history_risk')
    if rejected_rate >= 0.3:
        flags.add('user_history_risk')
    if row.get('last_90_days_claim_count', 0) >= 3:
        flags.add('user_history_risk')
    if flags:
        flags.add('manual_review_required')
    # Build natural language note
    note_parts = []
    note_parts.append(f"User history note: {row.get('past_claim_count',0)} past claims")
    if row.get('rejected_claim',0):
        note_parts.append(f"{row.get('rejected_claim')} rejected")
    if row.get('last_90_days_claim_count',0):
        note_parts.append(f"{row.get('last_90_days_claim_count')} in last 90 days")
    if row.get('history_summary'):
        note_parts.append(f"history summary: {row.get('history_summary')}")
    note = "; ".join(note_parts)
    if not note:
        note = "User history note: no risk indicators; 0 past claims, mostly accepted."
    return (note, flags)


def _coerce_bool(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ('true','1','yes')
    return bool(val)


def _extract_image_ids(image_paths: str) -> List[str]:
    if not image_paths:
        return []
    parts = [p.strip() for p in image_paths.split(';') if p.strip()]
    ids = []
    for p in parts:
        name = os.path.splitext(os.path.basename(p))[0]
        ids.append(name)
    return ids


def validate_and_repair(pipeline: PipelineData, raw: Dict[str, Any], row: Dict[str, str]) -> Dict[str, Any]:
    # Work on a shallow copy
    r = dict(raw)
    image_ids = set(_extract_image_ids(row.get('image_paths','')))

    # claim_status
    cs = r.get('claim_status')
    if cs not in CLAIM_STATUS:
        r['claim_status'] = 'not_enough_information'
        pipeline.incr('claim_status')

    # issue_type
    it = r.get('issue_type')
    if it not in ISSUE_TYPE:
        r['issue_type'] = 'unknown'
        pipeline.incr('issue_type')

    # object_part depending on claim_object
    claim_obj = row.get('claim_object')
    op = r.get('object_part')
    allowed_parts = OBJECT_PART.get(claim_obj, {"unknown"})
    if op not in allowed_parts:
        r['object_part'] = 'unknown'
        pipeline.incr('object_part')

    # severity
    sev = r.get('severity')
    if sev not in SEVERITY:
        r['severity'] = 'unknown'
        pipeline.incr('severity')

    # evidence_standard_met and valid_image coercion
    esm = r.get('evidence_standard_met')
    esm_bool = _coerce_bool(esm)
    if isinstance(esm, str) and esm.strip().lower() not in ('true','false','1','0','yes','no') and not isinstance(esm, bool):
        pipeline.incr('evidence_standard_met')
    r['evidence_standard_met'] = esm_bool

    valid_image = r.get('valid_image')
    valid_image_bool = _coerce_bool(valid_image)
    if isinstance(valid_image, str) and valid_image.strip().lower() not in ('true','false','1','0','yes','no') and not isinstance(valid_image, bool):
        pipeline.incr('valid_image')
    r['valid_image'] = valid_image_bool

    # risk_flags filter
    rf = r.get('risk_flags') or []
    if isinstance(rf, str):
        rf_list = [s.strip() for s in rf.split(';') if s.strip()]
    else:
        rf_list = list(rf)
    rf_filtered = [f for f in rf_list if f in RISK_FLAGS]
    if len(rf_filtered) != len(rf_list):
        pipeline.incr('risk_flags')
    if not rf_filtered:
        rf_filtered = ['none']
    r['risk_flags'] = rf_filtered

    # supporting_image_ids filter
    sup = r.get('supporting_image_ids') or []
    if isinstance(sup, str):
        sup_list = [s.strip() for s in sup.split(';') if s.strip()]
    else:
        sup_list = list(sup)
    sup_filtered = [s for s in sup_list if s in image_ids]
    if len(sup_filtered) != len(sup_list):
        pipeline.incr('supporting_image_ids')
    if not sup_filtered:
        sup_filtered = ['none']
    r['supporting_image_ids'] = sup_filtered

    # reason/justification templates
    for k in list(r.keys()):
        if k.endswith('_reason') or k.endswith('_justification'):
            v = r.get(k)
            if not v or (isinstance(v, str) and not v.strip()):
                r[k] = f"No {k} provided for {claim_obj} regarding {r.get('issue_type','unknown')}."
                pipeline.incr('low_quality_justification')

    # cross-field consistency
    if not r.get('evidence_standard_met'):
        # force claim_status = not_enough_information unless it already was
        if r.get('claim_status') != 'not_enough_information':
            r['claim_status'] = 'not_enough_information'
            pipeline.incr('crossfield_claim_status')

    if r.get('claim_status') == 'not_enough_information' and not r.get('evidence_standard_met'):
        # force supporting_image_ids = ['none']
        if r.get('supporting_image_ids') != ['none']:
            r['supporting_image_ids'] = ['none']
            pipeline.incr('crossfield_supporting_image_ids')

    if r.get('issue_type') == 'none' and r.get('severity') != 'none':
        r['severity'] = 'none'
        pipeline.incr('crossfield_severity')

    return r


def _output_values(result: Dict[str, Any]) -> List[Any]:
    values = []
    for column in OUTPUT_COLUMNS:
        value = result.get(column)
        if column in ('risk_flags', 'supporting_image_ids'):
            if isinstance(value, (list, set)):
                value = ';'.join(value)
        if isinstance(value, bool):
            value = 'true' if value else 'false'
        if value is None:
            value = ''
        values.append(value)
    return values


def write_output(results: List[Dict[str, Any]], output_path: str):
    # Column order per problem_statement.md
    output_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(output_dir, exist_ok=True)
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(OUTPUT_COLUMNS)
        for res in results:
            writer.writerow(_output_values(res))


def _append_output_row(result: Dict[str, Any], output_path: str) -> None:
    """Append and durably close one completed prediction row."""
    with open(output_path, 'a', newline='', encoding='utf-8') as output_file:
        writer = csv.writer(output_file)
        writer.writerow(_output_values(result))
        output_file.flush()
        os.fsync(output_file.fileno())


def _load_progress(progress_path: str) -> int:
    if not os.path.isfile(progress_path):
        return -1
    with open(progress_path, 'r', encoding='utf-8') as progress_file:
        progress = json.load(progress_file)
    return int(progress.get('last_completed_index', -1))


def _save_progress(progress_path: str, completed_index: int) -> None:
    """Durably replace progress.json after its CSV row has been committed."""
    temporary_path = progress_path + '.tmp'
    with open(temporary_path, 'w', encoding='utf-8', newline='\n') as progress_file:
        json.dump(
            {'last_completed_index': completed_index},
            progress_file,
            indent=2,
        )
        progress_file.write('\n')
        progress_file.flush()
        os.fsync(progress_file.fileno())
    os.replace(temporary_path, progress_path)


def _load_system_prompt() -> str:
    root_path = os.path.join(REPO_ROOT, 'prompt.md')
    if os.path.exists(root_path):
        with open(root_path, 'r', encoding='utf-8') as f:
            return f.read()
    return ""


def _encode_images(image_paths: str) -> Dict[str, Dict[str, str]]:
    """Return image IDs mapped to Gemini-ready MIME type and base64 data."""
    out = {}
    for p in [s.strip() for s in (image_paths or '').split(';') if s.strip()]:
        abs_path = os.path.abspath(os.path.join(REPO_ROOT, p))
        if not os.path.isfile(abs_path):
            abs_path = os.path.abspath(os.path.join(DATASET_DIR, p))
        image_id = os.path.splitext(os.path.basename(p))[0]
        with open(abs_path, 'rb') as f:
            original = f.read()

        with Image.open(BytesIO(original)) as image:
            image.thumbnail((1024, 1024))
            if image.mode != 'RGB':
                image = image.convert('RGB')
            compressed_buffer = BytesIO()
            image.save(
                compressed_buffer,
                format='JPEG',
                quality=75,
                optimize=True,
            )

        compressed = compressed_buffer.getvalue()
        orig_kb = len(original) / 1024
        compressed_kb = len(compressed) / 1024
        print(
            f"{image_id}: original={orig_kb:.1f}KB "
            f"compressed={compressed_kb:.1f}KB"
        )
        encoded = base64.b64encode(compressed).decode('ascii')
        out[image_id] = {'mime_type': 'image/jpeg', 'data': encoded}
    return out


def _send_gemini_request(
    system_prompt: str,
    user_message: str,
    raw_images: Dict[str, Dict[str, str]],
) -> str:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("Gemini_API_Key")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?{urlencode({'key': api_key})}"
    )

    parts = [{"text": user_message}]

    for image_id, image in raw_images.items():
        parts.append({"text": f"Image ID: {image_id}"})
        parts.append(
            {
                "inline_data": {
                    "mime_type": image["mime_type"],
                    "data": image["data"],
                }
            }
        )

    payload = {
        "system_instruction": {
            "parts": [{"text": system_prompt}]
        },
        "contents": [
            {
                "role": "user",
                "parts": parts,
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0,
        },
    }

    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urlopen(request, timeout=120) as response:
        body = json.loads(response.read().decode("utf-8"))
    return body["candidates"][0]["content"]["parts"][0]["text"]


def _send_qwen_fallback_request(
    system_prompt: str,
    user_message: str,
    raw_images: Dict[str, Dict[str, str]],
) -> str:
    """Make one OpenRouter request to the configured Qwen vision model."""
    api_key = os.getenv('OPENROUTER_API_KEY')
    if not api_key:
        raise RuntimeError(
            'Gemini failed and OPENROUTER_API_KEY is not set for Qwen fallback'
        )

    content = [{'type': 'text', 'text': user_message}]
    for image_id, image in raw_images.items():
        content.append({'type': 'text', 'text': f'Image ID: {image_id}'})
        content.append({
            'type': 'image_url',
            'image_url': {
                'url': f"data:{image['mime_type']};base64,{image['data']}"
            },
        })

    payload = {
        'model': os.getenv(
            'QWEN_FALLBACK_MODEL',
            'qwen/qwen2.5-vl-72b-instruct',
        ),
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': content},
        ],
        'response_format': {'type': 'json_object'},
        'temperature': 0,
    }
    request = Request(
        'https://openrouter.ai/api/v1/chat/completions',
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    with urlopen(request, timeout=120) as response:
        body = json.loads(response.read().decode('utf-8'))
    return body['choices'][0]['message']['content']


def _send_model_request(
    system_prompt: str,
    user_message: str,
    raw_images: Dict[str, Dict[str, str]],
) -> str:
    """Use Gemini first, then Qwen once if the Gemini request fails."""
    try:
        return _send_gemini_request(system_prompt, user_message, raw_images)
    except (
        HTTPError,
        URLError,
        TimeoutError,
        json.JSONDecodeError,
        KeyError,
        IndexError,
    ) as error:
        status = f' HTTP {error.code}' if isinstance(error, HTTPError) else ''
        print(f'Gemini failed with{status or " an API error"}; using Qwen fallback.')
        return _send_qwen_fallback_request(
            system_prompt,
            user_message,
            raw_images,
        )


def classify_claim(pipeline: PipelineData, row: Dict[str, str], history_note: str, evidence_ctx: Dict[str, str]) -> Dict[str, Any]:
    """Run the same model-call sequence used by debug_raw_response.py."""
    raw_images = row.get("image_paths", "")
    print(f"Raw 'image_paths' from CSV: '{raw_images}'")

    logging.basicConfig(level=logging.INFO, format='%(message)s')
    images = _encode_images(raw_images)

    print(f"Encoded {len(images)} image(s)")
    for image_id, image in images.items():
        encoded_kb = len(image['data']) / 1024
        print(f"  - {image_id}: {encoded_kb:.1f}KB base64")

    system_prompt = _load_system_prompt()
    if not system_prompt:
        raise FileNotFoundError(os.path.join(REPO_ROOT, 'prompt.md'))
    print(f"System prompt length: {len(system_prompt)} chars")

    pieces = [
        f"Claim object: {row.get('claim_object')}",
        f"User claim: {row.get('user_claim')}",
    ]
    if evidence_ctx and evidence_ctx.get('minimum_image_evidence'):
        pieces.append(
            "Evidence requirement: "
            f"{evidence_ctx.get('minimum_image_evidence')}"
        )
    pieces.append(f"History note: {history_note}")
    if images:
        pieces.append(f"Images: {', '.join(images.keys())}")
    user_message = "\n\n".join(pieces)

    print("\n--- USER MESSAGE PREVIEW (first 700 chars) ---")
    preview = user_message[:700] + ("..." if len(user_message) > 700 else "")
    print(preview)
    print(f"\n--- CALLING MODEL REQUEST ({len(images)} images) ---")

    content = _send_model_request(system_prompt, user_message, images)
    print("\n--- RAW RESPONSE ---")
    print(content[:2000] + ("..." if len(content) > 2000 else ""))
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        reminder = user_message + "\n\nReturn valid JSON only."
        retry_content = _send_model_request(system_prompt, reminder, images)
        print("\n--- RETRY RAW RESPONSE ---")
        print(
            retry_content[:2000]
            + ("..." if len(retry_content) > 2000 else "")
        )
        parsed = json.loads(retry_content)

    print("JSON parsed successfully")
    print("Keys:", list(parsed.keys()))
    return parsed


def run_pipeline(
    dataset_dir: str = DATASET_DIR,
    output_path: str = None,
    claims_filename: str = 'claims.csv',
    limit: int = None,
):
    pipeline = load_csvs(dataset_dir, claims_filename=claims_filename)
    results = []
    claim_rows = pipeline.claims[:limit] if limit is not None else pipeline.claims
    total_rows = len(claim_rows)
    if output_path is None:
        output_path = os.path.abspath(os.path.join(REPO_ROOT, 'output.csv'))
    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    progress_path = os.path.join(os.path.dirname(output_path), 'progress.json')
    progress_exists = os.path.isfile(progress_path)
    last_completed_index = _load_progress(progress_path)

    if last_completed_index < -1 or last_completed_index >= total_rows:
        raise ValueError(
            f'Invalid last_completed_index {last_completed_index} '
            f'for {total_rows} claims'
        )

    if last_completed_index == -1:
        with open(output_path, 'w', newline='', encoding='utf-8') as output_file:
            writer = csv.writer(output_file)
            writer.writerow(OUTPUT_COLUMNS)
            output_file.flush()
            os.fsync(output_file.fileno())
        if not progress_exists:
            _save_progress(progress_path, -1)
    elif not os.path.isfile(output_path):
        raise FileNotFoundError(
            f'{output_path} is missing but {progress_path} indicates '
            f'claim {last_completed_index} was completed'
        )

    start_index = last_completed_index + 1
    print(f'Resuming from claim index {start_index}')

    for index in range(start_index, total_rows):
        source_row = claim_rows[index]
        try:
            # Never expose expected-output columns from labeled sample data to the model.
            row = {column: source_row.get(column, '') for column in INPUT_COLUMNS}
            user_id = row.get('user_id')
            print(f"\n[{index + 1}/{total_rows}] Processing {user_id}")
            history_note, history_flags = build_history_note(pipeline, user_id)
            evidence_ctx = lookup_evidence_requirement(pipeline, row.get('claim_object'), row.get('issue_type'))
            raw = classify_claim(pipeline, row, history_note, evidence_ctx)
            print(f"[{index + 1}/{total_rows}] Model response parsed successfully")
            validated = validate_and_repair(pipeline, raw, row)
            # merge risk flags
            model_flags = validated.get('risk_flags') or []
            if isinstance(model_flags, str):
                model_flags = [s.strip() for s in model_flags.split(';') if s.strip()]
            merged = (set(model_flags) - {'none'}) | set(history_flags)
            validated['risk_flags'] = sorted(merged) if merged else ['none']
            # ensure supporting_image_ids filtered (validate_and_repair already filters)
            # prepare output row
            out_row = {
                'user_id': row.get('user_id'),
                'image_paths': row.get('image_paths'),
                'user_claim': row.get('user_claim'),
                'claim_object': row.get('claim_object'),
                'evidence_standard_met': validated.get('evidence_standard_met'),
                'evidence_standard_met_reason': validated.get('evidence_standard_met_reason',''),
                'risk_flags': validated.get('risk_flags'),
                'issue_type': validated.get('issue_type'),
                'object_part': validated.get('object_part'),
                'claim_status': validated.get('claim_status'),
                'claim_status_justification': validated.get('claim_status_justification',''),
                'supporting_image_ids': validated.get('supporting_image_ids'),
                'valid_image': validated.get('valid_image'),
                'severity': validated.get('severity')
            }

            # The checkpoint order is deliberate: process, append, then progress.
            _append_output_row(out_row, output_path)
            _save_progress(progress_path, index)
            results.append(out_row)
        except Exception as error:
            print(f'Error processing claim index {index}: {error}')
            raise

    print(f"\nCheckpointed through claim index {total_rows - 1}")
    print(f"Output: {output_path}")
    print(f"Progress: {progress_path}")
    return results


if __name__ == '__main__':
    run_pipeline()
