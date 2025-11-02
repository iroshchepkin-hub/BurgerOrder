import aiogram
import asyncio
from aiogram import Dispatcher, Bot, types
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import (InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton)
from aiogram.types import WebAppInfo
import sqlite3
import json
from datetime import datetime
import os
from dotenv import load_dotenv
from aiohttp import web
import asyncio
import threading

async def handle(request):
    return web.Response(text="Bot is running!")

def run_server():
    app = web.Application()
    app.add_routes([web.get('/', handle)])
    web.run_app(app, port=8000)

threading.Thread(target=run_server).start()

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")



bot = Bot(BOT_TOKEN)
dp = Dispatcher()

conn = sqlite3.connect('cart.db')
cur = conn.cursor()
cur.execute('''CREATE TABLE IF NOT EXISTS cart_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    product_id TEXT, 
    name TEXT NOT NULL,
    price REAL NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
''')


cur.execute('''CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, 
user_id INTEGER NOT NULL,
order_details TEXT,
total_price REAL NOT NULL,
phone_number TEXT NOT NULL,
order_date TIMESTAMP NOT NULL,    
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);''')

conn.commit()
conn.close()

ADMIN_ID = 5497236290



@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    kb = [
        [KeyboardButton(text='Меню🍔', web_app=WebAppInfo(
            url="https://iroshchepkin-hub.github.io/BurgerOrder/menu.html"))],
        [KeyboardButton(text='Напитки🥤', web_app=WebAppInfo(
            url="https://iroshchepkin-hub.github.io/BurgerOrder/beverages.html")),
         KeyboardButton(text = 'Корзина🛒')]
    ]
    keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=False)

    await message.answer("👋 Привет! Здесь ты можешь быстро заказать самые вкусные бургеры!\nОткрывай меню на клавиатуре 👇", reply_markup=keyboard)

def add_item(user_id, product_id, name, price, quantity):
    conn = sqlite3.connect('cart.db')
    cur = conn.cursor()

    cur.execute("SELECT id, quantity FROM cart_items WHERE user_id = ? AND product_id = ?",
                    (user_id, product_id))
    existing_item = cur.fetchone()

    if existing_item:
        new_quantity = existing_item[1] + quantity
        cur.execute("UPDATE cart_items SET quantity = ? WHERE id = ?",
                        (new_quantity, existing_item[0]))
    else:
        cur.execute("""
                    INSERT INTO cart_items (user_id, product_id, name, price, quantity)
                    VALUES (?, ?, ?, ?, ?)
                    """, (user_id, product_id, name, price, quantity))

    conn.commit()
    conn.close()

class OrderForm(StatesGroup):
    waiting_for_address = State()
    waiting_for_phone = State()


@dp.message(lambda msg: msg.text == 'Корзина🛒')
async def show_cart(message: types.Message):
    conn = sqlite3.connect('cart.db')
    cur = conn.cursor()

    cur.execute("SELECT id, name, price, quantity FROM cart_items WHERE user_id = ?", (message.from_user.id,))
    items = cur.fetchall()
    conn.close()

    if not items:
        await message.answer("🛒Ваша корзина пуста")
        return
    else:
        text = '🛒<b>Ваша корзина</b>\n\n'
        total = 0

        for item_id, name,price,quantity in items:
            summ = price * quantity
            total+=summ
            text += f'{name} - {quantity} * {price} = {summ}\n\n\n'



        clear_keyboard = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="🧹 Очистить корзину", callback_data="clear_cart")],
                [types.InlineKeyboardButton(text = '✅Оформить заказ', callback_data="make_order")],
            ]
        )
        await message.answer(text, parse_mode='HTML')
        await message.answer(f"<b>Итого:</b> {total} ₽", parse_mode="HTML", reply_markup=clear_keyboard)

@dp.callback_query(lambda c: c.data == "make_order")
async def make_order(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    conn = sqlite3.connect('cart.db')
    cur = conn.cursor()
    cur.execute('SELECT name, quantity, price FROM cart_items WHERE user_id = ?', (user_id,))
    items = cur.fetchall()

    if not items:
        await callback.answer('🛒 Ваша корзина пуста')
        conn.close()
        return

    order_text = ""
    total = 0
    for name, quantity, price in items:
        order_text += f"{name} — {quantity} шт × {price} ₽ = {price * quantity} ₽\n"
        total += price * quantity

    if total < 1000:
        await callback.answer("Недостаточная сумма для заказа. Пожалуйста, доберите товаров до 1000₽!")
        conn.close()
        return

    await callback.message.answer(
        f"Ваш заказ:\n\n{order_text}\n<b>Итого:</b> {total} ₽\n\n📍 Введите адрес доставки:",
        parse_mode='HTML'
    )
    await state.update_data(order_text=order_text, total=total)
    await state.set_state(OrderForm.waiting_for_address)
    conn.close()


@dp.message(OrderForm.waiting_for_address)
async def get_address(message: types.Message, state: FSMContext):
    await state.update_data(address=message.text)
    await message.answer("📞 Теперь введите номер телефона:")
    await state.set_state(OrderForm.waiting_for_phone)


@dp.message(OrderForm.waiting_for_phone)
async def get_phone(message: types.Message, state: FSMContext):
    data = await state.get_data()
    address = data["address"]
    order_text = data["order_text"]
    total = data["total"]
    phone = message.text
    user_id = message.from_user.id

    conn = sqlite3.connect('cart.db')
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO orders (user_id, order_details, total_price, phone_number, order_date) VALUES (?, ?, ?, ?, ?)",
        (user_id, order_text + f"\nАдрес: {address}", total, phone, datetime.now())
    )
    conn.commit()
    conn.close()

    conn = sqlite3.connect('cart.db')
    cur = conn.cursor()
    cur.execute("DELETE FROM cart_items WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

    payment = types.InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text = 'Оплатить', url = 'https://www.sberbank.com/promo/sberpay')]])



    await message.answer(
        f"✅ Заказ оформлен!\n\n📍 Адрес: {address}\n📞 Телефон: {phone}\n💰 Сумма: {total} ₽\n\nСпасибо за заказ! 🚀", reply_markup=payment
    )
    await state.clear()

@dp.callback_query(lambda c: c.data == "clear_cart")
async def clear_cart(callback: types.CallbackQuery):
    user_id = callback.from_user.id

    conn = sqlite3.connect('cart.db')
    cur = conn.cursor()
    cur.execute("DELETE FROM cart_items WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

    await callback.answer("🧹 Корзина очищена.")
    await callback.message.answer("Ваша корзина теперь пуста.")


@dp.message(lambda msg: getattr(msg, "web_app_data", None))
async def add_webapp_item(message: types.Message):
    try:
        raw_data = message.web_app_data.data


        item = json.loads(raw_data)
        name = item.get('name')
        price = int(item.get('price', 0))
        user_id = message.from_user.id
        product_id = name.lower()

        if not name or price <= 0:
            await message.answer("❌ Неверные данные товара.")
            return

        add_item(user_id, product_id, name, price, 1)


    except Exception as e:
        print(f"[ERROR] WebApp обработка: {e}")
        await message.answer("⚠️ Ошибка при добавлении товара.")


@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    """Главное меню админа"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас нет доступа к админ-панели.")
        return

    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="📦 Все заказы", callback_data="view_orders")],
            [types.InlineKeyboardButton(text="🧹 Очистить все заказы", callback_data="clear_orders")]
        ]
    )

    await message.answer("👨‍💼 Панель администратора", reply_markup=keyboard)


@dp.callback_query(lambda c: c.data == "view_orders")
async def view_orders(callback: types.CallbackQuery):
    """Просмотр всех заказов"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа.")
        return

    conn = sqlite3.connect('cart.db')
    cur = conn.cursor()
    cur.execute("SELECT id, user_id, order_details, total_price, phone_number, order_date FROM orders ORDER BY order_date DESC LIMIT 20")
    orders = cur.fetchall()
    conn.close()

    if not orders:
        await callback.message.answer("📭 Заказов пока нет.")
        return

    for order in orders:
        order_id, user_id, details, total, phone, date = order
        text = (
            f"🆔 <b>Заказ №{order_id}</b>\n"
            f"👤 User ID: {user_id}\n"
            f"📞 Телефон: {phone}\n"
            f"📅 Дата: {date}\n"
            f"💰 Сумма: {total} ₽\n"
            f"📝 Детали:\n{details}\n"
        )

        # Кнопка удаления конкретного заказа
        keyboard = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text=f"❌ Удалить заказ №{order_id}", callback_data=f"delete_order_{order_id}")]
            ]
        )

        await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@dp.callback_query(lambda c: c.data.startswith("delete_order_"))
async def delete_order(callback: types.CallbackQuery):
    """Удаление конкретного заказа"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа.")
        return

    # Извлекаем ID заказа из callback_data
    order_id = int(callback.data.split("_")[2])

    conn = sqlite3.connect('cart.db')
    cur = conn.cursor()
    cur.execute("DELETE FROM orders WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()

    await callback.message.edit_text(f"🗑 Заказ №{order_id} успешно удалён ✅")
    await callback.answer("Удалено.")


@dp.callback_query(lambda c: c.data == "clear_orders")
async def clear_all_orders(callback: types.CallbackQuery):
    """Удаление всех заказов"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа.")
        return

    conn = sqlite3.connect('cart.db')
    cur = conn.cursor()
    cur.execute("DELETE FROM orders")
    conn.commit()
    conn.close()

    await callback.message.answer("🧹 Все заказы удалены.")



async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
