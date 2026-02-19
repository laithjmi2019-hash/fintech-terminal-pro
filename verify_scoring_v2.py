from app.scoring import calculate_scores
import json

try:
    scores = calculate_scores("NVDA")
    print("Success!")
    print(f"Full Output: {json.dumps(scores, indent=2)}")
except Exception as e:
    print(f"CRASH DETECTED: {e}")
