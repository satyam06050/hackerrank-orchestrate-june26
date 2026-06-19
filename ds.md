claims.csv
"user_id","image_paths","user_claim","claim_object"
eg:"user_008","images/test/case_006/img_1.jpg","Customer: Hi, I am not sure if I am filing this in the right place, so please bear with me for a minute. | Support: No problem, tell me what happened. | Customer: The weather was bad last night and I had parked outside because the covered parking was full. In the morning I was already late, so I did not inspect the car properly. | Support: When did you first notice a possible issue? | Customer: Later in the day, after a colleague mentioned that my car looked a little different from the front. I walked around it twice and honestly could not decide if I was overthinking it. | Support: Which area should we review? | Customer: I first checked the windshield and the sides, but those are not what I want to claim. | Support: Okay, what is the actual damage claim? | Customer: The hood seems to have small hail dents, so please review the hood for hail damage.","car"

evidence_requirements.csv
"requirement_id","claim_object","applies_to","minimum_image_evidence"
eg:"REQ_GENERAL_OBJECT_PART","all","general claim review","The claimed object and relevant part should be visible clearly enough to inspect the claimed condition."

output.csv
"user_id","image_paths","user_claim","claim_object","evidence_standard_met","evidence_standard_met_reason","risk_flags","issue_type","object_part","claim_status","claim_status_justification","supporting_image_ids","valid_image","severity"

sample_claims.csv
"user_id","image_paths","user_claim","claim_object","evidence_standard_met","evidence_standard_met_reason","risk_flags","issue_type","object_part","claim_status","claim_status_justification","supporting_image_ids","valid_image","severity"
eg:"user_018","images/sample/case_013/img_1.jpg","Customer: I am not sure if this should be a repair claim or a replacement claim, so I wanted to ask first. | Support: We can help. What device is this about? | Customer: It is my laptop. I carry it every day, and yesterday my bag got pressed between two seats during travel. At first I thought the laptop was okay because it still opened. | Support: What changed after that? | Customer: Later, while using it, I noticed marks on the display area. I restarted it twice because I thought it might just be something on the screen, but it still bothered me. | Support: Are you reporting keyboard, hinge, body, or screen damage? | Customer: Not the keyboard or hinge. The issue I want checked is the screen. It looks shattered to me, so I am submitting this as screen damage.","laptop","true","The laptop screen is visible and the crack pattern can be verified from the submitted image.","none","crack","screen","supported","The image supports the claim because the laptop screen has visible cracking consistent with the user's screen damage report.","img_1","true","medium"

user_history.csv
"user_id","past_claim_count","accept_claim","manual_review_claim","rejected_claim","last_90_days_claim_count","history_flags","history_summary"
eg:"user_005","7","2","2","3","4","user_history_risk","Several exaggerated vehicle damage claims in recent history"


