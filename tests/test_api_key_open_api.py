import asyncio
import copy
import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio

from astrbot.core import LogBroker
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.utils.auth_password import (
    hash_dashboard_password,
    hash_md5_dashboard_password,
)
from astrbot.dashboard.asgi_runtime import FastAPIAppAdapter
from astrbot.dashboard.responses import ok
from astrbot.dashboard.server import AstrBotDashboard

_TEST_DASHBOARD_PASSWORD = "AstrbotTest123"


async def _create_api_key(
    app: FastAPIAppAdapter,
    authenticated_header: dict,
    *,
    scopes: list[str],
    name_prefix: str = "openapi-test",
) -> tuple[str, str]:
    test_client = app.test_client()
    create_res = await test_client.post(
        "/api/apikey/create",
        json={"name": f"{name_prefix}-{uuid.uuid4().hex[:8]}", "scopes": scopes},
        headers=authenticated_header,
    )
    assert create_res.status_code == 200
    create_data = await create_res.get_json()
    assert create_data["status"] == "ok"
    return create_data["data"]["api_key"], create_data["data"]["key_id"]


@pytest_asyncio.fixture(scope="module")
async def core_lifecycle_td(tmp_path_factory):
    tmp_db_path = tmp_path_factory.mktemp("data") / "test_data_api_key.db"
    db = SQLiteDatabase(str(tmp_db_path))
    log_broker = LogBroker()
    core_lifecycle = AstrBotCoreLifecycle(log_broker, db)
    await core_lifecycle.initialize()
    core_lifecycle.astrbot_config["admins_id"] = ["api-key-test-admin"]
    generated_password = getattr(
        core_lifecycle.astrbot_config,
        "_generated_dashboard_password",
        None,
    )
    dashboard_password = generated_password or _TEST_DASHBOARD_PASSWORD
    if not generated_password:
        core_lifecycle.astrbot_config["dashboard"]["pbkdf2_password"] = (
            hash_dashboard_password(dashboard_password)
        )
        core_lifecycle.astrbot_config["dashboard"]["password"] = (
            hash_md5_dashboard_password(dashboard_password)
        )
    object.__setattr__(
        core_lifecycle,
        "_dashboard_plain_password",
        dashboard_password,
    )
    try:
        yield core_lifecycle
    finally:
        try:
            stop_result = core_lifecycle.stop()
            if asyncio.iscoroutine(stop_result):
                await stop_result
        except Exception:
            pass


@pytest.fixture(scope="module")
def app(core_lifecycle_td: AstrBotCoreLifecycle):
    shutdown_event = asyncio.Event()
    server = AstrBotDashboard(core_lifecycle_td, core_lifecycle_td.db, shutdown_event)
    return server.app


def _resolve_dashboard_password(core_lifecycle_td: AstrBotCoreLifecycle) -> str:
    generated_password = getattr(core_lifecycle_td, "_dashboard_plain_password", None)
    if generated_password:
        return generated_password
    password = core_lifecycle_td.astrbot_config["dashboard"]["pbkdf2_password"]
    if isinstance(password, str) and password.startswith("pbkdf2_sha256$"):
        return "astrbot"
    return password


@pytest_asyncio.fixture(scope="module")
async def authenticated_header(
    app: FastAPIAppAdapter, core_lifecycle_td: AstrBotCoreLifecycle
):
    test_client = app.test_client()
    response = await test_client.post(
        "/api/auth/login",
        json={
            "username": core_lifecycle_td.astrbot_config["dashboard"]["username"],
            "password": _resolve_dashboard_password(core_lifecycle_td),
        },
    )
    data = await response.get_json()
    token = data["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_api_key_scope_and_revoke(
    app: FastAPIAppAdapter, authenticated_header: dict
):
    test_client = app.test_client()

    raw_key, key_id = await _create_api_key(
        app,
        authenticated_header,
        scopes=["im"],
        name_prefix="im-scope-key",
    )

    open_bot_res = await test_client.get(
        "/api/v1/im/bots",
        headers={"X-API-Key": raw_key},
    )
    assert open_bot_res.status_code == 200
    open_bot_data = await open_bot_res.get_json()
    assert open_bot_data["status"] == "ok"
    assert isinstance(open_bot_data["data"]["bot_ids"], list)

    revoke_res = await test_client.post(
        "/api/apikey/revoke",
        json={"key_id": key_id},
        headers=authenticated_header,
    )
    assert revoke_res.status_code == 200
    revoke_data = await revoke_res.get_json()
    assert revoke_data["status"] == "ok"

    revoked_access_res = await test_client.get(
        "/api/v1/im/bots",
        headers={"X-API-Key": raw_key},
    )
    assert revoked_access_res.status_code == 401


@pytest.mark.asyncio
async def test_open_send_message_with_api_key(
    app: FastAPIAppAdapter, authenticated_header: dict, core_lifecycle_td
):
    test_client = app.test_client()
    # The gateway build has no built-in WebChat platform; register a stub bot.
    sent = []

    async def send_by_session(session, chain):
        sent.append((str(session), chain.get_plain_text()))

    stub = SimpleNamespace(
        meta=lambda: SimpleNamespace(id="stub_bot"), send_by_session=send_by_session
    )
    core_lifecycle_td.platform_manager.platform_insts.append(stub)

    raw_key, _ = await _create_api_key(
        app,
        authenticated_header,
        scopes=["im"],
        name_prefix="send-message-key",
    )

    send_res = await test_client.post(
        "/api/v1/im/message",
        json={
            "umo": "stub_bot:FriendMessage:open_api_test_session",
            "message": "hello",
        },
        headers={"X-API-Key": raw_key},
    )
    assert send_res.status_code == 200
    send_data = await send_res.get_json()
    assert send_data["status"] == "ok"
    assert sent == [("stub_bot:FriendMessage:open_api_test_session", "hello")]
    core_lifecycle_td.platform_manager.platform_insts.remove(stub)


@pytest.mark.asyncio
async def test_open_api_auth_validation_and_key_carriers(
    app: FastAPIAppAdapter,
    authenticated_header: dict,
):
    test_client = app.test_client()

    missing_key_res = await test_client.get("/api/v1/im/bots")
    assert missing_key_res.status_code == 401
    missing_key_data = await missing_key_res.get_json()
    assert missing_key_data["status"] == "error"
    assert missing_key_data["message"] == "Missing API key"

    invalid_key_res = await test_client.get(
        "/api/v1/im/bots",
        headers={"X-API-Key": "abk_invalid"},
    )
    assert invalid_key_res.status_code == 401
    invalid_key_data = await invalid_key_res.get_json()
    assert invalid_key_data["status"] == "error"
    assert invalid_key_data["message"] == "Invalid API key"

    raw_key, _ = await _create_api_key(
        app,
        authenticated_header,
        scopes=["im"],
        name_prefix="auth-carrier-key",
    )

    headers_and_urls = [
        ({"X-API-Key": raw_key}, "/api/v1/im/bots"),
        ({}, f"/api/v1/im/bots?api_key={raw_key}"),
        ({}, f"/api/v1/im/bots?key={raw_key}"),
        ({"Authorization": f"Bearer {raw_key}"}, "/api/v1/im/bots"),
        ({"Authorization": f"ApiKey {raw_key}"}, "/api/v1/im/bots"),
    ]
    for headers, url in headers_and_urls:
        res = await test_client.get(url, headers=headers)
        assert res.status_code == 200
        data = await res.get_json()
        assert data["status"] == "ok"
        assert isinstance(data["data"]["bot_ids"], list)


@pytest.mark.asyncio
async def test_open_send_message_error_paths(
    app: FastAPIAppAdapter, authenticated_header: dict
):
    test_client = app.test_client()
    raw_key, _ = await _create_api_key(
        app,
        authenticated_header,
        scopes=["im"],
        name_prefix="im-errors-key",
    )

    missing_message_res = await test_client.post(
        "/api/v1/im/message",
        json={
            "umo": f"webchat:FriendMessage:open_api_im_{uuid.uuid4().hex[:8]}",
            "message": None,
        },
        headers={"X-API-Key": raw_key},
    )
    missing_message_data = await missing_message_res.get_json()
    assert missing_message_data["status"] == "error"
    assert missing_message_data["message"] == "Missing key: message"

    missing_umo_res = await test_client.post(
        "/api/v1/im/message",
        json={"message": "hello"},
        headers={"X-API-Key": raw_key},
    )
    missing_umo_data = await missing_umo_res.get_json()
    assert missing_umo_data["status"] == "error"
    assert missing_umo_data["message"] == "Missing key: umo"

    invalid_umo_res = await test_client.post(
        "/api/v1/im/message",
        json={"umo": "broken-umo", "message": "hello"},
        headers={"X-API-Key": raw_key},
    )
    invalid_umo_data = await invalid_umo_res.get_json()
    assert invalid_umo_data["status"] == "error"
    assert invalid_umo_data["message"].startswith("Invalid umo:")

    missing_platform_res = await test_client.post(
        "/api/v1/im/message",
        json={
            "umo": f"platform-not-running:FriendMessage:{uuid.uuid4().hex[:8]}",
            "message": "hello",
        },
        headers={"X-API-Key": raw_key},
    )
    missing_platform_data = await missing_platform_res.get_json()
    assert missing_platform_data["status"] == "error"
    assert missing_platform_data["message"] == (
        "Bot not found or not running for platform: platform-not-running"
    )


@pytest.mark.asyncio
async def test_open_api_key_scope_normalization(
    app: FastAPIAppAdapter,
    authenticated_header: dict,
):
    test_client = app.test_client()

    config_res = await test_client.post(
        "/api/apikey/create",
        json={"name": "config-contained-scopes-key", "scopes": ["config"]},
        headers=authenticated_header,
    )
    config_data = await config_res.get_json()

    assert config_res.status_code == 200
    assert config_data["status"] == "ok"
    assert set(config_data["data"]["scopes"]) == {"config", "bot", "provider"}

    extra_scope_res = await test_client.post(
        "/api/apikey/create",
        json={"name": "mcp-skill-scope-key", "scopes": ["mcp", "skill"]},
        headers=authenticated_header,
    )
    extra_scope_data = await extra_scope_res.get_json()

    assert extra_scope_res.status_code == 200
    assert extra_scope_data["status"] == "ok"
    assert set(extra_scope_data["data"]["scopes"]) == {"mcp", "skill"}

    edit_admin_res = await test_client.post(
        "/api/apikey/create",
        json={
            "name": "config-edit-admin-key",
            "scopes": ["config", "config:edit_admin"],
        },
        headers=authenticated_header,
    )
    edit_admin_data = await edit_admin_res.get_json()
    assert edit_admin_res.status_code == 200
    assert edit_admin_data["status"] == "ok"
    assert set(edit_admin_data["data"]["scopes"]) == {
        "config",
        "config:edit_admin",
        "bot",
        "provider",
    }

    orphan_subscope_res = await test_client.post(
        "/api/apikey/create",
        json={"name": "orphan-edit-admin-key", "scopes": ["config:edit_admin"]},
        headers=authenticated_header,
    )
    orphan_subscope_data = await orphan_subscope_res.get_json()
    assert orphan_subscope_data["status"] == "error"
    assert orphan_subscope_data["message"] == (
        "config:edit_admin requires the config scope"
    )

    chat_admin_res = await test_client.post(
        "/api/apikey/create",
        json={"name": "chat-admin-key", "scopes": ["chat", "chat:admin"]},
        headers=authenticated_header,
    )
    chat_admin_data = await chat_admin_res.get_json()
    assert chat_admin_res.status_code == 200
    assert chat_admin_data["status"] == "ok"
    assert set(chat_admin_data["data"]["scopes"]) == {"chat", "chat:admin"}

    orphan_chat_admin_res = await test_client.post(
        "/api/apikey/create",
        json={"name": "orphan-chat-admin-key", "scopes": ["chat:admin"]},
        headers=authenticated_header,
    )
    orphan_chat_admin_data = await orphan_chat_admin_res.get_json()
    assert orphan_chat_admin_data["status"] == "error"
    assert orphan_chat_admin_data["message"] == (
        "chat:admin requires the chat scope"
    )


@pytest.mark.asyncio
async def test_config_edit_admin_subscope_controls_admin_id_changes(
    app: FastAPIAppAdapter,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    """Only the config edit-admin subscope may change administrator IDs."""
    test_client = app.test_client()
    config_key, _ = await _create_api_key(
        app,
        authenticated_header,
        scopes=["config"],
        name_prefix="config-without-edit-admin",
    )
    edit_admin_key, _ = await _create_api_key(
        app,
        authenticated_header,
        scopes=["config", "config:edit_admin"],
        name_prefix="config-with-edit-admin",
    )
    config_res = await test_client.get(
        "/api/v1/system-config",
        headers={"X-API-Key": config_key},
    )
    config_data = await config_res.get_json()
    original_config = copy.deepcopy(config_data["data"]["config"])
    changed_config = copy.deepcopy(original_config)
    changed_config["admins_id"] = [*original_config["admins_id"], "api-admin-test"]

    denied_res = await test_client.put(
        "/api/v1/system-config",
        json=changed_config,
        headers={"X-API-Key": config_key},
    )
    denied_data = await denied_res.get_json()
    assert denied_res.status_code == 403
    assert denied_data["message"] == (
        "config:edit_admin scope is required to change admins_id"
    )

    try:
        allowed_res = await test_client.put(
            "/api/v1/system-config",
            json=changed_config,
            headers={"X-API-Key": edit_admin_key},
        )
        allowed_data = await allowed_res.get_json()
        assert allowed_res.status_code == 200
        assert allowed_data["status"] == "ok"
        assert "api-admin-test" in core_lifecycle_td.astrbot_config["admins_id"]
    finally:
        restore_res = await test_client.put(
            "/api/v1/system-config",
            json=original_config,
            headers=authenticated_header,
        )
        assert restore_res.status_code == 200


