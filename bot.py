# Бот сообщества ВК «Smart Service»: отвечает клиентам через ИИ
# Документация по vkbottle: ../../docs/vkbottle-README.md
import asyncio
import logging
import os
import ssl

import certifi
from aiohttp import TCPConnector
from dotenv import load_dotenv
from vkbottle import API, VKAPIError
from vkbottle.bot import Bot, Message
from vkbottle.http import AiohttpClient

from ai import ask_ai

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("smart-service-bot")

load_dotenv()  # .env рядом с ботом

# на Mac системных сертификатов в питоне нет — берём список из certifi
ssl_context = ssl.create_default_context(cafile=certifi.where())


def build_bot() -> Bot:
    # TCPConnector привязывается к циклу событий при создании, поэтому
    # сетевой клиент собираем внутри async-функции, а не на уровне модуля
    connector = TCPConnector(ssl=ssl_context)
    api = API(
        token=os.environ["VK_TOKEN"],
        http_client=AiohttpClient(connector=connector),
    )
    return Bot(api=api)


def register_handlers(bot: Bot) -> None:
    @bot.on.private_message()
    async def ai_chat(message: Message):
        # отвечаем только в личных сообщениях сообщества
        text = (message.text or "").strip()
        if not text:
            await message.answer("Задайте вопрос текстом — отвечу.")
            return
        answer = await ask_ai(message.peer_id, text)
        await message.answer(answer)

    # ошибка 902: человек запретил сообществу писать первым
    @bot.error_handler.register_error_handler(VKAPIError)
    async def vk_api_error(e: VKAPIError):
        logger.warning("Ошибка VK API: %s %s", e.code, e.error_msg)


async def main() -> None:
    bot = build_bot()
    register_handlers(bot)
    logger.info("Бот запущен")
    await bot.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
