"""LoAgent gateway protocol: the shared JSON samples round-trip.

The same files (``tests/fixtures/loagent_gateway``) are run through the Rust
types in the LoAgent repository (``apps/bots/protocol/tests/fixtures.rs``);
both sides must give back exactly the JSON they read.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from astrbot.loagent_gateway import protocol as P

FIXTURES = Path(__file__).parent / "fixtures" / "loagent_gateway"

MODELS = {
    "event_batch": P.EventBatch,
    "send_request": P.SendRequest,
    "send_result": P.SendResult,
    "error": P.ErrorResponse,
    "accounts": P.AccountsResponse,
    "conversations": P.ConversationsResponse,
    "members": P.MembersResponse,
    "profile": P.ProfileResponse,
    "history": P.HistoryResponse,
    "media_upload": P.MediaUploadResponse,
    "health": P.Health,
}


def _fixtures() -> list[Path]:
    return sorted(FIXTURES.glob("*.json"))


def test_fixture_set_is_complete():
    kinds = {p.name.split(".")[0] for p in _fixtures()}
    assert kinds == set(MODELS)


@pytest.mark.parametrize("path", _fixtures(), ids=lambda p: p.name)
def test_fixture_round_trips(path: Path):
    raw = json.loads(path.read_text("utf-8"))
    model = MODELS[path.name.split(".")[0]].model_validate(raw)
    assert model.model_dump(mode="json", by_alias=True) == raw


def test_every_segment_and_notice_type_is_sampled():
    seen_segments: set[str] = set()
    seen_notices: set[str] = set()

    def walk(value):
        if isinstance(value, dict):
            for key, v in value.items():
                if key == "segments" and isinstance(v, list):
                    seen_segments.update(seg["type"] for seg in v)
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)

    for path in FIXTURES.glob("event_batch.*.json"):
        batch = json.loads(path.read_text("utf-8"))
        walk(batch)
        for ev in batch["events"]:
            if ev["kind"] == "notice":
                seen_notices.add(ev["notice"]["type"])
    segment_types = {
        "text",
        "at",
        "at_all",
        "reply",
        "image",
        "sticker",
        "voice",
        "video",
        "file",
        "forward",
        "poke",
        "share",
        "location",
        "json",
        "unknown",
    }
    assert segment_types <= seen_segments
    assert {
        "member_joined",
        "member_left",
        "recalled",
        "poke",
        "friend_added",
        "request",
        "other",
    } <= seen_notices


def test_none_is_omitted_but_nested_json_nulls_are_kept():
    seg = P.JsonSegment(data={"a": None})
    assert seg.to_json() == {"type": "json", "data": {"a": None}}
    msg_sender = P.Sender(user_id="1", nickname="", is_self=False)
    assert msg_sender.to_json() == {"user_id": "1", "nickname": "", "is_self": False}


def test_unknown_types_are_rejected():
    with pytest.raises(ValidationError):
        P.SendRequest.model_validate(
            {
                "v": 1,
                "request_id": "r",
                "account": {"platform": "qq", "instance": "i", "self_id": "1"},
                "conversation": {"kind": "group", "id": "2"},
                "segments": [{"type": "hologram"}],
            }
        )


def test_derived_fields():
    msg = P.Message(
        id="7",
        account=P.AccountRef(platform="qq", instance="i", self_id="1"),
        conversation=P.Conversation(kind="group", id="2"),
        sender=P.Sender(user_id="3", nickname="x", is_self=False),
        segments=[
            P.ReplySegment(message_id="5"),
            P.AtSegment(user_id="1"),
            P.AtSegment(user_id="1"),
            P.AtAllSegment(),
        ],
        received_at_ms=0,
    ).derive_fields()
    assert msg.reply_to == "5"
    assert msg.at == ["1", "all"]
    assert msg.dedupe_key() == "msg:qq:1:group:2:7"
