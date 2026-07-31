from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select, func, and_, or_
from .database import async_session_maker
from .models import Trip, Booking, User
from .config import PENDING_TIMEOUT_HOURS, VND_TO_RUB, VND_TO_KZT

HANOI_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def format_price(amount: int) -> str:
    s = f"{amount:,}".replace(",", " ")
    return f"{s} VND"


def format_price_converted(price_vnd: int, payment_method: str = None) -> str:
    if payment_method == "transfer_rub":
        rub = price_vnd * VND_TO_RUB
        return f"{rub:,.0f} RUB".replace(",", " ")
    elif payment_method == "transfer_kzt":
        kzt = price_vnd * VND_TO_KZT
        return f"{kzt:,.0f} KZT".replace(",", " ")
    return format_price(price_vnd)


def format_price_verbose(price_vnd: int, payment_method: str = None) -> str:
    base = format_price(price_vnd)
    if payment_method == "transfer_rub":
        rub = price_vnd * VND_TO_RUB
        return f"{base} (~{rub:,.0f} RUB)".replace(",", " ")
    elif payment_method == "transfer_kzt":
        kzt = price_vnd * VND_TO_KZT
        return f"{base} (~{kzt:,.0f} KZT)".replace(",", " ")
    return base


def format_date_ru(d) -> str:
    months = [
        "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря",
    ]
    return f"{d.day} {months[d.month - 1]} {d.year}"


def tg_account_name(tg_user) -> str:
    parts = [
        getattr(tg_user, "first_name", "") or "",
        getattr(tg_user, "last_name", "") or "",
    ]
    name = " ".join(p for p in parts if p).strip()
    return name or (getattr(tg_user, "username", "") or "")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_hanoi() -> datetime:
    return datetime.now(HANOI_TZ)


async def get_or_create_user(session, telegram_id: int, username: str = None) -> User:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(telegram_id=telegram_id, username=username)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    elif username and user.username != username:
        user.username = username
        await session.commit()
    return user


async def get_pending_bookings_older_than(hours: int = 1) -> list[Booking]:
    async with async_session_maker() as session:
        cutoff = now_utc() - timedelta(hours=hours)
        result = await session.execute(
            select(Booking).where(
                and_(
                    Booking.status == "pending",
                    Booking.created_at < cutoff,
                    Booking.payment_method != "cash_vnd",
                )
            ).order_by(Booking.created_at)
        )
        return result.scalars().all()


async def get_occupied_seats(session, trip_id: int) -> int:
    result = await session.execute(
        select(Booking.selected_seats).where(
            and_(
                Booking.trip_id == trip_id,
                Booking.status.in_(["pending", "paid"]),
                Booking.selected_seats.isnot(None),
            )
        )
    )
    total = 0
    for row in result:
        if row[0]:
            total += len(row[0].split(","))
    return total


async def get_occupied_seat_ids(session, trip_id: int) -> set[str]:
    result = await session.execute(
        select(Booking.selected_seats).where(
            and_(
                Booking.trip_id == trip_id,
                Booking.status.in_(["pending", "paid"]),
                Booking.selected_seats.isnot(None),
            )
        )
    )
    seat_ids: set[str] = set()
    for row in result:
        if row[0]:
            for s in row[0].split(","):
                s = s.strip()
                if s:
                    seat_ids.add(s)
    return seat_ids


def get_trip_total_seats(trip: Trip) -> int:
    return trip.seats_left + trip.seats_middle + trip.seats_right


def render_seat_map(
    bus_type: str,
    seats_left: int,
    seats_middle: int,
    seats_right: int,
    occupied: set[str],
    selected: set[str] | None = None,
) -> str:
    if selected is None:
        selected = set()
    rows = max(seats_left, seats_middle, seats_right)
    bus_label = "VIP" if bus_type == "vip" else "Sleeper"
    lines = [f"🚌 Автобус: {bus_label}", ""]

    if bus_type == "vip":
        lines.append("    Лево    |    Право")
    else:
        lines.append("    Лево    |   Центр   |    Право")

    for i in range(1, rows + 1):
        parts = [f"{i:<2}"]
        if i <= seats_left:
            left_id = f"L{i}"
            left_sym = "🔵" if left_id in selected else ("🔴" if left_id in occupied else "🟢")
            parts.append(f"{left_sym} {left_id:<3}")
        parts.append("⬜")
        if bus_type == "sleeper" and i <= seats_middle:
            mid_id = f"M{i}"
            mid_sym = "🔵" if mid_id in selected else ("🔴" if mid_id in occupied else "🟢")
            parts.append(f"{mid_sym} {mid_id:<3}")
            parts.append("⬜")
        if i <= seats_right:
            right_id = f"R{i}"
            right_sym = "🔵" if right_id in selected else ("🔴" if right_id in occupied else "🟢")
            parts.append(f"{right_sym} {right_id}")
        lines.append("  ".join(parts))

    lines.append("")
    lines.append("🟢 свободно  🔴 занято  🔵 ваше  ⬜ проход")
    return "\n".join(lines)


async def get_trip_stats(session, trip_id: int) -> dict:
    trip_result = await session.execute(select(Trip).where(Trip.id == trip_id))
    trip = trip_result.scalar_one_or_none()
    if not trip:
        return None

    occupied = await get_occupied_seats(session, trip_id)
    total_seats = get_trip_total_seats(trip)

    paid_result = await session.execute(
        select(func.coalesce(func.sum(Booking.adults + Booking.children), 0)).where(
            and_(Booking.trip_id == trip_id, Booking.status == "paid")
        )
    )
    paid = paid_result.scalar() or 0

    pending_result = await session.execute(
        select(func.coalesce(func.sum(Booking.adults + Booking.children), 0)).where(
            and_(Booking.trip_id == trip_id, Booking.status == "pending")
        )
    )
    pending_seats = pending_result.scalar() or 0

    return {
        "trip": trip,
        "occupied": occupied,
        "free": total_seats - occupied,
        "paid": paid,
        "pending_seats": pending_seats,
    }


async def deactivate_past_trips():
    async with async_session_maker() as session:
        today = now_hanoi().date()
        result = await session.execute(
            select(Trip).where(and_(Trip.is_active == True, Trip.date < today))
        )
        past_trips = result.scalars().all()
        for trip in past_trips:
            trip.is_active = False
        if past_trips:
            await session.commit()


async def cancel_expired_pending():
    async with async_session_maker() as session:
        cutoff = now_utc() - timedelta(hours=PENDING_TIMEOUT_HOURS)
        result = await session.execute(
            select(Booking).where(
                and_(
                    Booking.status == "pending",
                    Booking.created_at < cutoff,
                    or_(Booking.payment_method.is_(None), Booking.payment_method != "cash_vnd"),
                )
            )
        )
        expired = result.scalars().all()
        for booking in expired:
            booking.status = "cancelled"
        if expired:
            await session.commit()
    return expired


async def get_upcoming_trip_bookings() -> list[Booking]:
    async with async_session_maker() as session:
        tomorrow = now_hanoi().date() + timedelta(days=1)
        result = await session.execute(
            select(Booking).join(Booking.trip).where(
                and_(
                    Booking.status == "paid",
                    Trip.date == tomorrow,
                    Trip.is_active == True,
                )
            )
        )
        return result.scalars().all()


STATUS_EMOJI = {
    "pending": "ожидает оплаты",
    "paid": "оплачено",
    "cancelled": "отменено",
}
