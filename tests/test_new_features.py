"""Tests for the starter-pack features: /mood (+ storage), the command-menu
registration, /breathe, Telegram mini-games, and /trivia."""

import json
from unittest.mock import patch, MagicMock


def make_message(text="hello", user_id=123, chat_id=456):
    msg = MagicMock()
    msg.text = text
    msg.from_user.id = user_id
    msg.chat.id = chat_id
    return msg


# ── bot/mood.py storage ──────────────────────────────────────────────────────


def test_get_moods_stateless_returns_empty():
    with patch("bot.mood.store", None):
        from bot.mood import get_moods

        assert get_moods(123) == []


def test_log_mood_stateless_returns_false():
    with patch("bot.mood.store", None):
        from bot.mood import log_mood

        assert log_mood(123, "good") is False


def test_log_mood_appends_and_persists():
    fake = MagicMock()
    fake.get.return_value = None
    with patch("bot.mood.store", fake):
        from bot.mood import log_mood

        assert log_mood(123, "great") is True
        key, value = fake.set.call_args[0][0], fake.set.call_args[0][1]
        assert key == "mood:123"
        saved = json.loads(value)
        assert saved[-1]["level"] == "great" and "date" in saved[-1]


def test_get_moods_reads_existing():
    fake = MagicMock()
    fake.get.return_value = json.dumps([{"date": "2026-01-01", "level": "okay"}])
    with patch("bot.mood.store", fake):
        from bot.mood import get_moods

        assert get_moods(7) == [{"date": "2026-01-01", "level": "okay"}]


def test_log_mood_caps_at_max():
    from bot.mood import MAX_MOODS

    existing = [{"date": "2026-01-01", "level": "okay"}] * (MAX_MOODS + 10)
    fake = MagicMock()
    fake.get.return_value = json.dumps(existing)
    with patch("bot.mood.store", fake):
        from bot.mood import log_mood

        log_mood(1, "good")
        assert len(json.loads(fake.set.call_args[0][1])) == MAX_MOODS


# ── command menu (bot.clients.set_bot_commands) ──────────────────────────────


def test_set_bot_commands_calls_set_my_commands():
    with patch("bot.clients.bot") as mock_bot:
        from bot.clients import set_bot_commands

        msg = set_bot_commands()
        mock_bot.set_my_commands.assert_called_once()
        assert "registered" in msg


def test_set_bot_commands_survives_failure():
    with patch("bot.clients.bot") as mock_bot:
        mock_bot.set_my_commands.side_effect = Exception("proxy 503")
        from bot.clients import set_bot_commands

        assert "failed" in set_bot_commands()  # must not raise


def test_set_bot_commands_adds_model_only_with_hf():
    with patch("bot.clients.bot") as mock_bot, patch("bot.config.HF_SPACE_ID", ""):
        from bot.clients import set_bot_commands

        set_bot_commands()
        n_without = len(mock_bot.set_my_commands.call_args[0][0])
    with patch("bot.clients.bot") as mock_bot, patch("bot.config.HF_SPACE_ID", "x/y"):
        from bot.clients import set_bot_commands

        set_bot_commands()
        n_with = len(mock_bot.set_my_commands.call_args[0][0])
    assert n_with == n_without + 1


# ── /mood handler + callback ─────────────────────────────────────────────────


def test_cmd_mood_sends_inline_buttons():
    with patch("bot.handlers.bot") as mock_bot:
        from bot.handlers import cmd_mood

        cmd_mood(make_message())
        mock_bot.send_message.assert_called_once()
        assert "reply_markup" in mock_bot.send_message.call_args.kwargs


def test_cb_mood_logs_and_replies():
    call = MagicMock()
    call.data = "mood:down"
    call.from_user.id = 123
    call.message.chat.id = 456
    with (
        patch("bot.handlers.bot") as mock_bot,
        patch("bot.handlers.log_mood") as mock_log,
    ):
        from bot.handlers import cb_mood

        cb_mood(call)
        mock_log.assert_called_once_with(123, "down")
        mock_bot.answer_callback_query.assert_called_once()
        assert mock_bot.send_message.call_args[0][1]  # a supportive reply


# ── /breathe ─────────────────────────────────────────────────────────────────


def test_run_breathing_edits_each_step():
    with patch("bot.handlers.bot") as mock_bot, patch("bot.handlers.time.sleep"):
        from bot.handlers import _run_breathing, _BREATHE_STEPS, _BREATHE_CYCLES

        _run_breathing(456, 99)
        assert mock_bot.edit_message_text.call_count == (
            len(_BREATHE_STEPS) * _BREATHE_CYCLES + 1
        )


def test_cmd_breathe_offloads_to_thread():
    with (
        patch("bot.handlers.bot") as mock_bot,
        patch("bot.handlers.threading.Thread") as mock_thread,
    ):
        mock_bot.send_message.return_value = MagicMock(message_id=99)
        from bot.handlers import cmd_breathe

        cmd_breathe(make_message())
        mock_bot.send_message.assert_called_once()  # intro sent synchronously
        mock_thread.return_value.start.assert_called_once()  # animation offloaded


# ── mini-games ───────────────────────────────────────────────────────────────


def test_minigame_outcome_user_wins_increments():
    fake = MagicMock()
    fake.incr.return_value = 3
    with patch("bot.handlers.store", fake):
        from bot.handlers import _minigame_outcome

        result = _minigame_outcome(123, "dice", 6, 2)
        assert "you win" in result.lower()
        fake.incr.assert_called_once_with("minigame_wins:123")
        assert "3" in result


def test_minigame_outcome_seal_wins_no_increment():
    fake = MagicMock()
    with patch("bot.handlers.store", fake):
        from bot.handlers import _minigame_outcome

        assert "I win" in _minigame_outcome(123, "dice", 1, 5)
        fake.incr.assert_not_called()


def test_minigame_outcome_tie():
    with patch("bot.handlers.store", None):
        from bot.handlers import _minigame_outcome

        assert "tie" in _minigame_outcome(123, "dice", 4, 4).lower()


def test_minigame_outcome_slots_jackpot_vs_miss():
    with patch("bot.handlers.store", MagicMock()):
        from bot.handlers import _minigame_outcome

        assert "JACKPOT" in _minigame_outcome(1, "slots", 64, 1)
        assert "No jackpot" in _minigame_outcome(1, "slots", 30, 1)


def test_cmd_minigame_throws_two_dice_with_right_emoji():
    with (
        patch("bot.handlers.bot") as mock_bot,
        patch("bot.handlers.threading.Thread") as mock_thread,
        patch("bot.handlers.store", MagicMock()),
    ):
        mock_bot.send_dice.side_effect = [
            MagicMock(dice=MagicMock(value=5)),
            MagicMock(dice=MagicMock(value=3)),
        ]
        from bot.handlers import cmd_minigame

        cmd_minigame(make_message(text="/dart"))
        assert mock_bot.send_dice.call_count == 2
        assert mock_bot.send_dice.call_args_list[0].kwargs["emoji"] == "🎯"
        mock_thread.return_value.start.assert_called_once()


# ── /trivia ──────────────────────────────────────────────────────────────────

_GOOD_TRIVIA = (
    '{"question": "Q?", "options": ["a","b","c","d"], '
    '"correct_index": 2, "explanation": "x"}'
)


def test_make_trivia_parses_valid_json():
    with patch("bot.handlers.generate", return_value=_GOOD_TRIVIA):
        from bot.handlers import _make_trivia

        q = _make_trivia()
        assert q["question"] == "Q?"
        assert q["options"] == ["a", "b", "c", "d"]
        assert q["correct_index"] == 2


def test_make_trivia_fallback_on_garbage():
    with patch("bot.handlers.generate", return_value="not json"):
        from bot.handlers import _make_trivia, _TRIVIA_FALLBACK

        assert _make_trivia()["question"] == _TRIVIA_FALLBACK["question"]


def test_make_trivia_fallback_on_wrong_option_count():
    bad = '{"question": "Q?", "options": ["a","b"], "correct_index": 0}'
    with patch("bot.handlers.generate", return_value=bad):
        from bot.handlers import _make_trivia, _TRIVIA_FALLBACK

        assert _make_trivia()["question"] == _TRIVIA_FALLBACK["question"]


def test_make_trivia_fallback_when_generate_raises():
    with patch("bot.handlers.generate", side_effect=Exception("API down")):
        from bot.handlers import _make_trivia, _TRIVIA_FALLBACK

        assert _make_trivia()["question"] == _TRIVIA_FALLBACK["question"]


def test_cmd_trivia_sends_quiz_poll():
    with (
        patch("bot.handlers.generate", return_value=_GOOD_TRIVIA),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_trivia

        cmd_trivia(make_message())
        mock_bot.send_poll.assert_called_once()
        kwargs = mock_bot.send_poll.call_args.kwargs
        assert kwargs["type"] == "quiz"
        assert kwargs["correct_option_id"] == 2
