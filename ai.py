# Работа с ИИ через ProxyAPI (OpenAI-совместимый API)
import asyncio
import json
import logging
import os
import ssl
from collections import deque
from pathlib import Path

import aiohttp
import certifi
from dotenv import load_dotenv

# на Mac системных сертификатов в питоне нет — берём список из certifi
_ssl_context = ssl.create_default_context(cafile=certifi.where())

logger = logging.getLogger("smart-service-bot.ai")

API_URL = "https://api.proxyapi.ru/v1/chat/completions"
DEFAULT_MODEL = "deepseek/deepseek-v4-flash"

# историю диалога с каждым клиентом держим в памяти (последние 8 реплик)
_histories: dict[int, deque] = {}

PROMPT_FILE = Path(__file__).parent / "prompt-ассистента.txt"


def _system_prompt() -> str:
    if PROMPT_FILE.exists():
        return PROMPT_FILE.read_text(encoding="utf-8")
    # запасной вариант, если файл с персоной удалили
    return "Ты — вежливый ассистент сообщества ВКонтакте. Отвечай по-русски, коротко и по делу."


def _load_key() -> str:
    load_dotenv()
    key = os.environ.get("PROXYAPI_KEY")
    if not key:
        raise RuntimeError("PROXYAPI_KEY не найден в .env")
    return key


async def ask_ai(peer_id: int, text: str) -> str:
    history = _histories.setdefault(peer_id, deque(maxlen=8))
    messages = (
        [{"role": "system", "content": _system_prompt()}]
        + list(history)
        + [{"role": "user", "content": text}]
    )
    payload = {"model": os.environ.get("AI_MODEL", DEFAULT_MODEL), "messages": messages}

    # две попытки на случай сбоя сети или лимита; бесконечных повторов нет
    last_error = None
    for attempt in (1, 2):
        try:
            reply = await _request(payload)
            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": reply})
            return reply
        except Exception as e:  # noqa: BLE001 — при любом сбое честный откат, не падение бота
            last_error = e
            logger.warning("Попытка %s не удалась: %s", attempt, e)
            await asyncio.sleep(2 * attempt)
    logger.error("ИИ не ответил: %s", last_error)
    return "Сейчас техническая неполадка, ответ не пришёл. Напишите ещё раз или позже."


async def _request(payload: dict) -> str:
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=_ssl_context)) as session:
        async with session.post(
            API_URL,
            headers={"Authorization": "Bearer " + _load_key()},
            json=payload,
            timeout=aiohttp.ClientTimeout(total=60),
        ) as r:
            raw = await r.text()
    data = json.loads(raw)
    if "error" in data:
        raise RuntimeError("ProxyAPI вернул ошибку: " + data["error"].get("message", ""))
    return data["choices"][0]["message"]["content"]
