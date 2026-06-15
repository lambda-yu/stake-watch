import json
import asyncio
import random
import string
import time
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from stake_watch.api.deps import get_config_store
from stake_watch.storage.config_store import ConfigStore

router = APIRouter()

class WalletCreate(BaseModel):
    chain: str
    address: str
    label: str | None = None

class WalletResponse(BaseModel):
    id: int
    chain: str
    address: str
    label: str | None

class IntervalsUpdate(BaseModel):
    positions: int | None = None
    protocol_stats: int | None = None
    stablecoin_price: int | None = None
    stablecoin_supply: int | None = None
    reserves: int | None = None

class RiskUpdate(BaseModel):
    liquidation_warning: float | None = None
    liquidation_critical: float | None = None
    depeg_warning: float | None = None
    depeg_critical: float | None = None
    tvl_crash_threshold: float | None = None
    apy_change_threshold: float | None = None

class TelegramUpdate(BaseModel):
    bot_token: str | None = None
    chat_id: str | None = None

@router.get("/wallets")
async def list_wallets(store: ConfigStore = Depends(get_config_store)):
    wallets = await store.list_wallets()
    return [WalletResponse(id=w.id, chain=w.chain, address=w.address, label=w.label) for w in wallets]

@router.post("/wallets", status_code=201)
async def add_wallet(data: WalletCreate, store: ConfigStore = Depends(get_config_store)):
    w = await store.add_wallet(data.chain, data.address, data.label)
    return WalletResponse(id=w.id, chain=w.chain, address=w.address, label=w.label)

@router.delete("/wallets/{wallet_id}", status_code=204)
async def delete_wallet(wallet_id: int, store: ConfigStore = Depends(get_config_store)):
    await store.delete_wallet(wallet_id)
    return Response(status_code=204)

@router.get("/intervals")
async def get_intervals(store: ConfigStore = Depends(get_config_store)):
    settings = await store.load_app_settings()
    return settings.intervals.model_dump()

@router.put("/intervals")
async def update_intervals(data: IntervalsUpdate, store: ConfigStore = Depends(get_config_store)):
    for field, value in data.model_dump(exclude_none=True).items():
        await store.set_setting(f"intervals.{field}", value)
    settings = await store.load_app_settings()
    return settings.intervals.model_dump()

@router.get("/risk")
async def get_risk(store: ConfigStore = Depends(get_config_store)):
    settings = await store.load_app_settings()
    return settings.risk.model_dump()

@router.put("/risk")
async def update_risk(data: RiskUpdate, store: ConfigStore = Depends(get_config_store)):
    for field, value in data.model_dump(exclude_none=True).items():
        await store.set_setting(f"risk.{field}", value)
    settings = await store.load_app_settings()
    return settings.risk.model_dump()


@router.get("/telegram")
async def get_telegram(store: ConfigStore = Depends(get_config_store)):
    bot_token = await store.get_setting("telegram.bot_token") or ""
    chat_id = await store.get_setting("telegram.chat_id") or ""
    return {"bot_token": bot_token, "chat_id": chat_id, "configured": bool(bot_token and chat_id)}


@router.put("/telegram")
async def update_telegram(data: TelegramUpdate, store: ConfigStore = Depends(get_config_store)):
    if data.bot_token is not None:
        await store.set_setting("telegram.bot_token", data.bot_token)
    if data.chat_id is not None:
        await store.set_setting("telegram.chat_id", data.chat_id)
    bot_token = await store.get_setting("telegram.bot_token") or ""
    chat_id = await store.get_setting("telegram.chat_id") or ""
    return {"bot_token": bot_token, "chat_id": chat_id, "configured": bool(bot_token and chat_id)}


@router.post("/telegram/test")
async def test_telegram(store: ConfigStore = Depends(get_config_store)):
    bot_token = await store.get_setting("telegram.bot_token")
    chat_id = await store.get_setting("telegram.chat_id")
    if not bot_token or not chat_id:
        return {"success": False, "error": "Telegram 未配置，请先填写 Bot Token 和 Chat ID"}
    try:
        from telegram import Bot
        bot = Bot(token=bot_token)
        await bot.send_message(chat_id=chat_id, text="Stake Watch 测试消息 - 推送配置成功")
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


# --- Telegram Bind (listen for verification code) ---

_bind_state: dict = {}  # {"code": str, "expires": float, "task": Task|None, "chat_id": str|None, "status": str}


def _generate_code() -> str:
    return ''.join(random.choices(string.digits, k=6))


@router.post("/telegram/bind/start")
async def start_bind(store: ConfigStore = Depends(get_config_store)):
    bot_token = await store.get_setting("telegram.bot_token")
    if not bot_token:
        return {"success": False, "error": "请先填写 Bot Token"}

    code = _generate_code()
    _bind_state.clear()
    _bind_state.update({
        "code": code,
        "expires": time.time() + 300,
        "chat_id": None,
        "status": "waiting",
    })

    task = asyncio.create_task(_poll_for_code(bot_token, code, store))
    _bind_state["task"] = task

    return {"success": True, "code": code, "expires_in": 300}


@router.get("/telegram/bind/status")
async def bind_status():
    if not _bind_state:
        return {"status": "idle"}
    if time.time() > _bind_state.get("expires", 0):
        _cancel_bind()
        return {"status": "expired"}
    if _bind_state.get("status") == "bound":
        return {"status": "bound", "chat_id": _bind_state.get("chat_id")}
    return {"status": "waiting", "code": _bind_state.get("code")}


@router.post("/telegram/bind/cancel")
async def cancel_bind():
    _cancel_bind()
    return {"status": "cancelled"}


def _cancel_bind():
    task = _bind_state.get("task")
    if task and not task.done():
        task.cancel()
    _bind_state.clear()


import re

def _extract_code_from_text(text: str, code: str) -> bool:
    """Match verification code in various message formats:

    Group (privacy mode ON — only /commands get through):
    - "/bind 123456"
    - "/bind@mybot 123456"
    - "/bind_123456"
    - "/bind_123456@mybot"
    - "/start 123456"
    - "/verify 123456"

    Private chat or group (privacy mode OFF):
    - "123456"
    - "@botname 123456"
    - "123456 @botname"
    """
    stripped = text.strip()
    # Handle /command@botname format (Telegram appends @botname in groups)
    cmd_match = re.match(r'^/(bind|start|verify)(?:@\S+)?\s+(.*)', stripped)
    if cmd_match:
        return cmd_match.group(2).strip() == code
    # Handle /bind_CODE@botname format
    underscore_match = re.match(r'^/(bind|start|verify)_([\d]+)(?:@\S+)?$', stripped)
    if underscore_match:
        return underscore_match.group(2) == code
    # Handle plain text: strip @mentions
    cleaned = re.sub(r'@\S+', '', stripped).strip()
    return cleaned == code


async def _poll_for_code(bot_token: str, code: str, store: ConfigStore):
    try:
        from telegram import Bot
        bot = Bot(token=bot_token)
        offset = None

        while time.time() < _bind_state.get("expires", 0):
            try:
                updates = await bot.get_updates(offset=offset, timeout=5, allowed_updates=["message"])
                for update in updates:
                    offset = update.update_id + 1
                    msg = update.message
                    if not msg or not msg.text:
                        continue
                    if _extract_code_from_text(msg.text, code):
                        chat_id = str(msg.chat_id)
                        chat_type = msg.chat.type if msg.chat else "private"
                        chat_title = msg.chat.title if msg.chat and msg.chat.title else "私聊"
                        await store.set_setting("telegram.chat_id", chat_id)
                        _bind_state["chat_id"] = chat_id
                        _bind_state["status"] = "bound"
                        await bot.send_message(
                            chat_id=chat_id,
                            text=(
                                f"Stake Watch 绑定成功\n\n"
                                f"Chat ID: {chat_id}\n"
                                f"聊天类型: {chat_type} ({chat_title})\n"
                                f"验证码: {code}\n\n"
                                f"后续告警将推送到此{'群组' if 'group' in chat_type else '对话'}"
                            )
                        )
                        return
            except Exception:
                await asyncio.sleep(2)
            await asyncio.sleep(1)

        _bind_state["status"] = "expired"
    except asyncio.CancelledError:
        pass
