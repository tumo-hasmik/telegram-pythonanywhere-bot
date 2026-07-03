import json
from datetime import date
from bot.clients import store

# Per-user mood check-ins logged via /mood. Stored as a JSON list under
# mood:{user_id}, each entry {"date": "YYYY-MM-DD", "level": "<level>"}.
# Follows the same graceful-degradation pattern as notes.py / history.py:
# when the store is unavailable (stateless mode or a runtime failure) the
# log behaves as empty and nothing crashes.

MAX_MOODS = 90  # keep roughly the last ~3 months of daily check-ins

# The moods the /mood buttons offer, best → worst. Label = "<emoji> <word>";
# handlers.py shows just the emoji on the button and stores the key. Kept here
# (not in handlers) so future /stats and /streak features share the vocabulary.
MOOD_LEVELS = {
    "great": "😄 Great",
    "good": "🙂 Good",
    "okay": "😐 Okay",
    "down": "😔 Down",
    "awful": "😢 Awful",
}


def get_moods(user_id: int) -> list:
    if store is None:
        return []
    try:
        data = store.get(f"mood:{user_id}")
        return json.loads(data) if data else []
    except Exception as e:
        print(f"Store read error (mood): {e}")
        return []


def log_mood(user_id: int, level: str) -> bool:
    if store is None:
        return False
    try:
        moods = get_moods(user_id)
        moods.append({"date": date.today().isoformat(), "level": level})
        store.set(f"mood:{user_id}", json.dumps(moods[-MAX_MOODS:]))
        return True
    except Exception as e:
        print(f"Store write error (mood): {e}")
        return False
