from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Date
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    username = Column(String(255), nullable=True)
    full_name = Column(String(255), nullable=True)
    phone = Column(String(20), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    bookings = relationship("Booking", back_populates="user", lazy="selectin")


class Trip(Base):
    __tablename__ = "trips"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    max_seats = Column(Integer, nullable=False, default=40)
    bus_type = Column(String(10), nullable=False, default="vip")
    seats_left = Column(Integer, nullable=False, default=20)
    seats_middle = Column(Integer, nullable=False, default=0)
    seats_right = Column(Integer, nullable=False, default=20)
    price_adult = Column(Integer, nullable=False, default=1450000)
    price_child = Column(Integer, nullable=False, default=1000000)
    pickup_location = Column(String(500), nullable=False)
    departure_time = Column(String(5), nullable=True)
    bus_number = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    bookings = relationship("Booking", back_populates="trip", lazy="selectin")


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False)
    adults = Column(Integer, nullable=False, default=1)
    children = Column(Integer, nullable=False, default=0)
    total_price = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    payment_method = Column(String(30), nullable=True)
    payment_details = Column(String(500), nullable=True)
    payment_comment = Column(String(255), nullable=True)
    pending_add_amount = Column(Integer, nullable=True)
    pending_add_people = Column(Integer, nullable=True)
    selected_seats = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="bookings", lazy="selectin")
    trip = relationship("Trip", back_populates="bookings", lazy="selectin")
    payments = relationship("Payment", back_populates="booking", lazy="selectin", cascade="all, delete-orphan")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False)
    amount = Column(Integer, nullable=False)
    method = Column(String(30), nullable=True)
    comment = Column(String(255), nullable=True)
    details = Column(String(500), nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    paid_at = Column(DateTime(timezone=True), nullable=True)

    booking = relationship("Booking", back_populates="payments", lazy="selectin")
