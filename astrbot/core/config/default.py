"""如需修改配置，请在 `data/cmd_config.json` 中修改或者在管理面板中可视化修改。"""

import os

from astrbot import __version__
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

VERSION = __version__

DB_PATH = os.path.join(get_astrbot_data_path(), "data_v4.db")
PERSONAL_WECHAT_CONFIG_METADATA = {
    "weixin_oc_base_url": {
        "description": "Base URL",
        "type": "string",
        "hint": "默认值: https://ilinkai.weixin.qq.com",
    },
    "weixin_oc_bot_type": {
        "description": "扫码参数 bot_type",
        "type": "string",
        "hint": "默认值: 3",
        "invisible": True,
    },
    "weixin_oc_qr_poll_interval": {
        "description": "二维码状态轮询间隔（秒）",
        "type": "int",
        "hint": "每隔多少秒轮询一次二维码状态。",
        "invisible": True,
    },
    "weixin_oc_long_poll_timeout_ms": {
        "description": "getUpdates 长轮询超时时间（毫秒）",
        "type": "int",
        "hint": "会话消息拉取接口超时参数。",
    },
    "weixin_oc_api_timeout_ms": {
        "description": "HTTP 请求超时（毫秒）",
        "type": "int",
        "hint": "通用 API 请求超时参数。",
    },
    "weixin_oc_token": {
        "description": "登录后 token（可留空）",
        "type": "string",
        "hint": "扫码登录成功后会自动写入；高级场景可手动填写。",
        "secret": True,
        "invisible": True,
    },
    "weixin_oc_account_id": {"invisible": True},
    "weixin_oc_sync_buf": {"invisible": True},
    "weixin_oc_context_tokens": {"invisible": True},
}

WEBHOOK_SUPPORTED_PLATFORMS = [
    "qq_official_webhook",
    "weixin_official_account",
    "wecom",
    "wecom_ai_bot",
    "slack",
    "lark",
    "line",
]

# 默认配置
DEFAULT_CONFIG = {
    "config_version": 5,
    "platform_settings": {
        "unique_session": False,
        "rate_limit": {
            "time": 60,
            "count": 30,
            "strategy": "stall",  # stall, discard
        },
        "reply_prefix": "",
        "forward_threshold": 1500,
        "enable_id_white_list": True,
        "id_whitelist": [],
        "id_whitelist_log": True,
        "wl_ignore_admin_on_group": True,
        "wl_ignore_admin_on_friend": True,
        "reply_with_mention": False,
        "reply_with_quote": False,
        "path_mapping": [],
        "segmented_reply": {
            "enable": False,
            "only_llm_result": True,
            "interval_method": "random",
            "interval": "1.5,3.5",
            "log_base": 2.6,
            "words_count_threshold": 150,
            "split_mode": "regex",  # regex 或 words
            "regex": ".*?[。？！~…]+|.+$",
            "split_words": [
                "。",
                "？",
                "！",
                "~",
                "…",
            ],  # 当 split_mode 为 words 时使用
            "content_cleanup_rule": "",
        },
        "no_permission_reply": True,
        "empty_mention_waiting": True,
        "empty_mention_waiting_need_reply": True,
        "friend_message_needs_wake_prefix": False,
        "ignore_bot_self_message": False,
        "ignore_at_all": False,
    },
    # LoAgent channel gateway: the LoAgent project this configuration (persona)
    # forwards to. Empty means messages are not forwarded.
    "loagent_project": "",
    # Also send group messages that did not wake the bot to LoAgent's
    # /api/channel/observe (recorded in memory, never answered).
    "loagent_observe": False,
    # Global LoAgent entry point. Only read from the default configuration;
    # LOAGENT_ENDPOINT / LOAGENT_TOKEN environment variables take precedence.
    "loagent": {
        "endpoint": "http://loagent:3080",
        "token": "",
        "timeout": 120.0,
    },
    # Kept for the retained pipeline stages (wake prefix, reply decoration and
    # streaming fallback); the LLM-specific settings were removed.
    "provider_settings": {
        "enable": True,
        "wake_prefix": "",
        "display_reasoning_text": False,
        "identifier": False,
        "prompt_prefix": "{{prompt}}",
        "streaming_response": False,
        "unsupported_streaming_strategy": "realtime_segmenting",
        "quoted_message_parser": {
            "max_component_chain_depth": 4,
            "max_forward_node_depth": 6,
            "max_forward_fetch": 32,
            "warn_on_action_failure": False,
        },
    },
    "provider_stt_settings": {
        "enable": False,
        "provider_id": "",
    },
    "provider_tts_settings": {
        "enable": False,
        "provider_id": "",
        "dual_output": False,
        "use_file_service": False,
        "trigger_probability": 1.0,
    },
    "content_safety": {
        "also_use_in_response": False,
        "internal_keywords": {"enable": True, "extra_keywords": []},
        "baidu_aip": {"enable": False, "app_id": "", "api_key": "", "secret_key": ""},
    },
    "admins_id": ["astrbot"],
    "t2i": False,
    "t2i_word_threshold": 150,
    "t2i_strategy": "remote",
    "t2i_endpoint": "",
    "t2i_use_file_service": False,
    "t2i_active_template": "base",
    "http_proxy": "",
    "no_proxy": ["localhost", "127.0.0.1", "::1", "10.*", "192.168.*"],
    "dashboard": {
        "enable": True,
        "username": "astrbot",
        "password": "",
        "pbkdf2_password": "",
        "password_storage_upgraded": False,
        "password_change_required": False,
        "jwt_secret": "",
        "host": "0.0.0.0",
        "port": 6185,
        "disable_access_log": True,
        "trust_proxy_headers": False,
        "auth_rate_limit": {
            "enable": True,
            "average_interval": 1.0,
            "max_burst": 3,
        },
        "totp": {
            "enable": False,
            "secret": "",
            "recovery_code_hash": "",
        },
        "ssl": {
            "enable": False,
            "cert_file": "",
            "key_file": "",
            "ca_certs": "",
        },
    },
    "platform": [],
    "platform_specific": {
        # 平台特异配置：按平台分类，平台下按功能分组
        "lark": {
            "pre_ack_emoji": {"enable": False, "emojis": ["Typing"]},
        },
        "telegram": {
            "pre_ack_emoji": {"enable": False, "emojis": ["✍️"]},
        },
        "discord": {
            "pre_ack_emoji": {"enable": False, "emojis": ["🤔"]},
        },
    },
    "wake_prefix": ["/"],
    "log_level": "INFO",
    "log_file_enable": False,
    "log_file_path": "logs/astrbot.log",
    "log_file_max_mb": 20,
    "temp_dir_max_size": 1024,
    "trace_enable": False,
    "trace_db_path": "logs/traces.db",
    "trace_db_max_mb": 80,
    "trace_retention_days": 7,
    "pip_install_arg": "",
    "pypi_index_url": "https://mirrors.aliyun.com/pypi/simple/",
    "timezone": "Asia/Shanghai",
    "callback_api_base": "",
    "plugin_set": ["*"],  # "*" 表示使用所有可用的插件, 空列表表示不使用任何插件
    "disable_builtin_commands": False,
    "disable_metrics": False,
}


"""
AstrBot v3 时代的配置元数据，目前仅承担以下功能：

1. 保存配置时，配置项的类型验证
2. WebUI 展示提供商和平台适配器模版

WebUI 的配置文件在 `CONFIG_METADATA_3` 中。

未来将会逐步淘汰此配置元数据。
"""
CONFIG_METADATA_2 = {
    "platform_group": {
        "metadata": {
            "platform": {
                "description": "消息平台适配器",
                "type": "list",
                "config_template": {
                    "QQ 官方机器人(Websocket, 推荐)": {
                        "id": "default",
                        "type": "qq_official",
                        "enable": True,
                        "appid": "",
                        "secret": "",
                        "enable_group_c2c": True,
                        "enable_guild_direct_message": True,
                        "use_markdown": True,
                    },
                    "QQ 官方机器人(Webhook)": {
                        "id": "default",
                        "type": "qq_official_webhook",
                        "enable": True,
                        "appid": "",
                        "secret": "",
                        "use_markdown": True,
                        "is_sandbox": False,
                        "unified_webhook_mode": True,
                        "webhook_uuid": "",
                        "callback_server_host": "0.0.0.0",
                        "port": 6196,
                    },
                    "OneBot v11": {
                        "id": "default",
                        "type": "aiocqhttp",
                        "enable": True,
                        "ws_reverse_host": "0.0.0.0",
                        "ws_reverse_port": 6199,
                        "ws_reverse_token": "",
                    },
                    "飞书(Lark)": {
                        "id": "lark",
                        "type": "lark",
                        "enable": True,
                        "app_id": "",
                        "app_secret": "",
                        "domain": "https://open.feishu.cn",
                        "lark_connection_mode": "socket",  # webhook, socket
                        "webhook_uuid": "",
                        "lark_encrypt_key": "",
                        "lark_verification_token": "",
                    },
                    "个人微信": {
                        "id": "weixin_personal",
                        "type": "weixin_oc",
                        "enable": True,
                        "weixin_oc_base_url": "https://ilinkai.weixin.qq.com",
                        "weixin_oc_bot_type": "3",
                        "weixin_oc_qr_poll_interval": 1,
                        "weixin_oc_long_poll_timeout_ms": 35_000,
                        "weixin_oc_api_timeout_ms": 120_000,
                    },
                    "企业微信 (智能机器人)": {
                        "id": "wecom_ai_bot",
                        "type": "wecom_ai_bot",
                        "hint": "如果发现字段有异常，请重新创建",
                        "enable": True,
                        "wecom_ai_bot_connection_mode": "long_connection",  # long_connection, webhook
                        "wecom_ai_bot_name": "",
                        "wecomaibot_ws_bot_id": "",
                        "wecomaibot_ws_secret": "",
                        "wecomaibot_token": "",
                        "wecomaibot_encoding_aes_key": "",
                        "wecomaibot_init_respond_text": "",
                        "wecomaibot_friend_message_welcome_text": "",
                        "msg_push_webhook_url": "",
                        "only_use_webhook_url_to_send": False,
                        "wecomaibot_ws_url": "wss://openws.work.weixin.qq.com",
                        "wecomaibot_heartbeat_interval": 30,
                        "unified_webhook_mode": True,
                        "webhook_uuid": "",
                        "callback_server_host": "0.0.0.0",
                        "port": 6198,
                    },
                    "企业微信应用 & 微信客服": {
                        "id": "wecom",
                        "type": "wecom",
                        "enable": True,
                        "corpid": "",
                        "secret": "",
                        "token": "",
                        "encoding_aes_key": "",
                        "kf_name": "",
                        "api_base_url": "https://qyapi.weixin.qq.com/cgi-bin/",
                        "unified_webhook_mode": True,
                        "webhook_uuid": "",
                        "callback_server_host": "0.0.0.0",
                        "port": 6195,
                    },
                    "微信公众平台": {
                        "id": "weixin_official_account",
                        "type": "weixin_official_account",
                        "enable": True,
                        "appid": "",
                        "secret": "",
                        "token": "",
                        "encoding_aes_key": "",
                        "api_base_url": "https://api.weixin.qq.com/cgi-bin/",
                        "unified_webhook_mode": True,
                        "webhook_uuid": "",
                        "callback_server_host": "0.0.0.0",
                        "port": 6194,
                        "active_send_mode": False,
                    },
                    "钉钉(DingTalk)": {
                        "id": "dingtalk",
                        "type": "dingtalk",
                        "enable": True,
                        "client_id": "",
                        "client_secret": "",
                        "card_template_id": "",
                    },
                    "Telegram": {
                        "id": "telegram",
                        "type": "telegram",
                        "enable": True,
                        "telegram_token": "",
                        "start_message": "Hello, I'm AstrBot!",
                        "telegram_api_base_url": "https://api.telegram.org/bot",
                        "telegram_file_base_url": "https://api.telegram.org/file/bot",
                        "telegram_command_register": True,
                        "telegram_command_auto_refresh": True,
                        "telegram_command_register_interval": 300,
                        "telegram_polling_restart_delay": 5.0,
                    },
                    "Discord": {
                        "id": "discord",
                        "type": "discord",
                        "enable": True,
                        "discord_token": "",
                        "discord_proxy": "",
                        "discord_command_register": True,
                        "discord_activity_name": "",
                        "discord_allow_bot_messages": False,
                    },
                    "Misskey": {
                        "id": "misskey",
                        "type": "misskey",
                        "enable": True,
                        "misskey_instance_url": "https://misskey.example",
                        "misskey_token": "",
                        "misskey_default_visibility": "public",
                        "misskey_local_only": False,
                        "misskey_enable_chat": True,
                        # download / security options
                        "misskey_allow_insecure_downloads": False,
                        "misskey_download_timeout": 15,
                        "misskey_download_chunk_size": 65536,
                        "misskey_max_download_bytes": None,
                        "misskey_enable_file_upload": True,
                        "misskey_upload_concurrency": 3,
                        "misskey_upload_folder": "",
                    },
                    "Slack": {
                        "id": "slack",
                        "type": "slack",
                        "enable": True,
                        "bot_token": "",
                        "app_token": "",
                        "signing_secret": "",
                        "slack_connection_mode": "socket",  # webhook, socket
                        "unified_webhook_mode": True,
                        "webhook_uuid": "",
                        "slack_webhook_host": "0.0.0.0",
                        "slack_webhook_port": 6197,
                        "slack_webhook_path": "/astrbot-slack-webhook/callback",
                    },
                    "Line": {
                        "id": "line",
                        "type": "line",
                        "enable": True,
                        "channel_access_token": "",
                        "channel_secret": "",
                        "unified_webhook_mode": True,
                        "webhook_uuid": "",
                    },
                    "Satori": {
                        "id": "satori",
                        "type": "satori",
                        "enable": True,
                        "satori_api_base_url": "http://localhost:5140/satori/v1",
                        "satori_endpoint": "ws://localhost:5140/satori/v1/events",
                        "satori_token": "",
                        "satori_auto_reconnect": True,
                        "satori_heartbeat_interval": 10,
                        "satori_reconnect_delay": 5,
                    },
                    "KOOK": {
                        "id": "kook",
                        "type": "kook",
                        "enable": True,
                        "kook_bot_token": "",
                        "kook_reconnect_delay": 1,
                        "kook_max_reconnect_delay": 60,
                        "kook_max_retry_delay": 60,
                        "kook_heartbeat_interval": 30,
                        "kook_heartbeat_timeout": 6,
                        "kook_max_heartbeat_failures": 3,
                        "kook_max_consecutive_failures": 5,
                    },
                    "Mattermost": {
                        "id": "mattermost",
                        "type": "mattermost",
                        "enable": True,
                        "mattermost_url": "https://chat.example.com",
                        "mattermost_bot_token": "",
                        "mattermost_reconnect_delay": 5.0,
                    },
                    # "WebChat": {
                    #     "id": "webchat",
                    #     "type": "webchat",
                    #     "enable": False,
                    #     "webchat_link_path": "",
                    #     "webchat_present_type": "fullscreen",
                    # },
                },
                "items": {
                    # "webchat_link_path": {
                    #     "description": "链接路径",
                    #     "_special": "webchat_link_path",
                    #     "type": "string",
                    # },
                    # "webchat_present_type": {
                    #     "_special": "webchat_present_type",
                    #     "description": "展现形式",
                    #     "type": "string",
                    #     "options": ["fullscreen", "embedded"],
                    # },
                    "app_id": {
                        "description": "应用 ID",
                        "type": "string",
                        "hint": "消息平台开放平台中的应用 ID。",
                        "show_key": True,
                    },
                    "app_secret": {
                        "description": "应用密钥",
                        "type": "string",
                        "hint": "消息平台开放平台中的应用密钥。请妥善保管，避免泄露。",
                        "show_key": True,
                        "secret": True,
                    },
                    "domain": {
                        "description": "开放平台 API 地址",
                        "type": "string",
                        "hint": "开放平台 API 的基础地址。使用默认官方服务时通常无需修改。",
                        "show_key": True,
                    },
                    "corpid": {
                        "description": "企业 ID",
                        "type": "string",
                        "hint": "企业微信后台中的企业 ID（CorpID）。",
                        "show_key": True,
                    },
                    "token": {
                        "description": "回调 Token",
                        "type": "string",
                        "hint": "消息平台回调配置中用于验证请求的 Token。",
                        "show_key": True,
                        "secret": True,
                    },
                    "encoding_aes_key": {
                        "description": "消息加密密钥",
                        "type": "string",
                        "hint": "消息平台回调配置中的 EncodingAESKey，用于加密和解密消息。",
                        "show_key": True,
                        "secret": True,
                    },
                    "api_base_url": {
                        "description": "API 基础地址",
                        "type": "string",
                        "hint": "消息平台 API 的基础地址。使用默认官方服务时通常无需修改。",
                        "show_key": True,
                    },
                    "client_id": {
                        "description": "客户端 ID",
                        "type": "string",
                        "hint": "消息平台开放平台中的客户端 ID。",
                        "show_key": True,
                    },
                    "client_secret": {
                        "description": "客户端密钥",
                        "type": "string",
                        "hint": "消息平台开放平台中的客户端密钥。请妥善保管，避免泄露。",
                        "show_key": True,
                        "secret": True,
                    },
                    "start_message": {
                        "description": "Start 命令回复",
                        "type": "string",
                        "hint": "用户向 Telegram 机器人发送 /start 命令时回复的内容。",
                        "show_key": True,
                    },
                    "telegram_api_base_url": {
                        "description": "API 地址",
                        "type": "string",
                        "hint": "Telegram Bot API 的基础地址。使用官方服务时通常无需修改。",
                        "show_key": True,
                    },
                    "telegram_file_base_url": {
                        "description": "文件 API 地址",
                        "type": "string",
                        "hint": "Telegram Bot API 文件下载接口的基础地址。使用官方服务时通常无需修改。",
                        "show_key": True,
                    },
                    "bot_token": {
                        "description": "Slack Bot Token",
                        "type": "string",
                        "hint": "Slack 应用的 Bot User OAuth Token，通常以 xoxb- 开头。",
                        "show_key": True,
                        "secret": True,
                    },
                    "app_token": {
                        "description": "Slack App Token",
                        "type": "string",
                        "hint": "Slack Socket Mode 使用的 App-Level Token，通常以 xapp- 开头。",
                        "condition": {
                            "slack_connection_mode": "socket",
                        },
                        "show_key": True,
                        "secret": True,
                    },
                    "signing_secret": {
                        "description": "Slack Signing Secret",
                        "type": "string",
                        "hint": "Slack 应用的 Signing Secret，用于验证 Webhook 请求。",
                        "condition": {
                            "slack_connection_mode": "webhook",
                        },
                        "show_key": True,
                        "secret": True,
                    },
                    "channel_access_token": {
                        "description": "LINE 频道访问令牌",
                        "type": "string",
                        "hint": "LINE Messaging API 频道的 Channel Access Token。",
                        "show_key": True,
                        "secret": True,
                    },
                    "channel_secret": {
                        "description": "LINE 频道密钥",
                        "type": "string",
                        "hint": "LINE Messaging API 频道的 Channel Secret。",
                        "show_key": True,
                        "secret": True,
                    },
                    "lark_connection_mode": {
                        "description": "订阅方式",
                        "type": "string",
                        "options": ["socket", "webhook"],
                        "labels": ["长连接模式", "推送至服务器模式"],
                    },
                    "lark_encrypt_key": {
                        "description": "Encrypt Key",
                        "type": "string",
                        "hint": "用于解密飞书回调数据的加密密钥",
                        "secret": True,
                        "condition": {
                            "lark_connection_mode": "webhook",
                        },
                    },
                    "lark_verification_token": {
                        "description": "Verification Token",
                        "type": "string",
                        "hint": "用于验证飞书回调请求的令牌",
                        "secret": True,
                        "condition": {
                            "lark_connection_mode": "webhook",
                        },
                    },
                    "is_sandbox": {
                        "description": "沙箱模式",
                        "type": "bool",
                    },
                    "satori_api_base_url": {
                        "description": "Satori API 终结点",
                        "type": "string",
                        "hint": "Satori API 的基础地址。",
                    },
                    "satori_endpoint": {
                        "description": "Satori WebSocket 终结点",
                        "type": "string",
                        "hint": "Satori 事件的 WebSocket 端点。",
                    },
                    "satori_token": {
                        "description": "Satori 令牌",
                        "type": "string",
                        "hint": "用于 Satori API 身份验证的令牌。",
                        "secret": True,
                    },
                    "satori_auto_reconnect": {
                        "description": "启用自动重连",
                        "type": "bool",
                        "hint": "断开连接时是否自动重新连接 WebSocket。",
                    },
                    "satori_heartbeat_interval": {
                        "description": "Satori 心跳间隔",
                        "type": "int",
                        "hint": "发送心跳消息的间隔（秒）。",
                    },
                    "satori_reconnect_delay": {
                        "description": "Satori 重连延迟",
                        "type": "int",
                        "hint": "尝试重新连接前的延迟时间（秒）。",
                    },
                    "slack_connection_mode": {
                        "description": "Slack Connection Mode",
                        "type": "string",
                        "options": ["webhook", "socket"],
                        "hint": "The connection mode for Slack. `webhook` uses a webhook server, `socket` uses Slack's Socket Mode.",
                    },
                    "slack_webhook_host": {
                        "description": "Slack Webhook Host",
                        "type": "string",
                        "hint": "Only valid when Slack connection mode is `webhook`.",
                        "condition": {
                            "slack_connection_mode": "webhook",
                            "unified_webhook_mode": False,
                        },
                    },
                    "slack_webhook_port": {
                        "description": "Slack Webhook Port",
                        "type": "int",
                        "hint": "Only valid when Slack connection mode is `webhook`.",
                        "condition": {
                            "slack_connection_mode": "webhook",
                            "unified_webhook_mode": False,
                        },
                    },
                    "slack_webhook_path": {
                        "description": "Slack Webhook Path",
                        "type": "string",
                        "hint": "Only valid when Slack connection mode is `webhook`.",
                        "condition": {
                            "slack_connection_mode": "webhook",
                            "unified_webhook_mode": False,
                        },
                    },
                    "active_send_mode": {
                        "description": "是否换用主动发送接口",
                        "type": "bool",
                        "desc": "只有企业认证的公众号才能主动发送。主动发送接口的限制会少一些。",
                    },
                    "wpp_active_message_poll": {
                        "description": "是否启用主动消息轮询",
                        "type": "bool",
                        "hint": "只有当你发现微信消息没有按时同步到 AstrBot 时，才需要启用这个功能，默认不启用。",
                    },
                    "wpp_active_message_poll_interval": {
                        "description": "主动消息轮询间隔",
                        "type": "int",
                        "hint": "主动消息轮询间隔，单位为秒，默认 3 秒，最大不要超过 60 秒，否则可能被认为是旧消息。",
                    },
                    "kf_name": {
                        "description": "微信客服账号名",
                        "type": "string",
                        "hint": "可选。微信客服账号名(不是 ID)。可在 https://kf.weixin.qq.com/kf/frame#/accounts 获取",
                    },
                    "telegram_token": {
                        "description": "Bot Token",
                        "type": "string",
                        "hint": "如果你的网络环境为中国大陆，请在 `其他配置` 处设置代理或更改 api_base。",
                        "secret": True,
                    },
                    "mattermost_url": {
                        "description": "Mattermost URL",
                        "type": "string",
                        "hint": "Mattermost 服务地址，例如 https://chat.example.com。",
                    },
                    "mattermost_bot_token": {
                        "description": "Mattermost Bot Token",
                        "type": "string",
                        "hint": "在 Mattermost 中创建 Bot 账户后生成的访问令牌。",
                        "secret": True,
                    },
                    "mattermost_reconnect_delay": {
                        "description": "Mattermost 重连延迟",
                        "type": "float",
                        "hint": "WebSocket 断开后的重连等待时间，单位为秒。默认 5 秒。",
                    },
                    "misskey_instance_url": {
                        "description": "Misskey 实例 URL",
                        "type": "string",
                        "hint": "例如 https://misskey.example，填写 Bot 账号所在的 Misskey 实例地址",
                    },
                    "misskey_token": {
                        "description": "Misskey Access Token",
                        "type": "string",
                        "hint": "连接服务设置生成的 API 鉴权访问令牌（Access token）",
                        "secret": True,
                    },
                    "misskey_default_visibility": {
                        "description": "默认帖子可见性",
                        "type": "string",
                        "options": ["public", "home", "followers"],
                        "hint": "机器人发帖时的默认可见性设置。public：公开，home：主页时间线，followers：仅关注者。",
                    },
                    "misskey_local_only": {
                        "description": "仅限本站（不参与联合）",
                        "type": "bool",
                        "hint": "启用后，机器人发出的帖子将仅在本实例可见，不会联合到其他实例",
                    },
                    "misskey_enable_chat": {
                        "description": "启用聊天消息响应",
                        "type": "bool",
                        "hint": "启用后，机器人将会监听和响应私信聊天消息",
                    },
                    "misskey_enable_file_upload": {
                        "description": "启用文件上传到 Misskey",
                        "type": "bool",
                        "hint": "启用后，适配器会尝试将消息链中的文件上传到 Misskey。URL 文件会先尝试服务器端上传，异步上传失败时会回退到下载后本地上传。",
                    },
                    "misskey_allow_insecure_downloads": {
                        "description": "允许不安全下载（禁用 SSL 验证）",
                        "type": "bool",
                        "hint": "当远端服务器存在证书问题导致无法正常下载时，自动禁用 SSL 验证作为回退方案。适用于某些图床的证书配置问题。启用有安全风险，仅在必要时使用。",
                    },
                    "misskey_download_timeout": {
                        "description": "远端下载超时时间（秒）",
                        "type": "int",
                        "hint": "下载远程文件时的超时时间（秒），用于异步上传回退到本地上传的场景。",
                    },
                    "misskey_download_chunk_size": {
                        "description": "流式下载分块大小（字节）",
                        "type": "int",
                        "hint": "流式下载和计算 MD5 时使用的每次读取字节数，过小会增加开销，过大会占用内存。",
                    },
                    "misskey_max_download_bytes": {
                        "description": "最大允许下载字节数（超出则中止）",
                        "type": "int",
                        "hint": "如果希望限制下载文件的最大大小以防止 OOM，请填写最大字节数；留空或 null 表示不限制。",
                    },
                    "misskey_upload_concurrency": {
                        "description": "并发上传限制",
                        "type": "int",
                        "hint": "同时进行的文件上传任务上限（整数，默认 3）。",
                    },
                    "misskey_upload_folder": {
                        "description": "上传到网盘的目标文件夹 ID",
                        "type": "string",
                        "hint": "可选：填写 Misskey 网盘中目标文件夹的 ID，上传的文件将放置到该文件夹内。留空则使用账号网盘根目录。",
                    },
                    "card_template_id": {
                        "description": "卡片模板 ID",
                        "type": "string",
                        "hint": "可选。钉钉互动卡片模板 ID。启用后将使用互动卡片进行流式回复。",
                    },
                    "telegram_command_register": {
                        "description": "命令注册",
                        "type": "bool",
                        "hint": "启用后，AstrBot 将会自动注册 Telegram 命令。",
                        "show_key": True,
                    },
                    "telegram_command_auto_refresh": {
                        "description": "命令自动刷新",
                        "type": "bool",
                        "hint": "启用后，AstrBot 将会在运行时自动刷新 Telegram 命令。(单独设置此项无效)",
                        "show_key": True,
                    },
                    "telegram_command_register_interval": {
                        "description": "命令自动刷新间隔",
                        "type": "int",
                        "hint": "Telegram 命令自动刷新间隔，单位为秒。",
                        "show_key": True,
                    },
                    "telegram_polling_restart_delay": {
                        "description": "轮询重启延迟",
                        "type": "float",
                        "hint": "当轮询意外结束尝试自动重启时的延迟时间，理论上越短恢复越快，但过短（<0.1s）可能导致死循环针对 API 服务器的请求阻断。单位为秒。默认为 5s。",
                        "show_key": True,
                    },
                    "id": {
                        "description": "机器人名称",
                        "type": "string",
                        "hint": "机器人名称",
                    },
                    "type": {
                        "description": "适配器类型",
                        "type": "string",
                        "invisible": True,
                    },
                    "enable": {
                        "description": "启用",
                        "type": "bool",
                        "hint": "是否启用该适配器。未启用的适配器对应的消息平台将不会接收到消息。",
                    },
                    "appid": {
                        "description": "appid",
                        "type": "string",
                        "hint": "必填项。当前消息平台的 AppID。如何获取请参考对应平台接入文档。",
                    },
                    "secret": {
                        "description": "secret",
                        "type": "string",
                        "hint": "必填项。",
                        "secret": True,
                    },
                    "enable_group_c2c": {
                        "description": "启用消息列表单聊",
                        "type": "bool",
                        "hint": "启用后，机器人可以接收到 QQ 消息列表中的私聊消息。你可能需要在 QQ 机器人平台上通过扫描二维码的方式添加机器人为你的好友。详见文档。",
                    },
                    "enable_guild_direct_message": {
                        "description": "启用频道私聊",
                        "type": "bool",
                        "hint": "启用后，机器人可以接收到频道的私聊消息。",
                    },
                    "use_markdown": {
                        "description": "主动消息使用 Markdown",
                        "type": "bool",
                        "hint": "启用后，机器人主动发送消息默认以 Markdown 模式发送；插件显式调用 use_markdown() 指定行为时不受此配置影响。",
                    },
                    "ws_reverse_host": {
                        "description": "反向 Websocket 主机",
                        "type": "string",
                        "hint": "AstrBot 将作为服务器端。",
                    },
                    "ws_reverse_port": {
                        "description": "反向 Websocket 端口",
                        "type": "int",
                    },
                    "ws_reverse_token": {
                        "description": "反向 Websocket Token",
                        "type": "string",
                        "hint": "反向 Websocket Token。未设置则不启用 Token 验证。",
                        "secret": True,
                    },
                    "wecom_ai_bot_name": {
                        "description": "企业微信智能机器人的名字",
                        "type": "string",
                        "hint": "请务必填写正确，否则无法使用一些指令。",
                    },
                    "wecom_ai_bot_connection_mode": {
                        "description": "企业微信智能机器人连接模式",
                        "type": "string",
                        "options": ["webhook", "long_connection"],
                        "labels": ["Webhook 回调", "长连接"],
                        "hint": "Webhook 回调模式需要配置 Token/EncodingAESKey。长连接模式需要配置 BotID/Secret。",
                    },
                    "wecomaibot_init_respond_text": {
                        "description": "企业微信智能机器人初始响应文本",
                        "type": "string",
                        "hint": "当机器人收到消息时，首先回复的文本内容。留空则不设置。",
                    },
                    "wecomaibot_friend_message_welcome_text": {
                        "description": "企业微信智能机器人私聊欢迎语",
                        "type": "string",
                        "hint": "当用户当天进入智能机器人单聊会话，回复欢迎语，留空则不回复。",
                    },
                    "wecomaibot_token": {
                        "description": "企业微信智能机器人 Token",
                        "type": "string",
                        "hint": "用于 Webhook 回调模式的身份验证。",
                        "secret": True,
                        "condition": {
                            "wecom_ai_bot_connection_mode": "webhook",
                        },
                    },
                    "wecomaibot_encoding_aes_key": {
                        "description": "企业微信智能机器人 EncodingAESKey",
                        "type": "string",
                        "hint": "用于 Webhook 回调模式的消息加密解密。",
                        "secret": True,
                        "condition": {
                            "wecom_ai_bot_connection_mode": "webhook",
                        },
                    },
                    "msg_push_webhook_url": {
                        "description": "企业微信消息推送 Webhook URL",
                        "type": "string",
                        "hint": "用于 send_by_session 主动消息推送。格式示例: https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx",
                        "secret": True,
                    },
                    "only_use_webhook_url_to_send": {
                        "description": "仅使用 Webhook 发送消息",
                        "type": "bool",
                        "hint": "启用后，企业微信智能机器人的所有回复都改为通过消息推送 Webhook 发送。消息推送 Webhook 支持更多的消息类型（如图片、文件等）。",
                    },
                    "wecomaibot_ws_bot_id": {
                        "description": "长连接 BotID",
                        "type": "string",
                        "hint": "企业微信智能机器人长连接模式凭证 BotID。",
                        "condition": {
                            "wecom_ai_bot_connection_mode": "long_connection",
                        },
                    },
                    "wecomaibot_ws_secret": {
                        "description": "长连接 Secret",
                        "type": "string",
                        "hint": "企业微信智能机器人长连接模式凭证 Secret。",
                        "secret": True,
                        "condition": {
                            "wecom_ai_bot_connection_mode": "long_connection",
                        },
                    },
                    "wecomaibot_ws_url": {
                        "description": "长连接 WebSocket 地址",
                        "type": "string",
                        "invisible": True,
                        "hint": "默认值为 wss://openws.work.weixin.qq.com，一般无需修改。",
                        "condition": {
                            "wecom_ai_bot_connection_mode": "long_connection",
                        },
                    },
                    "wecomaibot_heartbeat_interval": {
                        "description": "长连接心跳间隔",
                        "type": "int",
                        "invisible": True,
                        "hint": "长连接模式心跳间隔（秒），建议 30 秒。",
                        "condition": {
                            "wecom_ai_bot_connection_mode": "long_connection",
                        },
                    },
                    "discord_token": {
                        "description": "Discord Bot Token",
                        "type": "string",
                        "hint": "在此处填入你的Discord Bot Token",
                        "secret": True,
                    },
                    "discord_proxy": {
                        "description": "Discord 代理地址",
                        "type": "string",
                        "hint": "可选的代理地址：http://ip:port",
                    },
                    "discord_command_register": {
                        "description": "注册 Discord 指令",
                        "hint": "启用后，自动将插件指令注册为 Discord 斜杠指令",
                        "type": "bool",
                    },
                    "discord_activity_name": {
                        "description": "Discord 活动名称",
                        "type": "string",
                        "hint": "可选的 Discord 活动名称。留空则不设置活动。",
                    },
                    "discord_allow_bot_messages": {
                        "description": "允许接收机器人消息",
                        "type": "bool",
                        "hint": "启用后，AstrBot 将接收来自其他 Discord 机器人的消息。适用于机器人间通信场景（如消息转发）。默认关闭。",
                    },
                    "port": {
                        "description": "回调服务器端口",
                        "type": "int",
                        "hint": "回调服务器端口。留空则不启用回调服务器。",
                        "condition": {
                            "unified_webhook_mode": False,
                        },
                    },
                    "callback_server_host": {
                        "description": "回调服务器主机",
                        "type": "string",
                        "hint": "回调服务器主机。留空则不启用回调服务器。",
                        "condition": {
                            "unified_webhook_mode": False,
                        },
                    },
                    "unified_webhook_mode": {
                        "description": "统一 Webhook 模式",
                        "type": "bool",
                        "hint": "Webhook 模式下使用 AstrBot 统一 Webhook 入口，无需单独开启端口。回调地址为 /api/platform/webhook/{webhook_uuid}。",
                    },
                    **PERSONAL_WECHAT_CONFIG_METADATA,
                    "webhook_uuid": {
                        "invisible": True,
                        "description": "Webhook UUID",
                        "type": "string",
                        "hint": "统一 Webhook 模式下的唯一标识符，创建平台时自动生成。",
                    },
                    "kook_bot_token": {
                        "description": "机器人 Token",
                        "type": "string",
                        "hint": "必填项。从 KOOK 开发者平台获取的机器人 Token。",
                        "secret": True,
                    },
                    "kook_reconnect_delay": {
                        "description": "重连延迟",
                        "type": "int",
                        "hint": "重连延迟时间（秒），使用指数退避策略。",
                    },
                    "kook_max_reconnect_delay": {
                        "description": "最大重连延迟",
                        "type": "int",
                        "hint": "重连延迟的最大值（秒）。",
                    },
                    "kook_max_retry_delay": {
                        "description": "最大重试延迟",
                        "type": "int",
                        "hint": "重试的最大延迟时间（秒）。",
                    },
                    "kook_heartbeat_interval": {
                        "description": "心跳间隔",
                        "type": "int",
                        "hint": "心跳检测间隔时间（秒）。",
                    },
                    "kook_heartbeat_timeout": {
                        "description": "心跳超时时间",
                        "type": "int",
                        "hint": "心跳检测超时时间（秒）。",
                    },
                    "kook_max_heartbeat_failures": {
                        "description": "最大心跳失败次数",
                        "type": "int",
                        "hint": "允许的最大心跳失败次数，超过后断开连接。",
                    },
                    "kook_max_consecutive_failures": {
                        "description": "最大连续失败次数",
                        "type": "int",
                        "hint": "允许的最大连续失败次数，超过后停止重试。",
                    },
                },
            },
            "platform_settings": {
                "type": "object",
                "items": {
                    "unique_session": {
                        "type": "bool",
                    },
                    "rate_limit": {
                        "type": "object",
                        "items": {
                            "time": {"type": "int"},
                            "count": {"type": "int"},
                            "strategy": {
                                "type": "string",
                                "options": ["stall", "discard"],
                            },
                        },
                    },
                    "no_permission_reply": {
                        "type": "bool",
                        "hint": "启用后，当用户没有权限执行某个操作时，机器人会回复一条消息。",
                    },
                    "empty_mention_waiting": {
                        "type": "bool",
                        "hint": "启用后，当消息内容只有 @ 机器人时，会触发等待，在 60 秒内的该用户的任意一条消息均会唤醒机器人。这在某些平台不支持 @ 和语音/图片等消息同时发送时特别有用。",
                    },
                    "empty_mention_waiting_need_reply": {
                        "type": "bool",
                        "hint": "在上面一个配置项中，如果启用了触发等待，启用此项后，机器人会使用 LLM 生成一条回复。否则，将不回复而只是等待。",
                    },
                    "friend_message_needs_wake_prefix": {
                        "type": "bool",
                        "hint": "启用后，私聊消息需要唤醒前缀才会被处理，同群聊一样。",
                    },
                    "ignore_bot_self_message": {
                        "type": "bool",
                        "hint": "某些平台会将自身账号在其他 APP 端发送的消息也当做消息事件下发导致给自己发消息时唤醒机器人",
                    },
                    "ignore_at_all": {
                        "type": "bool",
                        "hint": "启用后，机器人会忽略 @ 全体成员 的消息事件。",
                    },
                    "segmented_reply": {
                        "type": "object",
                        "items": {
                            "enable": {
                                "type": "bool",
                            },
                            "only_llm_result": {
                                "type": "bool",
                            },
                            "interval_method": {
                                "type": "string",
                                "options": ["random", "log"],
                            },
                            "interval": {
                                "type": "string",
                            },
                            "log_base": {
                                "type": "float",
                            },
                            "words_count_threshold": {
                                "type": "int",
                            },
                            "regex": {
                                "type": "string",
                            },
                            "content_cleanup_rule": {
                                "type": "string",
                            },
                        },
                    },
                    "reply_prefix": {
                        "type": "string",
                        "hint": "机器人回复消息时带有的前缀。",
                    },
                    "forward_threshold": {
                        "type": "int",
                        "hint": "超过一定字数后，机器人会将消息折叠成 QQ 群聊的 “转发消息”，以防止刷屏。目前仅 QQ 平台适配器适用。",
                    },
                    "enable_id_white_list": {
                        "type": "bool",
                    },
                    "id_whitelist": {
                        "type": "list",
                        "_special": "umo",
                        "items": {"type": "string"},
                        "hint": "只处理填写的 ID 发来的消息事件，为空时不启用。可使用 /sid 指令获取在平台上的会话 ID(类似 abc:GroupMessage:123)。管理员可在 WebUI 的配置文件 -> 访问控制 -> 白名单中管理白名单。",
                    },
                    "id_whitelist_log": {
                        "type": "bool",
                        "hint": "启用后，当一条消息没通过白名单时，会输出 INFO 级别的日志。",
                    },
                    "wl_ignore_admin_on_group": {
                        "type": "bool",
                    },
                    "wl_ignore_admin_on_friend": {
                        "type": "bool",
                    },
                    "reply_with_mention": {
                        "type": "bool",
                        "hint": "启用后，机器人回复消息时会 @ 发送者。实际效果以具体的平台适配器为准。",
                    },
                    "reply_with_quote": {
                        "type": "bool",
                        "hint": "启用后，机器人回复消息时会引用原消息。实际效果以具体的平台适配器为准。",
                    },
                    "path_mapping": {
                        "type": "list",
                        "items": {"type": "string"},
                        "hint": "此功能解决由于文件系统不一致导致路径不存在的问题。格式为 <原路径>:<映射路径>。如 `/app/.config/QQ:/var/lib/docker/volumes/xxxx/_data`。这样，当消息平台下发的事件中图片和语音路径以 `/app/.config/QQ` 开头时，开头被替换为 `/var/lib/docker/volumes/xxxx/_data`。这在 AstrBot 或者平台协议端使用 Docker 部署时特别有用。",
                    },
                },
            },
            "content_safety": {
                "type": "object",
                "items": {
                    "also_use_in_response": {
                        "type": "bool",
                        "hint": "启用后，大模型的响应也会通过内容安全审核。",
                    },
                    "baidu_aip": {
                        "type": "object",
                        "items": {
                            "enable": {
                                "type": "bool",
                                "hint": "启用此功能前，您需要手动在设备中安装 baidu-aip 库。一般来说，安装指令如下: `pip3 install baidu-aip`",
                            },
                            "app_id": {"description": "APP ID", "type": "string"},
                            "api_key": {
                                "description": "API Key",
                                "type": "string",
                                "secret": True,
                            },
                            "secret_key": {
                                "type": "string",
                                "secret": True,
                            },
                        },
                    },
                    "internal_keywords": {
                        "type": "object",
                        "items": {
                            "enable": {
                                "type": "bool",
                            },
                            "extra_keywords": {
                                "type": "list",
                                "items": {"type": "string"},
                                "hint": "额外的屏蔽关键词列表，支持正则表达式。",
                            },
                        },
                    },
                },
            },
        },
    },
    "misc_config_group": {
        "metadata": {
            "wake_prefix": {
                "type": "list",
                "items": {"type": "string"},
            },
            "t2i": {
                "type": "bool",
            },
            "t2i_word_threshold": {
                "type": "int",
            },
            "admins_id": {
                "type": "list",
                "_special": "sender_id",
                "items": {"type": "string"},
            },
            "http_proxy": {
                "type": "string",
            },
            "no_proxy": {
                "description": "直连地址列表",
                "type": "list",
                "items": {"type": "string"},
                "hint": "在此处添加不希望通过代理访问的地址，例如内部服务地址。回车添加，可添加多个，如未设置代理请忽略此配置",
            },
            "timezone": {
                "type": "string",
            },
            "callback_api_base": {
                "type": "string",
            },
            "disable_metrics": {
                "description": "禁用匿名使用统计",
                "type": "bool",
                "hint": "禁用后，AstrBot 将不再上传匿名使用统计数据。",
            },
            "log_level": {
                "type": "string",
                "options": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            },
            "dashboard.ssl.enable": {"type": "bool"},
            "dashboard.trust_proxy_headers": {"type": "bool"},
            "dashboard.auth_rate_limit.enable": {"type": "bool"},
            "dashboard.auth_rate_limit.average_interval": {"type": "float"},
            "dashboard.auth_rate_limit.max_burst": {"type": "int"},
            "dashboard.ssl.cert_file": {
                "type": "string",
                "condition": {"dashboard.ssl.enable": True},
            },
            "dashboard.ssl.key_file": {
                "type": "string",
                "condition": {"dashboard.ssl.enable": True},
            },
            "dashboard.ssl.ca_certs": {
                "type": "string",
                "condition": {"dashboard.ssl.enable": True},
            },
            "log_file_enable": {"type": "bool"},
            "log_file_path": {"type": "string", "condition": {"log_file_enable": True}},
            "log_file_max_mb": {"type": "int", "condition": {"log_file_enable": True}},
            "temp_dir_max_size": {"type": "int"},
            "trace_enable": {"type": "bool"},
            "trace_db_path": {"type": "string"},
            "trace_db_max_mb": {"type": "int"},
            "trace_retention_days": {"type": "int"},
            "t2i_strategy": {
                "type": "string",
                "options": ["remote", "local"],
            },
            "t2i_endpoint": {
                "type": "string",
            },
            "t2i_use_file_service": {
                "type": "bool",
            },
            "pip_install_arg": {
                "type": "string",
            },
            "pypi_index_url": {
                "type": "string",
            },
        },
    },
}


"""
Since v4.7.0, fields such as name, description, and hint support i18n.
Their resources are stored in:

- dashboard/src/i18n/locales/<locale>/features/config-metadata.json

When adding configuration fields here, update this file for every supported
Dashboard locale.
"""
CONFIG_METADATA_3 = {
    "loagent_group": {
        "name": "LoAgent",
        "metadata": {
            "loagent": {
                "description": "LoAgent 转发",
                "hint": "唤醒、白名单和限流通过后，消息会转发给 LoAgent 的 /api/channel/message，由 LoAgent 决定回复内容或保持沉默。",
                "type": "object",
                "items": {
                    "loagent_project": {
                        "description": "LoAgent 项目",
                        "type": "string",
                        "hint": "这份配置（人格）对应的 LoAgent 项目 ID。留空时不转发消息。",
                    },
                    "loagent_observe": {
                        "description": "旁听未唤醒的群消息",
                        "type": "bool",
                        "hint": "开启后，群里没有唤醒机器人的消息也会发给 LoAgent 的 /api/channel/observe，只记进记忆，不回复。仍受白名单和会话开关限制。",
                    },
                },
            },
        },
    },
    "platform_group": {
        "name": "平台与消息",
        "metadata": {
            "general": {
                "description": "基本",
                "type": "object",
                "items": {
                    "platform_settings.unique_session": {
                        "description": "隔离对话",
                        "type": "bool",
                        "hint": "启用后，支持隔离的渠道会为每位群成员使用独立上下文。指令权限请在「管理行为 → 指令」中设置。",
                    },
                    "wake_prefix": {
                        "description": "唤醒词",
                        "hint": "唤醒机器人的消息前缀的列表。也可以通过 @ 机器人来唤醒。",
                        "type": "list",
                        "items": {"type": "string"},
                    },
                    "platform_settings.friend_message_needs_wake_prefix": {
                        "description": "私聊消息需要唤醒词",
                        "hint": "私聊消息也必须带上唤醒前缀才能唤醒机器人。",
                        "type": "bool",
                    },
                    "platform_settings.reply_prefix": {
                        "description": "回复时的文本前缀",
                        "hint": "回复中附带的文本前缀。",
                        "type": "string",
                    },
                    "platform_settings.reply_with_mention": {
                        "description": "回复时 @ 发送人",
                        "hint": "回复时提及发送人。",
                        "type": "bool",
                    },
                    "platform_settings.reply_with_quote": {
                        "description": "回复时引用发送人消息",
                        "hint": "回复时引用发送人的对应消息。",
                        "type": "bool",
                    },
                    "platform_settings.forward_threshold": {
                        "description": "转发消息的字数阈值",
                        "hint": "在受支持的平台上，当回复消息过长时，采用 “合并消息转发” 的方式发送消息。",
                        "type": "int",
                    },
                    "platform_settings.empty_mention_waiting": {
                        "description": "只 @ 机器人是否触发等待",
                        "hint": "当发送一条只有提及机器人的消息时，是否在接下来的 1 分钟内保持唤醒状态等待用户的第二条消息。",
                        "type": "bool",
                    },
                    "disable_builtin_commands": {
                        "description": "禁用自带指令",
                        "type": "bool",
                        "hint": "禁用所有 AstrBot 的自带指令，如 help, sid, new 等。",
                    },
                },
            },
            "rate_limit": {
                "description": "速率限制",
                "type": "object",
                "items": {
                    "platform_settings.rate_limit.time": {
                        "description": "消息速率限制时间(秒)",
                        "type": "int",
                    },
                    "platform_settings.rate_limit.count": {
                        "description": "消息速率限制计数",
                        "type": "int",
                    },
                    "platform_settings.rate_limit.strategy": {
                        "description": "速率限制策略",
                        "type": "string",
                        "options": ["stall", "discard"],
                    },
                },
            },
            "content_safety": {
                "description": "内容安全",
                "type": "object",
                "items": {
                    "content_safety.also_use_in_response": {
                        "description": "同时检查模型的响应内容",
                        "type": "bool",
                    },
                    "content_safety.baidu_aip.enable": {
                        "description": "使用百度内容安全审核",
                        "type": "bool",
                        "hint": "您需要手动安装 baidu-aip 库。",
                    },
                    "content_safety.baidu_aip.app_id": {
                        "description": "App ID",
                        "type": "string",
                        "condition": {
                            "content_safety.baidu_aip.enable": True,
                        },
                    },
                    "content_safety.baidu_aip.api_key": {
                        "description": "API Key",
                        "type": "string",
                        "secret": True,
                        "condition": {
                            "content_safety.baidu_aip.enable": True,
                        },
                    },
                    "content_safety.baidu_aip.secret_key": {
                        "description": "Secret Key",
                        "type": "string",
                        "secret": True,
                        "condition": {
                            "content_safety.baidu_aip.enable": True,
                        },
                    },
                    "content_safety.internal_keywords.enable": {
                        "description": "关键词检查",
                        "type": "bool",
                    },
                    "content_safety.internal_keywords.extra_keywords": {
                        "description": "额外关键词",
                        "type": "list",
                        "items": {"type": "string"},
                        "hint": "额外的屏蔽关键词列表，支持正则表达式。",
                    },
                },
            },
            "others": {
                "description": "其他配置",
                "type": "object",
                "items": {
                    "platform_settings.ignore_bot_self_message": {
                        "description": "是否忽略机器人自身的消息",
                        "type": "bool",
                    },
                    "platform_settings.ignore_at_all": {
                        "description": "是否忽略 @ 全体成员事件",
                        "type": "bool",
                    },
                    "platform_settings.no_permission_reply": {
                        "description": "用户权限不足时是否回复",
                        "type": "bool",
                    },
                    "platform_specific.lark.pre_ack_emoji.enable": {
                        "description": "[飞书] 启用预回应表情",
                        "type": "bool",
                    },
                    "platform_specific.lark.pre_ack_emoji.emojis": {
                        "description": "表情列表（飞书表情枚举名）",
                        "type": "list",
                        "items": {"type": "string"},
                        "hint": "表情枚举名参考：https://open.feishu.cn/document/server-docs/im-v1/message-reaction/emojis-introduce",
                        "condition": {
                            "platform_specific.lark.pre_ack_emoji.enable": True,
                        },
                    },
                    "platform_specific.telegram.pre_ack_emoji.enable": {
                        "description": "[Telegram] 启用预回应表情",
                        "type": "bool",
                    },
                    "platform_specific.telegram.pre_ack_emoji.emojis": {
                        "description": "表情列表（Unicode）",
                        "type": "list",
                        "items": {"type": "string"},
                        "hint": "Telegram 仅支持固定反应集合，参考：https://gist.github.com/Soulter/3f22c8e5f9c7e152e967e8bc28c97fc9",
                        "condition": {
                            "platform_specific.telegram.pre_ack_emoji.enable": True,
                        },
                    },
                    "platform_specific.discord.pre_ack_emoji.enable": {
                        "description": "[Discord] 启用预回应表情",
                        "type": "bool",
                    },
                    "platform_specific.discord.pre_ack_emoji.emojis": {
                        "description": "表情列表（Unicode 或自定义表情名）",
                        "type": "list",
                        "items": {"type": "string"},
                        "hint": "填写 Unicode 表情符号，例如：👍、🤔、⏳",
                        "condition": {
                            "platform_specific.discord.pre_ack_emoji.enable": True,
                        },
                    },
                },
            },
        },
    },
    "access_group": {
        "name": "访问控制",
        "metadata": {
            "admins": {
                "description": "管理员",
                "type": "object",
                "items": {
                    "admins_id": {
                        "description": "管理员 ID",
                        "type": "list",
                        "_special": "sender_id",
                        "items": {"type": "string"},
                        "hint": "给机器人发送 /sid 指令以获取 ID。",
                    },
                },
            },
            "whitelist": {
                "description": "白名单",
                "type": "object",
                "items": {
                    "platform_settings.enable_id_white_list": {
                        "description": "启用白名单",
                        "type": "bool",
                        "hint": "启用后,只有在白名单内的会话会被响应。",
                    },
                    "platform_settings.id_whitelist": {
                        "description": "白名单 ID 列表",
                        "type": "list",
                        "_special": "umo",
                        "items": {"type": "string"},
                        "hint": "给机器人发送 /sid 指令以获取 ID。为空时代表不启用白名单功能。",
                    },
                    "platform_settings.id_whitelist_log": {
                        "description": "输出拦截日志",
                        "type": "bool",
                        "hint": "输出未通过白名单校验的消息的日志。",
                    },
                    "platform_settings.wl_ignore_admin_on_group": {
                        "description": "管理员群组消息无视 ID 白名单",
                        "type": "bool",
                    },
                    "platform_settings.wl_ignore_admin_on_friend": {
                        "description": "管理员私聊消息无视 ID 白名单",
                        "type": "bool",
                    },
                },
            },
        },
    },
    "plugin_group": {
        "name": "插件",
        "metadata": {
            "plugin": {
                "description": "插件",
                "type": "object",
                "items": {
                    "plugin_set": {
                        "description": "可用插件",
                        "type": "bool",
                        "hint": "默认启用全部未被禁用的插件。若插件在插件页面被禁用，则此处的选择不会生效。",
                        "_special": "select_plugin_set",
                    },
                },
            },
        },
    },
    "ext_group": {
        "name": "扩展功能",
        "metadata": {
            "segmented_reply": {
                "description": "分段回复",
                "type": "object",
                "items": {
                    "platform_settings.segmented_reply.enable": {
                        "description": "启用分段回复",
                        "hint": "以分段输出的方式发送回复消息。",
                        "type": "bool",
                    },
                    "platform_settings.segmented_reply.only_llm_result": {
                        "description": "仅对 LLM 结果分段",
                        "type": "bool",
                        "condition": {
                            "platform_settings.segmented_reply.enable": True,
                        },
                    },
                    "platform_settings.segmented_reply.interval_method": {
                        "description": "间隔方法。",
                        "hint": "random 为随机时间，log 为根据消息长度计算，$y=log_<log_base>(x)$，x为字数，y的单位为秒。",
                        "type": "string",
                        "options": ["random", "log"],
                        "condition": {
                            "platform_settings.segmented_reply.enable": True,
                        },
                    },
                    "platform_settings.segmented_reply.interval": {
                        "description": "随机间隔时间",
                        "type": "string",
                        "hint": "格式：最小值,最大值（如：1.5,3.5）",
                        "condition": {
                            "platform_settings.segmented_reply.enable": True,
                            "platform_settings.segmented_reply.interval_method": "random",
                        },
                    },
                    "platform_settings.segmented_reply.log_base": {
                        "description": "对数底数",
                        "type": "float",
                        "hint": "对数间隔的底数，默认为 2.6。取值范围为 1.0-10.0。",
                        "condition": {
                            "platform_settings.segmented_reply.enable": True,
                            "platform_settings.segmented_reply.interval_method": "log",
                        },
                    },
                    "platform_settings.segmented_reply.words_count_threshold": {
                        "description": "分段回复字数阈值",
                        "hint": "分段回复的字数上限。只有字数小于此值的消息才会被分段，超过此值的长消息将直接发送（不分段）。默认为 150",
                        "type": "int",
                        "condition": {
                            "platform_settings.segmented_reply.enable": True,
                        },
                    },
                    "platform_settings.segmented_reply.split_mode": {
                        "description": "分段模式",
                        "type": "string",
                        "options": ["regex", "words"],
                        "labels": ["正则表达式", "分段词列表"],
                        "condition": {
                            "platform_settings.segmented_reply.enable": True,
                        },
                    },
                    "platform_settings.segmented_reply.regex": {
                        "description": "分段正则表达式",
                        "hint": "用于分隔一段消息。默认情况下会根据句号、问号等标点符号分隔。如填写 `[。？！]` 将移除所有的句号、问号、感叹号。re.findall(r'<regex>', text)",
                        "type": "string",
                        "condition": {
                            "platform_settings.segmented_reply.enable": True,
                            "platform_settings.segmented_reply.split_mode": "regex",
                        },
                    },
                    "platform_settings.segmented_reply.split_words": {
                        "description": "分段词列表",
                        "type": "list",
                        "hint": "检测到列表中的任意词时进行分段，如：。、？、！等",
                        "condition": {
                            "platform_settings.segmented_reply.enable": True,
                            "platform_settings.segmented_reply.split_mode": "words",
                        },
                    },
                    "platform_settings.segmented_reply.content_cleanup_rule": {
                        "description": "内容过滤正则表达式",
                        "type": "string",
                        "hint": "移除分段后内容中的指定内容。如填写 `[。？！]` 将移除所有的句号、问号、感叹号。",
                        "condition": {
                            "platform_settings.segmented_reply.enable": True,
                        },
                    },
                },
            },
            "t2i": {
                "description": "文本转图像",
                "type": "object",
                "items": {
                    "t2i": {
                        "description": "文本转图像输出",
                        "hint": "将模型回复转换成图片后再发送，防止刷屏。",
                        "type": "bool",
                    },
                    "t2i_word_threshold": {
                        "description": "文本转图像字数阈值",
                        "type": "int",
                        "condition": {
                            "t2i": True,
                        },
                    },
                    "t2i_strategy": {
                        "description": "文本转图像策略",
                        "type": "string",
                        "hint": "文本转图像策略。`remote` 为使用远程基于 HTML 的渲染服务，`local` 为使用 PIL 本地渲染。当使用 local 时，将 ttf 字体命名为 'font.ttf' 放在 data/ 目录下可自定义字体。",
                        "options": ["remote", "local"],
                        "condition": {
                            "t2i": True,
                        },
                    },
                    "t2i_endpoint": {
                        "description": "文本转图像服务 API 地址",
                        "type": "string",
                        "hint": "为空时使用 AstrBot API 服务",
                        "condition": {
                            "t2i": True,
                            "t2i_strategy": "remote",
                        },
                    },
                    "t2i_template": {
                        "description": "文本转图像自定义模版",
                        "type": "bool",
                        "hint": "启用后可自定义 HTML 模板用于文转图渲染。",
                        "condition": {
                            "t2i": True,
                            "t2i_strategy": "remote",
                        },
                        "_special": "t2i_template",
                    },
                    "t2i_active_template": {
                        "description": "当前应用的文转图渲染模板",
                        "type": "string",
                        "hint": "此处的值由文转图模板管理页面进行维护。",
                        "invisible": True,
                    },
                },
            },
        },
    },
}

CONFIG_METADATA_3_SYSTEM = {
    "system_group": {
        "name": "系统配置",
        "metadata": {
            "system": {
                "description": "系统配置",
                "type": "object",
                "items": {
                    "loagent.endpoint": {
                        "description": "LoAgent 入口地址",
                        "type": "string",
                        "hint": "LoAgent 服务的地址，消息会 POST 到 <地址>/api/channel/message。环境变量 LOAGENT_ENDPOINT 优先。",
                    },
                    "loagent.token": {
                        "description": "LoAgent 入口 token",
                        "type": "string",
                        "hint": "请求时放在 Authorization: Bearer <token> 中。环境变量 LOAGENT_TOKEN 优先，其次是 LOAGENT_CHANNEL_TOKEN。",
                    },
                    "loagent.timeout": {
                        "description": "LoAgent 请求超时（秒）",
                        "type": "float",
                        "hint": "等待 LoAgent 回复的最长时间，超时后不回复。",
                    },
                    "log_level": {
                        "description": "控制台日志级别",
                        "type": "string",
                        "hint": "控制台输出日志的级别。",
                        "options": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                    },
                    "dashboard.ssl.enable": {
                        "description": "启用 WebUI HTTPS",
                        "type": "bool",
                        "hint": "启用后，WebUI 将直接使用 HTTPS 提供服务。",
                    },
                    "dashboard.trust_proxy_headers": {
                        "description": "信任代理请求头获取客户端 IP",
                        "type": "bool",
                        "hint": "关闭时忽略 X-Forwarded-For/X-Real-IP，仅使用连接地址。",
                    },
                    "dashboard.auth_rate_limit.enable": {
                        "description": "启用登录验证速率限制",
                        "type": "bool",
                        "hint": "关闭后将不对登录、TOTP 等身份验证接口进行速率限制。",
                    },
                    "dashboard.auth_rate_limit.average_interval": {
                        "description": "验证端点速率限制平均间隔(秒)",
                        "type": "float",
                        "hint": "两次身份验证请求之间的最小平均间隔时间。例如设置为 1.0 表示每秒最多处理 1 个请求。",
                        "condition": {"dashboard.auth_rate_limit.enable": True},
                    },
                    "dashboard.auth_rate_limit.max_burst": {
                        "description": "验证端点速率限制最大突发数",
                        "type": "int",
                        "hint": "允许的瞬时最大突发请求数。例如设置为 3 表示在短时间内最多连续处理 3 个请求。",
                        "condition": {"dashboard.auth_rate_limit.enable": True},
                    },
                    "dashboard.totp.enable": {
                        "description": "启用 WebUI TOTP 双因素认证",
                        "type": "bool",
                        "hint": "启用后，登录 WebUI 需要额外输入验证码。",
                        "_special": "dashboard_totp_manager",
                    },
                    "dashboard.ssl.cert_file": {
                        "description": "SSL 证书文件路径",
                        "type": "string",
                        "hint": "证书文件路径（PEM）。支持绝对路径和相对路径（相对于当前工作目录）。",
                        "condition": {"dashboard.ssl.enable": True},
                    },
                    "dashboard.ssl.key_file": {
                        "description": "SSL 私钥文件路径",
                        "type": "string",
                        "hint": "私钥文件路径（PEM）。支持绝对路径和相对路径（相对于当前工作目录）。",
                        "condition": {"dashboard.ssl.enable": True},
                    },
                    "dashboard.ssl.ca_certs": {
                        "description": "SSL CA 证书文件路径",
                        "type": "string",
                        "hint": "可选。用于指定 CA 证书文件路径。",
                        "condition": {"dashboard.ssl.enable": True},
                    },
                    "log_file_enable": {
                        "description": "启用文件日志",
                        "type": "bool",
                        "hint": "开启后会将日志写入指定文件。",
                    },
                    "log_file_path": {
                        "description": "日志文件路径",
                        "type": "string",
                        "hint": "相对路径以 data 目录为基准，例如 logs/astrbot.log；支持绝对路径。",
                    },
                    "log_file_max_mb": {
                        "description": "日志文件大小上限 (MB)",
                        "type": "int",
                        "hint": "超过大小后自动轮转，默认 20MB。",
                    },
                    "temp_dir_max_size": {
                        "description": "临时目录大小上限 (MB)",
                        "type": "int",
                        "hint": "用于限制 data/temp 目录总大小，单位为 MB。系统每 10 分钟检查一次，超限时按文件修改时间从旧到新删除，释放约 30% 当前体积。",
                    },
                    "trace_enable": {
                        "description": "启用追踪记录",
                        "type": "bool",
                        "hint": "追踪用户的每次指令和 AI 调用。",
                    },
                    "trace_db_path": {
                        "description": "追踪数据库路径",
                        "type": "string",
                        "hint": "相对路径以 data 目录为基准，例如 logs/traces.db；支持绝对路径。",
                    },
                    "trace_db_max_mb": {
                        "description": "追踪数据库容量预算 (MB)",
                        "type": "int",
                        "hint": "默认 80 MB，最小 32 MB，低于最小值时按 32 MB 生效。超出后自动清除旧数据。",
                    },
                    "trace_retention_days": {
                        "description": "追踪保留天数",
                        "type": "int",
                        "hint": "默认 7 天，期限或容量先达到者触发清理。",
                    },
                    "pip_install_arg": {
                        "description": "pip 安装额外参数",
                        "type": "string",
                        "hint": "安装插件依赖时，会使用 Python 的 pip 工具。这里可以填写额外的参数，如 `--break-system-package` 等。",
                    },
                    "pypi_index_url": {
                        "description": "PyPI 软件仓库地址",
                        "type": "string",
                        "hint": "安装 Python 依赖时请求的 PyPI 软件仓库地址。默认为 https://mirrors.aliyun.com/pypi/simple/",
                    },
                    "callback_api_base": {
                        "description": "对外可达的回调接口地址",
                        "type": "string",
                        "hint": "外部服务可能会通过 AstrBot 生成的回调链接（如文件下载链接）访问 AstrBot 后端。由于 AstrBot 无法自动判断部署环境中对外可达的主机地址（host），因此需要通过此配置项显式指定 “外部服务如何访问 AstrBot” 的地址。如 http://localhost:6185，https://example.com 等。",
                    },
                    "timezone": {
                        "description": "时区",
                        "type": "string",
                        "hint": "时区设置。请填写 IANA 时区名称, 如 Asia/Shanghai, 为空时使用系统默认时区。所有时区请查看: https://data.iana.org/time-zones/tzdb-2021a/zone1970.tab",
                    },
                    "http_proxy": {
                        "description": "代理",
                        "type": "string",
                        "hint": "启用后，会以添加环境变量的方式设置代理。支持 http://、https://、socks5:// 格式，例如：http://127.0.0.1:7890 或 socks5://127.0.0.1:7891",
                    },
                    "no_proxy": {
                        "description": "直连地址列表",
                        "type": "list",
                        "items": {"type": "string"},
                    },
                },
            },
        },
    },
}


DEFAULT_VALUE_MAP = {
    "int": 0,
    "float": 0.0,
    "bool": False,
    "string": "",
    "text": "",
    "list": [],
    "file": [],
    "object": {},
    "template_list": [],
    "dict": {},
}
