import json
from bot.clients import store

# Per-user notes saved via /remember and listed via /recall. Stored as a
# JSON list under notes:{user_id} so a user can keep more than one note.
# Follows the same graceful-degradation pattern as history.py: when the
# store is unavailable (stateless mode or a runtime failure) notes just
# behave as empty and nothing crashes.

MAX_NOTES = 50


def get_notes(user_id: int) -> list:
    if store is None:
        return []
    try:
        data = store.get(f"notes:{user_id}")
        return json.loads(data) if data else []
    except Exception as e:
        print(f"Store read error (notes): {e}")
        return []


def add_note(user_id: int, note: str) -> bool:
    if store is None:
        return False
    try:
        notes = get_notes(user_id)
        notes.append(note)
        store.set(f"notes:{user_id}", json.dumps(notes[-MAX_NOTES:]))
        return True
    except Exception as e:
        print(f"Store write error (notes): {e}")
        return False


def clear_notes(user_id: int) -> None:
    if store is None:
        return
    try:
        store.delete(f"notes:{user_id}")
    except Exception as e:
        print(f"Store delete error (notes): {e}")
