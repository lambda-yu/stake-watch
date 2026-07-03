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
    command_bot = TelegramCommandBot(bot_token, int(chat_id), storage)
    bot_task = asyncio.create_task(_safe_run_bot(command_bot))
    logger.info("Telegram command bot started")
```

`_safe_run_bot` 是本地 helper：`try: await bot.run(); except Exception: logger.exception(...)`。目的：bot 若崩，不影响 FastAPI 与 scheduler。

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
async def run(self):
    self._app = ApplicationBuilder().token(self._bot_token).build()
    self._app.add_handler(CommandHandler("help", self._on_help))
    self._app.add_handler(CommandHandler("protocols", self._on_protocols))
    self._app.add_handler(CommandHandler("compare", self._on_compare))
    self._app.add_handler(CommandHandler("protocol", self._on_protocol))
    await self._app.initialize()
    await self._app.start()
    await self._app.updater.start_polling(drop_pending_updates=True)
    self._stopped = asyncio.Event()
    await self._stopped.wait()

async def stop(self):
    if self._app is None:
        return
    try:
        await self._app.updater.stop()
        await self._app.stop()
        await self._app.shutdown()
    finally:
        if self._stopped is not None:
            self._stopped.set()
```

`drop_pending_updates=True` 避免服务重启时把积压消息全跑一遍。

### 权限守卫

每个 handler 首行：

```python
if not self._authorized(update):
    return
```

`_authorized` 检查 `update.effective_chat and update.effective_chat.id == self._chat_id`。不匹配直接 `return`，不回复任何内容 —— 避免暴露 bot 存在。

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

直接 `await send_protocols_report(self._storage)`。该函数内部已经：
1. 触发 `refresh_all_protocols` 拿最新数据；
2. 组装并向 `telegram.chat_id` 推送文字报告。

命令 handler 本身不需要额外回复。

### `/compare`

直接 `await send_comparison_screenshot(self._storage)`。返回值可选择性用来回复错误信息：

```python
result = await send_comparison_screenshot(self._storage)
if not result.get("success"):
    await update.message.reply_text(f"截图失败：{result.get('error')}")
```

成功时截图本身已推送到 chat，无需额外回复。

### `/protocol <name>`

行为：

1. 从 `context.args` 拿参数。空 → 回复"用法：`/protocol <名字>`\n可用：\<候选\>"。
2. 参数用第一个 token（`context.args[0]`），忽略后面的（简化）。
3. `ConfigStore.list_protocols()` → 找 `p.name.lower() == arg.lower()`。
4. 未找到 → 回复"未找到 '\<arg\>'。可用：\<候选\>"。
5. 找到 → 组装文本回复。

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

数据源：
- `ProtocolConfigRow`: `name`, `chain`, `enabled`, `safety_score`, `risk_scores`
- `chains_breakdown = await config_store.get_setting(f"protocols.{name}.chains")` — 已经是每链每 asset 的 `{apy, tvl_usd}` 结构（复用 `protocols_report.py` 的读取路径）
- 若 `chains_breakdown` 为空：fallback 到 `storage.get_latest_protocol_stats(name)`，展示单一 chain + pool
- 时间戳来自 stats 记录（`ProtocolStats.timestamp`）；无则省略"最新数据"行
- TVL 格式化复用 `protocols_report._format_tvl` （对外暴露或重新实现小工具）

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

`tests/alerts/test_bot_commands.py`：

1. **`format_help`** — 输出包含 4 个命令名。
2. **`format_protocol_detail`**：
   - 有 chains_breakdown + stats + risk_scores → 完整格式
   - 无 chains_breakdown 但有 stats → fallback 分支
   - 无 stats → 省略"最新数据"行
   - risk_scores 为空 → 省略风险评分行
3. **权限守卫** — 构造 `Update` mock，`effective_chat.id` 不匹配时 handler 无副作用（不调用 `send_protocols_report` / `reply_text`）。
4. **`/protocol` 参数处理**：
   - 空参数 → 回复用法
   - 未匹配名字 → 回复"未找到"+ 候选
   - 大小写不敏感匹配成功 → 调用格式化函数
5. **候选列表格式化** — 空 DB / 有多个协议时的输出。

Handler 测试用 `AsyncMock` 模拟 `update.message.reply_text` 和 `Storage` / `ConfigStore`。不启动真的 polling。

不测试：`Application` 本身的 polling loop（属于第三方库行为）；`send_protocols_report` / `send_comparison_screenshot` 已有各自覆盖。

## 前端

无改动。设置页已经能编辑 `telegram.bot_token` 和 `telegram.chat_id`。

## 风险与权衡

- **共享 event loop**：bot polling、FastAPI、APScheduler 共享一个 loop。若某 handler 阻塞，会拖慢 API。缓解：handler 内的工作（`send_protocols_report` 等）本就是 async；截图操作已在 Playwright 里跑 subprocess。
- **`drop_pending_updates=True`**：重启期间用户发的命令丢失。可接受（个人工具，非关键路径）。
- **进程重启才能换 token**：接受。
- **`send_protocols_report` 内部会重跑一次 `refresh_all_protocols`**：用户频繁 `/protocols` 可能触发大量外部调用。当前不加限流，先观察实际使用；如成问题再加 per-user cooldown。

## 交付清单

1. `src/stake_watch/alerts/bot_commands.py` — 新文件
2. `src/stake_watch/main.py` — 集成启动/关闭
3. `tests/alerts/test_bot_commands.py` — 新测试
4. 无 seed.yaml / DB migration 改动
