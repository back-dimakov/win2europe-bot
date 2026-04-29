import asyncio
import html
import logging
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urlencode

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.methods import RefundStarPayment
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    ReplyKeyboardMarkup,
)


def load_env_file(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[7:].strip()

        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


load_env_file()


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "@wintoeurope_bot").strip()
SUPPORT_URL = os.getenv("SUPPORT_URL", "https://t.me/win2europe?direct").strip()
SUBSCRIPTION_BASE_URL = os.getenv("SUBSCRIPTION_BASE_URL", "https://sub.example.com/s").strip()
DB_PATH = os.getenv("DB_PATH", "vpn_bot.db").strip()
CHECK_EXPIRED_EVERY_SECONDS = int(os.getenv("CHECK_EXPIRED_EVERY_SECONDS", "60"))
USE_MOCK_MARZBAN = os.getenv("USE_MOCK_MARZBAN", "1").strip() == "1"
MARZBAN_BASE_URL = os.getenv("MARZBAN_BASE_URL", "http://localhost:8000").strip()
MARZBAN_USERNAME = os.getenv("MARZBAN_USERNAME", "").strip()
MARZBAN_PASSWORD = os.getenv("MARZBAN_PASSWORD", "").strip()
MARZBAN_VLESS_INBOUND = os.getenv("MARZBAN_VLESS_INBOUND", "VLESS TCP REALITY").strip()
VPN_ADDRESS = os.getenv("VPN_ADDRESS", "").strip()
VPN_PORT = int(os.getenv("VPN_PORT", "443"))
VPN_SNI = os.getenv("VPN_SNI", "www.microsoft.com").strip()
VPN_PUBLIC_KEY = os.getenv("VPN_PUBLIC_KEY", "").strip()
VPN_SHORT_ID = os.getenv("VPN_SHORT_ID", "").strip()
VPN_FINGERPRINT = os.getenv("VPN_FINGERPRINT", "chrome").strip()
VPN_ALPN = os.getenv("VPN_ALPN", "").strip()
VPN_FLOW = os.getenv("VPN_FLOW", "xtls-rprx-vision").strip()
VPN_SPIDER_X = os.getenv("VPN_SPIDER_X", "").strip()
ADMIN_IDS = {
    int(item.strip())
    for item in os.getenv("ADMIN_IDS", "").split(",")
    if item.strip().isdigit()
}

MENU_TARIFFS = "Тарифы"
MENU_MY_VPN = "Моя подписка"
MENU_SUPPORT = "Поддержка"

@dataclass(frozen=True)
class Plan:
    code: str
    title: str
    description: str
    stars: int
    days: int
    devices: int
    tier: str
    recommended: bool = False


PLANS = {
    "plus_1m": Plan(
        code="plus_1m",
        title="Plus • 2 устройства • 1 месяц",
        description="Рекомендуемый тариф для телефона и компьютера. Оптимальный баланс цены и удобства.",
        stars=199,
        days=30,
        devices=2,
        tier="Plus",
        recommended=True,
    ),
    "plus_3m": Plan(
        code="plus_3m",
        title="Plus • 2 устройства • 3 месяца",
        description="Рекомендуемый тариф для телефона и компьютера. Удобно брать на сезон без частых продлений.",
        stars=499,
        days=90,
        devices=2,
        tier="Plus",
        recommended=True,
    ),
    "plus_6m": Plan(
        code="plus_6m",
        title="Plus • 2 устройства • 6 месяцев",
        description="Рекомендуемый тариф для телефона и компьютера. Самый выгодный вариант в линейке Plus.",
        stars=899,
        days=180,
        devices=2,
        tier="Plus",
        recommended=True,
    ),
    "basic_1m": Plan(
        code="basic_1m",
        title="Basic • 1 устройство • 1 месяц",
        description="Базовый тариф для одного телефона или одного компьютера. Хороший стартовый вариант.",
        stars=149,
        days=30,
        devices=1,
        tier="Basic",
    ),
    "basic_3m": Plan(
        code="basic_3m",
        title="Basic • 1 устройство • 3 месяца",
        description="Базовый тариф для одного устройства. Подходит, если нужен доступ надолго без переплат.",
        stars=379,
        days=90,
        devices=1,
        tier="Basic",
    ),
    "basic_6m": Plan(
        code="basic_6m",
        title="Basic • 1 устройство • 6 месяцев",
        description="Базовый тариф для одного устройства на долгий срок.",
        stars=699,
        days=180,
        devices=1,
        tier="Basic",
    ),
    "family_1m": Plan(
        code="family_1m",
        title="Family / Team • 5 устройств • 1 месяц",
        description="Для семьи, нескольких своих устройств или маленькой команды.",
        stars=349,
        days=30,
        devices=5,
        tier="Family / Team",
    ),
    "family_3m": Plan(
        code="family_3m",
        title="Family / Team • 5 устройств • 3 месяца",
        description="Для семьи, нескольких своих устройств или маленькой команды на длительный срок.",
        stars=899,
        days=90,
        devices=5,
        tier="Family / Team",
    ),
    "family_6m": Plan(
        code="family_6m",
        title="Family / Team • 5 устройств • 6 месяцев",
        description="Максимальный тариф для семьи или команды. Дает лучший срок в старшей линейке.",
        stars=1599,
        days=180,
        devices=5,
        tier="Family / Team",
    ),
}

router = Router()


def require_token() -> None:
    if not BOT_TOKEN or BOT_TOKEN == "PASTE_YOUR_BOT_TOKEN_HERE":
        raise RuntimeError("Set BOT_TOKEN in the environment or in the local .env file.")


def require_real_marzban_settings() -> None:
    required_fields = {
        "MARZBAN_BASE_URL": MARZBAN_BASE_URL,
        "MARZBAN_USERNAME": MARZBAN_USERNAME,
        "MARZBAN_PASSWORD": MARZBAN_PASSWORD,
        "VPN_ADDRESS": VPN_ADDRESS,
        "VPN_PUBLIC_KEY": VPN_PUBLIC_KEY,
        "VPN_SHORT_ID": VPN_SHORT_ID,
    }
    missing = [key for key, value in required_fields.items() if not value]
    if missing:
        raise RuntimeError(f"Missing required Marzban/VPN settings: {', '.join(missing)}")


def build_vless_link(user_uuid: str, remark: str) -> str:
    query = {
        "encryption": "none",
        "flow": VPN_FLOW,
        "security": "reality",
        "sni": VPN_SNI,
        "fp": VPN_FINGERPRINT,
        "pbk": VPN_PUBLIC_KEY,
        "sid": VPN_SHORT_ID,
        "type": "tcp",
    }
    if VPN_SPIDER_X:
        query["spx"] = VPN_SPIDER_X
    if VPN_ALPN:
        query["alpn"] = VPN_ALPN
    return f"vless://{user_uuid}@{VPN_ADDRESS}:{VPN_PORT}?{urlencode(query, safe=',/')}#{quote(remark)}"


def extract_vless_uuid(user_data: dict) -> str:
    proxies = user_data.get("proxies") or {}
    vless_proxy = proxies.get("vless") or {}
    user_uuid = (vless_proxy.get("id") or "").strip()
    if not user_uuid:
        raise RuntimeError("Marzban did not return a VLESS UUID for the user.")
    return user_uuid


def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = db_connect()
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                telegram_user_id INTEGER PRIMARY KEY,
                telegram_username TEXT,
                marzban_username TEXT NOT NULL,
                subscription_url TEXT NOT NULL,
                paid_until INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 0,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                payload TEXT PRIMARY KEY,
                telegram_user_id INTEGER NOT NULL,
                plan_code TEXT NOT NULL,
                amount_xtr INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS payments (
                telegram_payment_charge_id TEXT PRIMARY KEY,
                telegram_user_id INTEGER NOT NULL,
                payload TEXT NOT NULL UNIQUE,
                plan_code TEXT NOT NULL,
                amount_xtr INTEGER NOT NULL,
                paid_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS refund_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL,
                telegram_payment_charge_id TEXT NOT NULL UNIQUE,
                plan_code TEXT NOT NULL,
                amount_xtr INTEGER NOT NULL,
                status TEXT NOT NULL,
                reason TEXT NOT NULL,
                admin_note TEXT DEFAULT '',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                refunded_at INTEGER DEFAULT 0
            )
            """
        )
    conn.close()


def now_ts() -> int:
    return int(time.time())


def fmt_ts(value: int) -> str:
    if not value:
        return "не активирована"
    return datetime.fromtimestamp(value).strftime("%d.%m.%Y %H:%M")


def render_connection_url(url: str) -> str:
    return f"<code>{html.escape(url, quote=False)}</code>"


async def safe_edit_message(
    callback: CallbackQuery,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: Optional[str] = None,
) -> None:
    try:
        await callback.message.edit_text(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=True,
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise
    await callback.answer()


async def replace_callback_message(
    callback: CallbackQuery,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: Optional[str] = None,
) -> None:
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    await callback.message.answer(
        text,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
        disable_web_page_preview=True,
    )
    await callback.answer()


def reply_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=MENU_TARIFFS), KeyboardButton(text=MENU_MY_VPN)],
            [KeyboardButton(text=MENU_SUPPORT)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выберите действие",
    )


def build_payload(plan_code: str, telegram_user_id: int) -> str:
    return f"vpn:{plan_code}:{telegram_user_id}:{uuid.uuid4().hex}"


def parse_payload(payload: str) -> tuple[str, int]:
    try:
        prefix, plan_code, user_id, _nonce = payload.split(":")
    except ValueError as exc:
        raise ValueError("Некорректный payload") from exc
    if prefix != "vpn":
        raise ValueError("Неизвестный prefix payload")
    return plan_code, int(user_id)


def create_order(payload: str, telegram_user_id: int, plan: Plan) -> None:
    conn = db_connect()
    with conn:
        conn.execute(
            """
            INSERT INTO orders (payload, telegram_user_id, plan_code, amount_xtr, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (payload, telegram_user_id, plan.code, plan.stars, "pending", now_ts()),
        )
    conn.close()


def get_order(payload: str) -> Optional[sqlite3.Row]:
    conn = db_connect()
    row = conn.execute("SELECT * FROM orders WHERE payload = ?", (payload,)).fetchone()
    conn.close()
    return row


def mark_order_paid(payload: str) -> None:
    conn = db_connect()
    with conn:
        conn.execute(
            "UPDATE orders SET status = ? WHERE payload = ?",
            ("paid", payload),
        )
    conn.close()


def payment_exists(telegram_payment_charge_id: str) -> bool:
    conn = db_connect()
    row = conn.execute(
        "SELECT 1 FROM payments WHERE telegram_payment_charge_id = ?",
        (telegram_payment_charge_id,),
    ).fetchone()
    conn.close()
    return row is not None


def save_payment(
    charge_id: str,
    telegram_user_id: int,
    payload: str,
    plan: Plan,
) -> None:
    conn = db_connect()
    with conn:
        conn.execute(
            """
            INSERT INTO payments (
                telegram_payment_charge_id,
                telegram_user_id,
                payload,
                plan_code,
                amount_xtr,
                paid_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (charge_id, telegram_user_id, payload, plan.code, plan.stars, now_ts()),
        )
    conn.close()


def get_latest_payment(telegram_user_id: int) -> Optional[sqlite3.Row]:
    conn = db_connect()
    row = conn.execute(
        """
        SELECT *
        FROM payments
        WHERE telegram_user_id = ?
        ORDER BY paid_at DESC
        LIMIT 1
        """,
        (telegram_user_id,),
    ).fetchone()
    conn.close()
    return row


def get_refund_request_by_charge(charge_id: str) -> Optional[sqlite3.Row]:
    conn = db_connect()
    row = conn.execute(
        "SELECT * FROM refund_requests WHERE telegram_payment_charge_id = ?",
        (charge_id,),
    ).fetchone()
    conn.close()
    return row


def get_refund_request(refund_request_id: int) -> Optional[sqlite3.Row]:
    conn = db_connect()
    row = conn.execute(
        "SELECT * FROM refund_requests WHERE id = ?",
        (refund_request_id,),
    ).fetchone()
    conn.close()
    return row


def create_refund_request(
    telegram_user_id: int,
    charge_id: str,
    plan_code: str,
    amount_xtr: int,
    reason: str,
) -> sqlite3.Row:
    conn = db_connect()
    timestamp = now_ts()
    with conn:
        conn.execute(
            """
            INSERT INTO refund_requests (
                telegram_user_id,
                telegram_payment_charge_id,
                plan_code,
                amount_xtr,
                status,
                reason,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                telegram_user_id,
                charge_id,
                plan_code,
                amount_xtr,
                "pending",
                reason,
                timestamp,
                timestamp,
            ),
        )
    row = conn.execute(
        """
        SELECT *
        FROM refund_requests
        WHERE telegram_payment_charge_id = ?
        """,
        (charge_id,),
    ).fetchone()
    conn.close()
    return row


def update_refund_request(
    refund_request_id: int,
    status: str,
    admin_note: str = "",
    refunded_at: int = 0,
) -> Optional[sqlite3.Row]:
    conn = db_connect()
    with conn:
        conn.execute(
            """
            UPDATE refund_requests
            SET status = ?,
                admin_note = ?,
                updated_at = ?,
                refunded_at = ?
            WHERE id = ?
            """,
            (status, admin_note, now_ts(), refunded_at, refund_request_id),
        )
    row = conn.execute(
        "SELECT * FROM refund_requests WHERE id = ?",
        (refund_request_id,),
    ).fetchone()
    conn.close()
    return row


def get_user(telegram_user_id: int) -> Optional[sqlite3.Row]:
    conn = db_connect()
    row = conn.execute(
        "SELECT * FROM users WHERE telegram_user_id = ?",
        (telegram_user_id,),
    ).fetchone()
    conn.close()
    return row


def upsert_user(
    telegram_user_id: int,
    telegram_username: str,
    marzban_username: str,
    subscription_url: str,
    paid_until: int,
) -> sqlite3.Row:
    conn = db_connect()
    current = conn.execute(
        "SELECT * FROM users WHERE telegram_user_id = ?",
        (telegram_user_id,),
    ).fetchone()
    timestamp = now_ts()

    if current:
        current_paid_until = current["paid_until"] or 0
        new_paid_until = max(current_paid_until, paid_until)
        with conn:
            conn.execute(
                """
                UPDATE users
                SET telegram_username = ?,
                    marzban_username = ?,
                    subscription_url = ?,
                    paid_until = ?,
                    is_active = 1,
                    updated_at = ?
                WHERE telegram_user_id = ?
                """,
                (
                    telegram_username,
                    marzban_username,
                    subscription_url,
                    new_paid_until,
                    timestamp,
                    telegram_user_id,
                ),
            )
    else:
        new_paid_until = paid_until
        with conn:
            conn.execute(
                """
                INSERT INTO users (
                    telegram_user_id,
                    telegram_username,
                    marzban_username,
                    subscription_url,
                    paid_until,
                    is_active,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    telegram_user_id,
                    telegram_username,
                    marzban_username,
                    subscription_url,
                    new_paid_until,
                    1,
                    timestamp,
                    timestamp,
                ),
            )

    row = conn.execute(
        "SELECT * FROM users WHERE telegram_user_id = ?",
        (telegram_user_id,),
    ).fetchone()
    conn.close()
    return row


def update_user_connection_url(telegram_user_id: int, connection_url: str) -> Optional[sqlite3.Row]:
    conn = db_connect()
    with conn:
        conn.execute(
            """
            UPDATE users
            SET subscription_url = ?,
                updated_at = ?
            WHERE telegram_user_id = ?
            """,
            (connection_url, now_ts(), telegram_user_id),
        )
    row = conn.execute(
        "SELECT * FROM users WHERE telegram_user_id = ?",
        (telegram_user_id,),
    ).fetchone()
    conn.close()
    return row


def get_expired_active_users() -> list[sqlite3.Row]:
    conn = db_connect()
    rows = conn.execute(
        """
        SELECT * FROM users
        WHERE is_active = 1 AND paid_until > 0 AND paid_until <= ?
        """,
        (now_ts(),),
    ).fetchall()
    conn.close()
    return rows


def mark_user_inactive(telegram_user_id: int) -> None:
    conn = db_connect()
    with conn:
        conn.execute(
            """
            UPDATE users
            SET is_active = 0,
                updated_at = ?
            WHERE telegram_user_id = ?
            """,
            (now_ts(), telegram_user_id),
        )
    conn.close()


def revoke_local_access(telegram_user_id: int) -> None:
    conn = db_connect()
    with conn:
        conn.execute(
            """
            UPDATE users
            SET is_active = 0,
                paid_until = 0,
                updated_at = ?
            WHERE telegram_user_id = ?
            """,
            (now_ts(), telegram_user_id),
        )
    conn.close()


def is_admin_user(user_id: int) -> bool:
    return user_id in ADMIN_IDS


class MockMarzbanClient:
    async def create_or_extend_user(
        self,
        telegram_user_id: int,
        telegram_username: str,
        expire_ts: Optional[int] = None,
    ) -> tuple[str, str]:
        safe_username = telegram_username or f"user_{telegram_user_id}"
        marzban_username = f"tg_{telegram_user_id}"
        subscription_url = f"{SUBSCRIPTION_BASE_URL}/{marzban_username}?src={safe_username}"
        return marzban_username, subscription_url

    async def get_connection_url(self, marzban_username: str, telegram_username: str) -> str:
        safe_username = telegram_username or marzban_username
        return f"{SUBSCRIPTION_BASE_URL}/{marzban_username}?src={safe_username}"

    async def deactivate_user(self, _marzban_username: str) -> bool:
        return True


class RealMarzbanClient:
    def __init__(self) -> None:
        self._token: Optional[str] = None
        self._token_ts: int = 0

    async def _get_token(self) -> str:
        import aiohttp
        if self._token and (now_ts() - self._token_ts) < 3600:
            return self._token
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{MARZBAN_BASE_URL}/api/admin/token",
                data={"username": MARZBAN_USERNAME, "password": MARZBAN_PASSWORD},
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                self._token = data["access_token"]
                self._token_ts = now_ts()
                return self._token

    async def create_or_extend_user(
        self,
        telegram_user_id: int,
        telegram_username: str,
        expire_ts: Optional[int] = None,
    ) -> tuple[str, str]:
        import aiohttp
        require_real_marzban_settings()
        token = await self._get_token()
        marzban_username = f"tg_{telegram_user_id}"
        headers = {"Authorization": f"Bearer {token}"}
        expire_ts = expire_ts or (now_ts() + 30 * 24 * 60 * 60)

        async with aiohttp.ClientSession() as session:
            # Проверяем, существует ли пользователь
            async with session.get(
                f"{MARZBAN_BASE_URL}/api/user/{marzban_username}",
                headers=headers,
            ) as resp:
                exists = resp.status == 200
                current_user_data = await resp.json() if exists else None

            if exists:
                # Продлеваем
                async with session.put(
                    f"{MARZBAN_BASE_URL}/api/user/{marzban_username}",
                    headers=headers,
                    json={"expire": expire_ts, "status": "active"},
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
            else:
                # Создаём
                async with session.post(
                    f"{MARZBAN_BASE_URL}/api/user",
                    headers=headers,
                    json={
                        "username": marzban_username,
                        "proxies": {"vless": {"flow": VPN_FLOW}},
                        "inbounds": {"vless": [MARZBAN_VLESS_INBOUND]},
                        "expire": expire_ts,
                        "data_limit": 0,
                        "data_limit_reset_strategy": "no_reset",
                    },
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()

        try:
            user_uuid = extract_vless_uuid(data)
        except RuntimeError:
            if current_user_data:
                user_uuid = extract_vless_uuid(current_user_data)
            else:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{MARZBAN_BASE_URL}/api/user/{marzban_username}",
                        headers=headers,
                    ) as resp:
                        resp.raise_for_status()
                        refreshed_data = await resp.json()
                        user_uuid = extract_vless_uuid(refreshed_data)

        remark = telegram_username or marzban_username
        connection_url = build_vless_link(user_uuid, remark)
        return marzban_username, connection_url

    async def get_connection_url(self, marzban_username: str, telegram_username: str) -> str:
        import aiohttp

        require_real_marzban_settings()
        token = await self._get_token()
        headers = {"Authorization": f"Bearer {token}"}

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{MARZBAN_BASE_URL}/api/user/{marzban_username}",
                headers=headers,
            ) as resp:
                resp.raise_for_status()
                user_data = await resp.json()

        user_uuid = extract_vless_uuid(user_data)
        remark = telegram_username or marzban_username
        return build_vless_link(user_uuid, remark)

    async def deactivate_user(self, marzban_username: str) -> bool:
        import aiohttp
        try:
            token = await self._get_token()
            async with aiohttp.ClientSession() as session:
                async with session.put(
                    f"{MARZBAN_BASE_URL}/api/user/{marzban_username}",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"status": "disabled"},
                ) as resp:
                    return resp.status == 200
        except Exception as e:
            logging.warning("Ошибка деактивации пользователя %s: %s", marzban_username, e)
            return False


marzban_client: MockMarzbanClient | RealMarzbanClient = (
    MockMarzbanClient() if USE_MOCK_MARZBAN else RealMarzbanClient()
)


async def refresh_user_connection(row: Optional[sqlite3.Row]) -> Optional[sqlite3.Row]:
    if not row or USE_MOCK_MARZBAN:
        return row

    try:
        connection_url = await marzban_client.get_connection_url(
            row["marzban_username"],
            row["telegram_username"] or row["marzban_username"],
        )
        return update_user_connection_url(row["telegram_user_id"], connection_url) or row
    except Exception as exc:
        logging.warning(
            "Failed to refresh connection URL for %s: %s",
            row["marzban_username"],
            exc,
        )
        return row


async def notify_refund_admins(bot: Bot, refund_row: sqlite3.Row) -> None:
    if not ADMIN_IDS:
        logging.warning("Refund request created but ADMIN_IDS is empty.")
        return

    plan = PLANS.get(refund_row["plan_code"])
    plan_title = plan.title if plan else refund_row["plan_code"]
    text = (
        "Новый запрос на возврат.\n\n"
        f"Request ID: {refund_row['id']}\n"
        f"User ID: {refund_row['telegram_user_id']}\n"
        f"Тариф: {plan_title}\n"
        f"Сумма: {refund_row['amount_xtr']} Stars\n"
        f"Charge ID: <code>{html.escape(refund_row['telegram_payment_charge_id'], quote=False)}</code>\n"
        f"Причина: {html.escape(refund_row['reason'], quote=False)}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                text,
                parse_mode="HTML",
                reply_markup=refund_admin_keyboard(refund_row["id"]),
            )
        except Exception as exc:
            logging.warning("Failed to notify admin %s about refund request: %s", admin_id, exc)


async def submit_refund_request(message: Message, bot: Bot) -> None:
    latest_payment = get_latest_payment(message.from_user.id)
    if not latest_payment:
        await message.answer(
            "У вас пока нет платежей, по которым можно оформить возврат.",
            reply_markup=reply_menu_keyboard(),
        )
        return

    existing_request = get_refund_request_by_charge(latest_payment["telegram_payment_charge_id"])
    if existing_request:
        if existing_request["status"] in {"pending", "approved", "refunded"}:
            await message.answer(
                "По последнему платежу уже есть активный запрос на возврат. Если нужно уточнить детали, напишите в поддержку.",
                reply_markup=reply_menu_keyboard(),
            )
            return
        refund_row = update_refund_request(
            existing_request["id"],
            "pending",
            "Reopened by user",
            refunded_at=0,
        )
        await notify_refund_admins(bot, refund_row)
        await message.answer(
            refund_request_created_text(),
            reply_markup=reply_menu_keyboard(),
        )
        return

    plan = PLANS.get(latest_payment["plan_code"])
    reason = (
        f"Запрос из бота по тарифу {plan.title}" if plan else "Запрос из бота без дополнительного комментария"
    )
    refund_row = create_refund_request(
        telegram_user_id=message.from_user.id,
        charge_id=latest_payment["telegram_payment_charge_id"],
        plan_code=latest_payment["plan_code"],
        amount_xtr=latest_payment["amount_xtr"],
        reason=reason,
    )
    await notify_refund_admins(bot, refund_row)
    await message.answer(
        refund_request_created_text(),
        reply_markup=reply_menu_keyboard(),
    )

def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Тарифы", callback_data="open_plans")],
            [InlineKeyboardButton(text="Моя подписка", callback_data="my_vpn")],
            [InlineKeyboardButton(text="Главное меню", callback_data="back_to_start")],
            [InlineKeyboardButton(text="Поддержка", url=SUPPORT_URL)],
        ]
    )


def plans_menu_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=plan_label(plan), callback_data=f"buy:{plan.code}")]
        for plan in PLANS.values()
    ]
    rows.append([InlineKeyboardButton(text="Моя подписка", callback_data="my_vpn")])
    rows.append([InlineKeyboardButton(text="Главное меню", callback_data="back_to_start")])
    rows.append([InlineKeyboardButton(text="Поддержка", url=SUPPORT_URL)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def support_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Запросить возврат", callback_data="request_refund")],
            [InlineKeyboardButton(text="Написать в поддержку", url=SUPPORT_URL)],
        ]
    )


def refund_admin_keyboard(refund_request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Одобрить возврат",
                    callback_data=f"refund:approve:{refund_request_id}",
                ),
                InlineKeyboardButton(
                    text="Отклонить",
                    callback_data=f"refund:reject:{refund_request_id}",
                ),
            ]
        ]
    )


def plan_label(plan: Plan) -> str:
    badge = " ⭐ Рекомендуем" if plan.recommended else ""
    return f"{plan.title} — {plan.stars} Stars{badge}"


def start_message_text() -> str:
    return (
        "Привет! Это бот Win2Europe VPN.\n\n"
        "Здесь можно:\n"
        "- посмотреть тарифы\n"
        "- оплатить подписку в Stars\n"
        "- получить ссылку для подключения\n"
        "- быстро открыть поддержку\n\n"
        "Пользуйтесь кнопками внизу экрана."
    )


def formatted_user_status_text(row: Optional[sqlite3.Row]) -> str:
    if not row:
        return (
            "У вас пока нет активной подписки.\n\n"
            "Нажмите «Тарифы», выберите подходящий вариант, и бот сразу выдаст ссылку для подключения."
        )

    status = "активна" if row["is_active"] else "неактивна"
    return (
        f"Статус: {status}\n"
        f"Логин: <code>{html.escape(row['marzban_username'], quote=False)}</code>\n"
        f"Активна до: {fmt_ts(row['paid_until'])}\n"
        f"Ссылка для подключения:\n{render_connection_url(row['subscription_url'])}"
    )


def formatted_payment_success_text(plan: Plan, row: sqlite3.Row) -> str:
    return (
        "Оплата прошла успешно.\n\n"
        f"Тариф: {plan.title}\n"
        f"Активна до: {fmt_ts(row['paid_until'])}\n"
        f"Ссылка для подключения:\n{render_connection_url(row['subscription_url'])}\n\n"
        "Скопируйте ссылку и импортируйте ее в VPN-клиент как обычный VLESS-профиль."
    )


def refund_policy_text() -> str:
    return (
        "Возврат оформляется по запросу.\n\n"
        "Когда это уместно:\n"
        "- случайный или дублирующий платеж\n"
        "- ссылка не выдалась или доступ не заработал\n"
        "- покупка больше не нужна сразу после оплаты\n\n"
        "Что происходит дальше:\n"
        "- бот создаст запрос на возврат последнего платежа\n"
        "- мы проверим запрос вручную\n"
        "- после одобрения Stars вернутся через Telegram, а доступ будет отключен\n\n"
        "Если нужен возврат, нажмите кнопку ниже."
    )


def refund_request_created_text() -> str:
    return (
        "Запрос на возврат создан.\n\n"
        "Мы проверим последний платеж и вернемся с решением в этом чате. "
        "Если нужно добавить детали, напишите в поддержку."
    )


def refund_completed_text() -> str:
    return (
        "Возврат оформлен успешно.\n\n"
        "Telegram вернет Stars на баланс пользователя, а доступ к VPN по этому платежу отключен."
    )


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(start_message_text(), reply_markup=reply_menu_keyboard())


@router.message(Command("plans"))
@router.message(Command("buy"))
@router.message(Command("renew"))
async def cmd_plans(message: Message) -> None:
    lines = ["Тарифы Win2Europe VPN:\n"]
    for plan in PLANS.values():
        recommended = " — рекомендуем" if plan.recommended else ""
        lines.append(
            f"- {plan.title}: {plan.stars} Stars{recommended}\n"
            f"  {plan.description}"
        )
    lines.append("\nВыберите тариф кнопками под этим сообщением.")
    await message.answer("\n".join(lines), reply_markup=plans_menu_keyboard())


@router.message(Command("myvpn"))
@router.message(Command("status"))
async def cmd_myvpn(message: Message) -> None:
    row = get_user(message.from_user.id)
    row = await refresh_user_connection(row)
    await message.answer(
        formatted_user_status_text(row),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=reply_menu_keyboard(),
    )


@router.message(Command("support"))
@router.message(Command("paysupport"))
async def cmd_support(message: Message) -> None:
    await message.answer(
        "Поддержка Win2Europe VPN:\n"
        f"{SUPPORT_URL}\n\n"
        "Если оплата прошла, а ссылка не выдалась, напишите туда и пришлите свой Telegram ID.\n\n"
        + refund_policy_text(),
        reply_markup=support_menu_keyboard(),
    )


@router.message(F.text == MENU_TARIFFS)
async def menu_plans(message: Message) -> None:
    await cmd_plans(message)


@router.message(F.text == MENU_MY_VPN)
async def menu_myvpn(message: Message) -> None:
    await cmd_myvpn(message)


@router.message(F.text == MENU_SUPPORT)
async def menu_support(message: Message) -> None:
    await cmd_support(message)


@router.message(Command("refund"))
async def cmd_refund(message: Message, bot: Bot) -> None:
    await submit_refund_request(message, bot)


@router.callback_query(F.data == "open_plans")
async def cb_open_plans(callback: CallbackQuery) -> None:
    lines = ["Тарифы Win2Europe VPN:\n"]
    for plan in PLANS.values():
        lines.append(f"- {plan.title}: {plan.stars} ⭐, {plan.days} дней")
    lines.append("\nВыберите тариф кнопками под этим сообщением.")
    await replace_callback_message(callback, "\n".join(lines), reply_markup=plans_menu_keyboard())


@router.callback_query(F.data == "my_vpn")
async def cb_my_vpn(callback: CallbackQuery) -> None:
    row = get_user(callback.from_user.id)
    row = await refresh_user_connection(row)
    await replace_callback_message(
        callback,
        formatted_user_status_text(row),
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "back_to_start")
async def cb_back_to_start(callback: CallbackQuery) -> None:
    await replace_callback_message(callback, start_message_text(), reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "request_refund")
async def cb_request_refund(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    await submit_refund_request(callback.message, bot)


@router.callback_query(F.data.startswith("refund:approve:"))
async def cb_refund_approve(callback: CallbackQuery, bot: Bot) -> None:
    if not is_admin_user(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    refund_request_id = int(callback.data.rsplit(":", 1)[1])
    refund_row = get_refund_request(refund_request_id)
    if not refund_row:
        await callback.answer("Запрос не найден.", show_alert=True)
        return
    if refund_row["status"] != "pending":
        await callback.answer("Этот запрос уже обработан.", show_alert=True)
        return

    try:
        await bot(
            RefundStarPayment(
                user_id=refund_row["telegram_user_id"],
                telegram_payment_charge_id=refund_row["telegram_payment_charge_id"],
            )
        )
    except Exception as exc:
        await callback.answer("Не удалось оформить возврат через Telegram.", show_alert=True)
        logging.exception("Refund failed for request %s: %s", refund_request_id, exc)
        return

    update_refund_request(refund_request_id, "refunded", "Approved in bot", refunded_at=now_ts())

    user_row = get_user(refund_row["telegram_user_id"])
    if user_row:
        await marzban_client.deactivate_user(user_row["marzban_username"])
        revoke_local_access(refund_row["telegram_user_id"])

    await bot.send_message(refund_row["telegram_user_id"], refund_completed_text())
    await safe_edit_message(
        callback,
        "Возврат выполнен. Stars будут возвращены пользователю через Telegram, доступ отключен.",
    )


@router.callback_query(F.data.startswith("refund:reject:"))
async def cb_refund_reject(callback: CallbackQuery, bot: Bot) -> None:
    if not is_admin_user(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    refund_request_id = int(callback.data.rsplit(":", 1)[1])
    refund_row = get_refund_request(refund_request_id)
    if not refund_row:
        await callback.answer("Запрос не найден.", show_alert=True)
        return
    if refund_row["status"] != "pending":
        await callback.answer("Этот запрос уже обработан.", show_alert=True)
        return

    update_refund_request(refund_request_id, "rejected", "Rejected in bot")
    await bot.send_message(
        refund_row["telegram_user_id"],
        "Запрос на возврат рассмотрен. Сейчас он отклонен. Если хотите уточнить детали, напишите в поддержку.",
    )
    await safe_edit_message(callback, "Запрос на возврат отклонен.")


@router.callback_query(F.data.startswith("buy:"))
async def cb_buy(callback: CallbackQuery, bot: Bot) -> None:
    plan_code = callback.data.split(":", 1)[1]
    plan = PLANS.get(plan_code)
    if not plan:
        await callback.answer("Тариф не найден", show_alert=True)
        return

    payload = build_payload(plan.code, callback.from_user.id)
    create_order(payload, callback.from_user.id, plan)

    await bot.send_invoice(
        chat_id=callback.message.chat.id,
        title=plan.title,
        description=plan.description,
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=plan.title, amount=plan.stars)],
        start_parameter=f"buy-{plan.code}",
    )
    await callback.answer()


@router.pre_checkout_query()
async def on_pre_checkout(pre_checkout_query: PreCheckoutQuery) -> None:
    payload = pre_checkout_query.invoice_payload
    order = get_order(payload)
    if not order:
        await pre_checkout_query.answer(
            ok=False,
            error_message="Заказ не найден. Попробуй выбрать тариф заново.",
        )
        return

    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message) -> None:
    payment = message.successful_payment
    charge_id = payment.telegram_payment_charge_id

    if payment_exists(charge_id):
        await message.answer("Оплата уже была обработана. Если нужна ссылка, введи /myvpn.")
        return

    payload = payment.invoice_payload
    order = get_order(payload)
    if not order:
        await message.answer(
            "Оплата пришла, но заказ не найден. Напиши в поддержку и укажи свой Telegram ID."
        )
        return

    try:
        plan_code, user_id_from_payload = parse_payload(payload)
    except ValueError:
        await message.answer(
            "Не удалось разобрать заказ. Напиши в поддержку и укажи свой Telegram ID."
        )
        return

    if user_id_from_payload != message.from_user.id:
        await message.answer(
            "Этот заказ принадлежит другому пользователю. Напиши в поддержку."
        )
        return

    plan = PLANS.get(plan_code)
    if not plan:
        await message.answer("Тариф не найден. Напиши в поддержку.")
        return

    current = get_user(message.from_user.id)
    base_ts = max(now_ts(), current["paid_until"] if current else 0)
    new_paid_until = base_ts + plan.days * 24 * 60 * 60

    telegram_username = message.from_user.username or f"user_{message.from_user.id}"
    marzban_username, subscription_url = await marzban_client.create_or_extend_user(
        telegram_user_id=message.from_user.id,
        telegram_username=telegram_username,
        expire_ts=new_paid_until,
    )

    row = upsert_user(
        telegram_user_id=message.from_user.id,
        telegram_username=telegram_username,
        marzban_username=marzban_username,
        subscription_url=subscription_url,
        paid_until=new_paid_until,
    )
    row = await refresh_user_connection(row)
    save_payment(charge_id, message.from_user.id, payload, plan)
    mark_order_paid(payload)
    await message.answer(
        formatted_payment_success_text(plan, row),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=reply_menu_keyboard(),
    )


async def expiration_watcher(bot: Bot) -> None:
    while True:
        try:
            expired_rows = get_expired_active_users()
            for row in expired_rows:
                await marzban_client.deactivate_user(row["marzban_username"])
                mark_user_inactive(row["telegram_user_id"])
                try:
                    await bot.send_message(
                        row["telegram_user_id"],
                        "Подписка истекла и профиль отключен.\n"
                        "Чтобы продлить доступ, используй /renew.",
                    )
                except Exception as send_error:
                    logging.warning("Не удалось отправить уведомление пользователю: %s", send_error)
        except Exception as watcher_error:
            logging.exception("Ошибка в expiration_watcher: %s", watcher_error)

        await asyncio.sleep(CHECK_EXPIRED_EVERY_SECONDS)


async def on_startup(bot: Bot) -> None:
    init_db()
    asyncio.create_task(expiration_watcher(bot))
    logging.info("Бот запущен. Режим mock Marzban: %s", USE_MOCK_MARZBAN)


async def main() -> None:
    require_token()
    if not USE_MOCK_MARZBAN:
        require_real_marzban_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    dp.startup.register(on_startup)

    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен.")
