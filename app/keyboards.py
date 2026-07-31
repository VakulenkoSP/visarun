from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from .utils import format_date_ru


def main_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📅 Записаться на визаран", callback_data="book_start")
    kb.button(text="📋 Мои брони", callback_data="my_bookings")
    kb.button(text="ℹ️ Информация", callback_data="info")
    kb.adjust(1)
    return kb.as_markup()


def back_button(callback_data: str = "back_to_main") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="↩️ Назад", callback_data=callback_data)
    return kb.as_markup()


def trips_list_raw(trip_list: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for t in trip_list:
        free = t["free"]
        bus_icon = "💎" if t.get("bus_type") == "vip" else "🛌"
        bus_label = "VIP" if t.get("bus_type") == "vip" else "Sleeper"
        label = f"{'🟢' if free > 0 else '🔴'} {format_date_ru(t['date'])} {bus_icon}{bus_label} — {free}/{t['max_seats']}"
        kb.button(text=label, callback_data=f"trip_{t['id']}")
    kb.button(text="↩️ Назад", callback_data="back_to_main")
    kb.adjust(1)
    return kb.as_markup()


def trip_detail(trip_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Забронировать", callback_data=f"book_trip_{trip_id}")
    kb.button(text="↩️ Назад", callback_data="book_start")
    kb.adjust(1)
    return kb.as_markup()


def booking_confirm() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить бронь", callback_data="book_confirm")
    kb.button(text="❌ Отмена", callback_data="book_cancel")
    kb.adjust(1)
    return kb.as_markup()


def my_bookings_list(bookings_data: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for b in bookings_data:
        emoji = "✅" if b['status'] == "paid" else "⏳" if b['status'] == "pending" else "❌"
        label = f"{emoji} {format_date_ru(b['trip_date'])} — {b['status_text']}"
        kb.button(text=label, callback_data=f"my_booking_{b['id']}")
    kb.button(text="↩️ Назад", callback_data="back_to_main")
    kb.adjust(1)
    return kb.as_markup()


def my_booking_detail_kb(booking_id: int, show_pay: bool, show_cancel: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if show_pay:
        kb.button(text="✅ Я оплатил", callback_data=f"my_paid_{booking_id}")
    if show_cancel:
        kb.button(text="❌ Отменить бронь", callback_data=f"my_booking_cancel_{booking_id}")
    kb.button(text="↩️ Назад", callback_data="my_bookings")
    kb.adjust(1)
    return kb.as_markup()


def admin_main_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📦 Создать рейс", callback_data="admin_create_trip")
    kb.button(text="📋 Список рейсов", callback_data="admin_trips")
    kb.button(text="🚪 Выйти", callback_data="back_to_main")
    kb.adjust(1)
    return kb.as_markup()


def admin_trips_list_raw(trip_list: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for t in trip_list:
        bus_icon = "💎" if t.get("bus_type") == "vip" else "🛌"
        label = f"{bus_icon} {format_date_ru(t['date'])} — {t['occupied']}/{t['max_seats']}"
        kb.button(text=label, callback_data=f"admin_trip_{t['id']}")
    kb.button(text="↩️ Назад", callback_data="admin_menu")
    kb.adjust(1)
    return kb.as_markup()


def admin_trip_menu(trip_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Просмотр броней", callback_data=f"admin_bookings_{trip_id}")
    kb.button(text="✏️ Редактировать", callback_data=f"admin_edit_{trip_id}")
    kb.button(text="📊 Статистика", callback_data=f"admin_stats_{trip_id}")
    kb.button(text="📄 Экспорт", callback_data=f"admin_export_{trip_id}")
    kb.button(text="📊 Excel экспорт", callback_data=f"admin_export_xlsx_{trip_id}")
    kb.button(text="📢 Оповестить всех", callback_data=f"admin_broadcast_{trip_id}")
    kb.button(text="🗑 Удалить рейс", callback_data=f"admin_delete_{trip_id}")
    kb.button(text="↩️ Назад", callback_data="admin_trips")
    kb.adjust(1)
    return kb.as_markup()


def admin_bookings_filter(trip_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Все", callback_data=f"admin_bookings_{trip_id}_all")
    kb.button(text="⏳ Ожидают оплаты", callback_data=f"admin_bookings_{trip_id}_pending")
    kb.button(text="✅ Оплачено", callback_data=f"admin_bookings_{trip_id}_paid")
    kb.button(text="↩️ Назад", callback_data=f"admin_trip_{trip_id}")
    kb.adjust(1)
    return kb.as_markup()


def admin_edit_trip(trip_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📅 Дату", callback_data=f"admin_edit_{trip_id}_date")
    kb.button(text="🚌 Тип автобуса", callback_data=f"admin_edit_{trip_id}_bus_type")
    kb.button(text="🪑 Места слева", callback_data=f"admin_edit_{trip_id}_seats_left")
    kb.button(text="🪑 Места в центре", callback_data=f"admin_edit_{trip_id}_seats_middle")
    kb.button(text="🪑 Места справа", callback_data=f"admin_edit_{trip_id}_seats_right")
    kb.button(text="💰 Цену взрослого", callback_data=f"admin_edit_{trip_id}_price_adult")
    kb.button(text="🧒 Цену детского", callback_data=f"admin_edit_{trip_id}_price_child")
    kb.button(text="📍 Место сбора", callback_data=f"admin_edit_{trip_id}_location")
    kb.button(text="⏰ Время отправления", callback_data=f"admin_edit_{trip_id}_time")
    kb.button(text="🚌 Номер автобуса", callback_data=f"admin_edit_{trip_id}_bus")
    kb.button(text="↩️ Назад", callback_data=f"admin_trip_{trip_id}")
    kb.adjust(1)
    return kb.as_markup()


def bus_type_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💎 VIP (2 ряда)", callback_data="bus_type_vip")
    kb.button(text="🛌 Sleeper (3 ряда)", callback_data="bus_type_sleeper")
    kb.adjust(1)
    return kb.as_markup()


def seat_selection_kb(
    bus_type: str,
    seats_left: int,
    seats_middle: int,
    seats_right: int,
    occupied: set[str],
    selected: set[str],
    needed: int,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    rows = max(seats_left, seats_middle, seats_right)
    for i in range(1, rows + 1):
        row_buttons = []
        if i <= seats_left:
            left_id = f"L{i}"
            left_emoji = "🔵" if left_id in selected else ("🔴" if left_id in occupied else "🟢")
            row_buttons.append(InlineKeyboardButton(
                text=f"{left_emoji} {left_id}", callback_data=f"seat_{left_id}"
            ))

        if bus_type == "sleeper" and i <= seats_middle:
            mid_id = f"M{i}"
            mid_emoji = "🔵" if mid_id in selected else ("🔴" if mid_id in occupied else "🟢")
            row_buttons.append(InlineKeyboardButton(
                text=f"{mid_emoji} {mid_id}", callback_data=f"seat_{mid_id}"
            ))

        if i <= seats_right:
            right_id = f"R{i}"
            right_emoji = "🔵" if right_id in selected else ("🔴" if right_id in occupied else "🟢")
            row_buttons.append(InlineKeyboardButton(
                text=f"{right_emoji} {right_id}", callback_data=f"seat_{right_id}"
            ))

        if row_buttons:
            kb.row(*row_buttons)

    kb.row(InlineKeyboardButton(
        text=f"✅ Подтвердить ({len(selected)}/{needed})",
        callback_data="seat_confirm",
    ))
    kb.row(InlineKeyboardButton(text="↩️ Назад", callback_data="seat_back"))
    return kb.as_markup()



def admin_booking_actions(booking_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Оплачено", callback_data=f"booking_paid_{booking_id}")
    kb.button(text="❌ Отменить", callback_data=f"booking_cancel_{booking_id}")
    kb.adjust(2)
    return kb.as_markup()


def existing_booking_actions(trip_id: int, booking_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить людей", callback_data=f"add_people_{booking_id}")
    kb.button(text="➖ Удалить человека", callback_data=f"remove_person_{booking_id}")
    kb.button(text="🔄 Отменить и создать новую", callback_data=f"rebook_trip_{trip_id}")
    kb.button(text="↩️ Назад", callback_data="book_start")
    kb.adjust(1)
    return kb.as_markup()


def remove_confirm_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить удаление", callback_data="remove_confirm")
    kb.button(text="❌ Отмена", callback_data="book_cancel")
    kb.adjust(1)
    return kb.as_markup()


def booking_confirmed_main() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🏠 Главное меню", callback_data="back_to_main")
    return kb.as_markup()


def booking_confirmed_transfer(booking_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Оплатил", callback_data=f"my_paid_{booking_id}")
    kb.button(text="🏠 Главное меню", callback_data="back_to_main")
    kb.adjust(1)
    return kb.as_markup()


def payment_methods_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💵 Наличными (VND)", callback_data="pay_method_cash_vnd")
    kb.button(text="💳 Перевод (RUB)", callback_data="pay_method_transfer_rub")
    kb.button(text="💳 Перевод (KZT)", callback_data="pay_method_transfer_kzt")
    kb.adjust(1)
    return kb.as_markup()


def comment_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⏭ Пропустить", callback_data="comment_skip")
    kb.button(text="↩️ Назад", callback_data="comment_back")
    kb.adjust(1)
    return kb.as_markup()


def admin_notification_actions(booking_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Оплачено", callback_data=f"booking_paid_{booking_id}")
    kb.button(text="❌ Отменить", callback_data=f"booking_cancel_{booking_id}")
    kb.adjust(2)
    return kb.as_markup()


def broadcast_confirm_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Отправить", callback_data="broadcast_send")
    kb.button(text="❌ Отмена", callback_data="broadcast_cancel")
    kb.adjust(1)
    return kb.as_markup()
