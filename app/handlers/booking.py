from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, and_
from ..database import async_session_maker
from ..models import Trip, Booking, Payment
from ..keyboards import (
    main_menu, trip_detail, booking_confirm, back_button,
    admin_notification_actions, payment_methods_kb,
    booking_confirmed_main, booking_confirmed_transfer,
    existing_booking_actions, remove_confirm_kb, seat_selection_kb, comment_kb,
)
from ..config import (
    MAX_PEOPLE_PER_BOOKING, ADMIN_IDS,
    VND_TO_RUB, VND_TO_KZT,
    PAYMENT_TRANSFER_RUB_INFO, PAYMENT_TRANSFER_KZT_INFO,
)
from ..utils import (
    get_or_create_user, format_date_ru, format_price, format_price_converted,
    format_price_verbose, now_utc, get_occupied_seats, get_occupied_seat_ids,
    get_trip_total_seats, render_seat_map, tg_account_name,
)

router = Router()


class BookingStates(StatesGroup):
    waiting_adults = State()
    waiting_children = State()
    selecting_seats = State()
    waiting_comment = State()


class RemovePersonStates(StatesGroup):
    waiting_adults = State()
    waiting_children = State()


def calc_price_in_rub(vnd: int) -> str:
    return f"{vnd * VND_TO_RUB:,.0f}".replace(",", " ") + " RUB"


def calc_price_in_kzt(vnd: int) -> str:
    return f"{vnd * VND_TO_KZT:,.0f}".replace(",", " ") + " KZT"


def payment_method_detail(method: str, total_vnd: int, full_name: str = "") -> str:
    if method == "cash_vnd":
        return f"💰 Сумма: {format_price(total_vnd)}"
    elif method == "transfer_rub":
        rub = calc_price_in_rub(total_vnd)
        comment = f"\n💳 Комментарий к переводу: {full_name}" if full_name else ""
        return f"{PAYMENT_TRANSFER_RUB_INFO}\n💰 Сумма: {rub} (по курсу {VND_TO_RUB}){comment}"
    elif method == "transfer_kzt":
        kzt = calc_price_in_kzt(total_vnd)
        comment = f"\n💳 Комментарий к переводу: {full_name}" if full_name else ""
        return f"{PAYMENT_TRANSFER_KZT_INFO}\n💰 Сумма: {kzt} (по курсу {VND_TO_KZT}){comment}"
    return ""


def payment_method_label(method: str) -> str:
    return {"cash_vnd": "💵 Наличными донгами", "transfer_rub": "💳 Перевод рублями", "transfer_kzt": "💳 Перевод тенге"}.get(method, method)


def _trip_price_text(trip, adults: int = None) -> str:
    lines = [
        f"💰 Взрослый билет: {format_price(trip.price_adult)}",
        f"👶 Детский билет: {format_price(trip.price_child)}",
    ]
    if adults:
        lines.append(
            f"💸 За взрослых: {adults} × {format_price(trip.price_adult)} = "
            f"{format_price(adults * trip.price_adult)}"
        )
    return "\n".join(lines)


def _hold_line(payment_method: str) -> str:
    if payment_method == "cash_vnd":
        return "✅ Бронь закреплена за вами до самой поездки. Оплата наличными при посадке в автобус.\n"
    return "⏰ Бронь держится 24 часа. Если не оплатите в течение 24 часов — бронь будет автоматически отменена.\n"


@router.callback_query(F.data.startswith("trip_"))
async def show_trip_detail(callback: CallbackQuery):
    await callback.answer()
    trip_id = int(callback.data.split("_")[-1])

    async with async_session_maker() as session:
        result = await session.execute(select(Trip).where(Trip.id == trip_id))
        trip = result.scalar_one_or_none()

    if not trip or not trip.is_active:
        await callback.message.edit_text(
            "❌ Этот рейс уже недоступен",
            reply_markup=back_button("book_start"),
        )
        return

    async with async_session_maker() as session:
        occupied = await get_occupied_seats(session, trip_id)
        occupied_ids = await get_occupied_seat_ids(session, trip_id)
    total_seats = get_trip_total_seats(trip)
    free = total_seats - occupied
    bus_type_label = "VIP" if trip.bus_type == "vip" else "Sleeper"
    seat_map = render_seat_map(
        trip.bus_type, trip.seats_left, trip.seats_middle,
        trip.seats_right, occupied_ids,
    )

    text = (
        f"🚌 Рейс на {format_date_ru(trip.date)}\n"
        + (f"⏰ Отправление: {trip.departure_time}\n" if trip.departure_time else "") +
        f"📍 Место сбора: {trip.pickup_location}\n"
        f"🚌 Автобус: {trip.bus_number or 'уточняется'} ({bus_type_label})\n"
        f"💰 Цена взрослого: {format_price(trip.price_adult)}\n"
        f"💰 Цена детского: {format_price(trip.price_child)}\n"
        f"🔢 Свободно мест: {free} из {total_seats}\n\n"
        f"{seat_map}"
    )

    await callback.message.edit_text(text, reply_markup=trip_detail(trip_id))


@router.callback_query(F.data.startswith("book_trip_"))
async def start_booking(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    trip_id = int(callback.data.split("_")[-1])

    async with async_session_maker() as session:
        result = await session.execute(select(Trip).where(Trip.id == trip_id))
        trip = result.scalar_one_or_none()

    if not trip or not trip.is_active:
        await callback.message.edit_text(
            "❌ Этот рейс уже недоступен",
            reply_markup=back_button("book_start"),
        )
        return

    async with async_session_maker() as session:
        occupied = await get_occupied_seats(session, trip_id)
    total_seats = get_trip_total_seats(trip)
    if occupied >= total_seats:
        await callback.message.edit_text(
            "❌ На этот рейс все места заняты",
            reply_markup=back_button("book_start"),
        )
        return

    async with async_session_maker() as session:
        user = await get_or_create_user(session, callback.from_user.id, callback.from_user.username)
        existing = await session.execute(
            select(Booking).where(
                and_(
                    Booking.user_id == user.id,
                    Booking.trip_id == trip_id,
                    Booking.status.in_(["pending", "paid"]),
                )
            )
        )
        existing_booking = existing.scalar_one_or_none()

    if existing_booking:
        await callback.message.edit_text(
        f"ℹ️ У вас уже есть бронь на этот рейс\n\n"
        f"📋 Текущая бронь #{existing_booking.id}:\n"
        f"🧑 Взрослых: {existing_booking.adults}\n"
        f"👶 Детей: {existing_booking.children}\n"
        f"💰 Сумма: {format_price(existing_booking.total_price)}\n\n"
        f"Вы можете добавить людей к существующей брони\n"
        f"или отменить её и создать новую",
            reply_markup=existing_booking_actions(trip_id, existing_booking.id),
        )
        return

    await state.update_data(trip_id=trip_id)
    await state.set_state(BookingStates.waiting_adults)

    await callback.message.edit_text(
        f"❓ Сколько взрослых (от 7 лет)?\n"
        f"{_trip_price_text(trip)}\n"
        f"🔢 Максимум человек в одной брони: {MAX_PEOPLE_PER_BOOKING}\n"
        f"(Отправьте число от 1 до {MAX_PEOPLE_PER_BOOKING})",
        reply_markup=back_button("book_start"),
    )


@router.callback_query(F.data.startswith("add_people_"))
async def add_people_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    booking_id = int(callback.data.split("_")[-1])

    async with async_session_maker() as session:
        result = await session.execute(select(Booking).where(Booking.id == booking_id))
        booking = result.scalar_one_or_none()

        if not booking or booking.user.telegram_id != callback.from_user.id:
            await callback.message.edit_text(
                "❌ Бронь не найдена", reply_markup=back_button("book_start")
            )
            return

        if booking.status == "cancelled":
            await callback.message.edit_text(
                "❌ Бронь отменена. Создайте новую",
                reply_markup=back_button("book_start"),
            )
            return

        trip = await session.execute(select(Trip).where(Trip.id == booking.trip_id))
        trip = trip.scalar_one_or_none()
        if not trip or not trip.is_active:
            await callback.message.edit_text(
                "❌ Этот рейс больше недоступен",
                reply_markup=back_button("book_start"),
            )
            return

        occupied = await get_occupied_seats(session, booking.trip_id)
        total_seats = get_trip_total_seats(trip)
        if occupied >= total_seats:
            await callback.message.edit_text(
                "❌ На этот рейс все места заняты",
                reply_markup=back_button("book_start"),
            )
            return

    await state.update_data(
        existing_booking_id=booking_id,
        trip_id=booking.trip_id,
        trip_date=format_date_ru(trip.date),
    )
    await state.set_state(BookingStates.waiting_adults)

    await callback.message.edit_text(
        f"❓ Сколько взрослых добавить?\n"
        f"📋 Сейчас в брони: {booking.adults} взрослых, {booking.children} детей\n"
        f"{_trip_price_text(trip)}\n"
        f"(Отправьте число от 0 до {MAX_PEOPLE_PER_BOOKING})",
        reply_markup=back_button("book_start"),
    )


@router.callback_query(F.data.startswith("rebook_trip_"))
async def rebook_trip(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    trip_id = int(callback.data.split("_")[-1])

    async with async_session_maker() as session:
        user = await get_or_create_user(session, callback.from_user.id, callback.from_user.username)
        existing = await session.execute(
            select(Booking).where(
                and_(
                    Booking.user_id == user.id,
                    Booking.trip_id == trip_id,
                    Booking.status.in_(["pending", "paid"]),
                )
            )
        )
        old_booking = existing.scalar_one_or_none()
        if old_booking:
            old_booking.status = "cancelled"
            await session.commit()

        trip_result = await session.execute(select(Trip).where(Trip.id == trip_id))
        trip = trip_result.scalar_one_or_none()

    if not trip or not trip.is_active:
        await callback.message.edit_text(
            "❌ Этот рейс больше недоступен",
            reply_markup=back_button("book_start"),
        )
        return

    await state.update_data(trip_id=trip_id)
    await state.set_state(BookingStates.waiting_adults)

    await callback.message.edit_text(
        f"✅ Старая бронь отменена. Создаём новую\n\n"
        f"❓ Сколько взрослых (от 7 лет)?\n"
        f"{_trip_price_text(trip)}\n"
        f"🔢 Максимум человек в одной брони: {MAX_PEOPLE_PER_BOOKING}\n"
        f"(Отправьте число от 1 до {MAX_PEOPLE_PER_BOOKING})",
        reply_markup=back_button("book_start"),
    )


@router.message(BookingStates.waiting_adults)
async def process_adults_count(message: Message, state: FSMContext):
    if not message.text or not message.text.strip().isdigit():
        await message.answer("⚠️ Пожалуйста, введите целое число")
        return
    text = message.text.strip()

    adults = int(text)

    data = await state.get_data()
    existing_booking_id = data.get("existing_booking_id")

    async with async_session_maker() as session:
        trip_result = await session.execute(select(Trip).where(Trip.id == data.get("trip_id")))
        trip = trip_result.scalar_one_or_none()

    price_block = _trip_price_text(trip, adults) if trip else ""

    if existing_booking_id:
        if adults < 0 or adults > MAX_PEOPLE_PER_BOOKING:
            await message.answer(
                f"⚠️ Количество дополнительных взрослых должно быть от 0 до {MAX_PEOPLE_PER_BOOKING}"
            )
            return
        if adults == 0:
            await state.update_data(add_adults=0)
            await state.set_state(BookingStates.waiting_children)
            await message.answer(
                f"❓ Сколько детей добавить?\n"
                f"{_trip_price_text(trip)}\n"
                f"(Отправьте число от 0 до {MAX_PEOPLE_PER_BOOKING})",
                reply_markup=back_button("book_start"),
            )
            return

        async with async_session_maker() as session:
            booking = await session.get(Booking, existing_booking_id)
            if booking and booking.adults + booking.children + adults > MAX_PEOPLE_PER_BOOKING:
                await message.answer(
                    f"⚠️ Общее количество человек в брони не может превышать "
                    f"{MAX_PEOPLE_PER_BOOKING}. Сейчас: {booking.adults + booking.children}"
                )
                return

        await state.update_data(add_adults=adults)
    else:
        if adults < 1 or adults > MAX_PEOPLE_PER_BOOKING:
            await message.answer(
                f"⚠️ Количество взрослых должно быть от 1 до {MAX_PEOPLE_PER_BOOKING}"
            )
            return
        await state.update_data(adults=adults)

    await state.set_state(BookingStates.waiting_children)

    if existing_booking_id:
        await message.answer(
            f"❓ Сколько детей добавить?\n"
            f"{price_block}\n"
            f"(Отправьте число от 0 до {MAX_PEOPLE_PER_BOOKING})",
            reply_markup=back_button("book_start"),
        )
    else:
        await message.answer(
            f"❓ Сколько детей (до 7 лет включительно)?\n"
            f"{price_block}\n"
            f"(Отправьте число от 0 до {MAX_PEOPLE_PER_BOOKING})",
            reply_markup=back_button("book_start"),
        )


@router.message(BookingStates.waiting_children)
async def process_children_count(message: Message, state: FSMContext):
    if not message.text or not message.text.strip().isdigit():
        await message.answer("⚠️ Пожалуйста, введите целое число")
        return
    text = message.text.strip()

    children = int(text)
    if children < 0 or children > MAX_PEOPLE_PER_BOOKING:
        await message.answer(
                f"⚠️ Количество детей должно быть от 0 до {MAX_PEOPLE_PER_BOOKING}"
        )
        return

    data = await state.get_data()
    trip_id = data["trip_id"]
    existing_booking_id = data.get("existing_booking_id")

    if existing_booking_id:
        add_adults = data.get("add_adults", 0)
        add_people = add_adults + children

        if add_people < 1:
            await message.answer("⚠️ Нужно добавить хотя бы 1 человек")
            return

        if add_adults + children > MAX_PEOPLE_PER_BOOKING:
            await message.answer(
                f"⚠️ Общее количество добавляемых человек не может превышать "
                f"{MAX_PEOPLE_PER_BOOKING}"
            )
            return

        async with async_session_maker() as session:
            result = await session.execute(select(Trip).where(Trip.id == trip_id))
            trip = result.scalar_one_or_none()

        if not trip:
            await message.answer("❌ Рейс не найден", reply_markup=back_button("book_start"))
            await state.clear()
            return

        async with async_session_maker() as session:
            occupied = await get_occupied_seats(session, trip_id)
        free = get_trip_total_seats(trip) - occupied

        if add_people > free:
            await message.answer(
                f"❌ Недостаточно свободных мест. Осталось: {free}, "
                f"вы пытаетесь добавить: {add_people}\n"
                f"Попробуйте уменьшить количество",
                reply_markup=back_button("book_start"),
            )
            await state.clear()
            return

        add_price = add_adults * trip.price_adult + children * trip.price_child
        total_people_to_add = add_adults + children

        await state.clear()
        await state.update_data(
            existing_booking_id=existing_booking_id,
            trip_id=trip_id,
            add_adults=add_adults,
            add_children=children,
            add_price=add_price,
            total_people_to_add=total_people_to_add,
            trip_date=format_date_ru(trip.date),
            selected_seats=[],
            trip_data={
                "bus_type": trip.bus_type,
                "seats_left": trip.seats_left,
                "seats_middle": trip.seats_middle,
                "seats_right": trip.seats_right,
            },
        )

        await show_seat_selection(message, state, trip)
        return

    adults = data["adults"]
    total_people = adults + children

    if total_people > MAX_PEOPLE_PER_BOOKING:
        await message.answer(
            f"⚠️ Общее количество человек (взрослые + дети) не может превышать "
            f"{MAX_PEOPLE_PER_BOOKING}. У вас получилось {total_people}"
        )
        return

    if total_people < 1:
        await message.answer("⚠️ Должен быть хотя бы 1 человек")
        return

    async with async_session_maker() as session:
        result = await session.execute(select(Trip).where(Trip.id == trip_id))
        trip = result.scalar_one_or_none()

    if not trip:
        await message.answer("❌ Рейс не найден", reply_markup=back_button("book_start"))
        await state.clear()
        return

    async with async_session_maker() as session:
        occupied = await get_occupied_seats(session, trip_id)
    total_seats = get_trip_total_seats(trip)
    free = total_seats - occupied

    if total_people > free:
        await message.answer(
            f"❌ Недостаточно свободных мест. Осталось: {free}, "
            f"вы пытаетесь забронировать: {total_people}\n"
            f"Попробуйте уменьшить количество",
            reply_markup=back_button("book_start"),
        )
        await state.clear()
        return

    total_price = adults * trip.price_adult + children * trip.price_child

    await state.clear()
    await state.update_data(
        trip_id=trip_id,
        adults=adults,
        children=children,
        total_price=total_price,
        total_people=total_people,
        trip_date=format_date_ru(trip.date),
        selected_seats=[],
        trip_data={
            "bus_type": trip.bus_type,
            "seats_left": trip.seats_left,
            "seats_middle": trip.seats_middle,
            "seats_right": trip.seats_right,
        },
    )

    await show_seat_selection(message, state, trip)
    return


async def show_seat_selection(target, state: FSMContext, trip: Trip):
    data = await state.get_data()
    existing_booking_id = data.get("existing_booking_id")
    if existing_booking_id:
        needed = data.get("total_people_to_add", 1)
    else:
        needed = data.get("total_people", 1)

    async with async_session_maker() as session:
        occupied_ids = await get_occupied_seat_ids(session, trip.id)

    selected = set(data.get("selected_seats", []))
    seat_map = render_seat_map(
        trip.bus_type, trip.seats_left, trip.seats_middle,
        trip.seats_right, occupied_ids, selected,
    )
    kb = seat_selection_kb(
        trip.bus_type, trip.seats_left, trip.seats_middle,
        trip.seats_right, occupied_ids, selected, needed,
    )

    await state.set_state(BookingStates.selecting_seats)

    text = (
        f"🗺 Выберите места (нужно {needed}):\n\n"
        f"{seat_map}"
    )

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb)
    else:
        msg = await target.answer(text, reply_markup=kb)
        if hasattr(target, 'message') and target.message:
            pass


@router.callback_query(BookingStates.selecting_seats, F.data.startswith("seat_"))
async def process_seat_selection(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    action = callback.data.split("_", 1)[1]

    if action == "back":
        await state.clear()
        await callback.message.edit_text(
            "❌ Выбор мест отменён",
            reply_markup=back_button("book_start"),
        )
        return

    if action == "confirm":
        data = await state.get_data()
        selected = data.get("selected_seats", [])
        existing_booking_id = data.get("existing_booking_id")

        if existing_booking_id:
            needed = data.get("total_people_to_add", 1)
        else:
            needed = data.get("total_people", 1)

        if len(selected) < needed:
            await callback.answer(f"❌ Выберите ещё {needed - len(selected)} мест")
            return

        await state.update_data(selected_seats=selected)
        await process_payment(callback, state)
        return

    seat_id = action
    data = await state.get_data()
    selected = list(data.get("selected_seats", []))

    if seat_id in selected:
        selected.remove(seat_id)
    else:
        existing_booking_id = data.get("existing_booking_id")
        if existing_booking_id:
            needed = data.get("total_people_to_add", 1)
        else:
            needed = data.get("total_people", 1)
        if len(selected) >= needed:
            await callback.answer(f"❌ Нужно только {needed} мест. Снимите лишние")
            return
        selected.append(seat_id)

    await state.update_data(selected_seats=selected)

    trip_data = data.get("trip_data", {})
    async with async_session_maker() as session:
        result = await session.execute(select(Trip).where(Trip.id == data["trip_id"]))
        trip = result.scalar_one_or_none()
        if trip:
            occupied_ids = await get_occupied_seat_ids(session, trip.id)
        else:
            occupied_ids = set()

    seat_map = render_seat_map(
        trip_data.get("bus_type", "vip"),
        trip_data.get("seats_left", 20),
        trip_data.get("seats_middle", 0),
        trip_data.get("seats_right", 20),
        occupied_ids, set(selected),
    )
    if existing_booking_id:
        needed = data.get("total_people_to_add", 1)
    else:
        needed = data.get("total_people", 1)

    kb = seat_selection_kb(
        trip_data.get("bus_type", "vip"),
        trip_data.get("seats_left", 20),
        trip_data.get("seats_middle", 0),
        trip_data.get("seats_right", 20),
        occupied_ids, set(selected), needed,
    )

    await callback.message.edit_text(
        f"🗺 Выберите места (нужно {needed}):\n\n{seat_map}",
        reply_markup=kb,
    )


async def process_payment(target, state: FSMContext):
    async with async_session_maker() as session:
        user = await get_or_create_user(session, target.from_user.id, target.from_user.username)
        full_name = user.full_name or ""

    data = await state.get_data()
    trip_id = data.get("trip_id")
    existing_booking_id = data.get("existing_booking_id")
    selected_seats = data.get("selected_seats", [])
    seats_str = ",".join(selected_seats) if selected_seats else ""

    await state.update_data(seats_str=seats_str)

    if existing_booking_id:
        add_price = data.get("add_price")
        add_adults = data.get("add_adults", 0)
        add_children = data.get("add_children", 0)
        add_people = add_adults + add_children

        await target.message.edit_text(
            f"💳 Выберите способ оплаты для дополнительных мест:",
            reply_markup=payment_methods_kb(),
        )
        return

    adults = data.get("adults")
    children = data.get("children")
    total_price = data.get("total_price")

    await target.message.edit_text(
        "💳 Выберите способ оплаты:",
        reply_markup=payment_methods_kb(),
    )


@router.callback_query(F.data.startswith("pay_method_"))
async def process_payment_method(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    method = callback.data.split("_", 2)[-1]

    data = await state.get_data()
    trip_id = data.get("trip_id")
    existing_booking_id = data.get("existing_booking_id")

    if existing_booking_id:
        add_adults = data.get("add_adults", 0)
        add_children = data.get("add_children", 0)
        add_price = data.get("add_price")

        if add_adults is None or add_children is None or add_price is None:
            await callback.message.edit_text(
                "❌ Ошибка данных. Начните заново",
                reply_markup=back_button("book_start"),
            )
            await state.clear()
            return
    else:
        adults = data.get("adults")
        children = data.get("children")
        total_price = data.get("total_price")

        if not all([trip_id, adults is not None, children is not None, total_price]):
            await callback.message.edit_text(
                "❌ Ошибка данных. Начните заново",
                reply_markup=back_button("book_start"),
            )
            await state.clear()
            return

    await state.update_data(payment_method=method)

    if method == "cash_vnd":
        await state.update_data(payment_comment="")
        await _show_confirmation(callback, state)
        return

    await state.set_state(BookingStates.waiting_comment)
    await callback.message.edit_text(
        "💬 Введите Ваше Имя и Фамилию для проверки платежа:\n\n"
        "Именно это имя увидит администратор. Можете пропустить этот шаг",
        reply_markup=comment_kb(),
    )


@router.message(BookingStates.waiting_comment)
async def process_payment_comment(message: Message, state: FSMContext):
    comment = (message.text or "").strip()
    if len(comment) > 100:
        await message.answer("⚠️ Комментарий слишком длинный (максимум 100 символов). Введите короче:")
        return
    await state.update_data(payment_comment=comment)
    await _show_confirmation(message, state)


@router.callback_query(F.data == "comment_skip")
async def skip_payment_comment(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(payment_comment="")
    await _show_confirmation(callback, state)


@router.callback_query(F.data == "comment_back")
async def comment_back_to_payment(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(None)
    data = await state.get_data()
    if data.get("existing_booking_id"):
        await callback.message.edit_text(
            "💳 Выберите способ оплаты для дополнительных мест:",
            reply_markup=payment_methods_kb(),
        )
    else:
        await callback.message.edit_text(
            "💳 Выберите способ оплаты:",
            reply_markup=payment_methods_kb(),
        )


async def _show_confirmation(target, state: FSMContext):
    data = await state.get_data()
    method = data.get("payment_method")
    payment_comment = (data.get("payment_comment") or "").strip()

    async with async_session_maker() as session:
        user = await get_or_create_user(session, target.from_user.id, target.from_user.username)
    transfer_comment = payment_comment or user.full_name or ""

    existing_booking_id = data.get("existing_booking_id")

    if existing_booking_id:
        add_adults = data.get("add_adults", 0)
        add_children = data.get("add_children", 0)
        add_price = data.get("add_price")
        add_people = add_adults + add_children

        payment_info = payment_method_detail(method, add_price, transfer_comment)

        seats_str = data.get("seats_str") or data.get("selected_seats", [])
        if isinstance(seats_str, list):
            seats_str = ",".join(seats_str)
        seats_line = f"🪑 Места: {seats_str}\n" if seats_str else ""

        text = (
            f"📝 Добавление к брони:\n\n"
            f"📅 Дата: {data.get('trip_date')}\n"
            f"🧑 Добавить взрослых: {add_adults}\n"
            f"👶 Добавить детей: {add_children}\n"
            f"🔢 Всего добавляем: {add_people}\n"
            f"{seats_line}"
            f"💰 Доплата: {format_price_converted(add_price, method)}\n"
            f"💳 Способ оплаты: {payment_method_label(method)}\n\n"
            f"{payment_info}\n\n"
            f"✅ Подтверждаете?"
        )
    else:
        adults = data.get("adults")
        children = data.get("children")
        total_price = data.get("total_price")
        total_people = adults + children

        payment_info = payment_method_detail(method, total_price, transfer_comment)

        seats_str = data.get("seats_str") or data.get("selected_seats", [])
        if isinstance(seats_str, list):
            seats_str = ",".join(seats_str)
        seats_line = f"🪑 Места: {seats_str}\n" if seats_str else ""

        text = (
            f"📝 Подтверждение брони:\n\n"
            f"📅 Дата: {data.get('trip_date')}\n"
            f"🧑 Взрослых: {adults}\n"
            f"👶 Детей: {children}\n"
            f"🔢 Всего человек: {total_people}\n"
            f"{seats_line}"
            f"💰 Сумма: {format_price_converted(total_price, method)}\n"
            f"💳 Способ оплаты: {payment_method_label(method)}\n\n"
            f"{payment_info}\n\n"
            f"✅ Подтверждаете?"
        )

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=booking_confirm())
    else:
        await target.answer(text, reply_markup=booking_confirm())


@router.callback_query(F.data == "book_confirm")
async def confirm_booking(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    trip_id = data.get("trip_id")
    payment_method = data.get("payment_method")
    existing_booking_id = data.get("existing_booking_id")

    if existing_booking_id:
        add_adults = data.get("add_adults", 0)
        add_children = data.get("add_children", 0)
        add_price = data.get("add_price")

        if not all([trip_id, add_price is not None, payment_method]):
            await callback.answer("❌ Ошибка: данные не найдены")
            await callback.message.edit_text(
                "❌ Ошибка: данные не найдены. Попробуйте снова",
                reply_markup=back_button("book_start"),
            )
            await state.clear()
            return

        async with async_session_maker() as session:
            result = await session.execute(select(Trip).where(Trip.id == trip_id))
            trip = result.scalar_one_or_none()

            if not trip or not trip.is_active:
                await callback.answer("❌ Рейс недоступен")
                await callback.message.edit_text(
                    "❌ Этот рейс больше недоступен",
                    reply_markup=back_button("book_start"),
                )
                await state.clear()
                return

            occupied = await get_occupied_seats(session, trip_id)
            add_people = add_adults + add_children
            total_seats = get_trip_total_seats(trip)
            if add_people > total_seats - occupied:
                await callback.answer("❌ Недостаточно мест")
                await callback.message.edit_text(
                    "❌ Недостаточно свободных мест",
                    reply_markup=back_button("book_start"),
                )
                await state.clear()
                return

            booking = await session.get(Booking, existing_booking_id)
            if not booking or booking.user.telegram_id != callback.from_user.id:
                await callback.answer("❌ Бронь не найдена")
                await callback.message.edit_text(
                    "❌ Бронь не найдена", reply_markup=back_button("book_start"),
                )
                await state.clear()
                return

            new_adults = booking.adults + add_adults
            new_children = booking.children + add_children
            new_total = booking.total_price + add_price

            seats_str = data.get("seats_str") or ""
            existing_seats = booking.selected_seats or ""
            if existing_seats and seats_str:
                booking.selected_seats = existing_seats + "," + seats_str
            elif seats_str:
                booking.selected_seats = seats_str

            booking.adults = new_adults
            booking.children = new_children
            booking.total_price = new_total
            user = booking.user
            payment_comment = (data.get("payment_comment") or "").strip()
            was_paid = booking.status == "paid"
            if was_paid:
                booking.pending_add_amount = (booking.pending_add_amount or 0) + add_price
                booking.pending_add_people = (booking.pending_add_people or 0) + add_people
            else:
                booking.status = "pending"
                booking.created_at = now_utc()
            session.add(Payment(
                booking_id=booking.id,
                amount=add_price,
                method=payment_method,
                comment=payment_comment,
                details=payment_method_detail(
                    payment_method, add_price, payment_comment or user.full_name or ""
                ),
                status="pending",
            ))
            await session.commit()
            await session.refresh(booking)

        await state.clear()

        method_label = payment_method_label(payment_method)
        payment_info = payment_method_detail(payment_method, add_price, payment_comment or user.full_name or "")
        status_line = "ℹ️ Статус: оплачено (ожидается доплата)" if was_paid else "ℹ️ Статус: ожидает оплаты"
        hold_line = _hold_line(payment_method) if not was_paid else ""
        seats_str = data.get("seats_str") or ""
        seats_line = f"🪑 Места: {seats_str}\n" if seats_str else ""

        text = (
            "✅ Бронь обновлена!\n\n"
            f"📅 Дата: {format_date_ru(trip.date)}\n"
            f"🧑 Взрослых: {new_adults} (+{add_adults})\n"
            f"👶 Детей: {new_children} (+{add_children})\n"
            f"{seats_line}"
            f"💰 Общая сумма: {format_price_converted(new_total, payment_method)}\n"
            f"💰 Доплата: {format_price_converted(add_price, payment_method)}\n"
            f"💳 Способ оплаты: {method_label}\n"
            f"{status_line}\n"
            f"{hold_line}\n"
            f"💳 Реквизиты для оплаты:\n{payment_info}"
        )

        if payment_method == "cash_vnd":
            await callback.message.edit_text(text, reply_markup=booking_confirmed_main())
        else:
            await callback.message.edit_text(
                text, reply_markup=booking_confirmed_transfer(booking.id)
            )
        await notify_admins_update(callback.bot, booking, trip, user, add_adults, add_children, add_price, callback.from_user, payment_method, payment_comment)
        return

    adults = data.get("adults")
    children = data.get("children")
    total_price = data.get("total_price")

    if not all([trip_id, adults is not None, children is not None, total_price, payment_method]):
        await callback.answer("❌ Ошибка: данные не найдены. Начните заново")
        await callback.message.edit_text(
            "❌ Ошибка: данные брони не найдены. Попробуйте снова",
            reply_markup=back_button("book_start"),
        )
        await state.clear()
        return

    async with async_session_maker() as session:
        result = await session.execute(select(Trip).where(Trip.id == trip_id))
        trip = result.scalar_one_or_none()

        if not trip or not trip.is_active:
            await callback.answer("❌ Рейс недоступен")
            await callback.message.edit_text(
                "❌ Этот рейс больше недоступен",
                reply_markup=back_button("book_start"),
            )
            await state.clear()
            return

        occupied = await get_occupied_seats(session, trip_id)
        total_people = adults + children
        total_seats = get_trip_total_seats(trip)
        if occupied + total_people > total_seats:
            free = total_seats - occupied
            await callback.answer("❌ Недостаточно мест")
            await callback.message.edit_text(
                f"❌ Недостаточно мест. Осталось: {free}",
                reply_markup=back_button("book_start"),
            )
            await state.clear()
            return

        user = await get_or_create_user(session, callback.from_user.id, callback.from_user.username)
        full_name = user.full_name or ""
        seats_str = data.get("seats_str") or ""
        payment_comment = (data.get("payment_comment") or "").strip()

        booking = Booking(
            user_id=user.id,
            trip_id=trip_id,
            adults=adults,
            children=children,
            total_price=total_price,
            payment_method=payment_method,
            payment_details=payment_method_detail(
                payment_method, total_price, payment_comment or full_name
            ),
            payment_comment=payment_comment,
            selected_seats=seats_str,
            status="pending",
            created_at=now_utc(),
        )
        session.add(booking)
        await session.flush()
        session.add(Payment(
            booking_id=booking.id,
            amount=total_price,
            method=payment_method,
            comment=payment_comment,
            details=payment_method_detail(
                payment_method, total_price, payment_comment or full_name
            ),
            status="pending",
        ))
        await session.commit()
        await session.refresh(booking)

    await state.clear()

    method_label = payment_method_label(payment_method)
    payment_info = payment_method_detail(payment_method, total_price, full_name)
    seats_line = f"🪑 Места: {seats_str}\n" if seats_str else ""
    hold_line = _hold_line(payment_method)

    text = (
        "✅ Бронь создана!\n\n"
        f"📅 Дата: {format_date_ru(trip.date)}\n"
        f"🧑 Взрослых: {adults}\n"
        f"👶 Детей: {children}\n"
        f"{seats_line}"
        f"💰 Сумма: {format_price_converted(total_price, payment_method)}\n"
        f"💳 Способ оплаты: {method_label}\n"
        f"ℹ️ Статус: ожидает оплаты\n"
        f"{hold_line}\n"
        f"💳 Реквизиты для оплаты:\n{payment_info}"
    )

    if payment_method == "cash_vnd":
        await callback.message.edit_text(text, reply_markup=booking_confirmed_main())
    else:
        await callback.message.edit_text(
            text, reply_markup=booking_confirmed_transfer(booking.id)
        )
    await notify_admins(callback.bot, booking, trip, user, callback.from_user)


@router.callback_query(F.data.startswith("remove_person_"))
async def remove_person_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    booking_id = int(callback.data.split("_")[-1])

    async with async_session_maker() as session:
        result = await session.execute(select(Booking).where(Booking.id == booking_id))
        booking = result.scalar_one_or_none()

        if not booking or booking.user.telegram_id != callback.from_user.id:
            await callback.message.edit_text(
                "❌ Бронь не найдена", reply_markup=back_button("my_bookings")
            )
            return

        if booking.status == "cancelled":
            await callback.message.edit_text(
                "❌ Бронь уже отменена", reply_markup=back_button("my_bookings")
            )
            return

        trip = await session.execute(select(Trip).where(Trip.id == booking.trip_id))
        trip = trip.scalar_one_or_none()

    await state.update_data(
        remove_booking_id=booking_id,
        trip_id=booking.trip_id,
        trip_date=format_date_ru(trip.date),
        old_adults=booking.adults,
        old_children=booking.children,
        old_total=booking.total_price,
        booking_status=booking.status,
        payment_method=booking.payment_method,
    )
    await state.set_state(RemovePersonStates.waiting_adults)

    await callback.message.edit_text(
        f"❓ Сколько взрослых удалить?\n"
        f"📋 Сейчас в брони: {booking.adults} взрослых, {booking.children} детей\n"
        f"(Отправьте число от 0 до {booking.adults})",
        reply_markup=back_button("my_bookings"),
    )


@router.message(RemovePersonStates.waiting_adults)
async def process_remove_adults(message: Message, state: FSMContext):
    if not message.text or not message.text.strip().isdigit():
        await message.answer("⚠️ Пожалуйста, введите целое число")
        return
    text = message.text.strip()

    adults = int(text)
    data = await state.get_data()
    old_adults = data["old_adults"]

    if adults < 0 or adults > old_adults:
        await message.answer(
            f"⚠️ Введите число от 0 до {old_adults} (текущее количество взрослых)"
        )
        return

    await state.update_data(remove_adults=adults)
    await state.set_state(RemovePersonStates.waiting_children)

    old_children = data["old_children"]
    await message.answer(
        f"❓ Сколько детей удалить?\n"
        f"(Отправьте число от 0 до {old_children})",
        reply_markup=back_button("my_bookings"),
    )


@router.message(RemovePersonStates.waiting_children)
async def process_remove_children(message: Message, state: FSMContext):
    if not message.text or not message.text.strip().isdigit():
        await message.answer("⚠️ Пожалуйста, введите целое число")
        return
    text = message.text.strip()

    children = int(text)
    data = await state.get_data()
    old_children = data["old_children"]
    remove_adults = data.get("remove_adults", 0)

    if children < 0 or children > old_children:
        await message.answer(
            f"⚠️ Введите число от 0 до {old_children} (текущее количество детей)"
        )
        return

    total_remove = remove_adults + children
    if total_remove < 1:
        await message.answer("⚠️ Нужно удалить хотя бы 1 человек")
        return

    old_adults = data["old_adults"]
    new_adults = old_adults - remove_adults
    new_children = old_children - children
    if new_adults < 1 and new_children < 1:
        await message.answer(
            "⚠️ Нельзя удалить всех. Если хотите отменить всю бронь, "
            "используйте «Отменить бронь»",
        )
        return

    async with async_session_maker() as session:
        result = await session.execute(select(Trip).where(Trip.id == data["trip_id"]))
        trip = result.scalar_one_or_none()

    if not trip:
        await message.answer("❌ Рейс не найден", reply_markup=back_button("my_bookings"))
        await state.clear()
        return

    remove_price = remove_adults * trip.price_adult + children * trip.price_child
    new_total = data["old_total"] - remove_price

    booking_status = data.get("booking_status", "pending")
    if booking_status == "paid":
        finance_line = f"💰 Сумма к возврату: {format_price(remove_price)}"
    else:
        finance_line = f"💰 Сумма уменьшена на: {format_price(remove_price)}"

    await state.update_data(
        remove_children=children,
        remove_price=remove_price,
        new_adults=new_adults,
        new_children=new_children,
        new_total=new_total,
    )

    await message.answer(
        f"📝 Подтверждение удаления:\n\n"
        f"📅 Дата: {data.get('trip_date')}\n"
        f"🧑 Удалить взрослых: {remove_adults}\n"
        f"👶 Удалить детей: {children}\n"
        f"🔢 Всего удаляем: {total_remove}\n"
        f"{finance_line}\n"
        f"🔢 Новый состав: {new_adults} взр + {new_children} дет\n"
        f"💰 Новая сумма: {format_price(new_total)}\n\n"
        f"✅ Подтверждаете?",
        reply_markup=remove_confirm_kb(),
    )


@router.callback_query(F.data == "remove_confirm")
async def confirm_remove(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    booking_id = data.get("remove_booking_id")

    if not booking_id:
        await callback.answer("❌ Ошибка данных")
        await state.clear()
        return

    async with async_session_maker() as session:
        booking = await session.get(Booking, booking_id)
        if not booking or booking.user.telegram_id != callback.from_user.id:
            await callback.answer("❌ Бронь не найдена")
            await state.clear()
            return

        trip = await session.execute(select(Trip).where(Trip.id == booking.trip_id))
        trip = trip.scalar_one_or_none()

        remove_adults = data["remove_adults"]
        remove_children = data["remove_children"]
        remove_price = data["remove_price"]
        new_adults = data["new_adults"]
        new_children = data["new_children"]
        new_total = data["new_total"]

        booking.adults = new_adults
        booking.children = new_children
        booking.total_price = new_total

        total_removed = remove_adults + remove_children
        if booking.selected_seats:
            seat_list = [s.strip() for s in booking.selected_seats.split(",") if s.strip()]
            if len(seat_list) >= total_removed:
                booking.selected_seats = ",".join(seat_list[:-total_removed])
            else:
                booking.selected_seats = ""

        if booking.status == "paid":
            booking.created_at = now_utc()
        await session.commit()
        await session.refresh(booking)

    await state.clear()

    user = callback.from_user
    await callback.message.edit_text(
        f"✅ Бронь #{booking.id} обновлена!\n\n"
        f"❌ Удалено: {remove_adults} взр + {remove_children} дет\n"
        f"🔢 Новый состав: {new_adults} взр + {new_children} дет\n"
        f"💰 Новая сумма: {format_price(new_total)}",
        reply_markup=back_button("my_bookings"),
    )

    await notify_admins_remove(
        callback.bot, booking, trip, user,
        remove_adults, remove_children, remove_price,
    )


@router.callback_query(F.data == "book_cancel")
async def cancel_booking_flow(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.edit_text(
        "❌ Бронирование отменено",
        reply_markup=main_menu(),
    )





async def notify_admins(bot, booking, trip, user, tg_user):
    full_name = user.full_name or "не указано"
    comment = (booking.payment_comment or "").strip()
    name_display = comment if comment else (tg_account_name(tg_user) or full_name)
    pm = booking.payment_method
    seats_line = f"🪑 Места: {booking.selected_seats}\n" if booking.selected_seats else ""
    action = "💳 Наличные" if pm == "cash_vnd" else "💳 Перевод"
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"🔔 Новая бронь! Надо принять оплату\n"
                f"{'═' * 30}\n"
                f" (@{user.username or '—'})\n"
                f"📅 {format_date_ru(trip.date)}\n"
                f"🧑 {booking.adults} взр + {booking.children} дет = {booking.adults + booking.children} чел\n"
                f"{seats_line}"
                f"{action} {format_price_verbose(booking.total_price, pm)}\n"
                f"🆔 #{booking.id}",
                f"Комментарий: 👤 {name_display}",
                reply_markup=admin_notification_actions(booking.id),
            )
        except Exception:
            pass


async def notify_admins_update(bot, booking, trip, user, add_adults, add_children, add_price, tg_user, payment_method=None, payment_comment=None):
    full_name = user.full_name or "не указано"
    comment = (payment_comment or "").strip() or (booking.payment_comment or "").strip()
    name_display = comment if comment else (tg_account_name(tg_user) or full_name)
    pm = payment_method or booking.payment_method
    seats_line = f"🪑 Места: {booking.selected_seats}\n" if booking.selected_seats else ""
    for admin_id in ADMIN_IDS:
        try:
            text = (
                f"🔔 Бронь #{booking.id} — добавлены люди! Примите доплату\n"
                f"{'═' * 30}\n"
                f"👤 {name_display} (@{user.username or '—'})\n"
                f"📅 {format_date_ru(trip.date)}\n"
                f"➕ +{add_adults} взр + {add_children} дет\n"
                f"🗂 {booking.adults} взр + {booking.children} дет = {booking.adults + booking.children} чел\n"
                f"{seats_line}"
                f"💰 Доплата: {format_price_verbose(add_price, pm)}\n"
                f"💳 {payment_method_label(pm)}"
            )
            await bot.send_message(
                admin_id, text, reply_markup=admin_notification_actions(booking.id),
            )
        except Exception:
            pass


async def notify_admins_remove(bot, booking, trip, user, remove_adults, remove_children, remove_price):
    full_name = user.full_name or "не указано"
    pm = booking.payment_method
    for admin_id in ADMIN_IDS:
        try:
            base = (
                f"👤 {full_name} (@{user.username or '—'})\n"
                f"📅 {format_date_ru(trip.date)}\n"
                f"➖ -{remove_adults} взр - {remove_children} дет\n"
                f"🗂 {booking.adults} взр + {booking.children} дет = {booking.adults + booking.children} чел\n"
            )
            if booking.status == "paid":
                text = (
                    f"🔔 Бронь #{booking.id} — удалены люди! Требуется возврат\n"
                    f"{'═' * 30}\n"
                    f"{base}"
                    f"💰 Вернуть: {format_price_verbose(remove_price, pm)}\n"
                    f"💳 {payment_method_label(pm)}"
                )
            else:
                text = (
                    f"🔔 Бронь #{booking.id} — удалены люди!\n"
                    f"{'═' * 30}\n"
                    f"{base}"
                    f"💰 Сумма уменьшена на: {format_price_verbose(remove_price, pm)}\n"
                    f"💳 {payment_method_label(pm)}"
                )
            await bot.send_message(
                admin_id, text, reply_markup=admin_notification_actions(booking.id),
            )
        except Exception:
            pass
