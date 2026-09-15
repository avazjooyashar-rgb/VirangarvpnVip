"""
مدیریت پلن‌های VPN توسط سوپر ادمین.
هر پلن به یک پنل PasarGuard مشخص وصل است.
مسیر: انتخاب پنل -> لیست پلن‌های آن پنل -> افزودن/ویرایش/حذف/فعال‌سازی
همه مراحل دکمه بازگشت دارند.
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from bot.states.admin_states import AdminPlanStates
from bot.keyboards import admin_kb as kb
from bot.utils.navigation import parse_admin_back_callback
from bot.utils.number_validators import validate_positive_int
from bot.database import queries as db
from bot.config import ADMIN_IDS

router = Router(name="admin_plans")


def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def _traffic_text(traffic_gb: int) -> str:
    return "نامحدود" if traffic_gb == 0 else f"{traffic_gb} گیگ"


# ==================== ورود به بخش مدیریت پلن‌ها ====================
