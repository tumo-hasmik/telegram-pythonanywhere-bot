"""Tests for the virtual seal pet: bot/pet.py (state + time-decay) and the
/adopt /feed /play /pet /release handlers."""

import json
from unittest.mock import patch, MagicMock


class FakeStore:
    """Minimal in-memory stand-in for SqliteStore (ignores TTL)."""

    def __init__(self):
        self.d = {}

    def get(self, key):
        return self.d.get(key)

    def set(self, key, value, ex=None):
        self.d[key] = value

    def delete(self, key):
        self.d.pop(key, None)


def make_message(text="hello", user_id=123, chat_id=456):
    msg = MagicMock()
    msg.text = text
    msg.from_user.id = user_id
    msg.chat.id = chat_id
    return msg


# ── bot/pet.py: state + decay ────────────────────────────────────────────────


def test_adopt_starts_full_and_decays_over_time():
    fs = FakeStore()
    with patch("bot.pet.store", fs), patch("bot.pet._now") as now:
        from bot.pet import adopt, get_pet

        now.return_value = 1000.0
        p = adopt(5, "Sealy")
        assert p["fullness"] == 100 and p["happiness"] == 100

        now.return_value = 1000.0 + 7200  # +2 hours
        aged = get_pet(5)
        assert 87 < aged["fullness"] < 89   # 100 - 2h * 6/h = 88
        assert 89 < aged["happiness"] < 91  # 100 - 2h * 5/h = 90


def test_feed_and_play_move_stats_and_clamp():
    fs = FakeStore()
    with patch("bot.pet.store", fs), patch("bot.pet._now") as now:
        from bot.pet import adopt, feed, play

        now.return_value = 0.0
        adopt(5, "S")
        now.return_value = 3600.0  # +1h so feeding has headroom then clamps
        assert feed(5)["fullness"] == 100  # ~94 + 35 -> clamped to 100
        after_play = play(5)
        assert after_play["happiness"] == 100  # ~95 + 30 -> clamped
        assert after_play["fullness"] == 90    # 100 - 10 play cost


def test_stats_never_go_negative():
    fs = FakeStore()
    with patch("bot.pet.store", fs), patch("bot.pet._now") as now:
        from bot.pet import adopt, get_pet

        now.return_value = 0.0
        adopt(5, "S")
        now.return_value = 10_000_000.0  # ages forever
        aged = get_pet(5)
        assert aged["fullness"] == 0 and aged["happiness"] == 0  # clamped, not dead


def test_mood_and_render():
    from bot.pet import render_pet, mood

    with patch("bot.pet._now", return_value=0.0):
        card = render_pet(
            {"name": "Waddles", "born": 0, "last_seen": 0, "fullness": 80, "happiness": 80}
        )
    assert "Waddles" in card and "🦭" in card and "/feed" in card
    assert "thriving" in mood({"fullness": 80, "happiness": 80})
    assert "starving" in mood({"fullness": 5, "happiness": 80})
    assert "lonely" in mood({"fullness": 80, "happiness": 5})


def test_release_deletes_pet():
    fs = FakeStore()
    fs.set("pet:5", "{}")
    with patch("bot.pet.store", fs):
        from bot.pet import release

        release(5)
        assert fs.get("pet:5") is None


def test_pet_functions_stateless():
    with patch("bot.pet.store", None):
        from bot.pet import get_pet, adopt, feed, play

        assert get_pet(5) is None
        assert adopt(5, "x") is None
        assert feed(5) is None and play(5) is None


# ── /adopt handler ───────────────────────────────────────────────────────────


def test_cmd_adopt_creates_pins_and_persists():
    fs = FakeStore()
    with (
        patch("bot.handlers.store", fs),
        patch("bot.pet.store", fs),
        patch("bot.handlers.bot") as mock_bot,
        patch("bot.handlers._SEAL_IMAGE", None),
    ):
        mock_bot.send_message.return_value = MagicMock(message_id=10)
        from bot.handlers import cmd_adopt

        cmd_adopt(make_message(text="/adopt Waddles"))
        mock_bot.pin_chat_message.assert_called_once()
        pet = json.loads(fs.get("pet:123"))
        assert pet["name"] == "Waddles"
        assert pet["msg_id"] == 10 and pet["chat_id"] == 456


def test_cmd_adopt_uses_photo_when_image_bundled():
    fs = FakeStore()
    with (
        patch("bot.handlers.store", fs),
        patch("bot.pet.store", fs),
        patch("bot.handlers.bot") as mock_bot,
        patch("bot.handlers._SEAL_IMAGE", "/fake/assets/seal.jpg"),
        patch("builtins.open", MagicMock()),
    ):
        mock_bot.send_photo.return_value = MagicMock(message_id=11)
        from bot.handlers import cmd_adopt

        cmd_adopt(make_message(text="/adopt Photo"))
        mock_bot.send_photo.assert_called_once()
        assert json.loads(fs.get("pet:123"))["is_photo"] is True


def test_cmd_adopt_declines_when_already_owned():
    fs = FakeStore()
    fs.set(
        "pet:123",
        json.dumps({"name": "Old", "born": 0, "last_seen": 0, "fullness": 50, "happiness": 50}),
    )
    with (
        patch("bot.handlers.store", fs),
        patch("bot.pet.store", fs),
        patch("bot.handlers.bot") as mock_bot,
    ):
        from bot.handlers import cmd_adopt

        cmd_adopt(make_message(text="/adopt New"))
        mock_bot.pin_chat_message.assert_not_called()
        assert "already have" in mock_bot.send_message.call_args[0][1]


def test_cmd_adopt_stateless():
    with patch("bot.handlers.store", None), patch("bot.handlers.bot") as mock_bot:
        from bot.handlers import cmd_adopt

        cmd_adopt(make_message(text="/adopt X"))
        assert "memory" in mock_bot.send_message.call_args[0][1].lower()


# ── /feed /play /pet /release handlers ───────────────────────────────────────


def _seed_pet(fs, **overrides):
    pet = {
        "name": "Sealy", "born": 0, "last_seen": 0, "fullness": 50, "happiness": 50,
        "chat_id": 456, "msg_id": 10, "is_photo": False,
    }
    pet.update(overrides)
    fs.set("pet:123", json.dumps(pet))


def test_cmd_feed_edits_pinned_card():
    fs = FakeStore()
    _seed_pet(fs, fullness=10)
    with patch("bot.pet.store", fs), patch("bot.handlers.bot") as mock_bot:
        from bot.handlers import cmd_feed

        cmd_feed(make_message())
        mock_bot.edit_message_text.assert_called_once()  # refreshed in place
        assert "full" in mock_bot.send_message.call_args[0][1]


def test_cmd_feed_without_pet_prompts_adopt():
    fs = FakeStore()
    with patch("bot.pet.store", fs), patch("bot.handlers.bot") as mock_bot:
        from bot.handlers import cmd_feed

        cmd_feed(make_message())
        assert "adopt" in mock_bot.send_message.call_args[0][1].lower()


def test_refresh_card_resends_and_repins_when_edit_fails():
    fs = FakeStore()
    pet = {
        "name": "Sealy", "born": 0, "last_seen": 0, "fullness": 50, "happiness": 50,
        "chat_id": 456, "msg_id": 10, "is_photo": False,
    }
    with (
        patch("bot.pet.store", fs),
        patch("bot.handlers.bot") as mock_bot,
        patch("bot.handlers._SEAL_IMAGE", None),
    ):
        mock_bot.edit_message_text.side_effect = Exception("message to edit not found")
        mock_bot.send_message.return_value = MagicMock(message_id=20)
        from bot.handlers import _refresh_card

        _refresh_card(make_message(), pet)
        mock_bot.pin_chat_message.assert_called_once()
        assert pet["msg_id"] == 20  # re-sent card's id


def test_cmd_release_unpins_and_deletes():
    fs = FakeStore()
    _seed_pet(fs)
    with patch("bot.pet.store", fs), patch("bot.handlers.bot") as mock_bot:
        from bot.handlers import cmd_release

        cmd_release(make_message())
        mock_bot.unpin_chat_message.assert_called_once()
        assert fs.get("pet:123") is None
        assert "released" in mock_bot.send_message.call_args[0][1].lower()
