import asyncio
import logging

from rich.logging import RichHandler
from rich.console import Console

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import load_config, Config
from handlers import start
from handlers.admin_handlers import create_work
from handlers.all_handlers import profile, edit, monetization, settings

# ⬇️ добавь импорт задач автопродления/уведомлений
from database.crud import autorenew_subscriptions, notify_expiring_subscriptions
from database.db import init_db, ping

# -----------------------------
# Логи с Rich
# -----------------------------
console = Console(force_terminal=True)
handler = RichHandler(
    console=console,
    rich_tracebacks=True,
    show_time=True,
    show_level=True,
    show_path=True
)
handler.level_styles = {
    "DEBUG": "dim cyan",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "bold red",
    "CRITICAL": "bold red on white"
}
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[handler]
)
logger = logging.getLogger("BOTV")


async def main():
    logger.info("🚀 Запуск BOTV")

    # Конфиг и бот
    config: Config = load_config()
    bot = Bot(
        token=config.tg_bot.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        timeout=120
    )
    dp = Dispatcher()

    # Роутеры
    dp.include_router(start.router)
    dp.include_router(edit.router)
    dp.include_router(profile.router)
    # dp.include_router(portfolio.router)
    dp.include_router(create_work.router)
    dp.include_router(monetization.router)
    dp.include_router(settings.router)

    # БД: быстрая проверка соединения
    try:
        await ping()
        logger.info("✅ DB ping OK")

        await init_db()
        logger.info("✅ Таблицы проверены/созданы")
    except Exception as e:
        logger.exception("❌ DB ping failed: %s", e)
        # корректно завершаем процесс с кодом 1
        import sys
        sys.exit(1)

    # # Webhook → off (важно для polling)
    # await bot.delete_webhook(drop_pending_updates=True)
    # logger.info("✅ Webhook удалён, запускаем polling...")

    # ---- Планировщик (UTC; поменяй timezone на 'Europe/Moscow', если нужно строго по Мск) ----
    # scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

    # # Автопродление: каждый день в 00:05 (UTC)
    # if config.tariff.autorenew_enabled:
    #     scheduler.add_job(
    #         autorenew_subscriptions,
    #         CronTrigger(hour=0, minute=5),
    #         args=[config.tariff.sub_price_kop, config.tariff.sub_duration_days, bot],
    #         id="sub_autorenew",
    #         replace_existing=True,
    #         max_instances=1,
    #         coalesce=True,
    #     )
    #     logger.info("🛠 Авторенев активирован: цена=%s коп., срок=%s дн.",
    #                 config.tariff.sub_price_kop, config.tariff.sub_duration_days)

    # # Уведомления: каждый день в 09:00 (UTC) — за N дней до конца
    # scheduler.add_job(
    #     notify_expiring_subscriptions,
    #     CronTrigger(hour=9, minute=0),
    #     args=[config.tariff.notify_days_before, bot],
    #     id="sub_notify",
    #     replace_existing=True,
    #     max_instances=1,
    #     coalesce=True,
    # )
    # logger.info("🔔 Уведомления активированы: за %s дн. до конца.",
    #             config.tariff.notify_days_before)
    #
    # scheduler.start()

    # Polling
    allowed_updates = dp.resolve_used_update_types()
    try:
        await dp.start_polling(bot, allowed_updates=allowed_updates)
    finally:
        # scheduler.shutdown(wait=False)
        await bot.session.close()
        logger.info("👋 Завершено")


if __name__ == "__main__":
    asyncio.run(main())
