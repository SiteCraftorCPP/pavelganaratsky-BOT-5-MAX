import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from config import BOT_TOKEN, get_telegram_proxy_url
from database import init_db, seed_march_if_needed
from handlers import router as user_router
from admin_handlers import router as admin_router
from scheduler import check_and_send_messages

# Configure logging
logging.basicConfig(level=logging.INFO)


async def scheduler_loop(bot: Bot):
    while True:
        try:
            await check_and_send_messages(bot)
        except Exception as e:
            logging.error(f"Scheduler error: {e}")
        # Check every 60 seconds
        await asyncio.sleep(60)


async def main():
    # Initialize DB
    await init_db()
    # Автоматически заполнить мартовскую рассылку, если её ещё нет
    await seed_march_if_needed()

    # Initialize Bot and Dispatcher
    proxy_url = get_telegram_proxy_url()
    session = AiohttpSession(proxy=proxy_url) if proxy_url else None
    bot = Bot(token=BOT_TOKEN, session=session)
    dp = Dispatcher()

    # Include routers
    dp.include_router(user_router)
    dp.include_router(admin_router)

    # Start scheduler in background
    asyncio.create_task(scheduler_loop(bot))

    print("Bot started!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped!")
