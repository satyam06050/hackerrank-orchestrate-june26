"""Score sample predictions against dataset/sample_claims.csv labels."""

import argparse
import csv
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_LABELS = REPO_ROOT / 'dataset' / 'sample_claims.csv'
SAMPLE_PREDICTIONS = (
    REPO_ROOT / 'code' / 'evaluation' / 'sample_predictions.csv'
)
EVAL_RESULTS = REPO_ROOT / 'code' / 'evaluation' / 'sample_eval_results.csv'

EXACT_FIELDS = (
    'evidence_standard_met',
    'claim_status',
    'issue_type',
    'object_part',
    'valid_image',
    'severity',
)
SET_FIELDS = ('risk_flags', 'supporting_image_ids')


def _read_rows(path: Path):
    with path.open(newline='', encoding='utf-8-sig') as csv_file:
        return list(csv.DictReader(csv_file))


def _normalize(value):
    return str(value or '').strip().lower()


def _as_set(value):
    return {
        _normalize(item)
        for item in str(value or '').split(';')
        if _normalize(item)
    }


def _generate_predictions():
    sys.path.insert(0, str(REPO_ROOT))
    from code.main import run_pipeline

    run_pipeline(
        dataset_dir=str(REPO_ROOT / 'dataset'),
        claims_filename='sample_claims.csv',
        output_path=str(SAMPLE_PREDICTIONS),
    )


def evaluate():
    expected_rows = _read_rows(SAMPLE_LABELS)
    predicted_rows = _read_rows(SAMPLE_PREDICTIONS)
    predictions = {row['user_id']: row for row in predicted_rows}
    compared = [row for row in expected_rows if row['user_id'] in predictions]

    if not compared:
        raise RuntimeError('No sample prediction rows match sample_claims.csv')

    matches = {field: 0 for field in EXACT_FIELDS + SET_FIELDS}
    jaccard_total = 0.0
    result_rows = []

    for expected in compared:
        user_id = expected['user_id']
        predicted = predictions[user_id]
        mismatches = []

        for field in EXACT_FIELDS:
            matched = _normalize(expected[field]) == _normalize(predicted[field])
            matches[field] += int(matched)
            if not matched:
                mismatches.append(field)
            result_rows.append({
                'user_id': user_id,
                'field': field,
                'expected': expected[field],
                'predicted': predicted[field],
                'match': str(matched).lower(),
            })

        for field in SET_FIELDS:
            expected_set = _as_set(expected[field])
            predicted_set = _as_set(predicted[field])
            matched = expected_set == predicted_set
            matches[field] += int(matched)
            if not matched:
                mismatches.append(field)
            result_rows.append({
                'user_id': user_id,
                'field': field,
                'expected': ';'.join(sorted(expected_set)),
                'predicted': ';'.join(sorted(predicted_set)),
                'match': str(matched).lower(),
            })

        expected_risk = _as_set(expected['risk_flags'])
        predicted_risk = _as_set(predicted['risk_flags'])
        union = expected_risk | predicted_risk
        jaccard_total += len(expected_risk & predicted_risk) / len(union) if union else 1.0

        if mismatches:
            print(f"{user_id}: mismatched {', '.join(mismatches)}")

    EVAL_RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with EVAL_RESULTS.open('w', newline='', encoding='utf-8') as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=('user_id', 'field', 'expected', 'predicted', 'match'),
        )
        writer.writeheader()
        writer.writerows(result_rows)

    total = len(compared)
    print(f'\nCompared {total}/{len(expected_rows)} labeled sample rows')
    print('Field                              Accuracy')
    print('---------------------------------  --------')
    for field in EXACT_FIELDS:
        print(f'{field:33}  {matches[field]}/{total}')
    print(f"{'risk_flags (set match)':33}  {matches['risk_flags']}/{total}")
    print(f"{'risk_flags (mean Jaccard)':33}  {jaccard_total / total:.3f}")
    print(
        f"{'supporting_image_ids (set match)':33}  "
        f"{matches['supporting_image_ids']}/{total}"
    )
    print(f'\nWrote mismatch details to {EVAL_RESULTS}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--generate',
        action='store_true',
        help='Run the multimodal pipeline on sample inputs before scoring.',
    )
    args = parser.parse_args()
    if args.generate:
        _generate_predictions()
    evaluate()


if __name__ == '__main__':
    main()
