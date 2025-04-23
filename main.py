import logging
import aiohttp
import matplotlib.pyplot as plt
import io
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes, JobQueue
)
from datetime import datetime
import asyncio

# ✅ Tu token visible
TOKEN = "7804851171:AAEp5TCO3e_-RsWSwGnyaHVpuZU5XA3KQC4"
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

ALTCOINS = ["binancecoin", "solana", "cardano", "ripple"]  # BNB, SOL, ADA, XRP

# === FUNCIONES DE DATOS Y RIESGO ===

async def fetch_btc_data():
    url = "https://api.coingecko.com/api/v3/coins/bitcoin?localization=false&tickers=false&market_data=true"
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

# === FUNCIONES DE RADAR ===

async def fetch_altcoin_data(coin):
    url = f"https://api.coingecko.com/api/v3/coins/{coin}?localization=false&tickers=false&market_data=true"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            market = data["market_data"]
            return {
                "name": data["name"],
                "price": market["current_price"]["usd"],
                "change_24h": market["price_change_percentage_24h_in_currency"]["usd"],
                "change_7d": market["price_change_percentage_7d_in_currency"]["usd"],
                "low_24h": market["low_24h"]["usd"],
                "high_24h": market["high_24h"]["usd"]
            }

async def radar_oportunidades(context_or_update, context=None):
    if isinstance(context_or_update, Update):
        chat_id = context_or_update.callback_query.message.chat_id
        await context_or_update.callback_query.message.reply_text("📡 Buscando oportunidades, un momento...")
    else:
        chat_id = context_or_update.job.chat_id
        context = context_or_update

    oportunidades = []
    for coin in ALTCOINS:
        data = await fetch_altcoin_data(coin)
        confianza = "✅ Alta" if data["change_7d"] > 0 else "⚠️ Baja"
        movimiento_rel = data["high_24h"] - data["low_24h"]
        if data["change_24h"] < -2:
            oportunidades.append(f"🔍 {data['name']}\n"
                                 f"💵 Precio: ${data['price']:.2f}\n"
                                 f"📉 24h: {data['change_24h']:.2f}%\n"
                                 f"📈 7d: {data['change_7d']:.2f}%\n"
                                 f"🔄 Rango: {movimiento_rel:.2f}\n"
                                 f"🔐 Confianza: {confianza}")

    if oportunidades:
        await context.bot.send_message(chat_id=chat_id, text="📡 *Oportunidades detectadas:*\n\n" + "\n\n".join(oportunidades), parse_mode="Markdown")
    else:
        await context.bot.send_message(chat_id=chat_id, text="✅ No se detectaron oportunidades relevantes ahora.")

# === FUNCIONES AUTOMÁTICAS Y COMANDOS ===

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

async def riesgo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    data = await fetch_btc_data()
    price = data["price"]
    price_24h = price - data["price_24h"]
    avg_7d_pct = data["avg_7d"]
    high = data["high"]
    low = data["low"]
    risk = calculate_risk(price, price_24h, avg_7d_pct, high, low)
    color = RISK_COLORS[risk]
    text = f"⚠️ *Riesgo BTC actual*: {risk}/10 {color}\n💵 Precio: ${price:,.2f}"
    await context.bot.send_message(chat_id=user_id, text=text, parse_mode="Markdown")

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
        text=(f"📊 *Resumen Diario BTC*\n💵 Precio: ${price:,.2f}\n"
              f"📉 Variación 24h: {change_24h:.2f}%\n"
              f"⚠️ Riesgo: {risk}/10 {color}"),
        parse_mode="Markdown"
    )

# === MENÚ Y BOTONES ===

async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    night_mode = user_settings.get(user_id, {}).get("night_mode", False)
    estado = "✅ Activado" if night_mode else "❌ Desactivado"

    keyboard = [
        [InlineKeyboardButton("📉 Riesgo ahora", callback_data="riesgo")],
        [InlineKeyboardButton("📡 Radar de Oportunidades", callback_data="radar")],
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
    elif query.data == "radar":
        await radar_oportunidades(update, context)
    elif query.data == "toggle_night":
        current = user_settings[user_id]["night_mode"]
        user_settings[user_id]["night_mode"] = not current
        estado = "✅ Activado" if not current else "❌ Desactivado"
        await query.message.reply_text(
            text=f"🌙 Modo nocturno: {estado}\nLas notificaciones {'NO ' if not current else ''}se enviarán de noche.",
        )
    elif query.data == "parar":
        await stop(update, context)

# === COMANDOS ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    user_settings.setdefault(user_id, {"night_mode": False})
    user_history.setdefault(user_id, [])

    context.job_queue.run_repeating(notify_risk, interval=3600, first=5, chat_id=user_id, name=f"risk_{user_id}")
    context.job_queue.run_daily(daily_summary, time=datetime.strptime("12:00", "%H:%M").time(), chat_id=user_id, name=f"summary_{user_id}")
    context.job_queue.run_repeating(radar_oportunidades, interval=3600, first=10, chat_id=user_id, name=f"radar_{user_id}")

    await update.message.reply_text("✅ Notificaciones activadas.")
    await show_menu(update, context)

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    for name in [f"risk_{user_id}", f"summary_{user_id}", f"radar_{user_id}"]:
        for job in context.job_queue.get_jobs_by_name(name):
            job.schedule_removal()
    user_last_risk.pop(user_id, None)
    await update.message.reply_text("🛑 Notificaciones detenidas.")

# === MAIN ===

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("parar", stop))
    app.add_handler(CommandHandler("riesgo", riesgo))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
