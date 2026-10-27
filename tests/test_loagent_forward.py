"""LoAgent channel gateway: the loagent_forward stage end to end.

A stub LoAgent HTTP service runs inside the test. An OneBot v11 group message
that @-mentions the bot is converted by the real aiocqhttp adapter and pushed
through the real pipeline scheduler; the bot's outgoing OneBot calls are
captured instead of reaching a protocol endpoint.
"""

from __future__ import annotations

import asyncio
import copy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from aiocqhttp import Event
from aiohttp import web

from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.message.components import At, AtAll, Image, Plain, Reply
from astrbot.core.pipeline.context import PipelineContext
from astrbot.core.pipeline.process_stage.method import loagent_forward
from astrbot.core.pipeline.process_stage.method.loagent_forward import (
    build_loagent_request,
    build_reply_chain,
)
from astrbot.core.pipeline.scheduler import PipelineScheduler
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
    AiocqhttpAdapter,
)
from astrbot.core.star.context import Context
from astrbot.core.star.session_llm_manager import SessionServiceManager
from astrbot.core.star.session_plugin_manager import SessionPluginManager

TOKEN = "test-token"
SELF_ID = 10001
GROUP_ID = 123456


class StubLoAgent:
    """Minimal LoAgent ``POST /api/channel/message`` implementation."""

    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.reply: dict = {"silent": True}
        self.delay = 0.0

    async def handle(self, request: web.Request) -> web.Response:
        if request.headers.get("Authorization") != f"Bearer {TOKEN}":
            return web.json_response({"error": "unauthorized"}, status=401)
        body = await request.json()
        self.requests.append({"headers": dict(request.headers), "body": body})
        if self.delay:
            await asyncio.sleep(self.delay)
        return web.json_response(self.reply)


@pytest_asyncio.fixture
async def stub_loagent():
    stub = StubLoAgent()
    app = web.Application()
    app.router.add_post("/api/channel/message", stub.handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    stub.endpoint = f"http://127.0.0.1:{port}"
    try:
        yield stub
    finally:
        await runner.cleanup()


def _make_adapter() -> AiocqhttpAdapter:
    """Create a real aiocqhttp adapter whose OneBot API calls are faked."""
    adapter = AiocqhttpAdapter(
        {"id": "qq_main", "ws_reverse_host": "127.0.0.1", "ws_reverse_port": 0},
        {},
        asyncio.Queue(),
    )

    async def call_action(action, **params):
        if action == "get_msg":
            return {
                "message_id": 555,
                "message_type": "group",
                "group_id": GROUP_ID,
                "self_id": SELF_ID,
                "user_id": 30003,
                "time": 1700000000,
                "sender": {"user_id": 30003, "nickname": "Bob"},
                "message": [{"type": "text", "data": {"text": "earlier message"}}],
            }
        if action == "get_group_member_info":
            names = {SELF_ID: "Gateway Bot", 30003: "Bob"}
            return {"card": names.get(params["user_id"], "Someone")}
        raise AssertionError(f"unexpected OneBot action {action}")

    adapter.bot.call_action = call_action
    adapter.bot.send_group_msg = AsyncMock()
    adapter.bot.send_private_msg = AsyncMock()
    return adapter


def _group_at_bot_payload() -> dict:
    """OneBot v11 group message: quote of #555, @bot, @Bob and text."""
    return {
        "post_type": "message",
        "message_type": "group",
        "sub_type": "normal",
        "message_id": 777,
        "group_id": GROUP_ID,
        "self_id": SELF_ID,
        "user_id": 20002,
        "time": 1700000100,
        "sender": {"user_id": 20002, "nickname": "alice", "card": "Alice"},
        "message": [
            {"type": "reply", "data": {"id": "555"}},
            {"type": "at", "data": {"qq": str(SELF_ID)}},
            {"type": "text", "data": {"text": " hello bot"}},
            {"type": "at", "data": {"qq": "30003"}},
        ],
    }


async def _run_pipeline(stub: StubLoAgent, monkeypatch, *, token=TOKEN, timeout=5.0):
    """Convert the payload with the adapter and execute the whole pipeline."""
    monkeypatch.setattr(
        SessionServiceManager, "is_session_enabled", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        SessionServiceManager,
        "should_process_llm_request",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        SessionPluginManager,
        "filter_handlers_by_session",
        AsyncMock(side_effect=lambda event, handlers: handlers),
    )
    monkeypatch.delenv("LOAGENT_ENDPOINT", raising=False)
    monkeypatch.delenv("LOAGENT_TOKEN", raising=False)

    config = copy.deepcopy(DEFAULT_CONFIG)
    config.update(
        admins_id=[],
        plugin_set=[],
        loagent_project="persona-a",
        loagent={"endpoint": stub.endpoint, "token": token, "timeout": timeout},
    )
    config["platform_settings"]["enable_id_white_list"] = False

    adapter = _make_adapter()
    star_context = Context(
        asyncio.Queue(),
        config,
        MagicMock(),
        SimpleNamespace(platform_insts=[adapter]),
        MagicMock(),
        MagicMock(),
    )
    scheduler = PipelineScheduler(
        PipelineContext(config, SimpleNamespace(context=star_context), "default")
    )
    await scheduler.initialize()

    abm = await adapter.convert_message(Event.from_payload(_group_at_bot_payload()))
    event = adapter.create_event(abm)
    await scheduler.execute(event)
    return adapter


@pytest.mark.asyncio
async def test_group_at_message_is_forwarded_and_reply_is_sent(
    stub_loagent, monkeypatch
):
    stub_loagent.reply = {
        "text": "hi Alice, noted.",
        "at": ["20002"],
        "replyTo": "777",
    }

    adapter = await _run_pipeline(stub_loagent, monkeypatch)

    assert len(stub_loagent.requests) == 1
    request = stub_loagent.requests[0]
    assert request["headers"]["Authorization"] == f"Bearer {TOKEN}"
    body = request["body"]
    sent_at = datetime.fromisoformat(body.pop("at"))
    assert abs(datetime.now(timezone.utc) - sent_at) < timedelta(minutes=1)
    assert body == {
        "project": "persona-a",
        "umo": f"qq_main:GroupMessage:{GROUP_ID}",
        "platform": {"id": "qq_main", "type": "aiocqhttp"},
        "messageType": "group",
        "messageId": "777",
        "groupId": str(GROUP_ID),
        "selfId": str(SELF_ID),
        "sender": {"id": "20002", "name": "Alice"},
        "text": "hello bot @Bob(30003)",
        "images": [],
        "mentions": {
            "bot": True,
            "all": False,
            "users": [{"id": "30003", "name": "Bob"}],
        },
        "replyTo": {
            "id": "555",
            "text": "earlier message",
            "sender": {"id": "30003", "name": "Bob"},
            "isBot": False,
        },
    }

    adapter.bot.send_group_msg.assert_awaited_once()
    kwargs = adapter.bot.send_group_msg.await_args.kwargs
    assert kwargs["group_id"] == GROUP_ID
    segments = kwargs["message"]
    assert segments[0] == {"type": "reply", "data": {"id": "777"}}
    assert segments[1] == {"type": "at", "data": {"qq": "20002"}}
    text = "".join(s["data"]["text"] for s in segments if s["type"] == "text")
    assert text.strip() == "hi Alice, noted."


@pytest.mark.asyncio
async def test_silent_reply_sends_nothing(stub_loagent, monkeypatch):
    stub_loagent.reply = {"silent": True}

    adapter = await _run_pipeline(stub_loagent, monkeypatch)

    assert len(stub_loagent.requests) == 1
    adapter.bot.send_group_msg.assert_not_awaited()


@pytest.mark.asyncio
async def test_auth_failure_logs_and_does_not_reply(stub_loagent, monkeypatch):
    fake_logger = MagicMock()
    monkeypatch.setattr(loagent_forward, "logger", fake_logger)

    adapter = await _run_pipeline(stub_loagent, monkeypatch, token="wrong")

    assert stub_loagent.requests == []
    adapter.bot.send_group_msg.assert_not_awaited()
    assert any(401 in call.args for call in fake_logger.error.call_args_list)


@pytest.mark.asyncio
async def test_timeout_logs_and_does_not_reply(stub_loagent, monkeypatch):
    fake_logger = MagicMock()
    monkeypatch.setattr(loagent_forward, "logger", fake_logger)
    stub_loagent.reply = {"text": "too late"}
    stub_loagent.delay = 2.0

    adapter = await _run_pipeline(stub_loagent, monkeypatch, timeout=0.3)

    adapter.bot.send_group_msg.assert_not_awaited()
    fake_logger.warning.assert_called()
    assert "did not reply" in fake_logger.warning.call_args.args[0]


@pytest.mark.asyncio
async def test_unreachable_loagent_logs_and_does_not_reply(stub_loagent, monkeypatch):
    fake_logger = MagicMock()
    monkeypatch.setattr(loagent_forward, "logger", fake_logger)
    endpoint = stub_loagent.endpoint
    stub_loagent.endpoint = "http://127.0.0.1:1"

    adapter = await _run_pipeline(stub_loagent, monkeypatch)

    stub_loagent.endpoint = endpoint
    adapter.bot.send_group_msg.assert_not_awaited()
    fake_logger.error.assert_called()


@pytest.mark.parametrize(
    "reply",
    [
        None,
        [],
        {"silent": True},
        {"text": ""},
        {"text": "   "},
        {"silent": True, "text": "x"},
    ],
)
def test_build_reply_chain_returns_none_for_silence(reply):
    assert build_reply_chain(reply) is None


def test_build_reply_chain_accepts_object_forms():
    chain = build_reply_chain(
        {
            "text": "hello",
            "at": [{"id": "1", "name": "A"}, "all"],
            "replyTo": {"id": 9},
            "images": ["https://example.com/a.png"],
        }
    )
    assert isinstance(chain[0], Reply) and chain[0].id == "9"
    assert isinstance(chain[1], At) and str(chain[1].qq) == "1" and chain[1].name == "A"
    assert isinstance(chain[3], AtAll)
    assert isinstance(chain[5], Plain) and chain[5].text == "hello"
    assert isinstance(chain[6], Image) and chain[6].file == "https://example.com/a.png"


def test_build_reply_chain_single_at_string():
    chain = build_reply_chain({"text": "yo", "at": "42"})
    assert [type(c) for c in chain] == [At, Plain, Plain]
    assert str(chain[0].qq) == "42"


@pytest.mark.asyncio
async def test_build_request_for_private_message_with_image():
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.self_id = "bot"
    message.message_id = "m1"
    message.sender = MessageMember(user_id="u1", nickname="User")
    message.message = [Plain("look"), Image.fromURL("https://example.com/cat.jpg")]
    message.timestamp = 0
    event = AstrMessageEvent(
        "look",
        message,
        PlatformMetadata(id="tg", name="telegram", description="Telegram"),
        "u1",
    )

    body = await build_loagent_request(event, "persona-b")

    assert body["messageType"] == "private"
    assert body["umo"] == "tg:FriendMessage:u1"
    assert body["platform"] == {"id": "tg", "type": "telegram"}
    assert body["images"] == ["https://example.com/cat.jpg"]
    assert body["mentions"] == {"bot": False, "all": False, "users": []}
    assert body["replyTo"] is None
    assert body["at"] == "1970-01-01T00:00:00+00:00"
