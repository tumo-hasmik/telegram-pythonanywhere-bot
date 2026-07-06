import json
import os
import random
import threading
import time
from datetime import datetime

from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.clients import bot, BOT_INFO, store
from bot.config import (
    COMMIT_SHA,
    HF_SPACE_ID,
    HOSTING_LABEL,
    MODEL,
    RATE_LIMIT,
    SEAL_STICKER_SET,
)
from bot.ai import ask_ai
from bot.helpers import is_allowed, keep_typing, send_reply, should_respond
from bot.history import clear_history
from bot.notes import add_note, clear_notes, get_notes
from bot.mood import MOOD_LEVELS, log_mood
from bot.pet import adopt, feed, get_pet, play, release, render_pet, save_pet
from bot.game import (
    MAX_ATTEMPTS,
    _normalize,
    check_guess,
    end_game,
    fetch_song,
    get_game,
    is_active,
    save_game,
)
from bot.preferences import get_provider, set_provider
from bot.providers import generate
from bot.rate_limit import is_rate_limited

# Verbose console logging for local dev and teaching. Enabled by
# BOT_VERBOSE_LOG=1 (run_local.py sets this automatically). Prints one
# line per inbound/outbound message so kids and teachers can see the
# conversation flow in their terminal while the bot is running.
VERBOSE_LOG = os.environ.get("BOT_VERBOSE_LOG", "").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)


def _log(message, direction: str, text: str) -> None:
    """Print a one-line trace of a message in verbose mode.

    direction is "in" (user → bot) or "out" (bot → user). Text is
    truncated to 500 characters so long AI replies don't flood the
    terminal. Newlines are collapsed for single-line readability.
    """
    if not VERBOSE_LOG:
        return
    user = message.from_user
    user_name = (
        f"@{user.username}" if user.username else (user.first_name or f"user:{user.id}")
    )
    bot_name = f"@{BOT_INFO.username}"
    snippet = (text or "").replace("\n", " ").replace("\r", " ")
    if len(snippet) > 500:
        snippet = snippet[:500] + "..."
    if direction == "in":
        sender, receiver = user_name, bot_name
    else:
        sender, receiver = bot_name, user_name
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {sender} → {receiver}: {snippet}", flush=True)


@bot.message_handler(commands=["start"], func=is_allowed)
def cmd_start(message):
    bot.send_message(
        message.chat.id,
        "Hii! 🦭 🦭 I'm your AI assistant-seal. Send me a message to get started(˶˃ ᵕ ˂˶) \n\nUse /help to know me better)) DISCLAIMER: I'm not a professional specialist so you should see a trusted doctor if your problems are more complicated, I'm just talking to people so they SHORTLY forget about their problems.",
    )

@bot.message_handler(commands=["cute"], func=is_allowed)
def cmd_joke(message):
 reply = ask_ai(message.from_user.id, "write a cute poem about the user.")
 bot.send_message(message.chat.id, reply)


# ── Seal stickers (/sealie) ──────────────────────────────────────────────────
# Sends a random sticker from the configured seal pack (SEAL_STICKER_SET).
# The pack's sticker file_ids are fetched once from Telegram and cached, since
# a public pack's contents rarely change and re-fetching on every call is waste.
_seal_sticker_ids: list = []


def _get_seal_sticker_ids() -> list:
    """Return cached seal sticker file_ids, fetching the pack once on first use."""
    global _seal_sticker_ids
    if _seal_sticker_ids:
        return _seal_sticker_ids
    try:
        sticker_set = bot.get_sticker_set(SEAL_STICKER_SET)
        _seal_sticker_ids = [s.file_id for s in sticker_set.stickers]
    except Exception as e:
        print(f"Could not load seal sticker set {SEAL_STICKER_SET!r}: {e}")
    return _seal_sticker_ids


@bot.message_handler(commands=["sealie"], func=is_allowed)
def cmd_sealie(message):
    sticker_ids = _get_seal_sticker_ids()
    if not sticker_ids:
        bot.send_message(
            message.chat.id, "My seal stickers are napping right now 🦭 Try again later!"
        )
        return
    bot.send_sticker(message.chat.id, random.choice(sticker_ids))


@bot.message_handler(commands=["poem"], func=is_allowed)
def cmd_poem(message):
    # ask_ai loads this user's conversation history and prepends it, so the
    # model can write about the person based on what they've talked about.
    reply = ask_ai(
        message.from_user.id,
        "Write a short, warm poem about me based on our previous conversation — "
        "what I've talked about, my mood, and the little things I've shared. "
        "If we haven't talked much yet, write a gentle poem welcoming me.",
    )
    bot.send_message(message.chat.id, reply)


@bot.message_handler(commands=["joke"], func=is_allowed)
def cmd_joke(message):
 reply = ask_ai(message.from_user.id, "Tell one really funny gen Z joke to burst out laughing.")
 bot.send_message(message.chat.id, reply)


@bot.message_handler(commands=["quote"], func=is_allowed)
def cmd_joke(message):
 reply = ask_ai(message.from_user.id, "Tell me 1 really deep quote that will make me question my life choices.")
 bot.send_message(message.chat.id, reply)


@bot.message_handler(commands=["fact"], func=is_allowed)
def cmd_joke(message):
 reply = ask_ai(message.from_user.id, "Tell me 1 fact about seals/ ocean/ underwater life.")
 bot.send_message(message.chat.id, reply)

@bot.message_handler(commands=["remember"], func=is_allowed)
def cmd_remember(message):
    parts = (message.text or "").split(maxsplit=1)
    note = parts[1].strip() if len(parts) > 1 else ""
    if not note:
        bot.send_message(
            message.chat.id, "What should I remember? Try: /remember buy milk 📝"
        )
        return
    if add_note(message.from_user.id, note):
        bot.send_message(message.chat.id, "Saved! 📝 Use /recall to see your notes.")
    else:
        bot.send_message(
            message.chat.id, "I couldn't save that right now — memory is off."
        )


@bot.message_handler(commands=["recall"], func=is_allowed)
def cmd_recall(message):
    # No AI — just read back the notes saved via /remember.
    notes = get_notes(message.from_user.id)
    if not notes:
        bot.send_message(
            message.chat.id, "You have no saved notes yet. Save one with /remember 📝"
        )
        return
    lines = ["📝 Your saved notes:"]
    lines += [f"{i}. {note}" for i, note in enumerate(notes, 1)]
    bot.send_message(message.chat.id, "\n".join(lines))


@bot.message_handler(commands=["forget"], func=is_allowed)
def cmd_forget(message):
    # No AI — clear all notes saved via /remember.
    if not get_notes(message.from_user.id):
        bot.send_message(
            message.chat.id, "You have no saved notes to forget. 📝"
        )
        return
    clear_notes(message.from_user.id)
    bot.send_message(message.chat.id, "Done — I've forgotten all your notes. 🧽")

 
@bot.message_handler(commands=["compliment"], func=is_allowed)
def cmd_joke(message):
 reply = ask_ai(message.from_user.id, "Make me a compliment that'll make me blush so hard.")
 bot.send_message(message.chat.id, reply)

@bot.message_handler(commands=["roast"], func=is_allowed)
def cmd_roast(message):
    # Optional target: "/roast my playlist". Defaults to roasting the sender.
    parts = (message.text or "").split(maxsplit=1)
    target = parts[1].strip() if len(parts) > 1 else "the person talking to you"
    reply = ask_ai(
        message.from_user.id,
        f"Write a short, playful, friendly (never mean or hurtful) roast of {target}.",
    )
    bot.send_message(message.chat.id, reply)


@bot.message_handler(commands=["roll"], func=is_allowed)
def cmd_roll(message):
    # No AI — just a plain dice roll. Optional arg sets the number of
    # sides, e.g. "/roll 20" for a d20. Defaults to a 6-sided die.
    parts = (message.text or "").split(maxsplit=1)
    sides = 6
    if len(parts) > 1:
        try:
            sides = int(parts[1].strip())
        except ValueError:
            bot.send_message(
                message.chat.id, "Give me a number of sides, like /roll 20 🎲"
            )
            return
        if sides < 2:
            bot.send_message(
                message.chat.id, "A die needs at least 2 sides! 🎲"
            )
            return
    result = random.randint(1, sides)
    bot.send_message(message.chat.id, f"🎲 You rolled a {result} (d{sides})")


@bot.message_handler(commands=["help"], func=is_allowed)
def cmd_help(message):
    lines = [
        ask_ai(message.from_user.id, "In 2-3 sentences, introduce yourself and tell me how you can help."),
        "",
        "Here's what I can do 🦭",
        "",
        "💬 Just talk to me — I'm here to listen and chat.",
        "/sealie — send a random seal sticker",
        "/poem — a little poem about you, from our chats",
        "/cute — a cute poem about you",
        "/compliment — a compliment to make you blush",
        "/joke — a funny gen Z joke",
        "/roast — a playful, friendly roast",
        "/quote — a deep quote to ponder",
        "/fact — a fact about seals & the ocean",
        "/mood — check in on how you're feeling",
        "/breathe — a calming 4-7-8 breathing exercise",
        "/remember · /recall · /forget — save & read little notes",
        "/roll — roll a die (e.g. /roll 20)",
        "/trivia — a quick trivia question",
        "/game · /hint · /skip · /endgame — guess-the-song game",
        "/dice · /dart · /basket · /bowl · /slots — beat the seal",
        "/adopt · /feed · /play · /pet · /release — raise a seal pet",
        "/reset — clear our conversation",
        "/about — what's under the hood",
    ]
    if HF_SPACE_ID:
        lines.append("/model — switch AI provider")
    bot.send_message(message.chat.id, "\n".join(lines))


@bot.message_handler(commands=["sha"], func=is_allowed)
# def cmd_reset(message):
#     clear_history(message.from_user.id)
#     bot.send_message(message.chat.id, "Conversation cleared. Starting fresh!")


@bot.message_handler(commands=["reset"], func=is_allowed)
def cmd_reset(message):
    clear_history(message.from_user.id)
    bot.send_message(message.chat.id, "Conversation cleared. Starting fresh!")


@bot.message_handler(commands=["about"], func=is_allowed)
def cmd_about(message):
    if HF_SPACE_ID:
        provider = get_provider(message.from_user.id)
        model_line = f"{MODEL} (main)" if provider == "main" else f"{HF_SPACE_ID} (hf)"
    else:
        model_line = MODEL
    storage_line = "SQLite" if store is not None else "stateless (no memory)"
    lines = [
          "🦭 I'm your AI assistant-seal — here to chat and lend a flipper.",
          "",
          f"🧠 Model: {model_line}",
          f"💾 Memory: {storage_line}",
          f"☁️ Hosted on: {HOSTING_LABEL}",
      ]
    if COMMIT_SHA:
        lines.append(f"Version: {COMMIT_SHA}")
    bot.send_message(message.chat.id, "\n".join(lines))


@bot.message_handler(commands=["sha"], func=is_allowed)
def cmd_sha(message):
    sha = COMMIT_SHA or "unknown"
    bot.send_message(message.chat.id, f"Live SHA: {sha}")


# ── Mood check-in (/mood) ────────────────────────────────────────────────────
# Emoji buttons; tapping one logs the mood (bot/mood.py) and gets a warm,
# non-judgmental reply. No AI call — instant, free, and deterministic.

_MOOD_REPLIES = {
    "great": "Yesss! 🦭✨ So glad you're feeling great — soak it up!",
    "good": "Love that for you 🙂🌊 Glad today's being kind.",
    "okay": "Okay is completely valid 😌 I'm floating right here with you 🦭",
    "down": "Sorry you're feeling down 🫂 Thanks for telling me. Want to talk it out, hear a /joke, or play a /game?",
    "awful": "That sounds really heavy 🫂 I'm here with you. If it stays this rough, please lean on someone you trust too 🦭",
}


@bot.message_handler(commands=["mood"], func=is_allowed)
def cmd_mood(message):
    markup = InlineKeyboardMarkup(row_width=5)
    markup.add(
        *[
            InlineKeyboardButton(label.split()[0], callback_data=f"mood:{level}")
            for level, label in MOOD_LEVELS.items()
        ]
    )
    bot.send_message(
        message.chat.id, "How are you feeling right now? Tap one 🦭", reply_markup=markup
    )


@bot.callback_query_handler(func=lambda c: (c.data or "").startswith("mood:"))
def cb_mood(call):
    level = (call.data or "").split(":", 1)[1]
    log_mood(call.from_user.id, level)  # no-op in stateless mode
    try:
        bot.answer_callback_query(call.id)
    except Exception as e:
        print(f"answer_callback_query error: {e}")
    bot.send_message(
        call.message.chat.id, _MOOD_REPLIES.get(level, "Thanks for checking in 🦭")
    )


# ── Guided breathing (/breathe) ──────────────────────────────────────────────
# A 4-7-8 exercise animated by editing one message. The timed steps run in a
# background daemon thread (like keep_typing) so the webhook handler returns
# immediately — blocking ~40s inline would tie up PA's single worker and trip
# Telegram's webhook-timeout retry.

_BREATHE_STEPS = [("Breathe in… 🫁", 4), ("Hold… ✨", 7), ("Breathe out… 🌬️", 8)]
_BREATHE_CYCLES = 3


def _run_breathing(chat_id: int, message_id: int) -> None:
    try:
        for cycle in range(_BREATHE_CYCLES):
            for text, seconds in _BREATHE_STEPS:
                bot.edit_message_text(
                    f"{text}\n\ncycle {cycle + 1}/{_BREATHE_CYCLES}", chat_id, message_id
                )
                time.sleep(seconds)
        bot.edit_message_text(
            "Nicely done 🦭💙 However you feel now is okay.", chat_id, message_id
        )
    except Exception as e:
        print(f"/breathe animation error: {e}")


@bot.message_handler(commands=["breathe"], func=is_allowed)
def cmd_breathe(message):
    sent = bot.send_message(message.chat.id, "Let's breathe together 🦭 Follow along…")
    threading.Thread(
        target=_run_breathing, args=(message.chat.id, sent.message_id), daemon=True
    ).start()


# ── Telegram mini-games (/dice /dart /basket /bowl /slots) ───────────────────
# "Beat the seal": the bot throws for you and for itself; higher value wins.
# Uses Telegram's native animated dice — zero external calls, so these work on
# PythonAnywhere even when the /game song fetch (iTunes) doesn't.

# command -> (emoji, higher_value_wins). Slots has no ordering, so it's judged
# by jackpot (value 64) instead.
_MINIGAMES = {
    "dice": ("🎲", True),
    "dart": ("🎯", True),
    "basket": ("🏀", True),
    "bowl": ("🎳", True),
    "slots": ("🎰", False),
}
# Telegram's dice animation takes ~3s to settle; wait before announcing so the
# verdict doesn't spoil the reveal.
_DICE_REVEAL_SECONDS = 3


def _minigame_outcome(user_id: int, cmd: str, your_val: int, seal_val: int) -> str:
    """Build the result message and record a win. Pure logic — no Telegram I/O."""
    _, higher_wins = _MINIGAMES.get(cmd, ("🎲", True))
    won = False
    if not higher_wins:  # slots: only the 64 jackpot counts as a win
        if your_val == 64:
            result, won = "🎰 JACKPOT!! You win! 🦭🎉", True
        else:
            result = "🎰 No jackpot this spin — try again? 🦭"
    elif your_val > seal_val:
        result, won = f"You threw {your_val}, I got {seal_val} — you win! 🦭🎉", True
    elif your_val < seal_val:
        result = f"You threw {your_val}, I got {seal_val} — I win this one! 🦭"
    else:
        result = f"We both landed on {your_val} — it's a tie! 🤝🦭"
    if won and store is not None:
        try:
            wins = store.incr(f"minigame_wins:{user_id}")
            if wins:
                result += f"\nWins vs. the seal: {wins} 🏆"
        except Exception as e:
            print(f"minigame win incr error: {e}")
    return result


@bot.message_handler(commands=list(_MINIGAMES.keys()), func=is_allowed)
def cmd_minigame(message):
    # message.text is like "/dart" or "/dart@BotName" — recover the command.
    cmd = (message.text or "").split()[0].lstrip("/").split("@")[0].lower()
    emoji, _ = _MINIGAMES.get(cmd, ("🎲", True))
    chat_id = message.chat.id
    you = bot.send_dice(chat_id, emoji=emoji)
    seal = bot.send_dice(chat_id, emoji=emoji)
    result = _minigame_outcome(
        message.from_user.id, cmd, you.dice.value, seal.dice.value
    )

    # Announce after the animation settles, from a daemon thread so the webhook
    # handler returns immediately (same reasoning as /breathe).
    def announce():
        time.sleep(_DICE_REVEAL_SECONDS)
        try:
            bot.send_message(chat_id, result)
        except Exception as e:
            print(f"minigame announce error: {e}")

    threading.Thread(target=announce, daemon=True).start()


# ── Trivia (/trivia) ─────────────────────────────────────────────────────────
# One AI-written multiple-choice question delivered as a native Telegram quiz
# poll (Telegram scores the answer). Uses generate() directly with a one-off
# prompt so the seal persona + chat history don't corrupt the JSON.

_TRIVIA_PROMPT = (
    "Generate ONE fun, light general-knowledge trivia question suitable for teens. "
    "Reply with ONLY valid JSON (no markdown, no prose) in exactly this shape: "
    '{"question": "...", "options": ["a", "b", "c", "d"], "correct_index": 0, '
    '"explanation": "..."}. '
    "options must have exactly 4 entries; correct_index is 0-3; explanation is one short sentence."
)
_TRIVIA_FALLBACK = {
    "question": "🦭 Which is the largest ocean on Earth?",
    "options": ["Atlantic", "Indian", "Pacific", "Arctic"],
    "correct_index": 2,
    "explanation": "The Pacific is the largest and deepest ocean.",
}


def _extract_json(raw: str) -> str:
    """Pull the JSON object out of a model reply that may be fenced or padded."""
    text = (raw or "").strip()
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start != -1 and end > start else text


def _make_trivia() -> dict:
    """Ask the model for a quiz question; fall back to a canned one if the
    reply isn't usable JSON. Always returns a validated dict."""
    try:
        raw = generate(0, [{"role": "user", "content": _TRIVIA_PROMPT}])
        data = json.loads(_extract_json(raw))
        question = str(data["question"]).strip()
        options = data["options"]
        idx = int(data["correct_index"])
        if (
            not question
            or not isinstance(options, list)
            or len(options) != 4
            or not 0 <= idx <= 3
        ):
            raise ValueError("trivia JSON failed validation")
        return {
            "question": question,
            "options": [str(o).strip() for o in options],
            "correct_index": idx,
            "explanation": str(data.get("explanation", "")).strip()[:200],
        }
    except Exception as e:
        print(f"/trivia generation failed, using fallback: {e}")
        return dict(_TRIVIA_FALLBACK)


@bot.message_handler(commands=["trivia"], func=is_allowed)
def cmd_trivia(message):
    q = _make_trivia()
    try:
        bot.send_poll(
            message.chat.id,
            q["question"],
            q["options"],
            type="quiz",
            correct_option_id=q["correct_index"],
            is_anonymous=False,
            explanation=q["explanation"] or None,
        )
    except Exception as e:
        print(f"send_poll error: {e}")
        bot.send_message(
            message.chat.id, "Couldn't start trivia right now 😔 Try again in a bit 🦭"
        )


# ── Virtual seal pet (/adopt /feed /play /pet /release) ──────────────────────
# A Tamagotchi seal that lives in a PINNED message — the closest Telegram lets
# a bot get to "always on screen" (a bot can't float an image in the chat
# corner; it CAN pin a message to the top bar). Actions edit that same message
# in place. The card is a real photo when assets/seal.* is bundled, else a cute
# emoji status card — either way whitelist-proof (local file / no fetch). Stats
# decay over real time; state + logic live in bot/pet.py. Needs the store.

# Detected once at import: the bundled seal image, if the owner added one.
_SEAL_IMAGE = None
for _seal_name in ("seal.jpg", "seal.jpeg", "seal.png", "seal.webp"):
    _seal_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", _seal_name
    )
    if os.path.exists(_seal_path):
        _SEAL_IMAGE = _seal_path
        break


def _send_pet_card(chat_id: int, pet: dict):
    """Send the pet card as a photo (if a seal image is bundled) or as text.
    Returns (sent_message, is_photo)."""
    card = render_pet(pet)
    if _SEAL_IMAGE:
        try:
            with open(_SEAL_IMAGE, "rb") as image:
                return bot.send_photo(chat_id, image, caption=card), True
        except Exception as e:
            print(f"send_photo (pet) failed, falling back to text: {e}")
    return bot.send_message(chat_id, card), False


def _edit_pet_card(pet: dict) -> bool:
    """Edit the pinned card in place to reflect current stats. Returns False if
    it couldn't (e.g. the message was deleted) so the caller can re-send."""
    msg_id = pet.get("msg_id")
    chat_id = pet.get("chat_id")
    if not msg_id or not chat_id:
        return False
    card = render_pet(pet)
    try:
        if pet.get("is_photo"):
            bot.edit_message_caption(caption=card, chat_id=chat_id, message_id=msg_id)
        else:
            bot.edit_message_text(card, chat_id, msg_id)
        return True
    except Exception as e:
        print(f"edit pet card failed: {e}")
        return False


def _refresh_card(message, pet: dict) -> None:
    """Update the pinned card; if the old message is gone, re-send and re-pin."""
    if _edit_pet_card(pet):
        return
    sent, is_photo = _send_pet_card(message.chat.id, pet)
    pet["chat_id"] = message.chat.id
    pet["msg_id"] = sent.message_id
    pet["is_photo"] = is_photo
    save_pet(message.from_user.id, pet)
    try:
        bot.pin_chat_message(message.chat.id, sent.message_id, disable_notification=True)
    except Exception as e:
        print(f"re-pin pet card failed: {e}")


@bot.message_handler(commands=["adopt"], func=is_allowed)
def cmd_adopt(message):
    if store is None:
        bot.send_message(
            message.chat.id,
            "Adopting needs memory turned on (SQLITE_PATH). Ask the bot owner 🦭",
        )
        return
    existing = get_pet(message.from_user.id)
    if existing:
        bot.send_message(
            message.chat.id,
            f"You already have {existing['name']} 🦭 Use /pet to check on them, "
            "/feed and /play to care for them (or /release to say goodbye).",
        )
        return
    parts = (message.text or "").split(maxsplit=1)
    name = parts[1].strip()[:20] if len(parts) > 1 else "Sealy"
    pet = adopt(message.from_user.id, name or "Sealy")
    if pet is None:
        bot.send_message(message.chat.id, "Couldn't adopt right now 😔 Try again later.")
        return
    sent, is_photo = _send_pet_card(message.chat.id, pet)
    pet["chat_id"] = message.chat.id
    pet["msg_id"] = sent.message_id
    pet["is_photo"] = is_photo
    save_pet(message.from_user.id, pet)
    try:
        bot.pin_chat_message(message.chat.id, sent.message_id, disable_notification=True)
    except Exception as e:
        print(f"pin pet card failed: {e}")
    bot.send_message(
        message.chat.id,
        f"🎉 You adopted {pet['name']}! I pinned them up top so they're always in "
        "view. Keep them fed (/feed) and happy (/play) 🦭",
    )


@bot.message_handler(commands=["feed"], func=is_allowed)
def cmd_feed(message):
    pet = feed(message.from_user.id)
    if pet is None:
        bot.send_message(message.chat.id, "You don't have a seal yet 🦭 Adopt one with /adopt")
        return
    _refresh_card(message, pet)
    bot.send_message(
        message.chat.id, f"Nom nom! 🍤 {pet['name']} is {int(pet['fullness'])}% full."
    )


@bot.message_handler(commands=["play"], func=is_allowed)
def cmd_play(message):
    pet = play(message.from_user.id)
    if pet is None:
        bot.send_message(message.chat.id, "You don't have a seal yet 🦭 Adopt one with /adopt")
        return
    _refresh_card(message, pet)
    bot.send_message(
        message.chat.id,
        f"Wheee! 🎾 {pet['name']} is {int(pet['happiness'])}% happy (and a bit hungrier).",
    )


@bot.message_handler(commands=["pet"], func=is_allowed)
def cmd_pet(message):
    pet = get_pet(message.from_user.id)
    if pet is None:
        bot.send_message(message.chat.id, "You don't have a seal yet 🦭 Adopt one with /adopt")
        return
    save_pet(message.from_user.id, pet)  # checkpoint the decay snapshot
    _refresh_card(message, pet)


@bot.message_handler(commands=["release"], func=is_allowed)
def cmd_release(message):
    pet = get_pet(message.from_user.id)
    if pet is None:
        bot.send_message(message.chat.id, "You don't have a seal to release 🦭")
        return
    msg_id = pet.get("msg_id")
    if msg_id:
        try:
            bot.unpin_chat_message(message.chat.id, msg_id)
        except Exception as e:
            print(f"unpin on release failed: {e}")
    release(message.from_user.id)
    bot.send_message(
        message.chat.id,
        f"You released {pet['name']} back into the ocean 🌊🦭 Thanks for caring for them.",
    )


if HF_SPACE_ID:

    @bot.message_handler(commands=["model"], func=is_allowed)
    def cmd_model(message):
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) == 1:
            current = get_provider(message.from_user.id)
            bot.send_message(
                message.chat.id,
                f"Current provider: {current}\n\n"
                "Options:\n"
                "/model main — Cerebras (fast, multilingual, with memory)\n"
                "/model hf — ArmGPT (Armenian only, slow, no memory)",
            )
            return
        choice = parts[1].strip().lower()
        if choice not in ("main", "hf"):
            bot.send_message(
                message.chat.id, "Invalid choice. Use: /model main or /model hf"
            )
            return
        if not set_provider(message.from_user.id, choice):
            bot.send_message(
                message.chat.id, "Could not save preference. Try again later."
            )
            return
        if choice == "hf":
            bot.send_message(
                message.chat.id,
                "Switched to hf (ArmGPT).\n\n"
                "Note: this is a tiny base completion model trained only on Armenian text. "
                "It will continue whatever you write rather than answer questions, "
                "and it does not understand English. Replies take ~30-60s and there is no memory.",
            )
        else:
            bot.send_message(message.chat.id, "Switched to Main Provider.")


# ── Song-guessing game (/game) ──────────────────────────────────────────────
# No AI. Plays a ~30s iTunes preview; the user types guesses. See bot/game.py.


def _start_round(message, score: int) -> None:
    """Fetch a song, save it as this user's current answer, and play it."""
    bot.send_chat_action(message.chat.id, "upload_voice")
    song = fetch_song()
    if song is None:
        bot.send_message(
            message.chat.id,
            "Couldn't grab a song right now 😔 Try /game again in a moment.",
        )
        end_game(message.from_user.id)
        return
    state = {
        "title": song["title"],
        "artist": song["artist"],
        "attempts": 0,
        "score": score,
    }
    if not save_game(message.from_user.id, state):
        bot.send_message(
            message.chat.id, "Couldn't start the game right now. Try again later."
        )
        return
    try:
        bot.send_audio(
            message.chat.id,
            song["preview_url"],
            title="🎧 Guess this song!",
            performer="???",
        )
    except Exception as e:
        print(f"send_audio error: {e}")
        bot.send_message(
            message.chat.id, "Had trouble sending the clip 😔 Try /game again."
        )
        end_game(message.from_user.id)
        return
    bot.send_message(
        message.chat.id,
        "🎵 Guess the song — just type your answer!\n/hint · /skip · /endgame",
    )


@bot.message_handler(commands=["game"], func=is_allowed)
def cmd_game(message):
    if store is None:
        bot.send_message(
            message.chat.id,
            "The song game needs memory turned on (SQLITE_PATH). Ask the bot owner 🦭",
        )
        return
    existing = get_game(message.from_user.id)
    score = existing.get("score", 0) if existing else 0
    _start_round(message, score)


@bot.message_handler(commands=["hint"], func=is_allowed)
def cmd_hint(message):
    state = get_game(message.from_user.id)
    if not state:
        bot.send_message(message.chat.id, "No game running. Start one with /game 🎵")
        return
    title = state["title"].strip()
    words = len(_normalize(title).split())
    first = title[0] if title else "?"
    bot.send_message(
        message.chat.id,
        f'💡 Hint: by {state["artist"]} · {words} word(s) · starts with "{first}"',
    )


@bot.message_handler(commands=["skip"], func=is_allowed)
def cmd_skip(message):
    state = get_game(message.from_user.id)
    if not state:
        bot.send_message(message.chat.id, "No game running. Start one with /game 🎵")
        return
    bot.send_message(
        message.chat.id,
        f'⏭️ It was "{state["title"]}" by {state["artist"]}. Next one!',
    )
    _start_round(message, state.get("score", 0))


@bot.message_handler(commands=["endgame"], func=is_allowed)
def cmd_endgame(message):
    state = get_game(message.from_user.id)
    end_game(message.from_user.id)
    if state:
        bot.send_message(
            message.chat.id,
            f'Game over! Final score: {state.get("score", 0)} 🏆 Thanks for playing 🦭',
        )
    else:
        bot.send_message(message.chat.id, "No game was running. Type /game to play 🎵")


def _handle_guess(message, text: str) -> None:
    """Check a plain-text message as a guess for the active game."""
    user_id = message.from_user.id
    state = get_game(user_id)
    if state is None:
        return  # game expired between the is_active() check and here
    if check_guess(text, state["title"]):
        score = state.get("score", 0) + 1
        bot.send_message(
            message.chat.id,
            f'🎉 YES! It was "{state["title"]}" by {state["artist"]}.\n'
            f"Score: {score} 🔥 Next song coming up!",
        )
        _start_round(message, score)
        return
    state["attempts"] = state.get("attempts", 0) + 1
    save_game(user_id, state)
    if state["attempts"] >= MAX_ATTEMPTS:
        bot.send_message(
            message.chat.id,
            f'Out of tries! It was "{state["title"]}" by {state["artist"]}. '
            "Here's another 🎧",
        )
        _start_round(message, state.get("score", 0))
    else:
        left = MAX_ATTEMPTS - state["attempts"]
        bot.send_message(
            message.chat.id,
            f"❌ Not it! {left} tr{'y' if left == 1 else 'ies'} left. "
            "Try /hint or /skip.",
        )


@bot.message_handler(content_types=["text"], func=is_allowed)
def handle_message(message):
    if not should_respond(message):
        return
    # In game mode, plain text is a guess — never send it to the AI.
    if is_active(message.from_user.id):
        _handle_guess(message, message.text or "")
        return
    text = (message.text or "").replace(f"@{BOT_INFO.username}", "").strip()
    if not text:
        # Edited messages, forwards, or stickers-with-empty-caption can
        # arrive with no usable text. Don't burn rate-limit / AI calls on them.
        return
    _log(message, "in", text)
    if is_rate_limited(message.from_user.id):
        limit_msg = f"You've reached the daily limit of {RATE_LIMIT} messages. Try again tomorrow."
        bot.send_message(message.chat.id, limit_msg)
        _log(message, "out", f"[rate limited] {limit_msg}")
        return
    try:
        with keep_typing(message.chat.id):
            reply = ask_ai(message.from_user.id, text)
        send_reply(message, reply)
        _log(message, "out", reply)
    except Exception as e:
        print(f"Error in handle_message: {e}")
        bot.send_message(message.chat.id, "Something went wrong. Please try again.")
        _log(message, "out", f"[error] {e}")
