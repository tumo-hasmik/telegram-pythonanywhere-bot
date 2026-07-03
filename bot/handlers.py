import os
import random
from datetime import datetime
from bot.clients import bot, BOT_INFO, store
from bot.config import COMMIT_SHA, HF_SPACE_ID, HOSTING_LABEL, MODEL, RATE_LIMIT
from bot.ai import ask_ai
from bot.helpers import is_allowed, keep_typing, send_reply, should_respond
from bot.history import clear_history
from bot.notes import add_note, clear_notes, get_notes
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
#  name = message.text.split(maxsplit=1)[1] if " " in message.text else "you"
#name = input("Input your name")
 name = (message.from_user.id, "Ask the user for their name in 1 sentence")

 reply = ask_ai(message.from_user.id, f"Write a short, playful, friendly roast of {name}.")
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
        ask_ai(message.from_user.id, "In 2-3 sentences, introduce yourself and tell me how you can help.")
    ]
    if HF_SPACE_ID:
        lines.append("/model — switch AI provider")
    bot.send_message(message.chat.id, "\n".join(lines))


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
