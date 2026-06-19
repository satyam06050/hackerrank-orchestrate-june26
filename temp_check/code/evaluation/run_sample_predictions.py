import csv
import os
import sys
import time
from pprint import pprint

# Ensure repo root is on sys.path so `code` package imports work when running this script
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from code.main import (
    load_csvs,
    build_history_note,
    lookup_evidence_requirement,
    classify_claim,
    validate_and_repair,
    write_output,
)


def _extract_image_ids(image_paths):
    ids = set()

    for path in (image_paths or "").split(";"):
        path = path.strip()
        if not path:
            continue

        image_id = os.path.splitext(os.path.basename(path))[0]
        ids.add(image_id)

    return ids


def run_sample(n=3, delay=3):
    sample_path = os.path.join(
        repo_root,
        "dataset",
        "sample_claims.csv",
    )

    out_path = os.path.join(
        os.path.dirname(__file__),
        "sample_predictions.csv",
    )

    rows = []

    with open(sample_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for i, r in enumerate(reader):
            if i >= n:
                break

            rows.append(
                {
                    "user_id": r.get("user_id"),
                    "image_paths": r.get("image_paths"),
                    "user_claim": r.get("user_claim"),
                    "claim_object": r.get("claim_object"),
                }
            )

    pipeline = load_csvs()

    results = []

    print(f"Loaded {len(rows)} sample rows\n")

    for idx, row in enumerate(rows, start=1):
        uid = row.get("user_id")

        print("=" * 80)
        print(f"[{idx}/{len(rows)}] Processing {uid}")
        print("=" * 80)

        try:
            history_note, history_flags = build_history_note(
                pipeline,
                uid,
            )

            evidence_ctx = lookup_evidence_requirement(
                pipeline,
                row.get("claim_object"),
                "",
            )

            raw = classify_claim(
                pipeline,
                row,
                history_note,
                evidence_ctx,
            )

            print("\nRAW MODEL OUTPUT:")
            pprint(raw)

            validated = validate_and_repair(
                pipeline,
                raw,
                row,
            )

            print("\nVALIDATED OUTPUT:")
            pprint(validated)

            # --------------------------------------------------
            # Merge risk flags
            # --------------------------------------------------

            model_flags = validated.get("risk_flags") or []

            if isinstance(model_flags, str):
                model_flags = [
                    x.strip()
                    for x in model_flags.split(";")
                    if x.strip()
                ]

            merged_flags = set(model_flags) | set(history_flags)

            if merged_flags and "none" in merged_flags:
                merged_flags.remove("none")

            if not merged_flags:
                merged_flags = {"none"}

            validated["risk_flags"] = sorted(list(merged_flags))

            # --------------------------------------------------
            # Filter supporting image ids
            # --------------------------------------------------

            valid_image_ids = _extract_image_ids(
                row.get("image_paths")
            )

            supporting = validated.get(
                "supporting_image_ids",
                [],
            )

            if isinstance(supporting, str):
                supporting = [
                    x.strip()
                    for x in supporting.split(";")
                    if x.strip()
                ]

            filtered_supporting = [
                img_id
                for img_id in supporting
                if img_id in valid_image_ids
            ]

            if not filtered_supporting:
                filtered_supporting = ["none"]

            validated["supporting_image_ids"] = (
                filtered_supporting
            )

            # --------------------------------------------------
            # Build final output row
            # --------------------------------------------------

            out_row = {
                "user_id": row.get("user_id"),
                "image_paths": row.get("image_paths"),
                "user_claim": row.get("user_claim"),
                "claim_object": row.get("claim_object"),
                "evidence_standard_met": validated.get(
                    "evidence_standard_met"
                ),
                "evidence_standard_met_reason": validated.get(
                    "evidence_standard_met_reason",
                    "",
                ),
                "risk_flags": validated.get(
                    "risk_flags",
                    ["none"],
                ),
                "issue_type": validated.get(
                    "issue_type",
                    "unknown",
                ),
                "object_part": validated.get(
                    "object_part",
                    "unknown",
                ),
                "claim_status": validated.get(
                    "claim_status",
                    "not_enough_information",
                ),
                "claim_status_justification": validated.get(
                    "claim_status_justification",
                    "",
                ),
                "supporting_image_ids": validated.get(
                    "supporting_image_ids",
                    ["none"],
                ),
                "valid_image": validated.get(
                    "valid_image",
                    False,
                ),
                "severity": validated.get(
                    "severity",
                    "unknown",
                ),
            }

            results.append(out_row)

            print("\nFINAL OUTPUT ROW:")
            pprint(out_row)

        except Exception as e:
            print(f"\nERROR processing {uid}")
            print(type(e).__name__, str(e))

        if idx < len(rows):
            time.sleep(delay)

    write_output(results, out_path)

    print("\n" + "=" * 80)
    print("DONE")
    print("=" * 80)
    print(f"Wrote: {out_path}")
    print(f"Rows written: {len(results)}")

    if os.path.exists(out_path):
        print("\nGenerated CSV:\n")

        with open(out_path, encoding="utf-8") as f:
            print(f.read())


if __name__ == "__main__":
    run_sample(
        n=3,
        delay=3,
    )