import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import aiosqlite
import aiohttp

# ================= НАСТРОЙКИ =================
TOKEN = "8751576623:AAGjEv-nocBjEk1hnn_B8bd6sXS1GGL59iQ"

RAPIDAPI_KEY = "9235f8d305msh274f22d075849e6p1f0e64jsn8e8aaf457c0f"

PAYMENT_WALLET = "Кошелёк Dushanbe City: +992 918 68 67 24\n\nПосле оплаты пришлите скриншот и ID заказа"

PACKAGES = {
    "60": {"uc": 60, "price": 10, "name": "60 UC"},
    "300": {"uc": 300, "price": 50, "name": "300 UC"},
    "600": {"uc": 600, "price": 95, "name": "600 UC"},
    "1500": {"uc": 1500, "price": 230, "name": "1500 UC"},
    "3000": {"uc": 3000, "price": 450, "name": "3000 UC"},
}

ADMIN_ID = 647070744

# ============================================

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

class OrderForm(StatesGroup):
    choosing_package = State()
    entering_uid = State()
    confirming = State()

# ================= БАЗА ДАННЫХ =================
async def init_db():
    async with aiosqlite.connect("orders.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                uc INTEGER,
                price INTEGER,
                uid TEXT,
                nickname TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT
            )
        """)
        await db.commit()

# ================= СТАТУСЫ =================
STATUS_TEXT = {
    "pending": "⏳ Ожидает оплаты",
    "paid": "✅ Оплачен",
    "completed": "🚀 UC пополнен",
    "cancelled": "❌ Отменён"
}

# ================= ПОИСК НИКА =================
async def get_pubg_nickname(uid: str) -> str | None:
    url = f"https://check-id-game.p.rapidapi.com/api/rapid_api/cekpubgmobile/{uid}"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "check-id-game.p.rapidapi.com",
        "Content-Type": "application/json"
    }
    try:
        async with asyncio.timeout(7):
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("success") and isinstance(data.get("data"), dict):
                            return data["data"].get("username")
                    return None
    except Exception:
        return None

# ================= КЛАВИАТУРЫ =================
def main_menu(user_id: int = None):
    if user_id == ADMIN_ID:
        kb = [
            [types.KeyboardButton(text="📋 Активные заказы")],
            [types.KeyboardButton(text="👥 Покупатели")],
            [types.KeyboardButton(text="📊 Статистика")],
            [types.KeyboardButton(text="📥 Экспорт заказов")],
            [types.KeyboardButton(text="🚫 Черный список")]
        ]
    else:
        kb = [
            [types.KeyboardButton(text="🛒 Купить UC")],
            [types.KeyboardButton(text="📜 Мои заказы")],
            [types.KeyboardButton(text="💬 Поддержка")]
        ]
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def packages_keyboard():
    kb = [[types.InlineKeyboardButton(
        text=f"{info['name']} — {info['price']} TJS",
        callback_data=f"package_{uc}"
    )] for uc, info in PACKAGES.items()]
    return types.InlineKeyboardMarkup(inline_keyboard=kb)

def admin_order_keyboard(order_id: int):
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ UC пополнен", callback_data=f"admin_complete_{order_id}")],
        [types.InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_cancel_{order_id}")]
    ])

# ================= ХЕНДЛЕРЫ =================
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Добро пожаловать в магазин UC для PUBG Mobile!\n\n"
        "Выбирай пакет и пополняй аккаунт быстро и безопасно.",
        reply_markup=main_menu(message.from_user.id)
    )

@dp.message(F.text == "🛒 Купить UC")
async def buy_uc(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Выберите пакет UC:", reply_markup=packages_keyboard())
    await state.set_state(OrderForm.choosing_package)

@dp.message(F.text == "📜 Мои заказы")
async def my_orders(message: types.Message):
    async with aiosqlite.connect("orders.db") as db:
        cursor = await db.execute(
            "SELECT id, uc, price, status, created_at FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT 15",
            (message.from_user.id,)
        )
        rows = await cursor.fetchall()

    if not rows:
        await message.answer("У вас пока нет заказов.")
        return

    text = "📜 <b>Ваши заказы:</b>\n\n"
    for row in rows:
        oid, uc, price, status, created = row
        st = STATUS_TEXT.get(status, status)
        date = created[:16] if created else "—"
        text += f"<b>#{oid}</b> — {uc} UC — {price} TJS\n   {st} • {date}\n\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "💬 Поддержка")
async def support(message: types.Message):
    await message.answer("Напишите мне в личку @poligon_pubg или просто сюда — я отвечу.")

# ================= АДМИН ПАНЕЛЬ =================
@dp.message(F.text == "📋 Активные заказы")
async def show_active_orders(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    async with aiosqlite.connect("orders.db") as db:
        cursor = await db.execute("""
            SELECT id, username, uid, uc, price, status, created_at 
            FROM orders WHERE status IN ('pending', 'paid') ORDER BY id DESC
        """)
        rows = await cursor.fetchall()
    if not rows:
        await message.answer("Активных заказов нет.")
        return
    text = "📋 <b>Активные заказы:</b>\n\n"
    for row in rows:
        text += f"<b>#{row[0]}</b> | @{row[1] or '—'} | UID: {row[2]}\n{row[3]} UC — {row[4]} TJS | {STATUS_TEXT.get(row[5], row[5])}\n{row[6][:16]}\n\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "👥 Покупатели")
async def show_buyers(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    async with aiosqlite.connect("orders.db") as db:
        cursor = await db.execute("""
            SELECT username, COUNT(*) as purchases, SUM(price) as total 
            FROM orders WHERE status = 'completed' GROUP BY user_id ORDER BY purchases DESC
        """)
        rows = await cursor.fetchall()
    if not rows:
        await message.answer("Покупателей пока нет.")
        return
    text = "👥 <b>Покупатели:</b>\n\n"
    for username, purchases, total in rows:
        text += f"@{username or '—'} | Покупок: {purchases} | На сумму: {total or 0} TJS\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "📊 Статистика")
async def show_statistics(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    async with aiosqlite.connect("orders.db") as db:
        cursor = await db.execute("SELECT COUNT(*) as total, SUM(price) as revenue FROM orders WHERE status = 'completed'")
        completed = await cursor.fetchone()
        cursor = await db.execute("SELECT COUNT(*) FROM orders WHERE status = 'pending'")
        pending = (await cursor.fetchone())[0]
    text = f"📊 <b>Статистика:</b>\n\nУспешных заказов: {completed[0]}\nВыручка: {completed[1] or 0} TJS\nОжидают оплаты: {pending}"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "📥 Экспорт заказов")
async def export_orders(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    async with aiosqlite.connect("orders.db") as db:
        cursor = await db.execute("SELECT * FROM orders ORDER BY id DESC")
        rows = await cursor.fetchall()
    if not rows:
        await message.answer("Заказов нет.")
        return
    text = "📥 <b>Все заказы:</b>\n\n"
    for row in rows:
        text += f"#{row[0]} | @{row[2]} | UID: {row[5]} | {row[3]} UC — {row[4]} TJS | {STATUS_TEXT.get(row[7], row[7])}\n"
    await message.answer(text[:4000], parse_mode="HTML")

@dp.message(F.text == "🚫 Черный список")
async def show_blacklist(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("🚫 Черный список — в разработке (будет в следующей версии)")

# ================= АДМИН: КНОПКИ ПОД ЗАКАЗОМ =================
@dp.callback_query(F.data.startswith("admin_"))
async def admin_action(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    try:
        parts = callback.data.split("_")
        action = parts[1]
        order_id = int(parts[2])

        new_status = {
            "complete": "completed",
            "cancel": "cancelled"
        }[action]

        async with aiosqlite.connect("orders.db") as db:
            cursor = await db.execute("SELECT user_id FROM orders WHERE id = ?", (order_id,))
            row = await cursor.fetchone()
            user_id = row[0] if row else None

            await db.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, order_id))
            await db.commit()

        status_text = STATUS_TEXT.get(new_status, new_status)

        await callback.message.edit_text(
            f"{callback.message.text}\n\n✅ <b>Статус изменён:</b> {status_text}",
            reply_markup=None
        )

        if user_id:
            if new_status == "completed":
                await bot.send_message(user_id, f"🚀 <b>Ваш заказ #{order_id} успешно пополнен!</b>\n\nUC уже на вашем аккаунте. Приятной игры!", parse_mode="HTML")
            elif new_status == "cancelled":
                await bot.send_message(user_id, f"❌ <b>Ваш заказ #{order_id} отменён.</b>\n\nЕсли это ошибка — напишите в поддержку.", parse_mode="HTML")

        await callback.answer(f"✅ Заказ #{order_id} → {status_text}")

    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)

# ================= ОСТАЛЬНЫЕ ХЕНДЛЕРЫ =================
@dp.callback_query(F.data.startswith("package_"))
async def choose_package(callback: types.CallbackQuery, state: FSMContext):
    uc_key = callback.data.split("_")[1]
    package = PACKAGES[uc_key]
    await state.update_data(package=package)
    await callback.message.edit_text(
        f"✅ Вы выбрали: <b>{package['name']}</b> — {package['price']} TJS\n\n"
        "Теперь отправьте ваш **Player ID (UID)** из PUBG Mobile.",
        parse_mode="HTML"
    )
    await state.set_state(OrderForm.entering_uid)
    await callback.answer()

@dp.message(OrderForm.entering_uid)
async def process_uid(message: types.Message, state: FSMContext):
    raw = message.text.strip()
    uid = ''.join(c for c in raw if c.isdigit())
    if not uid or len(uid) < 8:
        await message.answer("❌ Player ID должен состоять только из цифр и быть не короче 8 символов.")
        return

    await message.answer("🔍 Ищу ник в игре...")
    nickname = await get_pubg_nickname(uid)
    data = await state.get_data()
    package = data["package"]

    text = f"✅ <b>Проверка заказа</b>\n\n🎮 <b>UID:</b> {uid}\n"
    if nickname:
        text += f"👤 <b>Ник в игре:</b> {nickname}\n"
    text += f"📦 <b>Пакет:</b> {package['name']}\n💰 <b>К оплате:</b> {package['price']} TJS\n\nВсё верно?"

    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ Да, всё верно", callback_data=f"confirm_{uid}_{nickname or 'no_nick'}")],
        [types.InlineKeyboardButton(text="🔄 Изменить UID", callback_data="change_uid")]
    ])

    await message.answer(text, reply_markup=kb, parse_mode="HTML")
    await state.update_data(uid=uid, nickname=nickname or "Не удалось получить")
    await state.set_state(OrderForm.confirming)

@dp.callback_query(F.data.startswith("confirm_"))
async def confirm_order(callback: types.CallbackQuery, state: FSMContext):
    try:
        _, uid, nickname_encoded = callback.data.split("_", 2)
        nickname = nickname_encoded.replace("_", " ") if nickname_encoded != "no_nick" else "Не удалось получить"

        data = await state.get_data()
        package = data["package"]

        async with aiosqlite.connect("orders.db") as db:
            await db.execute(
                """INSERT INTO orders (user_id, username, uc, price, uid, nickname, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (callback.from_user.id, callback.from_user.username or callback.from_user.first_name,
                 package["uc"], package["price"], uid, nickname, datetime.now().isoformat())
            )
            await db.commit()
            cursor = await db.execute("SELECT last_insert_rowid()")
            order_id = (await cursor.fetchone())[0]

        await callback.message.edit_text(
            f"✅ <b>Заказ #{order_id} создан!</b>\n\n"
            f"{PAYMENT_WALLET}\n\n"
            f"После оплаты пришлите скриншот + номер заказа <b>#{order_id}</b>.\n"
            f"Я сразу пополню UC через Midasbuy.",
            parse_mode="HTML"
        )

        admin_text = (
            f"🛒 <b>Новый заказ #{order_id}</b>\n\n"
            f"От: @{callback.from_user.username or 'no_username'}\n"
            f"UID: {uid}\n"
            f"Ник: {nickname}\n"
            f"Пакет: {package['name']} — {package['price']} TJS"
        )
        await bot.send_message(
            ADMIN_ID,
            admin_text,
            reply_markup=admin_order_keyboard(order_id)
        )

        await state.clear()
        await callback.answer("Заказ создан!")

    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)
        await state.clear()

@dp.callback_query(F.data == "change_uid")
async def change_uid(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🔄 Введите новый Player ID:")
    await state.set_state(OrderForm.entering_uid)
    await callback.answer()

# ================= ЗАПУСК =================
async def main():
    await init_db()
    print("🚀 Бот запущен! Версия 3.0")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())