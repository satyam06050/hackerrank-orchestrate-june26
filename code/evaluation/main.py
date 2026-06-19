import os
import sys
from pprint import pprint

# Ensure code/ is on sys.path so imports work when run as a script
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from main import load_csvs, build_history_note, lookup_evidence_requirement, validate_and_repair


def run_sample_checks():
    pipeline = load_csvs()
    sample_rows = pipeline.claims[:2]
    results = []
    for row in sample_rows:
        user_id = row.get('user_id')
        print(f"\n--- Processing sample row for {user_id} ---")
        note, flags = build_history_note(pipeline, user_id)
        print("History note:", note)
        print("History flags:", flags)

        # choose an issue_family for lookup using row's issue_type if present
        issue_family = row.get('issue_type', '')
        evidence_req = lookup_evidence_requirement(pipeline, row.get('claim_object'), issue_family)
        print('Evidence requirement (matched):')
        pprint(evidence_req)

        # Create a fake raw model output with some intentional invalids to exercise validation
        fake_raw = {
            'claim_status': 'Supported',
            'issue_type': row.get('issue_type', 'unknown'),
            'object_part': row.get('object_part', 'unknown'),
            'severity': 'Medium',
            'evidence_standard_met': 'yes',
            'evidence_standard_met_reason': '',
            'risk_flags': 'blurry_image;not_a_flag',
            'supporting_image_ids': 'img_1;img_999',
            'valid_image': 'True',
            'claim_status_justification': '',
        }

        repaired = validate_and_repair(pipeline, fake_raw, row)
        print('Repaired result:')
        pprint(repaired)
        results.append(repaired)

    # Write a small evaluation report with repair counters
    report_path = os.path.join(os.path.dirname(__file__), 'evaluation_report.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('# Evaluation Repair Report\n\n')
        f.write('Repair counters:\n\n')
        for k, v in sorted(pipeline.repair_counters.items()):
            f.write(f'- {k}: {v}\n')

    print('\nWrote evaluation report to', report_path)


if __name__ == '__main__':
    run_sample_checks()
