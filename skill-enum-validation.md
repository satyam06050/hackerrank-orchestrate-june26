# SKILL: enum-validation-and-repair

## When to use
Use whenever post-processing the raw JSON returned by the claim
classification model call, before writing a row to output.csv.

## Why this matters
Grading likely checks exact membership in the allowed value lists. A
single invalid string (extra word, wrong casing, synonym) silently fails
the column even if the underlying judgment was correct. This is pure
Python, zero API cost, and the highest-leverage 30 minutes of the whole
build.

## Allowed value sets (hardcode as Python sets/lists)

```python
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
```

## Repair rules (deterministic fallback, never re-prompt the model)

| Field | If invalid/missing | Fallback |
|---|---|---|
| `claim_status` | not in set | `"not_enough_information"` |
| `issue_type` | not in set | `"unknown"` |
| `object_part` | not in set for the row's claim_object | `"unknown"` |
| `severity` | not in set | `"unknown"` |
| `evidence_standard_met` / `valid_image` | not strict bool | coerce truthy strings ("true"/"True"/True -> True), else `False` |
| `risk_flags` | any entries not in set | drop the invalid entries; if result empty, use `["none"]` |
| `supporting_image_ids` | contains an id not present in this row's image_paths | drop it; if result empty, use `["none"]` |
| `*_reason` / `*_justification` | empty string | substitute a generic templated sentence referencing claim_object and issue_type, and increment a `low_quality_justification` counter for the eval report |

## Cross-field consistency checks (apply after individual repairs)

- If `evidence_standard_met == False`, force `claim_status =
  "not_enough_information"` UNLESS the model already explicitly chose
  `not_enough_information` (don't override `contradicted` results that
  came with evidence_standard_met=true — that's a valid combination, see
  prompt.md Example 3/4).
- If `claim_status == "not_enough_information"`, force
  `supporting_image_ids = ["none"]` unless evidence_standard_met is true
  (rare partial-evidence case).
- If `issue_type == "none"`, severity should be `"none"` (snap it if the
  model returned something else).
- Join `image_paths` to derive the valid set of image_ids for the row
  (filename stem of each path) and use that set for the
  `supporting_image_ids` filter above.

## Logging requirement
Keep a counter dict of every repair applied (by field name) across the
whole run. Dump this into `evaluation/evaluation_report.md` as a short
"data quality / repair stats" section — this demonstrates you handled
model unreliability deliberately rather than hoping for clean output.