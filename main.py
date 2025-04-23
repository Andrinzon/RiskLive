import logging
import aiohttp
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, JobQueue
import os

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID_FILE = "chat_id.txt"
ATH_BTC = 105000
ALTCOINS = ["binancecoin", "solana", "cardano", "ripple"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

user_settings = {}
user_history = {}
last_risk = {}
last_opportunities = {}

# --------- FUNCIONES PRINCIPALES ---------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    user_settings.setdefault(user_id, {"night_mode": False})
    user_history.setdefault(user_id, [])

    if context.job_queue.get_jobs_by_name(f"risk_{user_id}"):
        await update.message.reply_text("✅ Ya estás suscrito a las notificaciones.")
        await show_menu(update, context)
        return

    await update.message.reply_text("🔔 Comenzaré a notificarte sobre el riesgo de BTC cada hora (si cambia).")

    context.job_queue.run_repeating(notify_risk, interval=3600, first=5, chat_id=user_id, name=f"risk_{user_id}")
    context.job_queue.run_daily(daily_summary, time=datetime.strptime("12:00", "%H:%M").time(), chat_id=user_id, name=f"summary_{user_id}")
    context.job_queue.run_repeating(radar_auto, interval=1800, first=10, chat_id=user_id, name=f"radar_{user_id}")

    await show_menu(update, context)

async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📊 Ver riesgo actual", callback_data='riesgo')],
        [InlineKeyboardButton("📡 Radar de Oportunidades", callback_data='radar')],
        [InlineKeyboardButton("🌙 Modo Nocturno", callback_data='modo')],
        [InlineKeyboardButton("⛔ Parar notificaciones", callback_data='parar')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Elige una opción:", reply_markup=reply_markup)

async def notify_risk(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.chat_id
    if user_settings[user_id]["night_mode"]:
        now = datetime.now().time()
        if now.hour < 8 or now.hour >= 0:
            return

    async with aiohttp.ClientSession() as session:
        async with session.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd") as resp:
            data = await resp.json()
            btc_price = data["bitcoin"]["usd"]

    risk = calcular_riesgo(btc_price)
    if last_risk.get(user_id) != risk:
        last_risk[user_id] = risk
        mensaje = f"⚠️ Riesgo BTC: {risk}/10\n💰 Precio: ${btc_price:,.2f}"
        await context.bot.send_message(chat_id=user_id, text=mensaje)

def calcular_riesgo(precio):
    distancia_ath = (ATH_BTC - precio) / ATH_BTC
    if distancia_ath < 0.05:
        return 10
    elif distancia_ath < 0.1:
        return 9
    elif distancia_ath < 0.2:
        return 8
    elif distancia_ath < 0.3:
        return 7
    elif distancia_ath < 0.4:
        return 6
    elif distancia_ath < 0.5:
        return 5
    else:
        return 4

async def daily_summary(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.chat_id
    history = user_history.get(user_id, [])
    if not history:
        return
    resumen = "\n".join(history[-24:])
    await context.bot.send_message(chat_id=user_id, text=f"📈 Resumen diario de riesgo:\n\n{resumen}")

# --------- CALLBACKS ---------

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if query.data == 'riesgo':
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd") as resp:
                data = await resp.json()
                btc_price = data["bitcoin"]["usd"]
        riesgo = calcular_riesgo(btc_price)
        user_history[user_id].append(f"{datetime.now().strftime('%H:%M')} - {riesgo}/10")
        await query.edit_message_text(text=f"⚠️ Riesgo actual BTC: {riesgo}/10\n💰 Precio: ${btc_price:,.2f}")

    elif query.data == 'parar':
        jobs = context.job_queue.get_jobs_by_name(f"risk_{user_id}")
        for job in jobs:
            job.schedule_removal()
        await query.edit_message_text("⛔ Has detenido las notificaciones.")

    elif query.data == 'modo':
        actual = user_settings[user_id]["night_mode"]
        user_settings[user_id]["night_mode"] = not actual
        estado = "activado" if not actual else "desactivado"
        await query.edit_message_text(f"🌙 Modo nocturno {estado}.")

    elif query.data == 'radar':
        await ejecutar_radar(update, context)

# --------- RADAR DE OPORTUNIDADES ---------

async def ejecutar_radar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    mensaje = "🔍 Revisando oportunidades..."
    await context.bot.send_message(chat_id=user_id, text=mensaje)

    oportunidades = []

    async with aiohttp.ClientSession() as session:
        for coin in ALTCOINS:
            url = f"https://api.coingecko.com/api/v3/coins/{coin}?localization=false&tickers=false&market_data=true"
            async with session.get(url) as resp:
                data = await resp.json()
                m = data["market_data"]
                actual = m["current_price"]["usd"]
                cambio_24h = m["price_change_percentage_24h"]
                cambio_7d = m["price_change_percentage_7d"]
                if cambio_24h < -3 and cambio_7d < 0:
                    oportunidades.append(f"🔍 {data['name']} ({data['symbol'].upper()})\n💵 Precio: ${actual:,.2f}\n📉 24h: {cambio_24h:.2f}% / 7d: {cambio_7d:.2f}%")

    if oportunidades:
        texto = "🚨 *Oportunidades detectadas:*\n\n" + "\n\n".join(oportunidades)
        await context.bot.send_message(chat_id=user_id, text=texto, parse_mode="Markdown")
    else:
        await context.bot.send_message(chat_id=user_id, text="✅ No se detectaron oportunidades por ahora.")

async def radar_auto(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.chat_id
    oportunidades = []
    nuevas = []

    async with aiohttp.ClientSession() as session:
        for coin in ALTCOINS:
            url = f"https://api.coingecko.com/api/v3/coins/{coin}?localization=false&tickers=false&market_data=true"
            async with session.get(url) as resp:
                data = await resp.json()
                m = data["market_data"]
                actual = m["current_price"]["usd"]
                cambio_24h = m["price_change_percentage_24h"]
                cambio_7d = m["price_change_percentage_7d"]
                if cambio_24h < -3 and cambio_7d < 0:
                    info = f"{data['id']}: {actual:.2f}"
                    oportunidades.append(info)
                    nuevas.append(f"🔍 {data['name']} ({data['symbol'].upper()})\n💵 Precio: ${actual:,.2f}\n📉 24h: {cambio_24h:.2f}% / 7d: {cambio_7d:.2f}%")

    if oportunidades:
        previas = last_opportunities.get(user_id, [])
        if set(oportunidades) != set(previas):
            last_opportunities[user_id] = oportunidades
            mensaje = "🚨 *Nuevas oportunidades detectadas:*\n\n" + "\n\n".join(nuevas)
            await context.bot.send_message(chat_id=user_id, text=mensaje, parse_mode="Markdown")
    else:
        last_opportunities[user_id] = []

# --------- MAIN ---------

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_buttons))
    app.run_polling()

if __name__ == "__main__":
    main()
