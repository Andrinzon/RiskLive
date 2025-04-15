import logging
import aiohttp
import matplotlib.pyplot as plt
import io
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes, JobQueue
)
from datetime import datetime

TOKEN = "TU_TOKEN_AQUI"
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

# 📡 Obtener datos históricos de BTC desde 2016
async def fetch_btc_historical_data():
    url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=max"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            prices = data['prices']
            return prices  # Lista de precios [(timestamp, price), ...]

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

def is_night_time():
    now = datetime.utcnow().hour
    return 0 <= now < 8

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

    # Guardar historial para gráficas
    user_history.setdefault(user_id, []).append({
        "time": datetime.utcnow().strftime("%H:%M"),
        "price": price,
        "risk": risk
    })
    if len(user_history[user_id]) > 24:
        user_history[user_id] = user_history[user_id][-24:]

    if risk != previous_risk:
        user_last_risk[user_id] = risk
        color = RISK_COLORS[risk]
        await context.bot.send_message(
            chat_id=user_id,
            text=f"⚠️ *Riesgo BTC*: {risk}/10 {color}\n💵 *Precio actual*: ${price:,.2f}",
            parse_mode="Markdown"
        )

# 🧭 Función para generar el gráfico
async def mostrar_grafico(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.message.chat_id
    history = user_history.get(user_id, [])

    if not history:
        await update.callback_query.message.reply_text("❗ Aún no hay datos suficientes para generar la gráfica.")
        return

    horas = [d["time"] for d in history]
    precios = [d["price"] for d in history]
    riesgos = [d["risk"] for d in history]

    fig, ax1 = plt.subplots(figsize=(10, 5))
    ax1.set_xlabel("Hora")
    ax1.set_ylabel("Riesgo", color="red")
    ax1.plot(horas, riesgos, color="red", marker='o')
    ax1.tick_params(axis='y', labelcolor="red")
    ax1.set_ylim(1, 10)

    ax2 = ax1.twinx()
    ax2.set_ylabel("Precio BTC", color="blue")
    ax2.plot(horas, precios, color="blue", marker='x', linestyle='--')
    ax2.tick_params(axis='y', labelcolor="blue")

    plt.title("📈 Gráfico de Precio y Riesgo BTC")
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    buf.name = "grafico.png"

    await context.bot.send_photo(chat_id=user_id, photo=InputFile(buf))

# 🟢 Comando para ver la gráfica
async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    night_mode = user_settings.get(user_id, {}).get("night_mode", False)
    estado = "✅ Activado" if night_mode else "❌ Desactivado"

    keyboard = [
        [InlineKeyboardButton("📉 Riesgo ahora", callback_data="riesgo")],
        [InlineKeyboardButton("📊 Ver gráfico", callback_data="grafico")],
        [InlineKeyboardButton(f"🌙 Modo nocturno: {estado}", callback_data="toggle_night")],
        [InlineKeyboardButton("🛑 Detener notificaciones", callback_data="parar")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📋 Menú de opciones:", reply_markup=reply_markup)

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
