import logging
import aiohttp
import io
import matplotlib.pyplot as plt
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes, JobQueue
)
from datetime import datetime

TOKEN = "7463495309:AAFnWbMN8eYShhTt9UvygCD0TAFED-LuJhM"  # <-- Reemplaza con tu token real
ATH = 105000
user_last_risk = {}
user_settings = {}
user_history = {}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RISK_COLORS = {
    1: "🟢", 2: "🟢", 3: "🟢",
    4: "🟡", 5: "🟡", 6: "🟡",
    7: "🟠", 8: "🟠",
    9: "🔴", 10: "🔴"
}

# 📡 Obtener datos de BTC
async def fetch_btc_data():
    url = "https://api.coingecko.com/api/v3/coins/bitcoin?localization=false&tickers=false&market_data=true&community_data=false&developer_data=false&sparkline=false"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            market_data = data["market_data"]
            return {
                "price": market_data["current_price"]["usd"],
                "price_24h": market_data["price_change_24h_in_currency"]["usd"],
                "avg_7d": market_data["price_change_percentage_7d_in_currency"]["usd"],
                "high": market_data["high_24h"]["usd"],
                "low": market_data["low_24h"]["usd"]
            }

# 🔢 Lógica de riesgo
def calculate_risk(price, price_24h, avg_7d_pct, high, low):
    risk = 0
    change_pct = ((price - price_24h) / price_24h) * 100
    avg_7d_price = price / (1 + (avg_7d_pct / 100))

    if price > avg_7d_price:
        risk += 1
    else:
        risk -= 1

    if change_pct >= 5:
        risk += 2
    elif change_pct >= 2:
        risk += 1
    elif change_pct <= -5:
        risk -= 2
    elif change_pct <= -2:
        risk -= 1

    perc_ath = (price / ATH) * 100
    if perc_ath >= 90:
        risk += 3
    elif perc_ath >= 70:
        risk += 2
    elif perc_ath >= 50:
        risk += 1

    if (high - low) / price > 0.1:
        risk += 1

    return max(1, min(10, risk + 5))

# 🕒 Verifica si estamos en horario nocturno
def is_night_time():
    now = datetime.utcnow().hour
    return 0 <= now < 8

# 🔔 Notificación automática
async def notify_risk(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.chat_id
    settings = user_settings.get(user_id, {"night_mode": False})

    if settings.get("night_mode") and is_night_time():
        return

    data = await fetch_btc_data()
    price = data["price"]
    price_24h = price - data["price_24h"]
    avg_7d_pct = data["avg_7d"]
    high = data["high"]
    low = data["low"]

    risk = calculate_risk(price, price_24h, avg_7d_pct, high, low)
    previous_risk = user_last_risk.get(user_id)

    if risk != previous_risk:
        user_last_risk[user_id] = risk
        user_history.setdefault(user_id, []).append({
            "time": datetime.utcnow().strftime("%H:%M"),
            "price": price,
            "risk": risk
        })

        color = RISK_COLORS[risk]
        await context.bot.send_message(
            chat_id=user_id,
            text=f"⚠️ *Riesgo BTC*: {risk}/10 {color}\n💵 *Precio actual*: ${price:,.2f}",
            parse_mode="Markdown"
        )

# 🗓️ Resumen diario
async def daily_summary(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.chat_id
    data = await fetch_btc_data()
    price = data["price"]
    change_24h = ((price - (price - data["price_24h"])) / (price - data["price_24h"])) * 100
    price_24h = price - data["price_24h"]
    avg_7d_pct = data["avg_7d"]
    high = data["high"]
    low = data["low"]
    risk = calculate_risk(price, price_24h, avg_7d_pct, high, low)
    color = RISK_COLORS[risk]

    await context.bot.send_message(
        chat_id=user_id,
        text=(f"📊 *Resumen Diario BTC*\n"
              f"💵 Precio: ${price:,.2f}\n"
              f"📉 Variación 24h: {change_24h:.2f}%\n"
              f"⚠️ Riesgo: {risk}/10 {color}"),
        parse_mode="Markdown"
    )

# 📈 Mostrar gráfico
async def mostrar_grafico(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.message.chat_id
    history = user_history.get(user_id, [])

    if len(history) < 2:
        await query.message.reply_text("❗ Aún no hay datos suficientes para generar la gráfica (se necesitan al menos 2 puntos).")
        return

    generating_msg = await query.message.reply_text("⌛ Generando gráfica...")

    horas = [d["time"] for d in history]
    precios = [d["price"] for d in history]
    riesgos = [d["risk"] for d in history]

    fig, ax1 = plt.subplots(figsize=(10, 5))
    ax1.set_xlabel("Hora")
    ax1.set_ylabel("Riesgo", color="red")
    ax1.plot(horas, riesgos, color="red", marker='o', linestyle='-', label="Riesgo")
    ax1.tick_params(axis='y', labelcolor="red")
    ax1.set_ylim(1, 10)

    ax2 = ax1.twinx()
    ax2.set_ylabel("Precio BTC", color="blue")
    ax2.plot(horas, precios, color="blue", marker='x', linestyle='--', label="Precio BTC")
    ax2.tick_params(axis='y', labelcolor="blue")

    plt.title("📈 Gráfico de Precio y Riesgo BTC")
    fig.autofmt_xdate(rotation=45)
    plt.grid(True)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    buf.name = "grafico.png"

    await generating_msg.delete()
    await context.bot.send_photo(chat_id=user_id, photo=InputFile(buf))

# 🟢 Comandos
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    await update.message.reply_text("🔔 Comenzaré a notificarte sobre el riesgo de BTC cada hora (si cambia).")
    user_settings.setdefault(user_id, {"night_mode": False})
    user_history.setdefault(user_id, [])

    context.job_queue.run_repeating(notify_risk, interval=3600, first=5, chat_id=user_id, name=f"risk_{user_id}")
    context.job_queue.run_daily(daily_summary, time=datetime.strptime("12:00", "%H:%M").time(), chat_id=user_id, name=f"summary_{user_id}")
    await show_menu(update, context)

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    for job in context.job_queue.get_jobs_by_name(f"risk_{user_id}"):
        job.schedule_removal()
    for job in context.job_queue.get_jobs_by_name(f"summary_{user_id}"):
        job.schedule_removal()
    user_last_risk.pop(user_id, None)
    await update.message.reply_text("🛑 Notificaciones detenidas.")

async def riesgo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id if update.message else update.callback_query.message.chat.id

    data = await fetch_btc_data()
    price = data["price"]
    price_24h = price - data["price_24h"]
    avg_7d_pct = data["avg_7d"]
    high = data["high"]
    low = data["low"]
    risk = calculate_risk(price, price_24h, avg_7d_pct, high, low)
    color = RISK_COLORS[risk]

    user_history.setdefault(user_id, []).append({
        "time": datetime.utcnow().strftime("%H:%M"),
        "price": price,
        "risk": risk
    })

    await context.bot.send_message(chat_id=user_id, text=f"⚠️ *Riesgo BTC actual*: {risk}/10 {color}\n💵 Precio: ${price:,.2f}", parse_mode="Markdown")

# 🧭 Menú
async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    night_mode = user_settings.get(user_id, {}).get("night_mode", False)
    estado = "✅ Activado" if night_mode else "❌ Desactivado"

    keyboard = [
        [InlineKeyboardButton("📉 Riesgo ahora", callback_data="riesgo")],
        [InlineKeyboardButton("📈 Ver gráfica", callback_data="grafico")],
        [InlineKeyboardButton(f"🌙 Modo nocturno: {estado}", callback_data="toggle_night")],
        [InlineKeyboardButton("🛑 Detener notificaciones", callback_data="parar")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📋 Menú de opciones:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.message.chat_id

    if query.data == "riesgo":
        await riesgo(update, context)
    elif query.data == "grafico":
        await mostrar_grafico(update, context)
    elif query.data == "toggle_night":
        current = user_settings[user_id]["night_mode"]
        user_settings[user_id]["night_mode"] = not current
        estado = "✅ Activado" if not current else "❌ Desactivado"
        await query.message.reply_text(text=f"🌙 Modo nocturno: {estado}\nLas notificaciones {'NO ' if not current else ''}se enviarán de noche.")
    elif query.data == "parar":
        await stop(update, context)

# 🚀 Lanzar bot
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("parar", stop))
    app.add_handler(CommandHandler("riesgo", riesgo))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
