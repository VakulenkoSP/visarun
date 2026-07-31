# VisaRun — Border Run Telegram Bot

Telegram bot for booking bus trips on the **Nha Trang → Laos** visa-run route (and back). It lets customers book seats on their own 24/7, while the admin keeps full control over trips, bookings and payments from a simple admin panel.

## Features

- **Self-service booking** — customers pick a trip date, choose seats on a visual bus diagram (VIP / Sleeper), and set the number of adults and children.
- **Flexible payment methods** — cash in VND or bank transfer in RUB / KZT with automatic conversion at the configured rate. Customers can add a payment comment (name) so the admin can verify the transfer.
- **Payment history** — every payment (initial booking and each add-on) is stored separately with method, amount, comment and status, so partial or mixed payments never get lost or overwritten.
- **Admin panel** — password-protected area to manage trips, view bookings with status filters, confirm payments, mark "people added without payment", see per-trip stats and export passenger lists to Excel in a couple of taps.
- **Automatic reminders & auto-cancel** — unpaid transfer bookings are auto-cancelled after 24 hours; cash bookings are held until departure. Customers get notified.
- **Booking management for customers** — add or remove people, view booking details and payment status.
- **Admin notifications** — admins are notified in real time about new bookings, extra people added, removals and payment confirmations.

## Tech stack

- Python 3
- aiogram 3 (Telegram Bot API)
- SQLAlchemy 2 (async)
- SQLite / aiosqlite (PostgreSQL-ready via `DATABASE_URL`)
- openpyxl (Excel export)
- python-dotenv

## Quick start

1. Clone the repository and create a virtual environment:

   ```bash
   python -m venv .venv
   ```

2. Activate it:

   - Windows (PowerShell): `.venv\Scripts\Activate.ps1`
   - macOS / Linux: `source .venv/bin/activate`

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Copy the environment template and fill it in:

   ```bash
   cp .env.example .env
   ```

5. Set at least these values in `.env`:

   ```bash
   BOT_TOKEN=your_bot_token_here       # from @BotFather
   ADMIN_IDS=123456789                 # comma-separated Telegram IDs of admins
   ADMIN_PASSWORD=your_pass            # admin panel password
   ```

   Adjust prices, exchange rates and payment details as needed.

6. Run the bot:

   ```bash
   python run.py
   ```

   The SQLite database is created automatically at `data/bot.db` on first run.

## Admin panel

- Open the bot and use the **/admin** command (or the admin menu) and enter the password from `ADMIN_PASSWORD`.
- Create and manage trips: date, bus type and seats, prices, pickup location, departure time and bus number.
- View all bookings per trip, filter by status and confirm payments in one tap.
- Export the passenger list to Excel.
- Statistics show occupied seats and revenue per trip.

## Configuration reference

| Variable | Description | Example |
| --- | --- | --- |
| `BOT_TOKEN` | Telegram bot token from @BotFather | `123456:ABC-...` |
| `ADMIN_IDS` | Comma-separated admin Telegram IDs | `123456789,987654321` |
| `ADMIN_PASSWORD` | Admin panel password | `admin123` |
| `PRICE_ADULT` / `PRICE_CHILD` | Default ticket prices in VND | `1450000` / `1000000` |
| `MAX_PEOPLE_PER_BOOKING` | Max people per booking | `10` |
| `PENDING_TIMEOUT_HOURS` | Hours before an unpaid transfer booking is auto-cancelled | `24` |
| `VND_TO_RUB` / `VND_TO_KZT` | Exchange rates for transfer payments | `0.0037` / `0.018` |
| `PAYMENT_CASH_VND_INFO` | Cash payment instructions | `Pay in cash in VND when boarding` |
| `PAYMENT_TRANSFER_RUB_INFO` | Transfer details (RUB) | `Bank card details...` |
| `PAYMENT_TRANSFER_KZT_INFO` | Transfer details (KZT) | `Kaspi bank...` |
| `DATABASE_URL` | Optional custom DB connection (e.g. PostgreSQL) | `postgresql+asyncpg://user:pass@host/db` |

## License

No license specified.
