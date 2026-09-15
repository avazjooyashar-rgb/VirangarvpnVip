"""
مدیریت پنل‌های PasarGuard (زیرساخت اصلی) توسط سوپر ادمین.
لیست / افزودن (با تست اتصال) / ویرایش / فعال‌سازی‌غیرفعال‌سازی / حذف.
همه مراحل دکمه بازگشت دارند.
"""
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from bot.states.admin_states import AdminPanelStates
from bot.keyboards import admin_kb as kb
from bot.utils.navigation import parse_admin_back_callback
from bot.database import queries as db
from bot.services.pasarguard import PasarGuardClient, PasarGuardError
from bot.config import ADMIN_IDS

router = Router(name="admin_panels")


def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ==================== ورود به بخش مدیریت پنل‌ها ====================

@router.callback_query(F.data == "admin_panels_menu")
async def open_panels_menu(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
