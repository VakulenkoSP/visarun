from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, and_
from ..database import async_session_maker
from ..models import Trip, Booking
from ..keyboards import main_menu, back_button, trips_list_raw, my_booking_detail_kb, admin_notification_actions
from ..config import ADMIN_IDS
from ..utils import (
    get_or_create_user, format_date_ru, format_price, format_price_converted,
    format_price_verbose, get_occupied_seats, get_trip_total_seats,
    now_hanoi, STATUS_EMOJI, tg_account_name,
)
from .booking import payment_method_label

router = Router()

WELCOME_TEXT = (
    "🇻🇳 Я Border Run Vietnam бот.\n"
    "Помогу Вам организовать поездку на границу, где Вы сможете "
    "обновить своё законное пребывание во Вьетнаме ещё на:\n"
    "• 90 дней — с визой\n"
    "• 45 дней — без визы\n\n"
    "🔸 Что я умею:\n"
    "- Записаться на визаран\n"
    "- Показать цены и маршруты\n"
    "- Показать мои брони\n"
    "- Объяснить, как всё работает\n"
    "- Связаться с менеджером\n"
    "- Напомнить о предстоящей поездке\n\n"
    "🔸 Доступные маршруты:\n"
    "- Нячанг • Лаос • Нячанг\n\n"
    "💰 Цены от 1 000 000 VND\n\n"
    "Выберите, что Вас интересует 👇"
)


class NameStates(StatesGroup):
    waiting_name = State()


async def _info_text() -> str:
    async with async_session_maker() as session:
        today = now_hanoi().date()
        trips = await session.execute(
            select(Trip).where(
                and_(Trip.is_active == True, Trip.date >= today)
            ).order_by(Trip.date).limit(2)
        )
        trips = trips.scalars().all()

        lines = ["ℹ️ Информация о визаране\n"]
        if trips:
            for i, t in enumerate(trips, 1):
                occ = await get_occupied_seats(session, t.id)
                total = get_trip_total_seats(t)
                bus_icon = "💎VIP" if t.bus_type == "vip" else "🛌Sleeper"
                lines.append(f"🚌 {'Ближайший' if i == 1 else 'Следующий'} рейс: {format_date_ru(t.date)} ({bus_icon})")
                lines.append(f"📍 Сбор: {t.pickup_location}")
                lines.append(f"💰 Взрослый: {format_price(t.price_adult)}")
                lines.append(f"👶 Детский: {format_price(t.price_child)}")
                lines.append(f"🪑 Свободно: {total - occ}/{total}\n")
            dep_line = f"⏰ Отправление: {format_date_ru(trips[0].date)}"
            if trips[0].departure_time:
                dep_line += f" в {trips[0].departure_time}"
            lines.append(dep_line)
        else:
            lines.append("❌ Ближайших рейсов нет\n")

    lines.append("📞 Контакты: @vakden")
    return "\n".join(lines)


async def _reply(target, text, reply_markup=None):
    if isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(text, reply_markup=reply_markup)
        except Exception:
            await target.message.answer(text, reply_markup=reply_markup)
    else:
        await target.answer(text, reply_markup=reply_markup)


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    async with async_session_maker() as session:
        user = await get_or_create_user(session, message.from_user.id, message.from_user.username)
        if not user.full_name:
            await state.set_state(NameStates.waiting_name)
            await message.answer(
                "🇻🇳 Добро пожаловать в бот для записи на визаран из Нячанга в Лаос\n\n"
                "Пожалуйста, напишите ваше Имя и Фамилию"
            )
            return
    await _reply(message, WELCOME_TEXT, main_menu())


@router.message(NameStates.waiting_name)
async def process_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if len(name) < 2 or " " not in name.strip():
        await message.answer("✍️ Пожалуйста, напишите Имя и Фамилию через пробел (например: Иван Иванов):")
        return
    async with async_session_maker() as session:
        user = await get_or_create_user(session, message.from_user.id, message.from_user.username)
        user.full_name = name
        await session.commit()
    await state.clear()
    await _reply(message, WELCOME_TEXT, main_menu())


@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await _reply(callback, "📋 Выберите действие:", main_menu())


@router.callback_query(F.data == "my_bookings")
async def show_my_bookings(callback: CallbackQuery):
    await callback.answer()
    await _show_my_bookings(callback, callback.from_user.id, callback.from_user.username)


async def _ensure_name(target, user_id, username, state: FSMContext) -> bool:
    async with async_session_maker() as session:
        user = await get_or_create_user(session, user_id, username)
        if user.full_name:
            return True
    await state.set_state(NameStates.waiting_name)
    await _reply(target, "✍️ Пожалуйста, напишите ваше Имя и Фамилию:")
    return False


async def _show_my_bookings(target, user_id, username):
    async with async_session_maker() as session:
        user = await get_or_create_user(session, user_id, username)
        result = await session.execute(
            select(Booking).where(Booking.user_id == user.id).order_by(Booking.created_at.desc())
        )
        bookings = result.scalars().all()

        booking_list = []
        for b in bookings:
            trip = b.trip
            booking_list.append({
                "id": b.id,
                "trip_date": trip.date,
                "status": b.status,
                "status_text": STATUS_EMOJI.get(b.status, b.status),
            })

    if not booking_list:
        await _reply(target, "📭 У вас пока нет бронирований", back_button("back_to_main"))
        return

    from ..keyboards import my_bookings_list
    await _reply(target, "📋 Ваши бронирования:", my_bookings_list(booking_list))


@router.callback_query(F.data.startswith("my_booking_"))
async def my_booking_detail(callback: CallbackQuery):
    await callback.answer()
    parts = callback.data.split("_")
    if len(parts) == 3 and parts[0] == "my" and parts[1] == "booking":
        booking_id = int(parts[2])
    else:
        return

    async with async_session_maker() as session:
        result = await session.execute(select(Booking).where(Booking.id == booking_id))
        booking = result.scalar_one_or_none()

        if not booking:
            await _reply(callback, "❌ Бронь не найдена", back_button("my_bookings"))
            return

        if booking.user.telegram_id != callback.from_user.id:
            await _reply(callback, "⚠️ Это не ваша бронь", back_button("my_bookings"))
            return

        trip = booking.trip
        status_text = STATUS_EMOJI.get(booking.status, booking.status)

        seats_line = f"🪑 Места: {booking.selected_seats}\n" if booking.selected_seats else ""

        text = (
            f"📋 Бронь #{booking.id}\n\n"
            f"📅 Дата: {format_date_ru(trip.date)}\n"
            f"👤 Взрослых: {booking.adults}\n"
            f"👶 Детей: {booking.children}\n"
            f"{seats_line}"
            f"💰 Сумма: {format_price_converted(booking.total_price, booking.payment_method)}\n"
            f"📌 Статус: {status_text}"
        )
        if booking.pending_add_amount:
            text += f"\n⏳ Долг: {format_price_converted(booking.pending_add_amount, booking.payment_method)}"
            if booking.pending_add_people:
                text += f"\n👥 Добавлено без оплаты: {booking.pending_add_people} чел"
        if booking.payments:
            hist_lines = []
            for p in booking.payments:
                mark = "✅" if p.status == "paid" else "⏳"
                line = f"  {mark} {payment_method_label(p.method)} {format_price_converted(p.amount, p.method)}"
                if (p.comment or "").strip():
                    line += f" ({p.comment.strip()})"
                hist_lines.append(line)
            text += "\n💳 Оплаты:\n" + "\n".join(hist_lines)
        if booking.status == "paid":
            if trip.departure_time:
                text += f"\n⏰ Отправление: {trip.departure_time}"
            text += f"\n📍 Место сбора: {trip.pickup_location}\n"
            if trip.bus_number:
                text += f"🚌 Автобус: {trip.bus_number}"

        is_pending = booking.status == "pending" or bool(booking.pending_add_amount)
        await _reply(
            callback, text,
            my_booking_detail_kb(booking.id, show_pay=is_pending, show_cancel=is_pending),
        )


@router.callback_query(F.data.startswith("my_paid_"))
async def my_paid_notify(callback: CallbackQuery):
    await callback.answer()
    booking_id = int(callback.data.split("_")[-1])

    async with async_session_maker() as session:
        result = await session.execute(select(Booking).where(Booking.id == booking_id))
        booking = result.scalar_one_or_none()

        if not booking:
            await _reply(callback, "❌ Бронь не найдена", back_button("my_bookings"))
            return

        if booking.user.telegram_id != callback.from_user.id:
            await _reply(callback, "⚠️ Это не ваша бронь", back_button("my_bookings"))
            return

        if booking.status != "pending" and not booking.pending_add_amount:
            await _reply(callback, "⚠️ Эта бронь уже оплачена или отменена", back_button("my_bookings"))
            return

        trip = booking.trip

    user_full_name = booking.user.full_name or "не указано"
    tg_user = callback.from_user
    is_addition = bool(booking.pending_add_amount)

    await _reply(callback, "✅ Уведомление отправлено администратору\nПосле проверки оплаты статус будет обновлён", back_button("my_bookings"))

    pending_payments = [p for p in booking.payments if p.status != "paid"]
    latest_payment = pending_payments[-1] if pending_payments else None
    comment = ((latest_payment.comment if latest_payment else None) or booking.payment_comment or "").strip()
    comment_display = comment if comment else (tg_account_name(tg_user) or user_full_name)

    for admin_id in ADMIN_IDS:
        try:
            label = "о доплате" if is_addition else "об оплате"
            debt_line = ""
            if is_addition:
                debt_line = f"⚠️ Долг: {format_price_verbose(booking.pending_add_amount, booking.payment_method)}\n"
                if booking.pending_add_people:
                    debt_line += f"👥 Добавлено без оплаты: {booking.pending_add_people} чел\n"
            await callback.bot.send_message(
                admin_id,
                f"🔔 Пользователь сообщает {label}! Подтвердите\n"
                f"{'═' * 30}\n"
                f"👤 {user_full_name} (@{tg_user.username or '—'})\n"
                f"📅 {format_date_ru(trip.date)}\n"
                f"🧑 {booking.adults} взр + {booking.children} дет\n"
                f"💰 {format_price_verbose(booking.total_price, booking.payment_method)}\n"
                f"{debt_line}"
                f"🆔 #{booking_id}\n"
                f"💬 Комментарий: {comment_display}",
                reply_markup=admin_notification_actions(booking_id),
            )
        except Exception:
            pass


@router.callback_query(F.data.startswith("my_booking_cancel_"))
async def my_booking_cancel(callback: CallbackQuery):
    await callback.answer()
    booking_id = int(callback.data.split("_")[-1])

    async with async_session_maker() as session:
        result = await session.execute(select(Booking).where(Booking.id == booking_id))
        booking = result.scalar_one_or_none()

        if not booking:
            await _reply(callback, "❌ Бронь не найдена", back_button("my_bookings"))
            return

        if booking.user.telegram_id != callback.from_user.id:
            await _reply(callback, "⚠️ Это не ваша бронь", back_button("my_bookings"))
            return

        if booking.status != "pending":
            await _reply(callback, "⚠️ Нельзя отменить оплаченную или уже отменённую бронь", back_button("my_bookings"))
            return

        booking.status = "cancelled"
        await session.commit()

        trip = booking.trip
        booking_id_val = booking.id
        adults = booking.adults
        children = booking.children
        total_price = booking.total_price
        user_full_name = booking.user.full_name or "не указано"
        payment_method = booking.payment_method

    await _reply(callback, f"✅ Бронь #{booking_id} на {format_date_ru(trip.date)} отменена", back_button("my_bookings"))

    tg_user = callback.from_user
    for admin_id in ADMIN_IDS:
        try:
            await callback.bot.send_message(
                admin_id,
                f"❌ Клиент отменил бронь #{booking_id_val}\n\n"
                f"👤 ФИО: {user_full_name}\n"
                f"📱 Пользователь: @{tg_user.username or 'нет юзернейма'} (ID: {tg_user.id})\n"
                f"📅 Рейс: {format_date_ru(trip.date)}\n"
                f"👤 Взрослых: {adults}\n"
                f"👶 Детей: {children}\n"
                f"💰 Сумма: {format_price_verbose(total_price, payment_method)}",
            )
        except Exception:
            pass


@router.callback_query(F.data == "info")
async def show_info(callback: CallbackQuery):
    await callback.answer()
    await _reply(callback, await _info_text(), back_button("back_to_main"))


@router.callback_query(F.data == "book_start")
async def show_trips_for_booking(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()

    if not await _ensure_name(callback, callback.from_user.id, callback.from_user.username, state):
        return

    async with async_session_maker() as session:
        today = now_hanoi().date()

        trips = await session.execute(
            select(Trip).where(
                and_(Trip.is_active == True, Trip.date >= today)
            ).order_by(Trip.date)
        )
        trips = trips.scalars().all()

        trip_list = []
        for trip in trips:
            occ = await get_occupied_seats(session, trip.id)
            total = get_trip_total_seats(trip)
            trip_list.append({
                "id": trip.id,
                "date": trip.date,
                "max_seats": total,
                "free": total - occ,
                "bus_type": trip.bus_type,
            })

    if not trip_list:
        await _reply(callback, f"На данный момент нет доступных рейсов", back_button("back_to_main"))
        return

    text_lines = []
    for t in trip_list:
        bus_icon = "💎VIP" if t["bus_type"] == "vip" else "🛌Sleeper"
        text_lines.append(f"{format_date_ru(t['date'])} {bus_icon} - {t['free']}/{t['max_seats']} мест")
    text = "\n".join(text_lines)

    await _reply(callback, f"📅 Выберите дату рейса:\n\n{text}", trips_list_raw(trip_list))


TEXT_TO_CALLBACK = {
    "записаться": "book_start",
    "записаться на визаран": "book_start",
    "хочу записаться": "book_start",
    "бронь": "book_start",
    "мои брони": "my_bookings",
    "моя бронь": "my_bookings",
    "брони": "my_bookings",
    "информация": "info",
    "инфо": "info",
}


@router.message(StateFilter(None), F.text, ~F.text.startswith("/"))
async def handle_any_message(message: Message, state: FSMContext):
    await state.clear()
    async with async_session_maker() as session:
        await get_or_create_user(session, message.from_user.id, message.from_user.username)

    text = message.text.strip().lower()

    if text in TEXT_TO_CALLBACK:
        cb = TEXT_TO_CALLBACK[text]
        if cb == "book_start":
            if not await _ensure_name(message, message.from_user.id, message.from_user.username, state):
                return
            await _show_book_start(message)
            return
        elif cb == "my_bookings":
            await _show_my_bookings(message, message.from_user.id, message.from_user.username)
            return
        elif cb == "info":
            await _reply(message, await _info_text(), back_button("back_to_main"))
            return

    await _reply(message, "Выберите действие:", main_menu())


@router.message(StateFilter(None), ~F.text)
async def handle_non_text(message: Message):
    await message.answer("Вау, классно, ты лучший(ая)!!!", reply_markup=main_menu())


async def _show_book_start(target):
    async with async_session_maker() as session:
        today = now_hanoi().date()
        trips = await session.execute(
            select(Trip).where(
                and_(Trip.is_active == True, Trip.date >= today)
            ).order_by(Trip.date)
        )
        trips = trips.scalars().all()

        trip_list = []
        for trip in trips:
            occ = await get_occupied_seats(session, trip.id)
            total = get_trip_total_seats(trip)
            trip_list.append({
                "id": trip.id,
                "date": trip.date,
                "max_seats": total,
                "free": total - occ,
                "bus_type": trip.bus_type,
            })

    if not trip_list:
        await _reply(target, "На данный момент нет доступных рейсов", back_button("back_to_main"))
        return

    text_lines = []
    for t in trip_list:
        bus_icon = "💎VIP" if t["bus_type"] == "vip" else "🛌Sleeper"
        text_lines.append(f"{format_date_ru(t['date'])} {bus_icon} - {t['free']}/{t['max_seats']} мест")
    text = "\n".join(text_lines)

    await _reply(target, f"📅 Выберите дату рейса:\n\n{text}", trips_list_raw(trip_list))
