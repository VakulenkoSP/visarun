import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is required. Set it in .env file.")

ADMIN_IDS = []
raw_ids = os.getenv("ADMIN_IDS")
if raw_ids and raw_ids != "твой_телеграм_id":
    ADMIN_IDS = [int(x.strip()) for x in raw_ids.split(",") if x.strip().isdigit()]

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
PRICE_ADULT = int(os.getenv("PRICE_ADULT"))
PRICE_CHILD = int(os.getenv("PRICE_CHILD"))
MAX_PEOPLE_PER_BOOKING = int(os.getenv("MAX_PEOPLE_PER_BOOKING", "10"))
PENDING_TIMEOUT_HOURS = int(os.getenv("PENDING_TIMEOUT_HOURS", "24"))

VND_TO_RUB = float(os.getenv("VND_TO_RUB", "0.0037"))
VND_TO_KZT = float(os.getenv("VND_TO_KZT", "0.018"))

PAYMENT_CASH_VND_INFO = os.getenv("PAYMENT_CASH_VND_INFO", "Наличными в донгах при посадке в автобус.")
PAYMENT_TRANSFER_RUB_INFO = os.getenv("PAYMENT_TRANSFER_RUB_INFO")
PAYMENT_TRANSFER_KZT_INFO = os.getenv("PAYMENT_TRANSFER_KZT_INFO")

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "bot.db").replace("\\", "/")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{DB_PATH}")
