import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from .config import BOT_TOKEN
from .database import init_db
from .handlers import user, booking, admin
from .utils import (
    deactivate_past_trips, cancel_expired_pending, get_pending_bookings_older_than,
    get_upcoming_trip_bookings, now_hanoi,
    format_date_ru, format_price, format_price_converted,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

_last_reminder_date = None


async def send_payment_reminders(bot: Bot):
    bookings = await get_pending_bookings_older_than(hours=2)
    for b in bookings:
        trip_date = format_date_ru(b.trip.date)
        try:
            await bot.send_message(
                b.user.telegram_id,
                f"📝 Напоминание: у вас есть неоплаченная бронь!\n\n"
                f"Бронь #{b.id}\n"
                f"Рейс: {trip_date}\n"
                f"Взрослых: {b.adults}\n"
                f"Детей: {b.children}\n"
                f"Сумма: {format_price(b.total_price)}\n\n"
                f"Пожалуйста, оплатите и нажмите «Я оплатил» в деталях брони",
            )
            logger.info(f"Sent reminder to user {b.user.telegram_id} for booking #{b.id}")
        except Exception as e:
            logger.warning(f"Failed to send reminder to user {b.user.telegram_id}: {e}")
        await asyncio.sleep(0.3)


async def send_trip_reminders(bot: Bot):
    global _last_reminder_date
    now = now_hanoi()
    if now.hour < 12:
        return
    today = now.date()
    if _last_reminder_date == today:
        return
    bookings = await get_upcoming_trip_bookings()
    for b in bookings:
        trip_date = format_date_ru(b.trip.date)
        price_str = format_price_converted(b.total_price, b.payment_method)
        dep_time = b.trip.departure_time
        dep_line = f"⏰ Отправление: {dep_time}\n" if dep_time else ""
        dep_line2 = f"🚌 Выезд в {dep_time} от офиса VisaRun (52 Hùng Vương)\n" if dep_time else ""
        try:
            await bot.send_message(
                b.user.telegram_id,
                f"🎉 Напоминание о поездке!\n\n"
                f"Бронь #{b.id}\n"
                f"Дата рейса: {trip_date}\n"
                f"{dep_line}"
                f"Взрослых: {b.adults}\n"
                f"Детей: {b.children}\n"
                f"Сумма: {price_str}\n\n"
                f"{dep_line2}"
                f"🛂 Не забудьте паспорт!",
            )
            logger.info(f"Sent trip reminder to user {b.user.telegram_id} for booking #{b.id}")
        except Exception as e:
            logger.warning(f"Failed to send trip reminder to user {b.user.telegram_id}: {e}")
        await asyncio.sleep(0.3)
    _last_reminder_date = today


async def background_loop(bot: Bot):
    while True:
        try:
            await deactivate_past_trips()

            expired = await cancel_expired_pending()
            if expired:
                logger.info(f"Auto-cancelled {len(expired)} expired pending bookings")

            await send_payment_reminders(bot)
            await send_trip_reminders(bot)
        except Exception as e:
            logger.error(f"Background task error: {e}")
        await asyncio.sleep(60)


async def main():
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized.")

    storage = MemoryStorage()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=storage)

    dp.include_router(admin.router)
    dp.include_router(booking.router)
    dp.include_router(user.router)

    asyncio.create_task(background_loop(bot))

    logger.info("Bot started polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
