import os
import sys
from pathlib import Path
import traceback
import logging

from dotenv import load_dotenv

# Load .env
load_dotenv()

# === SMART PROJECT ROOT DETECTION ===
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR

for _ in range(6):  # walk up max 6 levels
    if (PROJECT_ROOT / "code").exists() or (PROJECT_ROOT / "dataset").exists():
        break
    PROJECT_ROOT = PROJECT_ROOT.parent

print(f"Detected PROJECT_ROOT = {PROJECT_ROOT}")

# Add paths
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "code"))

try:
    import code.main as main
    print("✅ Successfully imported code.main")
except ImportError as e:
    print("❌ Could not import code.main")
    print("Error:", e)
    print("\nCurrent sys.path:")
    for p in sys.path[:8]:
        print("   ", p)
    sys.exit(1)

def main_debug():
    print("\n" + "=" * 100)
    print("          PIPELINE DEBUG RUNNER (Images Fixed)")
    print("=" * 100)

    print(f"PROJECT_ROOT = {PROJECT_ROOT}")
    print(f"DATASET_DIR  = {getattr(main, 'DATASET_DIR', 'NOT_FOUND')}")

    gemini_key = os.getenv("GEMINI_API_KEY")
    print(f"GEMINI_API_KEY     = {'[SET]' if gemini_key else '[MISSING]'}")
    print(f"requests available = {'yes' if getattr(main, 'requests', None) is not None else 'no'}")
    print(f"genai available    = {'yes' if getattr(main, 'genai', None) is not None else 'no'}")

    # Load data
    try:
        pipeline = main.load_csvs()
        print(f"✅ Loaded {len(pipeline.claims)} claims")
    except Exception as e:
        print("❌ Failed to load CSVs:", e)
        traceback.print_exc()
        return

    # Find test case
    row = next((r for r in pipeline.claims if r.get("user_id") == "user_001"), None)

    if not row:
        print("⚠️ user_001 not found in claims.csv, trying sample...")
        try:
            import csv
            for sp in [
                PROJECT_ROOT / "dataset" / "sample_claims.csv",
                PROJECT_ROOT / "code" / "dataset" / "sample_claims.csv"
            ]:
                if sp.exists():
                    with open(sp, newline="", encoding="utf-8") as f:
                        row = next((r for r in csv.DictReader(f) if r.get("user_id") == "user_001"), None)
                    if row:
                        break
        except Exception as e:
            print("Sample load failed:", e)

    if not row:
        print("❌ user_001 not found. Check your dataset.")
        return

    print(f"\n✅ Processing: user_001 → {row.get('claim_object')} | {row.get('user_claim')[:80]}...")

    # Show raw image paths
    raw_images = row.get("image_paths", "")
    print(f"\nRaw 'image_paths' from CSV: '{raw_images}'")

    # Setup logging to see image loading details
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    # Encode images (using the improved function)
    images = main._encode_images(raw_images)

    print(f"\n✅ Encoded {len(images)} image(s)")
    for img_id, b64 in images.items():
        print(f"   • {img_id} → {len(b64)//1024} KB")

    # Build context
    note, flags = main.build_history_note(pipeline, row.get("user_id"))
    evidence = main.lookup_evidence_requirement(
        pipeline, row.get("claim_object"), row.get("issue_type")
    )

    system_prompt = main._load_system_prompt()
    print(f"\nSystem prompt length: {len(system_prompt)} chars")

    # Build user message
    pieces = [
        f"Claim object: {row.get('claim_object')}",
        f"User claim: {row.get('user_claim')}",
    ]
    if evidence and evidence.get("minimum_image_evidence"):
        pieces.append(f"Evidence requirement: {evidence.get('minimum_image_evidence')}")
    pieces.append(f"History note: {note}")

    if images:
        pieces.append(f"Images: {', '.join(images.keys())}")

    user_message = "\n\n".join(pieces)

    print("\n--- USER MESSAGE PREVIEW (first 700 chars) ---")
    preview = user_message[:700] + ("..." if len(user_message) > 700 else "")
    print(preview)

    print(f"\n--- CALLING MODEL REQUEST ({len(images)} images) ---")

    try:
        raw = main._send_model_request(system_prompt, user_message, images)
        print("\n--- RAW RESPONSE ---")
        print(raw[:2000] + ("..." if len(raw) > 2000 else ""))

        import json
        parsed = json.loads(raw)
        print("\n✅ JSON parsed successfully!")
        print("Keys:", list(parsed.keys()))

    except Exception as e:
        print("\n❌ ERROR:")
        traceback.print_exc()


if __name__ == "__main__":
    main_debug()