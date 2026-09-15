"""
هندلر کامل فرآیند «خرید VPN»:
پنل -> پلن -> یوزرنیم -> خلاصه سفارش -> روش پرداخت -> (کارت به کارت | کیف پول)

هر مرحله دکمه «بازگشت» دارد که با الگوی back:<step> کار می‌کند.
"""
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from bot.states.purchase_states import PurchaseStates
from bot.keyboards import purchase_kb as kb
from bot.utils.navigation import parse_back_callback, PURCHASE_FLOW_PREVIOUS_STEP
from bot.utils.validators import validate_vpn_username
from bot.database import queries as db
from bot.services.pasarguard import PasarGuardClient, PasarGuardError
from bot.config import ADMIN_IDS, CARD_NUMBER, CARD_HOLDER_NAME

router = Router(name="purchase")


# ==================== شروع فرآیند خرید ====================

@router.callback_query(F.data == "buy_vpn")
async def start_purchase(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    panels = await db.get_active_panels()

    if not panels:
        await callback.message.edit_text("⚠️ در حال حاضر هیچ پنلی فعال نیست.")
        await callback.answer()
        return

    await state.set_state(PurchaseStates.choosing_panel)
    await callback.message.edit_text(
        "🖥 لطفاً یکی از پنل‌های زیر را انتخاب کنید:",
        reply_markup=kb.panels_keyboard(panels),
    )
    await callback.answer()


# ==================== مرحله ۱: انتخاب پنل ====================

@router.callback_query(F.data.startswith("panel:"))
async def choose_panel(callback: CallbackQuery, state: FSMContext):
    panel_id = int(callback.data.split(":")[1])
    panel = await db.get_panel_by_id(panel_id)

    if not panel:
        await callback.answer("این پنل یافت نشد.", show_alert=True)
        return

    plans = await db.get_active_plans_by_panel(panel_id)
    if not plans:
        await callback.answer("برای این پنل هیچ پلنی تعریف نشده.", show_alert=True)
        return

    await state.update_data(panel_id=panel_id, panel_name=panel["display_name"])
    await state.set_state(PurchaseStates.choosing_plan)

    await callback.message.edit_text(
        f"🖥 پنل انتخابی: {panel['display_name']}\n\n"
        "💎 لطفاً یکی از پلن‌های زیر را انتخاب کنید:",
        reply_markup=kb.plans_keyboard(plans),
    )
    await callback.answer()


# ==================== مرحله ۲: انتخاب پلن ====================

@router.callback_query(F.data.startswith("plan:"))
async def choose_plan(callback: CallbackQuery, state: FSMContext):
    plan_id = int(callback.data.split(":")[1])
    plan = await db.get_plan_by_id(plan_id)

    if not plan:
        await callback.answer("این پلن یافت نشد.", show_alert=True)
        return

    await state.update_data(
        plan_id=plan_id,
        plan_title=plan["title"],
        plan_price=plan["price"],
        plan_traffic_gb=plan["traffic_gb"],
        plan_duration_days=plan["duration_days"],
    )
    await state.set_state(PurchaseStates.entering_username)

    await callback.message.edit_text(
        "📝 لطفاً یک نام کاربری انگلیسی برای سرویس خود ارسال کنید.\n"
        "(فقط حروف انگلیسی، عدد و آندرلاین - بین ۳ تا ۲۰ کاراکتر)\n\n"
        "مثال: yashar",
        reply_markup=kb.username_step_keyboard(),
    )
    await callback.answer()


# ==================== مرحله ۳: دریافت یوزرنیم ====================

@router.message(PurchaseStates.entering_username, F.text)
async def receive_username(message: Message, state: FSMContext):
    username_input = message.text.strip()

    is_valid, error_msg = validate_vpn_username(username_input)
    if not is_valid:
        await message.answer(error_msg, reply_markup=kb.username_step_keyboard())
        return

    if await db.is_vpn_username_taken(username_input):
        await message.answer(
            "❌ این نام کاربری قبلاً استفاده شده. لطفاً نام دیگری انتخاب کنید.",
            reply_markup=kb.username_step_keyboard(),
        )
        return

    await state.update_data(vpn_username=username_input)
    await state.set_state(PurchaseStates.confirming_order)

    data = await state.get_data()
    traffic_text = "نامحدود" if data["plan_traffic_gb"] == 0 else f"{data['plan_traffic_gb']} گیگ"

    summary = (
        "🧾 خلاصه سفارش شما:\n\n"
        f"🖥 پنل: {data['panel_name']}\n"
        f"💎 پلن: {data['plan_title']} ({traffic_text} / {data['plan_duration_days']} روز)\n"
        f"👤 نام کاربری: {username_input}\n"
        f"💰 قیمت: {data['plan_price']:,} تومان\n\n"
        "آیا تأیید می‌کنید؟"
    )
    await message.answer(summary, reply_markup=kb.confirm_order_keyboard())


# ==================== مرحله ۴: تأیید خلاصه سفارش ====================

@router.callback_query(F.data == "confirm_order", PurchaseStates.confirming_order)
async def confirm_order(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PurchaseStates.choosing_payment_method)
    await callback.message.edit_text(
        "💳 لطفاً روش پرداخت را انتخاب کنید:",
        reply_markup=kb.payment_method_keyboard(),
    )
    await callback.answer()


# ==================== مرحله ۵: انتخاب روش پرداخت ====================

@router.callback_query(F.data == "pay:card", PurchaseStates.choosing_payment_method)
async def pay_with_card(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PurchaseStates.waiting_for_receipt)
    await callback.message.edit_text(
        "💳 لطفاً مبلغ را به شماره کارت زیر واریز کرده و سپس تصویر رسید را ارسال کنید:\n\n"
        f"شماره کارت: <code>{CARD_NUMBER}</code>\n"
        f"به نام: {CARD_HOLDER_NAME}",
        reply_markup=kb.card_payment_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "pay:wallet", PurchaseStates.choosing_payment_method)
async def pay_with_wallet(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    user = await db.get_user_by_telegram_id(callback.from_user.id)
    price = data["plan_price"]

    if user["wallet_balance"] < price:
        await callback.message.edit_text(
            f"❌ موجودی کیف پول شما ({user['wallet_balance']:,} تومان) "
            f"کافی نیست. مبلغ لازم: {price:,} تومان.",
            reply_markup=kb.insufficient_balance_keyboard(),
        )
        await callback.answer()
        return

    # کسر از موجودی
    new_balance = user["wallet_balance"] - price
    await db.update_wallet_balance(user["id"], new_balance)
    await db.add_transaction(
        user["id"], -price, "wallet_purchase",
        f"خرید سرویس {data['plan_title']} ({data['vpn_username']})",
    )

    # ساخت سرویس در PasarGuard
    await callback.message.edit_text("⏳ در حال ساخت سرویس شما، لطفاً صبر کنید...")
    try:
        service_info = await _create_vpn_service(data)
    except PasarGuardError as e:
        # برگرداندن پول در صورت خطا در ساخت سرویس
        await db.update_wallet_balance(user["id"], user["wallet_balance"])
        await db.add_transaction(
            user["id"], price, "wallet_charge",
            "برگشت وجه به دلیل خطا در ساخت سرویس",
        )
        await callback.message.edit_text(
            f"❌ متأسفانه در ساخت سرویس خطایی رخ داد. مبلغ به کیف پول شما بازگشت.\n"
            f"جزئیات خطا: {e}"
        )
        await callback.answer()
        await state.clear()
        return

    await db.create_service(
        user["id"], data["panel_id"], data["plan_id"],
        data["vpn_username"], service_info["subscription_url"],
    )

    await _send_service_to_user(bot, callback.from_user.id, data, service_info)
    await callback.answer()
    await state.clear()


# ==================== دریافت رسید کارت به کارت ====================

@router.message(PurchaseStates.waiting_for_receipt, F.photo)
async def receive_receipt(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    user = await db.get_user_by_telegram_id(message.from_user.id)
    receipt_file_id = message.photo[-1].file_id

    order_id = await db.create_order(
        user_id=user["id"],
        panel_id=data["panel_id"],
        plan_id=data["plan_id"],
        vpn_username=data["vpn_username"],
        payment_method="card_to_card",
        receipt_file_id=receipt_file_id,
    )

    await message.answer(
        "✅ رسید شما دریافت شد و برای بررسی به ادمین ارسال شد. "
        "پس از تأیید، سرویس برای شما فعال می‌شود."
    )
    await state.clear()

    # ارسال برای همه ادمین‌ها
    traffic_text = "نامحدود" if data["plan_traffic_gb"] == 0 else f"{data['plan_traffic_gb']} گیگ"
    admin_text = (
        "🧾 رسید پرداخت جدید\n\n"
        f"👤 کاربر: {message.from_user.full_name} (@{message.from_user.username})\n"
        f"🆔 آیدی عددی: {message.from_user.id}\n"
        f"🖥 پنل: {data['panel_name']}\n"
        f"💎 پلن: {data['plan_title']} ({traffic_text} / {data['plan_duration_days']} روز)\n"
        f"🔤 یوزرنیم سرویس: {data['vpn_username']}\n"
        f"💰 مبلغ: {data['plan_price']:,} تومان\n"
        f"🆔 شماره سفارش: {order_id}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_photo(
                admin_id, receipt_file_id, caption=admin_text,
                reply_markup=kb.admin_approve_keyboard(order_id),
            )
        except Exception:
            # اگر ادمین ربات را بلاک کرده یا استارت نزده، از این خطا رد شو
            continue


# ==================== تأیید/رد رسید توسط ادمین ====================

@router.callback_query(F.data.startswith("admin_approve:"))
async def admin_approve_order(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ شما دسترسی ادمین ندارید.", show_alert=True)
        return

    order_id = int(callback.data.split(":")[1])
    order = await db.get_order_by_id(order_id)

    if not order or order["status"] != "pending":
        await callback.answer("این سفارش قبلاً بررسی شده است.", show_alert=True)
        return

    plan = await db.get_plan_by_id(order["plan_id"])
    panel = await db.get_panel_by_id(order["panel_id"])
    user = await db.get_user_by_telegram_id(order["user_id"])  # توجه: در ادامه اصلاح می‌شود

    data_for_service = {
        "panel_id": order["panel_id"],
        "plan_id": order["plan_id"],
        "vpn_username": order["vpn_username"],
        "plan_traffic_gb": plan["traffic_gb"],
        "plan_duration_days": plan["duration_days"],
        "panel_name": panel["display_name"],
        "plan_title": plan["title"],
        "plan_price": plan["price"],
    }

    await callback.message.edit_caption(caption="⏳ در حال ساخت سرویس...")

    try:
        service_info = await _create_vpn_service(data_for_service)
    except PasarGuardError as e:
        await callback.message.edit_caption(
            caption=f"❌ خطا در ساخت سرویس: {e}"
        )
        await callback.answer()
        return

    await db.create_service(
        order["user_id"], order["panel_id"], order["plan_id"],
        order["vpn_username"], service_info["subscription_url"],
    )
    await db.update_order_status(order_id, "approved")
    await db.add_transaction(
        order["user_id"], plan["price"], "card_to_card",
        f"خرید سرویس {plan['title']} ({order['vpn_username']})",
    )

    # پیدا کردن آیدی عددی تلگرام کاربر برای ارسال سرویس
    telegram_id = await _resolve_telegram_id(order["user_id"])
    if telegram_id:
        await _send_service_to_user(bot, telegram_id, data_for_service, service_info)

    await callback.message.edit_caption(caption="✅ پرداخت تأیید و سرویس ساخته شد.")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_reject:"))
async def admin_reject_order(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ شما دسترسی ادمین ندارید.", show_alert=True)
        return

    order_id = int(callback.data.split(":")[1])
    order = await db.get_order_by_id(order_id)

    if not order or order["status"] != "pending":
        await callback.answer("این سفارش قبلاً بررسی شده است.", show_alert=True)
        return

    await db.update_order_status(order_id, "rejected")
    await callback.message.edit_caption(caption="❌ پرداخت رد شد.")

    telegram_id = await _resolve_telegram_id(order["user_id"])
    if telegram_id:
        try:
            await bot.send_message(
                telegram_id,
                "❌ متأسفانه رسید پرداخت شما توسط ادمین رد شد. "
                "در صورت داشتن سوال با پشتیبانی تماس بگیرید.",
            )
        except Exception:
            pass

    await callback.answer()


# ==================== دکمه بازگشت (عمومی برای کل فرآیند) ====================

@router.callback_query(F.data.startswith("back:"))
async def handle_back(callback: CallbackQuery, state: FSMContext):
    target_step = parse_back_callback(callback.data)

    if target_step == "main_menu":
        await state.clear()
        # اینجا باید به هندلر منوی اصلی پروژه وصل شود
        await callback.message.edit_text("🏠 به منوی اصلی بازگشتید.")
        await callback.answer()
        return

    data = await state.get_data()

    if target_step == "panel":
        panels = await db.get_active_panels()
        await state.set_state(PurchaseStates.choosing_panel)
        await callback.message.edit_text(
            "🖥 لطفاً یکی از پنل‌های زیر را انتخاب کنید:",
            reply_markup=kb.panels_keyboard(panels),
        )

    elif target_step == "plan":
        plans = await db.get_active_plans_by_panel(data["panel_id"])
        await state.set_state(PurchaseStates.choosing_plan)
        await callback.message.edit_text(
            f"🖥 پنل انتخابی: {data['panel_name']}\n\n"
            "💎 لطفاً یکی از پلن‌های زیر را انتخاب کنید:",
            reply_markup=kb.plans_keyboard(plans),
        )

    elif target_step == "username":
        await state.set_state(PurchaseStates.entering_username)
        await callback.message.edit_text(
            "📝 لطفاً یک نام کاربری انگلیسی برای سرویس خود ارسال کنید.\n"
            "(فقط حروف انگلیسی، عدد و آندرلاین - بین ۳ تا ۲۰ کاراکتر)",
            reply_markup=kb.username_step_keyboard(),
        )

    elif target_step == "confirm":
        traffic_text = "نامحدود" if data["plan_traffic_gb"] == 0 else f"{data['plan_traffic_gb']} گیگ"
        await state.set_state(PurchaseStates.confirming_order)
        summary = (
            "🧾 خلاصه سفارش شما:\n\n"
            f"🖥 پنل: {data['panel_name']}\n"
            f"💎 پلن: {data['plan_title']} ({traffic_text} / {data['plan_duration_days']} روز)\n"
            f"👤 نام کاربری: {data['vpn_username']}\n"
            f"💰 قیمت: {data['plan_price']:,} تومان\n\n"
            "آیا تأیید می‌کنید؟"
        )
        await callback.message.edit_text(summary, reply_markup=kb.confirm_order_keyboard())

    elif target_step == "payment_method":
        await state.set_state(PurchaseStates.choosing_payment_method)
        await callback.message.edit_text(
            "💳 لطفاً روش پرداخت را انتخاب کنید:",
            reply_markup=kb.payment_method_keyboard(),
        )

    await callback.answer()


# ==================== توابع کمکی داخلی ====================

async def _create_vpn_service(data: dict) -> dict:
    """ساخت سرویس در PasarGuard بر اساس اطلاعات پنل مربوطه."""
    panel = await db.get_panel_by_id(data["panel_id"])
    client = PasarGuardClient(panel["url"], panel["username"], panel["password"])
    return await client.create_vpn_user(
        vpn_username=data["vpn_username"],
        traffic_gb=data["plan_traffic_gb"],
        duration_days=data["plan_duration_days"],
    )


async def _send_service_to_user(bot: Bot, telegram_id: int, data: dict, service_info: dict):
    """ارسال QR کد + لینک ساب‌اسکریپشن برای کاربر."""
    import qrcode
    import io

    sub_url = service_info["subscription_url"]

    qr_img = qrcode.make(sub_url)
    buffer = io.BytesIO()
    qr_img.save(buffer, format="PNG")
    buffer.seek(0)
    buffer.name = "subscription_qr.png"

    traffic_text = "نامحدود" if data["plan_traffic_gb"] == 0 else f"{data['plan_traffic_gb']} گیگ"
    caption = (
        "🎉 سرویس شما با موفقیت ساخته شد!\n\n"
        f"🖥 پنل: {data['panel_name']}\n"
        f"💎 پلن: {data['plan_title']} ({traffic_text} / {data['plan_duration_days']} روز)\n"
        f"👤 یوزرنیم: {data['vpn_username']}\n\n"
        f"🔗 لینک ساب‌اسکریپشن:\n<code>{sub_url}</code>"
    )

    from aiogram.types import BufferedInputFile
    photo = BufferedInputFile(buffer.read(), filename="subscription_qr.png")
    await bot.send_photo(telegram_id, photo, caption=caption, parse_mode="HTML")


async def _resolve_telegram_id(internal_user_id: int) -> int | None:
    """
    تبدیل id داخلی جدول users به آیدی عددی تلگرام.
    """
    import aiosqlite
    from bot.database.models import DB_PATH

    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT telegram_id FROM users WHERE id = ?", (internal_user_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None
