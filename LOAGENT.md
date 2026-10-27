# AstrBot 的 LoAgent 通道网关分支（`loagent-gateway`）

这个分支把 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 精简成 [LoAgent](https://github.com/RuihanRZhao/LoAgent) 的**群聊通道网关**：

- AstrBot 只负责**通道（平台适配器）、路由（UMO → 配置）、唤醒规则**（@、唤醒词、私聊、白名单、限流、会话开关）。
- 大脑、记忆、人格都在 LoAgent。被唤醒的消息由新增的流水线阶段 `loagent_forward` 转发给 LoAgent，LoAgent 决定回复什么或者不说话。
- 一份 AstrBot 配置 = 一个人格 = LoAgent 的一个项目（`loagent_project`）。用 UMO 路由把平台、群、私聊分到不同配置。

设计来源：LoAgent 仓库 `docs/design/architecture.md` 的 A13，`docs/design/plan/stage2/README.md` 的 S2-1。

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

## 新增

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
  - 少数「接缝」文件是有意改过的，要手工合并：`core/core_lifecycle.py`、`core/star/context.py`（重写为精简版 Context）、`core/star/star_manager.py`、`core/star/star_tools.py`、`core/star/register/*`、`core/platform/astr_message_event.py`（去掉 `request_llm`）、`core/platform/manager.py`（不再启动 WebChat）、`core/pipeline/process_stage/stage.py`、`core/pipeline/scheduler.py`、`core/pipeline/session_status_check/stage.py`、`core/config/default.py`、`core/config/astrbot_config.py`、`core/utils/migra_helper.py`、`api/*`、`dashboard/api/{app,router,files,open_api,sessions}.py`、`dashboard/server.py`、`dashboard/services/{config,open_api,session_management,plugin,stat,bot_cleanup}_service.py`，以及前端的路由、侧边栏、配置页和会话管理页。
  - 上游新增的 LLM / Agent 功能：不合进来；新增的平台适配器：保留。
  - 依赖：合并 `pyproject.toml` / `requirements.txt` 后，再按上面的「删除 / 依赖」一栏删掉 LLM 相关包。
- 合并后在 LoAgent 的 `ci-py` 容器里跑 `uv sync && uv run pytest -q tests`，前端在 `ci` 容器里跑 `pnpm install && pnpm build && node --test tests/*.test.mjs && node scripts/check-i18n-keys.mjs`。

## 打包注意

- 管理面板的前端产物（`astrbot/dashboard/dist`）不在仓库里。没有本地产物、或者产物的 `assets/version` 和核心版本对不上时，AstrBot 启动会从上游下载**原版** WebUI，里面还有已删页面（调用已删接口会 404）。
- `Dockerfile` 在上游的基础上加了一个 `dashboard` 构建阶段：用 pnpm（和 LoAgent 的 `ci` 容器同一版本）从本分支的 `dashboard/` 构建前端，写入 `dist/assets/version`（取 `pyproject.toml` 的版本，加 `v` 前缀，和上游发布流程一样），再拷进运行镜像的 `astrbot/dashboard/dist`。所以镜像里的 WebUI 就是本分支精简后的界面，启动时不会下载。为此 `.dockerignore` 不再排除整个 `dashboard/`，只排除 `dashboard/node_modules/` 和 `dashboard/dist/`。
- 不用 Docker 时：在 `dashboard/` 里 `pnpm build`，写好 `dist/assets/version`，把 `dist/` 放进 `astrbot/dashboard/dist`（`ASTRBOT_BUILD_DASHBOARD=1` 时 hatch 构建钩子 `scripts/hatch_build.py` 会构建和拷贝，但不写版本文件）。
- 「修复管理面板」（`/dashboard_update`）只确认产物和核心版本一致，镜像里自带的产物满足条件，不会下载。但控制台里的「更新 AstrBot」会从上游下载原版核心和界面，覆盖本分支，部署后不要用（升级走重新构建镜像）。
- LoAgent 的部署（LoAgent 仓库 `deploy/compose.yml` 的 `astrbot` 服务）用这个 Dockerfile 构建，首次启动时用 `deploy/astrbot/cmd_config.seed.json` 生成 `data/cmd_config.json`（预置 OneBot v11 平台 `qq`、`wechat` 和 LoAgent 入口，已有配置不覆盖）。

## 许可证

- AstrBot 以 **AGPL-3.0-or-later** 发布，本分支继续沿用：保留上游的 `LICENSE`、版权声明和作者信息，`pyproject.toml` 的 `license` 不变。
- fork（`RuihanRZhao/AstrBot`）是公开仓库，所有修改都以源码形式公开，满足 AGPL 第 13 条「通过网络提供服务时公开修改后源码」的要求。
- LoAgent 只通过 HTTP 和这个网关通信（`/api/channel/message`、`/im/messages`），两者是独立的程序，LoAgent 的许可证不受影响。
