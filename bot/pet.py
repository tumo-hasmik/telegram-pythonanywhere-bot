import json
import time
from bot.clients import store

# Virtual seal pet (Tamagotchi) adopted via /adopt. State lives under
# pet:{user_id} as JSON. Stats decay over REAL time, computed lazily on read
# from the last-interaction timestamp — so no background job is needed (PA's
# free tier has no scheduled tasks). Same graceful-degradation as notes.py:
# without a store, /adopt tells the user memory is off.
#
# By design the seal never dies: neglect just drives fullness/happiness to 0
# ("hungry"/"lonely"), never removal. This is a supportive bot — losing a pet
# you forgot to feed would be a punishing note to strike.

MAX_STAT = 100.0
# Points lost per hour when left alone. Gentle enough that a pet comfortably
# survives a day away, but low enough that daily check-ins matter.
_FULLNESS_DECAY_PER_HOUR = 6.0
_HAPPINESS_DECAY_PER_HOUR = 5.0
# How much each action moves a stat.
_FEED_FULLNESS = 35.0
_PLAY_HAPPINESS = 30.0
_PLAY_FULLNESS_COST = 10.0


def _now() -> float:
    return time.time()


def _clamp(value: float) -> float:
    return max(0.0, min(MAX_STAT, value))


def _decayed(pet: dict, now: float) -> dict:
    """Apply time-decay to fullness/happiness up to `now` and set last_seen.

    Mutates and returns the same dict. Other keys (name, born, msg_id, …) are
    left untouched, so callers can read-modify-write the whole pet safely.
    """
    elapsed_hours = max(0.0, (now - pet.get("last_seen", now)) / 3600.0)
    pet["fullness"] = _clamp(
        pet.get("fullness", MAX_STAT) - _FULLNESS_DECAY_PER_HOUR * elapsed_hours
    )
    pet["happiness"] = _clamp(
        pet.get("happiness", MAX_STAT) - _HAPPINESS_DECAY_PER_HOUR * elapsed_hours
    )
    pet["last_seen"] = now
    return pet


def get_pet(user_id: int) -> dict | None:
    """Return the user's pet with stats decayed to now, or None if none/stateless."""
    if store is None:
        return None
    try:
        data = store.get(f"pet:{user_id}")
        if not data:
            return None
        return _decayed(json.loads(data), _now())
    except Exception as e:
        print(f"Store read error (pet): {e}")
        return None


def save_pet(user_id: int, pet: dict) -> bool:
    if store is None:
        return False
    try:
        store.set(f"pet:{user_id}", json.dumps(pet))
        return True
    except Exception as e:
        print(f"Store write error (pet): {e}")
        return False


def adopt(user_id: int, name: str) -> dict | None:
    """Create a brand-new pet at full stats. Returns the pet, or None if the
    store is unavailable. The caller fills in chat_id/msg_id after sending the
    card and saves again."""
    now = _now()
    pet = {
        "name": name,
        "born": now,
        "last_seen": now,
        "fullness": MAX_STAT,
        "happiness": MAX_STAT,
        "chat_id": None,
        "msg_id": None,
        "is_photo": False,
    }
    return pet if save_pet(user_id, pet) else None


def feed(user_id: int) -> dict | None:
    pet = get_pet(user_id)
    if pet is None:
        return None
    pet["fullness"] = _clamp(pet["fullness"] + _FEED_FULLNESS)
    save_pet(user_id, pet)
    return pet


def play(user_id: int) -> dict | None:
    pet = get_pet(user_id)
    if pet is None:
        return None
    pet["happiness"] = _clamp(pet["happiness"] + _PLAY_HAPPINESS)
    pet["fullness"] = _clamp(pet["fullness"] - _PLAY_FULLNESS_COST)
    save_pet(user_id, pet)
    return pet


def release(user_id: int) -> None:
    if store is None:
        return
    try:
        store.delete(f"pet:{user_id}")
    except Exception as e:
        print(f"Store delete error (pet): {e}")


def mood(pet: dict) -> str:
    """A one-word mood (with emoji) derived from the pet's stats."""
    fullness = pet.get("fullness", 0)
    happiness = pet.get("happiness", 0)
    if fullness <= 15:
        return "🥺 starving"
    if happiness <= 15:
        return "😢 lonely"
    if fullness >= 70 and happiness >= 70:
        return "😄 thriving"
    if fullness >= 40 and happiness >= 40:
        return "🙂 content"
    return "😟 needs some care"


def _bar(pct: float) -> str:
    filled = max(0, min(5, int(round(pct / 20.0))))
    return "▰" * filled + "▱" * (5 - filled)


def age_days(pet: dict, now: float | None = None) -> int:
    now = _now() if now is None else now
    return max(0, int((now - pet.get("born", now)) // 86400))


def render_pet(pet: dict) -> str:
    """The status card shown in (and edited into) the pinned message. Plain
    text — no Markdown — so a user-chosen name can't break the formatting."""
    fullness = pet.get("fullness", 0)
    happiness = pet.get("happiness", 0)
    days = age_days(pet)
    return (
        f"🦭 {pet.get('name', 'Sealy')} the seal\n"
        f"Mood: {mood(pet)}\n\n"
        f"🍤 Fullness  {_bar(fullness)}  {int(fullness)}%\n"
        f"💛 Happiness {_bar(happiness)}  {int(happiness)}%\n"
        f"🎂 Age: {days} day{'s' if days != 1 else ''}\n\n"
        f"/feed · /play · /pet · /release"
    )
