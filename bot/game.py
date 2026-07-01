"""Song-guessing game — the /game command.

Pulls ~30s song previews from the public iTunes Search API and stores a
per-user "current song" so plain text messages can be checked as guesses.

State lives in the KV store under game:{user_id} (JSON), mirroring the
graceful-degradation pattern in history.py. The game needs the store: each
Telegram message is a separate webhook request, so the current answer must
survive between requests. In stateless mode (store is None) the game is
unavailable and the handler tells the user so.

PA note: this calls itunes.apple.com to fetch the song list. Telegram itself
downloads the audio preview (audio-ssl.itunes.apple.com), so only
itunes.apple.com needs to be reachable from the worker — check the PA
outbound whitelist if /game fails on PythonAnywhere but works locally.
"""

import json
import random
import re

import requests

from bot.clients import store

ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
REQUEST_TIMEOUT = 10  # seconds — fail fast so a slow API can't wedge the worker
GAME_TTL = 3600  # a game with no activity for an hour is forgotten
MAX_ATTEMPTS = 3  # wrong guesses before the answer is revealed

# Each round picks one of these at random, queries iTunes, then picks a random
# track that has a playable preview. Broad + popular so guesses feel fair.
SEARCH_TERMS = [
    "Taylor Swift", "Ed Sheeran", "The Beatles", "Queen", "Coldplay",
    "Adele", "Bruno Mars", "Billie Eilish", "Michael Jackson", "Weezer",
    "Imagine Dragons", "Dua Lipa", "The Weeknd", "Ariana Grande", "Maroon 5",
    "Katy Perry", "Rihanna", "Beyonce", "Lady Gaga", "Elton John",
    "ABBA", "Nirvana", "Green Day", "Red Hot Chili Peppers", "Lana Del Rey",
]


def _normalize(text: str) -> str:
    """Lowercase and strip parenthetical suffixes + punctuation.

    So "My Name Is Jonas (2024 Remaster)" and "my name is jonas!" compare
    equal — the exact iTunes title is rarely what a player types.
    """
    text = re.sub(r"[\(\[].*?[\)\]]", "", text or "")  # drop (Remaster), [Live]
    text = text.lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_song():
    """Fetch a random song that has a playable preview.

    Returns {title, artist, preview_url} or None on network/parse failure
    or if nothing playable came back.
    """
    term = random.choice(SEARCH_TERMS)
    try:
        resp = requests.get(
            ITUNES_SEARCH_URL,
            params={"term": term, "media": "music", "entity": "song", "limit": 50},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
    except (requests.RequestException, ValueError) as e:
        print(f"iTunes fetch error: {e}")
        return None
    playable = [r for r in results if r.get("previewUrl") and r.get("trackName")]
    if not playable:
        return None
    pick = random.choice(playable)
    return {
        "title": pick["trackName"],
        "artist": pick.get("artistName", "Unknown artist"),
        "preview_url": pick["previewUrl"],
    }


def check_guess(guess: str, answer_title: str) -> bool:
    """True if the guess plausibly names the song.

    Exact normalized match, or one string contained in the other (guarded
    by a length floor so trivially short guesses can't win by substring).
    """
    g = _normalize(guess)
    a = _normalize(answer_title)
    if not g or not a:
        return False
    if g == a:
        return True
    return (len(a) >= 4 and a in g) or (len(g) >= 4 and g in a)


def _key(user_id: int) -> str:
    return f"game:{user_id}"


def get_game(user_id: int):
    if store is None:
        return None
    try:
        data = store.get(_key(user_id))
        return json.loads(data) if data else None
    except Exception as e:
        print(f"Store read error (game): {e}")
        return None


def save_game(user_id: int, state: dict) -> bool:
    if store is None:
        return False
    try:
        store.set(_key(user_id), json.dumps(state), ex=GAME_TTL)
        return True
    except Exception as e:
        print(f"Store write error (game): {e}")
        return False


def end_game(user_id: int) -> None:
    if store is None:
        return
    try:
        store.delete(_key(user_id))
    except Exception as e:
        print(f"Store delete error (game): {e}")


def is_active(user_id: int) -> bool:
    return get_game(user_id) is not None
