# AstrBot 的 LoAgent 网关分支（`feat/loagent-gateway`）

这个分支把 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 精简成 [LoAgent](https://github.com/Ry3nZhao/LoAgent) 的**平台接入层**。它有两种用法：

- **网关模式（LoAgent v3，`LOAGENT_GATEWAY=1`）**：AstrBot 只当各平台的接入 API。所有消息和平台事件原样上报给 LoAgent 的 Bot 服务（Bot 应用包的后端 `loagent-bots`），Bot 服务要发的话经网关的 HTTP 接口发出去。**唤醒、路由、白名单、审核都不在 AstrBot 里做**，AstrBot 自己的流水线在这个模式下不跑。协议见下面的「LoAgent 网关协议 v1」。
- **旧通道（v2 底座用，网关模式关着时）**：AstrBot 管通道、UMO 路由和唤醒规则，被唤醒的消息由流水线阶段 `loagent_forward` 同步转发给 LoAgent，见「旧通道」一节。v2 下线后删掉。

设计来源：LoAgent 仓库 `docs/design-v3/research/bots.md` 的 4.3、4.7、4.9（网关模式）；旧通道的设计在 v2 冻结分支的 `docs/design/architecture.md` A13。

## LoAgent 网关协议 v1

> 定于 2026-11-07（LoAgent 第三阶段 S3-2）。两边的类型：这里的 `astrbot/loagent_gateway/protocol.py`（pydantic），LoAgent 仓库的 `apps/bots/protocol`（Rust crate `loagent-bots-protocol`）。两边用同一组 JSON 样例做往返测试：`tests/fixtures/loagent_gateway/*.json` 是正本，LoAgent 那边有一份副本，它的测试会比对两份是否一致。

### 分工和连接

```
QQ（NapCat）──OneBot v11 反向 WS──┐
微信（wechat-selkies 网关）─OneBot v11 反向 WS──┤ AstrBot（网关模式）
Telegram、飞书……（以后）──各平台 SDK──┘   │ ① POST {Bot 服务}/v1/events（异步上报，2xx 才算收到）
                                         │ ② Bot 服务 → /api/v1/loagent/*（发送、查询、媒体）
                                   Bot 服务（loagent-bots）
```

- **入站**：适配器放进事件队列的每个事件（消息、通知、请求），`EventBus` 先交给网关。网关把它转成协议事件，**先写进自己的 SQLite 发件箱**（`data/loagent_gateway/gateway.db`），再按顺序批量 POST 给 Bot 服务。Bot 服务存好以后回 2xx；没收到 2xx 就退避重试（1 秒起，最长 60 秒），AstrBot 重启也不丢。400、413、422 表示 Bot 服务永远不收，这批移进 `dead` 表留查。
- **出站**：`POST /api/v1/loagent/send`。按 `instance + self_id` 找账号，**每次都带 `self_id`**，所以一个 OneBot 实例可以挂多个号（修 v2 的坑 1）。`request_id` 保证幂等：同一个 id 七天内再来，直接回上次的结果，不会再发。
- **鉴权**：两个方向用同一个令牌 `LOAGENT_GATEWAY_TOKEN`，放在 `Authorization: Bearer …`。网关没配令牌时，它的接口一律回 503（`not_configured`）。
- **AstrBot 控制台**不再给人用：网关模式下控制台的「更新」接口回 403（更新会拿原版覆盖本分支，v2 的坑 3），升级靠重新构建镜像。

### 通用规则

- JSON；**可选字段没有值时省略，不写 `null`**；列表和布尔值总是写出来；时间是 Unix 毫秒（`*_ms`）；id 一律是字符串。
- 每个事件和发送请求带 `"v": 1`。网关不认识的版本回 400（`unsupported_version`）。
- 不认识的段类型、事件类型直接报错，不静默丢。以后加类型就升版本。

### 账号、会话、发送者

| 类型 | 字段 |
|---|---|
| `AccountRef` | `platform`（网络：`qq`、`wechat`、`telegram`……）、`instance`（AstrBot 平台实例 id，发送时要用）、`self_id`（这个号自己的 id） |
| `Conversation` | `kind`（`group` / `private`）、`id`（群号；私聊是对方的 id）、`name?`（群名，只作显示） |
| `Sender` | `user_id`、`nickname`、`card?`（群名片）、`role?`（`owner` / `admin` / `member`）、`is_self`（这个号自己发的，比如从手机上） |

- `platform`：QQ 和微信都走 OneBot v11（适配器都是 `aiocqhttp`），所以由平台实例的配置项 **`loagent_platform`** 说明是哪个网络（Bot 服务用 `/bots` 管理接口建实例时填上）；没填时 OneBot 实例是 `onebot`，其他适配器用适配器名。
- 用户 id 只在同一个网络里可比。微信网关给的 id 是它自己映射出来的数字，换一个微信号就对不上，人物库合并时要注意。

### 消息和段

`Message`：`id`（平台消息 id；微信是网关给的稳定 id）、`account`、`conversation`、`sender`、`segments[]`、`reply_to?`、`at[]`、`sent_at_ms?`、`received_at_ms`。

- `reply_to` 和 `at` 是从段里推出来的，方便唤醒规则：`reply_to` 是第一个 `reply` 段的消息 id；`at` 是被 @ 的 id，@全体是 `"all"`，按出现顺序、不重复。**以段为准**。
- 收和发用同一套段（`type` 区分）：

| `type` | 字段 | 说明 |
|---|---|---|
| `text` | `text` | |
| `at` | `user_id`、`name?` | 真的 @，对方会收到提醒 |
| `at_all` | — | @全体成员 |
| `reply` | `message_id`、`sender_id?`、`sender_name?`、`text?`、`segments[]` | 引用。收到时网关填上原消息的发送者、文字和段（只展开一层）；发送时只看 `message_id` |
| `image` | `media`、`summary?` | |
| `sticker` | `media?`、`face_id?`、`name?` | 表情包（有 `media`）或平台表情（有 `face_id`，QQ 的 face） |
| `voice` | `media`、`duration_ms?`、`text?` | `text` 是平台自带的转写 |
| `video` | `media`、`cover?`、`duration_ms?` | |
| `file` | `media` | 文件名在 `media.name` |
| `forward` | `id?`、`nodes[]` | 合并转发。收到时平台常常只给 `id`；发送时用 `nodes`（`sender_id`、`sender_name`、`time_ms?`、`segments[]`） |
| `poke` | `target_id` | 戳一戳 |
| `share` | `url`、`title`、`content?`、`image?` | 链接卡片 |
| `location` | `lat`、`lon`、`title?`、`content?` | |
| `json` | `data` | 平台私有卡片（QQ ark），原样保留 |
| `unknown` | `raw_type`、`data` | 其他，原样保留 |

**媒体** `Media`：`url?`、`mime?`、`name?`、`size?`、`sha256?`。

- 收到时，`url` 是平台自己的 `http(s)` 地址（QQ 的图片地址会过期，Bot 服务要尽快下载），或者 `gateway://<sha256>`：网关手里只有本地文件、`base64://` 或 `data:` 的媒体，先拷进自己的缓存（`data/loagent_gateway/media/`，按内容哈希存，保留 7 天），Bot 服务用 `GET /api/v1/loagent/media/<sha256>` 取。没有 `url` 表示平台说有这个媒体，但网关拿不到。
- 发送时，`url` 可以是 `http(s)`（协议端自己去下）、`data:<mime>;base64,…`，或者先 `POST /api/v1/loagent/media` 上传拿到的 `gateway://` 引用。本地的媒体网关转成 `base64://` 交给协议端（协议端在别的容器里，看不到 AstrBot 的文件）。

### 入站事件：`POST {Bot 服务}/v1/events`

请求体 `{"events": [Event, …]}`，一批最多 50 个，按发生顺序。每个事件：

```jsonc
{ "v": 1, "id": "<网关的事件 id，32 位十六进制>", "dedupe_key": "…", "time_ms": 1794023157120,
  "kind": "message" | "notice" | "account", … }
```

| `kind` | 其余字段 | 什么时候发 |
|---|---|---|
| `message` | `message` | 群和私聊的**每一条**消息，有没有 @ 都发（没唤醒的群消息也进消息记录，取代旧的 observe 旁路） |
| `notice` | `account`、`conversation?`、`notice` | 平台通知和请求，见下表 |
| `account` | `status`（`AccountStatus`） | 账号状态每变一次发一次 |

`notice`（`type` 区分）：

| `type` | 字段 | 来自 OneBot v11 |
|---|---|---|
| `member_joined` | `user_id`、`operator_id?` | `group_increase` |
| `member_left` | `user_id`、`operator_id?`、`kicked` | `group_decrease`（`kick`、`kick_me` 算被踢） |
| `recalled` | `message_id`、`user_id?`、`operator_id?` | `group_recall`、`friend_recall` |
| `poke` | `user_id`、`target_id` | `notify` / `poke` |
| `friend_added` | `user_id` | `friend_add` |
| `request` | `request`（`friend` / `group_join` / `group_invite`）、`user_id`、`comment`、`flag` | `request` 事件。处理请求的接口以后再加 |
| `other` | `adapter`、`raw` | 其余通知（禁言、改群名片……）原样带上 |

**去重键** `dedupe_key`（Bot 服务按它去重，补交、重试都不会重复）：

| 事件 | 键 |
|---|---|
| 消息 | `msg:<platform>:<self_id>:<消息 id>`；平台没给 id 时，用会话、发送者、时间、文字算一个 `h…` 哈希当 id |
| 入群、退群 | `notice:<platform>:<self_id>:member_joined:<群>:<人>:<时间秒>`（`member_left` 同理） |
| 撤回 | `notice:<platform>:<self_id>:recalled:<消息 id>` |
| 戳一戳 | `notice:<platform>:<self_id>:poke:<会话>:<人>:<目标>:<时间秒>` |
| 加好友 | `notice:<platform>:<self_id>:friend_added:<人>:<时间秒>` |
| 请求 | `notice:<platform>:<self_id>:request:<种类>:<flag>` |
| 其他通知 | `notice:<platform>:<self_id>:other:<原始 JSON 的 md5>` |
| 账号状态 | `account:<platform>:<self_id>:<state>:<since_ms>` |

**账号状态** `AccountStatus`：`account`、`state`、`reason?`、`detail?`、`nickname?`、`since_ms`、`last_seen_ms?`。

| `state` | `reason` | 怎么判断（OneBot 实例：QQ、微信） |
|---|---|---|
| `connecting` | — | 协议端连上了（`meta_event` 的 `lifecycle` / `connect`），还没证明自己正常 |
| `online` | — | 心跳里 `status.online` 和 `status.good` 都不是 false，或者收到了这个号的消息、通知 |
| `offline` | `kicked` | NapCat 的 `bot_offline` 通知：被平台踢下线，要重新扫码 |
| `offline` | `unhealthy` | 心跳里 `online` 或 `good` 是 false |
| `offline` | `heartbeat_timeout` | 超过 3 个心跳间隔没有心跳（**假活**：连接还在、收不到东西） |
| `offline` | `disconnected` | 协议端的反向 WebSocket 断了 |
| `offline` | `platform_error` / `stopped` | AstrBot 的平台实例出错 / 被删或停了 |

看门狗每 5 秒查一次。重连、重启容器、扫码这些动作由 Bot 服务做（bots.md 4.7），网关只报状态。

### 出站：`POST /api/v1/loagent/send`

```jsonc
{ "v": 1, "request_id": "<bot.send 这个 Effect 的键>",
  "account": { "platform": "qq", "instance": "qq_main", "self_id": "10001" },
  "conversation": { "kind": "group", "id": "123456" },
  "segments": [ … ] }
```

- 成功（200）：`{ "request_id", "message_ids": […], "degraded": [{ "index", "from", "to", "reason" }…], "duplicate": false }`。段被拆开发时 `message_ids` 有多个；平台不回 id 时是空列表。
- 顺序照原样，只是 `reply` 挪到最前面。在 QQ 上，`file`、`voice`、`video`、`forward`、`poke` 要单独成一条消息，网关按顺序拆开发。
- **降级**：平台发不了的段，`share`、`location`、带 `nodes` 的 `forward`、带 `name` 的 `sticker` 改成文字，其余丢掉；每一处都记在 `degraded` 里。微信网关现在只能发文字、@ 和引用，图片、语音、文件都会被丢掉（要在 wechat-selkies 里补）。
- 拆开发的中途失败：一条都没发出去时 `retryable = true`；已经发出去一部分时 `retryable = false`，免得重试重复发。

### 查询

| 接口 | 参数 | 回答 |
|---|---|---|
| `GET /api/v1/loagent/health` | — | `{ v, astrbot_version, enabled, outbox: { pending, last_delivered_ms?, last_error? } }` |
| `GET /api/v1/loagent/accounts` | — | `{ accounts: [AccountStatus] }` |
| `GET /api/v1/loagent/conversations` | `instance`、`self_id` | `{ conversations: [{ kind, id, name?, member_count? }] }`（群加好友；微信网关没有好友列表） |
| `GET /api/v1/loagent/members` | `instance`、`self_id`、`group_id` | `{ members: [Member] }`，`Member` 是 `user_id`、`nickname`、`card?`、`role?`、`joined_at_ms?`、`last_sent_ms?` |
| `GET /api/v1/loagent/profile` | `instance`、`self_id`、`user_id`、`group_id?` | `{ profile: Member }` |
| `GET /api/v1/loagent/history` | `instance`、`self_id`、`kind`、`id`、`count?`（默认 20，最多 100）、`before?` | `{ messages: [Message] }`（NapCat 的 `get_group_msg_history` / `get_friend_msg_history`） |
| `POST /api/v1/loagent/media` | 请求体是文件内容；`Content-Type`、`X-Media-Name`（URL 编码） | `{ media: Media }`，`url` 是 `gateway://…` |
| `GET /api/v1/loagent/media/<sha256>` | — | 文件内容 |

查询现在只有 OneBot 实例支持，别的适配器回 501（`unsupported`）。

### 错误

非 2xx 的回答都是 `{ "error": { "code", "message", "retryable" } }`：

| `code` | HTTP | 说明 |
|---|---|---|
| `unauthorized` | 401 | 令牌不对 |
| `invalid_request` / `unsupported_version` | 400 | 请求体不对 / 版本不认识 |
| `account_not_found` | 404 | 没有这个实例，或者 `platform` 和实例对不上 |
| `account_offline` | 503 | 号没连上、被踢、不健康。`retryable = true`，Bot 服务的 Effects 会重试，过了时效的标成投递失败 |
| `unsupported_segment` / `media_unavailable` | 422 | 整条都发不了 / 媒体读不到 |
| `unsupported` | 501 | 这个平台没有这个查询 |
| `platform_error` | 502 | 协议端报错 |
| `not_configured` | 503 | 网关没配令牌 |

### 配置

| 环境变量 | 配置项（默认配置里的 `loagent_gateway`） | 说明 |
|---|---|---|
| `LOAGENT_GATEWAY` | `enabled` | `1` 打开网关模式。打开后 AstrBot 的流水线（唤醒、白名单、插件指令、旧通道）都不跑 |
| `LOAGENT_GATEWAY_ENDPOINT` | `endpoint` | Bot 服务的地址，事件 POST 到 `{endpoint}/v1/events`。没配时事件留在发件箱里 |
| `LOAGENT_GATEWAY_TOKEN` | `token` | 两个方向共用的令牌 |
| — | `heartbeat_grace`、`media_retention_days` | 心跳超时倍数（默认 3）、媒体缓存保留天数（默认 7） |

平台实例的配置里加 `loagent_platform`（`qq`、`wechat`……），见上面「账号」。

### 代码在哪

全部在独立的包 `astrbot/loagent_gateway/` 里（`protocol`、`convert`、`outbound`、`accounts`、`media`、`store`、`gateway`、`api`、`settings`），AstrBot 自己的代码只改了三处接缝，每处几行：

| 文件 | 改了什么 |
|---|---|
| `astrbot/core/event_bus.py` | `EventBus.observer`：分发前先交给它，它收下就不进流水线 |
| `astrbot/core/core_lifecycle.py` | 建网关、挂上 `observer`、和别的任务一起跑 `gateway.run()` |
| `astrbot/dashboard/api/app.py` | `loagent_gateway.api.install(app)`：挂路由、网关模式下拒绝自更新 |

测试：`tests/test_loagent_gateway.py`（上报、投递重试、账号状态、发送和降级、查询、HTTP 接口）、`tests/test_loagent_gateway_protocol.py`（共用样例往返）。

## 保留

| 模块 | 说明 |
|---|---|
| `astrbot/core/platform` | 全部平台适配器原样保留（`aiocqhttp`、`qqofficial`、`qqofficial_webhook`、`wecom`、`wecom_ai_bot`、`weixin_oc`、`weixin_official_account`、`telegram`、`lark`、`satori`、`dingtalk`、`discord`、`kook`、`slack`、`line`、`misskey`、`mattermost`）。适配器按需懒加载，不用的不占运行时 |
| `astrbot/core/pipeline` | `waking_check`、`whitelist_check`、`session_status_check`、`rate_limit_check`、`content_safety_check`（关键词 / 百度内容审核，不依赖 LLM，所以留着）、`preprocess_stage`、`process_stage`（插件指令 + `loagent_forward`）、`result_decorate`、`respond` |
| `astrbot/core/umop_config_router.py`、`astrbot_config_mgr.py` | UMO 路由和多份配置 |
| `astrbot/core/star` | 插件系统（指令、事件钩子、平台适配器注册）。去掉了 LLM 工具 / Agent 相关的注册入口 |
| `astrbot/builtin_stars/builtin_commands` | 只留 `/help`、`/sid`、`/name`、`/set`、`/unset`、`/dashboard_update` |
| `astrbot/core/db` | 数据库层整块保留（对话、人格等表还在，只是不再有代码写入），以后跟进上游的迁移脚本不冲突 |
| 开放 API | `POST /api/v1/im/messages`（LoAgent 主动发言）、`GET /api/v1/im/bots`，按 API key 的 `im` 权限 |
| dashboard | 平台（机器人）、配置文件和 UMO 路由、插件、会话管理（启用 / 转发开关 / 插件开关）、控制台和平台日志、统计、Trace、设置 |

## 删除

整块删除，没有在保留的代码里零散改动：

| 删除 | 内容 |
|---|---|
| `astrbot/core/provider` | 所有 LLM、TTS、STT、embedding、rerank 提供方和 provider 管理器 |
| `astrbot/core/agent` | Agent 运行器（内置工具循环、dify、coze、dashscope、deerflow）、子代理、MCP 客户端、上下文压缩 |
| `astrbot/core/astr_main_agent*.py`、`astr_agent_*.py`、`subagent_orchestrator.py`、`llm_error_messages.py` | 主 Agent 组装、工具执行、子代理编排 |
| `astrbot/core/tools` | 给 LLM 用的工具（网页搜索、cron、消息、知识库、computer use） |
| `astrbot/core/knowledge_base`、`astrbot/core/db/vec_db` | 知识库、faiss 向量库 |
| `astrbot/core/skills`、`astrbot/core/computer` | Skills、本地 / 沙箱代码执行 |
| `astrbot/core/cron` | 定时任务（LoAgent 自己调度） |
| `astrbot/core/conversation_mgr.py`、`persona_mgr.py`、`persona_error_reply.py` | 对话历史和人格（提示词）管理 |
| `astrbot/core/backup` | 备份导入导出（依赖知识库等已删模块） |
| `astrbot/core/utils/{history_saver,image_input,llm_metadata,file_extract}.py`、`config/agent_runner.py` | 只为 LLM 存在的工具 |
| `astrbot/core/pipeline/process_stage/method/{agent_request.py,agent_sub_stages/}`、`process_stage/follow_up.py` | 原来的 LLM 请求阶段 |
| `astrbot/core/platform/sources/webchat`（只留 `message_parts_helper.py`） | 管理面板里的聊天（ChatUI）。`message_parts_helper.py` 被 `/im/messages` 用来把请求转成消息链 |
| `astrbot/builtin_stars/astrbot` | 群聊上下文感知（LTM）、内置 office/pdf skills |
| 内置命令 `/reset`、`/new`、`/stop`、`/stats`、`/provider` | 对话和模型相关 |
| dashboard 后端 API | providers、personas、conversations、chat、chat_projects、live_chat、knowledge_bases、skills、tools（含 MCP）、subagents、cron、backups；Open API 的 `/chat`、`/chat/ws`、`/chat/sessions`、`/configs`、`/file`；聊天附件上传路由；会话按 provider 批量切换 |
| dashboard 前端 | 对应的页面、路由、侧边栏、组件、store、API 封装和生成的 OpenAPI 客户端代码；配置页的「AI」分组换成「LoAgent」分组 |
| 配置项 | `provider_sources`、`provider`、`agent_runner`、`subagent_orchestrator`、`provider_ltm_settings`、知识库、computer use / 沙箱、网页搜索等；`provider_settings` 只留保留阶段还在读的几项（唤醒前缀、引用解析、流式回退等） |
| 依赖 | `openai`、`anthropic`、`google-genai`、`dashscope`、`mcp`、`faiss-cpu`、`xinference-client`、`rank-bm25`、`jieba`、`markitdown-no-magika`、`pypdf`、`python-docx`、`openpyxl`、`pandas`、`reportlab`、`xlrd`、`shipyard-*`、`aiodocker`、`python-ripgrep`、`docstring-parser`、`ormsgpack`、`pydub`。新增显式依赖 `python-multipart`（原来由 `mcp` 间接带进来，dashboard 的表单解析要用） |

精简前后（Python 3.12，`uv pip install -r requirements.txt` 到干净的 venv）：

| | 精简前 | 精简后 |
|---|---|---|
| 直接依赖 | 65 | 43 |
| 安装后的包（含间接依赖） | 150 | 90 |
| venv 体积 | 458 MB | 189 MB |
| `astrbot/` 下 Python 代码 | 156,703 行 | 83,150 行 |

## 旧通道：`loagent_forward` 和 `loagent_observe`（v2 底座用）

> 网关模式关着时才跑。网关模式取代了它们：同步等回复改成异步上报加确认，旁路并进「每条消息都上报」，唤醒规则搬到 Bot 服务。v2 下线后删掉这一节和对应代码。

### 流水线阶段 `loagent_forward`

文件：`astrbot/core/pipeline/process_stage/method/loagent_forward.py`，替换原来的 `agent_request`，由 `ProcessStage` 调用。触发条件和原来的 LLM 请求一样：消息通过了唤醒、白名单、会话开关、限流，没有被插件指令处理，并且 `event.is_at_or_wake_command` 为真（被 @、带唤醒词、私聊，或者引用了机器人的消息）。会话管理页的「LLM 开关」现在就是「是否转发给 LoAgent」。

请求：`POST {endpoint}/api/channel/message`，头 `Authorization: Bearer {token}`（token 为空时不带），`Content-Type: application/json`：

```jsonc
{
  "project": "persona-a",                    // 这份配置的 loagent_project
  "umo": "qq_main:GroupMessage:123456",      // 平台id:消息类型:会话id
  "platform": { "id": "qq_main", "type": "aiocqhttp" },
  "messageType": "group",                    // group | private | other
  "messageId": "777",                        // 这条消息的平台 id，回复时 replyTo 可以用它
  "groupId": "123456",                       // 私聊为空串
  "selfId": "10001",                         // 机器人自己的账号
  "sender": { "id": "20002", "name": "Alice" },
  "text": "hello bot @Bob(30003)",           // AstrBot 解析后的纯文本，已去掉唤醒前缀和开头 @机器人
  "images": ["https://..."],                 // 图片 URL；本地文件转成 data:image/...;base64,...
  "mentions": {
    "bot": true,                             // 是否 @ 了机器人
    "all": false,                            // 是否 @全体成员
    "users": [{ "id": "30003", "name": "Bob" }]  // 其他被 @ 的人
  },
  "replyTo": {                               // 引用的消息；没有引用时为 null
    "id": "555",
    "text": "earlier message",
    "sender": { "id": "30003", "name": "Bob" },
    "isBot": false                           // 被引用的是不是机器人自己的消息
  },
  "at": "2026-10-27T04:45:57+00:00"          // 消息时间（ISO 8601，UTC）
}
```

回复（HTTP 200，JSON）：

```jsonc
{ "silent": true }                           // 不说话；text 为空、只有空白时也按不说话处理

{
  "text": "hi Alice, noted.",                // 回复文本
  "at": ["20002"],                           // 可选：要 @ 的人。字符串、{ "id", "name" } 或它们的数组；"all" 表示 @全体
  "replyTo": "777",                          // 可选：引用哪条消息，消息 id 或 { "id": ... }
  "images": ["https://..."]                  // 可选：图片，http(s) URL、data:...;base64,... 或 base64://...
}
```

转成消息链的顺序是 `Reply(replyTo)`、每个 `At` 后跟一个空格、`Plain(text)`、`Image...`，标记为模型结果，之后照常经过 `result_decorate`（回复前缀、分段、文转图）和 `respond`。回复里已经带了 At / Reply 时，配置里的「回复时 @ 发送者」「引用回复」不会再重复加。

错误处理：401 / 403 记 error 日志（提示检查 token），其他 4xx / 5xx 记 error 日志和响应前 500 字，超时记 warning，连接失败等异常记 error；这些情况都不回复，流水线照常结束，不会抛出。

### 旁路 `loagent_observe`

文件：`astrbot/core/pipeline/process_stage/method/loagent_observe.py`，由 `WakingCheckStage` 调用。LoAgent 要把群里的每条消息都记进事件记忆，不只是它回复的那些：没有唤醒机器人的群消息在唤醒检查这一步被拦下之前，先交给 `LoAgentObserver`。

- **条件**（全部满足才发）：这份配置打开了 `loagent_observe`、填了 `loagent_project`；是群消息；发送者不是机器人自己；通过这份配置的白名单（白名单阶段在唤醒检查之后，所以这里照同样的规则再查一次，包括「群里管理员不受白名单限制」）；会话整体启用，并且会话管理页的「LLM 开关」（即「转发给 LoAgent」）没关。
- **请求**：`POST {endpoint}/api/channel/observe`，请求体和 token 与 `loagent_forward` 完全相同（同一个 `build_loagent_request`），`mentions.bot` 自然是 `false`。LoAgent 只入库，返回 `204`，不回复。
- **不阻塞流水线**：请求在后台任务里发，超时 10 秒。失败只记日志（401 / 403 记 error，其他 HTTP 错误、超时、连接失败记 warning），不影响消息处理。
- 私聊总是被唤醒（除非开了「私聊需要唤醒词」），被唤醒的消息走 `loagent_forward`，不会重复发到旁路。

### 配置

| 配置项 | 位置 | 说明 |
|---|---|---|
| `loagent_project` | 每份配置（WebUI 配置页「LoAgent」分组） | 这份配置对应的 LoAgent 项目 ID。留空则不转发，也不旁听 |
| `loagent_observe` | 同上 | 「旁听未唤醒的群消息」，默认关。打开后没唤醒的群消息发到 `/api/channel/observe` |
| `loagent.endpoint` | 默认配置（系统配置），全局 | LoAgent 入口地址，默认 `http://loagent:3080`（compose 网络里的服务名）。环境变量 `LOAGENT_ENDPOINT` 优先 |
| `loagent.token` | 同上 | Bearer token。环境变量 `LOAGENT_TOKEN` 优先，其次 `LOAGENT_CHANNEL_TOKEN`（LoAgent 的 channel-gateway 读的就是这个名字，所以两个容器可以共用一个 env 文件，token 只填一次） |
| `loagent.timeout` | 同上 | 等待回复的秒数，默认 120（旁路固定 10 秒） |

## 怎么跟进上游

- 上游是 `AstrBotDevs/AstrBot` 的 `master`；本分支从 `cd405f2a7`（v4.29.3 之后）开出。
- 跟进时：`git fetch upstream && git merge upstream/master`（或 rebase）。冲突大多会落在下面几类，处理原则是「上游改了被删的模块就继续删，改了保留的模块就接受」：
  - 被删目录里的修改（modify/delete 冲突）：直接 `git rm`。
  - 少数「接缝」文件是有意改过的，要手工合并：`core/event_bus.py`（网关的 `observer`）、`core/core_lifecycle.py`（含建网关的几行）、`core/star/context.py`（重写为精简版 Context）、`core/star/star_manager.py`、`core/star/star_tools.py`、`core/star/register/*`、`core/platform/astr_message_event.py`（去掉 `request_llm`）、`core/platform/manager.py`（不再启动 WebChat）、`core/pipeline/process_stage/stage.py`、`core/pipeline/scheduler.py`、`core/pipeline/session_status_check/stage.py`、`core/config/default.py`、`core/config/astrbot_config.py`、`core/utils/migra_helper.py`、`api/*`、`dashboard/api/{app,router,files,open_api,sessions}.py`（`app.py` 含挂网关接口的一行）、`dashboard/server.py`、`dashboard/services/{config,open_api,session_management,plugin,stat,bot_cleanup}_service.py`，以及前端的路由、侧边栏、配置页和会话管理页。
  - 上游新增的 LLM / Agent 功能：不合进来；新增的平台适配器：保留。
  - 依赖：合并 `pyproject.toml` / `requirements.txt` 后，再按上面的「删除 / 依赖」一栏删掉 LLM 相关包。
  - 网关自己的包 `astrbot/loagent_gateway/` 是新增的，上游没有，不会冲突。
- 合并后跑 `uv sync && uv run pytest -q tests`（LoAgent v3 在本机 Mac 上跑；v2 底座当年在 `ci-py` 容器里跑），前端跑 `pnpm install && pnpm build && node --test tests/*.test.mjs && node scripts/check-i18n-keys.mjs`。网关的两个测试文件必须过。

## 打包注意

- 管理面板的前端产物（`astrbot/dashboard/dist`）不在仓库里。没有本地产物、或者产物的 `assets/version` 和核心版本对不上时，AstrBot 启动会从上游下载**原版** WebUI，里面还有已删页面（调用已删接口会 404）。
- `Dockerfile` 在上游的基础上加了一个 `dashboard` 构建阶段：用 pnpm（和 LoAgent 的 `ci` 容器同一版本）从本分支的 `dashboard/` 构建前端，写入 `dist/assets/version`（取 `pyproject.toml` 的版本，加 `v` 前缀，和上游发布流程一样），再拷进运行镜像的 `astrbot/dashboard/dist`。所以镜像里的 WebUI 就是本分支精简后的界面，启动时不会下载。为此 `.dockerignore` 不再排除整个 `dashboard/`，只排除 `dashboard/node_modules/` 和 `dashboard/dist/`。
- 不用 Docker 时：在 `dashboard/` 里 `pnpm build`，写好 `dist/assets/version`，把 `dist/` 放进 `astrbot/dashboard/dist`（`ASTRBOT_BUILD_DASHBOARD=1` 时 hatch 构建钩子 `scripts/hatch_build.py` 会构建和拷贝，但不写版本文件）。
- 「修复管理面板」（`/dashboard_update`）只确认产物和核心版本一致，镜像里自带的产物满足条件，不会下载。但控制台里的「更新 AstrBot」会从上游下载原版核心和界面，覆盖本分支，部署后不要用（升级走重新构建镜像）。
- LoAgent 的部署（LoAgent 仓库 `deploy/compose.yml` 的 `astrbot` 服务）用这个 Dockerfile 构建，首次启动时用 `deploy/astrbot/cmd_config.seed.json` 生成 `data/cmd_config.json`（预置 OneBot v11 平台 `qq`、`wechat` 和 LoAgent 入口，已有配置不覆盖）。

## 许可证

- AstrBot 以 **AGPL-3.0-or-later** 发布，本分支继续沿用：保留上游的 `LICENSE`、版权声明和作者信息，`pyproject.toml` 的 `license` 不变。
- fork（`Ry3nZhao/AstrBot`）是公开仓库，所有修改都以源码形式公开，满足 AGPL 第 13 条「通过网络提供服务时公开修改后源码」的要求。
- LoAgent 只通过 HTTP 和这个网关通信（网关模式：`/v1/events`、`/api/v1/loagent/*`；旧通道：`/api/channel/message`、`/im/messages`），两者是独立的程序，LoAgent 的许可证不受影响。
