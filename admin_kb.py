"""کیبوردهای اینلاین مربوط به بخش‌های مدیریتی سوپر ادمین."""
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup
from bot.utils.navigation import admin_back_callback


# ==================== مدیریت پنل‌های PasarGuard ====================

def admin_panels_list_keyboard(panels: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for panel in panels:
        status = "✅" if panel["is_active"] else "❌"
        builder.button(
            text=f"{status} {panel['display_name']}",
            callback_data=f"admin_panel_view:{panel['id']}",
        )
    builder.button(text="➕ افزودن پنل جدید", callback_data="admin_panel_add")
    builder.button(text="🔙 بازگشت به پنل مدیریت", callback_data=admin_back_callback("admin_home"))
    builder.adjust(1)
    return builder.as_markup()


def admin_panel_detail_keyboard(panel_id: int, is_active: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    toggle_text = "❌ غیرفعال کردن" if is_active else "✅ فعال کردن"
    builder.button(text="✏️ ویرایش", callback_data=f"admin_panel_edit:{panel_id}")
    builder.button(text=toggle_text, callback_data=f"admin_panel_toggle:{panel_id}")
    builder.button(text="🗑 حذف", callback_data=f"admin_panel_delete:{panel_id}")
    builder.button(text="🔙 بازگشت به لیست پنل‌ها", callback_data=admin_back_callback("panels_list"))
    builder.adjust(1)
