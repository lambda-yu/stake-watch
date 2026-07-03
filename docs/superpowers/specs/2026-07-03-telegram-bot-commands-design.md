# Telegram Bot 命令 — 主动查询协议信息

**Status:** Draft
**Date:** 2026-07-03

## 背景

Stake Watch 的 Telegram 集成目前只做**单向推送**：调度器周期性调用 `send_protocols_report`、`send_comparison_screenshot`、`send_stablecoin_report` 把消息推给配置好的 chat。用户无法主动查询数据，只能等下一次定时推送。

本设计新增 4 个 bot 命令，让用户从 Telegram 侧主动拉取协议对比、全量列表和单个协议详情。

## 范围

**In-scope:**
- 4 个 slash 命令：`/help`, `/protocols`, `/compare`, `/protocol <name>`
- 主进程内跑 polling，与 FastAPI + APScheduler 并行
- 仅允许配置好的 `telegram.chat_id` 触发（其他 chat 静默忽略）
- 自动启用：`telegram.bot_token` + `telegram.chat_id` 都配置时启动，否则不启动
- 单元测试覆盖格式化与权限守卫

**Out-of-scope:**
- 前端 UI 变动（无需 toggle 或额外配置项）
- 命令级别的开关（未来若需要，加 `telegram.bot_commands_enabled` 是简单扩展）
- Inline keyboards / callback query / conversation state
- Webhook 模式（保留 long polling）
- 稳定币报告命令 `/stables`（不在本次范围）
- 多用户 / 白名单（选项 2 已被否决，仅信任单一 chat_id）

## 架构

### 新增模块

**`src/stake_watch/alerts/bot_commands.py`** — 一个类 `TelegramCommandBot`：

```
TelegramCommandBot
├── __init__(bot_token, chat_id, storage)   # chat_id 存为 int
├── async run()                             # 建 Application、注册 handler、启动 polling
├── async stop()                            # 优雅关闭 updater + application
├── _authorized(update) -> bool             # chat_id 守卫
└── handlers:
    ├── _on_help
    ├── _on_protocols
    ├── _on_compare
    └── _on_protocol
```

以及独立的纯函数：

- `format_protocol_detail(protocol_row, stats, chains_breakdown, risk_scores, tz_offset) -> str`
- `format_help() -> str`

纯函数放在同一个文件（都是短的），便于单测。

### 生命周期集成（`main.py`）

在 `scheduled.start()` 之后、`server.serve()` 之前：

```python
bot_token = await config_store.get_setting("telegram.bot_token")
chat_id = await config_store.get_setting("telegram.chat_id")
command_bot = None
bot_task = None
if bot_token and chat_id:
    from stake_watch.alerts.bot_commands import TelegramCommandBot
    try:
        chat_id_int = int(str(chat_id).strip())
    except (TypeError, ValueError):
        logger.warning("Invalid telegram.chat_id %r; bot commands disabled", chat_id)
        chat_id_int = None
    if chat_id_int is not None:
        command_bot = TelegramCommandBot(bot_token, chat_id_int, storage)
        bot_task = asyncio.create_task(_safe_run_bot(command_bot))
        logger.info("Telegram command bot started")
```

`_safe_run_bot` 是本地 helper，只捕获 `Exception`（不是 `BaseException`，所以 `CancelledError` 仍能正常传播）并 log；再走 `finally` 保证 `stop()` 被调用。目的：bot 若崩不影响 FastAPI 与 scheduler，同时进程关闭时 polling 能干净退出：

```python
async def _safe_run_bot(bot):
    try:
        await bot.run()
    except Exception:
        logger.exception("Telegram command bot crashed")
    finally:
        await bot.stop()  # idempotent
```

关闭序列（`finally` 块内）：

```python
if command_bot is not None:
    await command_bot.stop()
if bot_task is not None:
    await bot_task
```

### polling 实现细节

使用 python-telegram-bot v22 的 `Application` 手动生命周期（避免 `run_polling()` 内置的 signal handler 抢主进程信号）：

```python
def __init__(self, bot_token, chat_id, storage):
    self._bot_token = bot_token
    self._chat_id = chat_id
    self._storage = storage
    self._app = None
    self._stopped = asyncio.Event()       # created eagerly — avoid start/stop race
    self._shutdown_done = False           # stop() idempotency
    self._protocols_lock = asyncio.Lock() # serialize /protocols refresh (see 并发)
    self._compare_lock = asyncio.Lock()   # serialize /compare screenshot

async def run(self):
    self._app = ApplicationBuilder().token(self._bot_token).build()
    self._app.add_handler(CommandHandler("help", self._on_help))
    self._app.add_handler(CommandHandler("protocols", self._on_protocols))
    self._app.add_handler(CommandHandler("compare", self._on_compare))
    self._app.add_handler(CommandHandler("protocol", self._on_protocol))
    self._app.add_error_handler(self._on_error)
    await self._app.initialize()
    await self._app.bot.set_my_commands([
        ("help",      "显示帮助"),
        ("protocols", "全部协议 APY / TVL 概览"),
        ("compare",   "协议对比页面截图"),
        ("protocol",  "单个协议详情：/protocol <名字>"),
    ])
    await self._app.start()
    await self._app.updater.start_polling(drop_pending_updates=True)
    await self._stopped.wait()

async def stop(self):
    if self._shutdown_done or self._app is None:
        self._stopped.set()
        return
    self._shutdown_done = True
    try:
        if self._app.updater and self._app.updater.running:
            await self._app.updater.stop()
        if self._app.running:
            await self._app.stop()
        await self._app.shutdown()
    finally:
        self._stopped.set()
```

要点：
- `_stopped` 在 `__init__` 里创建，避免 startup 与 shutdown 竞争导致 `run()` 永远挂起。
- `stop()` 是幂等的（`_shutdown_done` 短路），且能安全应对"start 之前就 stop"的场景。
- PTB v22 没有默认 error handler；必须显式 `add_error_handler(self._on_error)`，否则 handler 抛异常只会静默 log 到 PTB 自己的 logger。`_on_error` 里 log exception，若 `update` 来自授权 chat，则 `reply_text("处理命令时出错，请查看日志")`。
- `set_my_commands` 让 4 个命令进入 Telegram 客户端的 slash 自动补全菜单。

`drop_pending_updates=True` 避免服务重启时把积压消息全跑一遍。

### 权限守卫

每个 handler 首行：

```python
if not self._authorized(update):
    return
```

`_authorized` 检查 `update.effective_chat is not None and update.effective_chat.id == self._chat_id`。不匹配直接 `return`，不回复任何内容 —— 避免暴露 bot 存在。同时用 `logger.info("unauthorized: chat_id=%s cmd=%s", ...)` 记录，便于观察是否被外部尝试打扰。channel post / edited message 等无 `effective_chat` 的情况自然落入 False 分支。

## 命令行为

### `/help`

硬编码中文文本，列出 4 个命令的用法：

```
🤖 Stake Watch 命令
━━━━━━━━━━━━━━━━━━━━━━
/protocols  — 全部协议 APY / TVL 概览
/compare    — 协议对比页面截图
/protocol <名字>  — 单个协议详情
/help       — 显示此帮助
```

### `/protocols`

用 `self._protocols_lock` 序列化：

```python
if self._protocols_lock.locked():
    await update.message.reply_text("上一个查询还在跑，请稍等…")
    return
async with self._protocols_lock:
    await send_protocols_report(self._storage)
```

`send_protocols_report` 内部已经：
1. 触发 `refresh_all_protocols` 拿最新数据；
2. 组装并向 `telegram.chat_id` 推送文字报告。

锁避免用户连点两次触发两次全量 refresh（每次刷新会打所有 collectors 的外部 RPC/API）。成功时不额外回复，报告本身就是回复。

### `/compare`

同样用 `self._compare_lock` 序列化。截图涉及 Playwright 起 headless 浏览器，重入更贵。

```python
if self._compare_lock.locked():
    await update.message.reply_text("上一张截图还在生成，请稍等…")
    return
async with self._compare_lock:
    result = await send_comparison_screenshot(self._storage)
if not result.get("success"):
    await update.message.reply_text(f"截图失败：{result.get('error')}")
```

`send_comparison_screenshot` 返回 `dict` 形如 `{"success": True, "bytes": <int>}` 或 `{"success": False, "error": "<msg>"}`（见 `src/stake_watch/alerts/comparison_screenshot.py`）。成功时截图本身已推送到 chat，无需额外回复。

### `/protocol <name>`

行为：

1. 从 `context.args` 拿参数。空 → 回复"用法：`/protocol <名字>`\n可用：\<候选\>"。
2. 参数合并为 `" ".join(context.args).strip()` — 支持含空格 / 连字符的名字（当前 DB 名字都是单词，但未来若加入 `Aave V3` / `Sky Money` 之类不至于翻车）。
3. `ConfigStore.list_protocols()` → 找 `p.name.lower() == arg.lower()`。
4. 未找到 → 回复"未找到 '\<arg\>'。可用：\<候选\>"。
5. 找到 → 组装文本回复；若结果长度 > 3800 字符，截断并追加 `\n...(已截断)` —— Telegram 单条消息硬上限 4096 UTF-16 code units，留出余量。

**格式化函数** `format_protocol_detail`：

```
📋 Aave
━━━━━━━━━━━━━━━━━━━━━━
链: Ethereum
状态: 启用 ✓
Safety Score: 85

各链池子:
  Ethereum
    USDC  APY 4.12%  TVL $1.2B
    USDT  APY 3.98%  TVL $890M
  Base
    USDC  APY 5.20%  TVL $120M

风险评分: liquidity 90 / smart_contract 80 / governance 85
最新数据: 2026-07-03 14:20 (UTC+8)
```

**fallback 布局**（没有 `chains_breakdown` 但有 stats 时，与 `protocols_report.py` 的 fallback 保持一致）：

```
📋 Aave
━━━━━━━━━━━━━━━━━━━━━━
链: Ethereum
状态: 启用 ✓
Safety Score: 85

ETHEREUM USDC: APY 4.12%  TVL $1.2B

最新数据: 2026-07-03 14:20 (UTC+8)
```

数据源：
- `ProtocolConfigRow`: `name`, `chain`, `enabled`, `safety_score`, `risk_scores`
- `chains_breakdown = await config_store.get_setting(f"protocols.{name}.chains")` — 已经是每链每 asset 的 `{apy, tvl_usd}` 结构（复用 `protocols_report.py` 的读取路径）
- 若 `chains_breakdown` 为空：fallback 到 `storage.get_latest_protocol_stats(name)`，展示单一 chain + pool（asset 优先选 USDC，否则第一个 pool）
- 时间戳来自 stats 记录（`ProtocolStats.timestamp`）；格式化用 `alerts.timezone.now_display` 的同款模板作用在 `stats.timestamp` 上（`YYYY-MM-DD HH:MM (UTC±N)`），无 stats 则省略此行
- TVL 格式化：**把 `protocols_report._format_tvl` 提升为 `alerts/formatter.py` 里的 `format_tvl` 公共函数**，`protocols_report.py` 和 `bot_commands.py` 都 import 同一个，避免两份实现漂移。这是本 spec 的第 5 项交付物。

**Section 是否展示的规则:**
- Safety Score / 风险评分：值为 None 或空 dict 时省略该行
- 各链池子：空时省略整段，只显示上方 metadata

## 数据流

```
User → Telegram → polling → CommandHandler
                              │
                              ▼
                     _authorized? ─ no → return silently
                              │
                              yes
                              ▼
                     dispatch to handler
                              │
     ┌────────────────────────┼─────────────────────────┐
     ▼                        ▼                         ▼
send_protocols_report   send_comparison_screenshot   format_protocol_detail
     │                        │                         │
     ▼                        ▼                         ▼
Telegram push (existing)  Telegram push (existing)  reply_text (new)
```

## 错误处理

- **Bot 启动失败**（错误的 token 等）：`_safe_run_bot` 记 exception log，asyncio task 结束，其他部分继续。
- **单个命令内部异常**：python-telegram-bot 的 `Application` 自带 error handler；额外注册一个自定义 error handler 记 log，并向 chat 回复"处理命令时出错，请查看日志"（仅当 update 来自授权 chat 时）。
- **未配置 token/chat_id**：主进程日志"Telegram bot token or chat_id missing, bot commands disabled"，不启动 polling。
- **配置热更新**：不支持。用户在 Settings 里改 token/chat_id 需重启进程（跟 scheduler 大部分 job 的行为一致，简化设计）。

## 测试

按 `docs/testing/tdd.md` 的规范先写测试再实现。目标 80%+ 覆盖。

`tests/alerts/test_bot_commands.py`：

1. **`format_help`** — 输出包含 4 个命令名。
2. **`format_protocol_detail`**：
   - 有 chains_breakdown + stats + risk_scores → 完整格式
   - 无 chains_breakdown 但有 stats → fallback 分支（`<CHAIN> <asset>: APY x%  TVL y` 单行）
   - 无 stats → 省略"最新数据"行
   - risk_scores 为空 → 省略风险评分行
   - safety_score 为 None → 省略该行
3. **权限守卫**：
   - `effective_chat.id` 不匹配 → handler 无副作用（不调用 `send_protocols_report` / `reply_text`）
   - `effective_chat is None`（channel post / edited message 场景）→ 同上，返回 False
4. **`/protocol` 参数处理**：
   - 空参数 → 回复用法 + 候选
   - 未匹配名字 → 回复"未找到"+ 候选
   - 大小写不敏感匹配成功 → 调用格式化函数
   - 多 token 参数（`/protocol Aave V3`）→ join 后匹配
5. **候选列表格式化** — 空 DB / 有多个协议时的输出。
6. **并发锁**：`/protocols` 与 `/compare` 在锁被占用时回复"稍等"，不重复触发底层 refresh / 截图。
7. **生命周期**：
   - `stop()` 在 `run()` 之前被调用 → 无异常（幂等）
   - `stop()` 被连续调用两次 → 只 shutdown 一次
   - 注册的 error handler 捕获 handler 内 `raise` 后，polling loop 不崩（用 `AsyncMock` 让某 handler 抛异常，断言 `_on_error` 被调用）
8. **`chat_id` 解析**：`main.py` 的解析逻辑单测 —— 空串 / 非数字 → 不启动 bot 且 log warning。
9. **消息截断**：`format_protocol_detail` 结果 > 3800 字符时截断并加省略标记。
10. **`format_tvl`**（升级为 public 后）— 各量级的输出格式沿用旧的 `_format_tvl` 断言。

Handler 测试用 `AsyncMock` 模拟 `update.message.reply_text` 和 `Storage` / `ConfigStore`。不启动真的 polling。

不测试：`Application` 本身的 polling loop（属于第三方库行为）；`send_protocols_report` / `send_comparison_screenshot` 已有各自覆盖，仅在锁 / 授权层面 mock。

## 前端

无改动。设置页已经能编辑 `telegram.bot_token` 和 `telegram.chat_id`。

## 风险与权衡

- **共享 event loop**：bot polling、FastAPI、APScheduler 共享一个 loop。若某 handler 阻塞，会拖慢 API。缓解：handler 内的工作（`send_protocols_report` 等）本就是 async；截图操作已在 Playwright 里跑 subprocess。
- **`drop_pending_updates=True`**：重启期间用户发的命令丢失。可接受（个人工具，非关键路径）。
- **进程重启才能换 token / chat_id**：接受。前端改设置需重启。
- **`/protocols` 触发 `refresh_all_protocols` 的成本**：用 `_protocols_lock` 序列化。同一时刻只跑一个 refresh；后到的 `/protocols` 请求收到"稍等"提示而非再排队，避免请求堆积。
- **Telegram 4096 字节消息上限**：`/protocol` 结果做截断；`/protocols` 的输出由 `send_protocols_report` 自己负责（当前已知长度可控，本次不改）。

## 交付清单

1. `src/stake_watch/alerts/bot_commands.py` — 新文件（`TelegramCommandBot` + `format_help` + `format_protocol_detail`）
2. `src/stake_watch/alerts/formatter.py` — 增加 `format_tvl` 公共函数
3. `src/stake_watch/alerts/protocols_report.py` — 迁移到 `formatter.format_tvl`
4. `src/stake_watch/main.py` — 集成启动/关闭 + `chat_id` 解析容错
5. `tests/alerts/test_bot_commands.py` — 新测试
6. 无 seed.yaml / DB migration 改动

