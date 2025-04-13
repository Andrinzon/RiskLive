import requests
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta

TOKEN = "7463495309:AAFnWbMN8eYShhTt9UvygCD0TAFED-LuJhM"
ATH = 105000  # All-time high estimado
last_risk = {}
scheduler = AsyncIOScheduler()

# 📊 Obtener datos de precio desde CoinGecko
def get_price_data():
    now = datetime.now()
    end = int(now.timestamp())
    start = int((now - timedelta(days=8)).timestamp())

    url = f'https://api.coingecko.com/api/v3/coins/bitcoin/market_chart/range?vs_currency=usd&from={start}&to={end}'
    data = requests.get(url).json()
    prices = [p[1] for p in data['prices']]

    current = prices[-1]
    old = prices[-1450] if len(prices) > 1450 else prices[0]
    avg = sum(prices) / len(prices)
    high = max(prices)
    low = min(prices)

    return current, old, avg, high, low

# 🔢 Lógica de riesgo
def calculate_risk(price, price_24h, avg_7d, high, low):
    risk = 0
    change_pct = ((price - price_24h) / price_24h) * 100

    if price > avg_7d: risk += 1
    else: risk -= 1

    if change_pct >= 5: risk += 2
    elif change_pct >= 2: risk += 1
    elif change_pct <= -5: risk -= 2
    elif change_pct <= -2: risk -= 1

    perc_ath = (price / ATH) * 100
    if perc_ath >= 90: risk += 3
    elif perc_ath >= 70: risk += 2
    elif perc_ath >= 50: risk += 1

    if (high - low) / price > 0.1: risk += 1

    return max(1, min(10, risk + 5))

# 🎨 Color de riesgo
def risk_color(risk):
    if risk <= 3: return "🟢"
    elif risk <= 6: return "🟡"
    elif risk <= 8: return "🟠"
    else: return "🔴"

# 🧾 Mensaje completo
def build_risk_message(price, price_24h, avg, high, low, risk):
    return (
        f"{risk_color(risk)} *Riesgo actual: Nivel {risk}/10*\n"
        f"💰 Precio BTC: *${price:,.2f}*\n"
        f"📈 Tendencia 7d: {'🔼' if price > avg else '🔽'}\n"
        f"⚡ Cambio 24h: {((price - price_24h) / price_24h) * 100:.2f}%\n"
        f"📊 Volatilidad 7d: {(high - low)/price*100:.2f}%"
    )

# 🚨 Enviar riesgo
async def send_risk(context: ContextTypes.DEFAULT_TYPE, chat_id):
    try:
        price, old, avg, high, low = get_price_data()
        risk = calculate_risk(price, old, avg, high, low)
        msg = build_risk_message(price, old, avg, high, low, risk)

        await context.bot.send_message(
            chat_id=chat_id,
            text=msg,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔄 Consultar riesgo actual", callback_data="riesgo_actual")]]
            )
        )
        return risk
    except Exception as e:
        print(f"Error al enviar riesgo: {e}")

# ⏱ Tarea programada cada hora
async def check_risk(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    new_risk = await send_risk(context, chat_id)
    if new_risk is not None and last_risk.get(chat_id) != new_risk:
        last_risk[chat_id] = new_risk

# 🟢 /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        "✅ Bot activado. Te notificaré si el nivel de riesgo de BTC cambia.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔄 Consultar riesgo actual", callback_data="riesgo_actual")]]
        )
    )
    last_risk[chat_id] = await send_risk(context, chat_id)

    scheduler.add_job(
        check_risk,
        "interval",
        hours=1,
        args=[context],
        kwargs={"chat_id": chat_id},
        id=str(chat_id),
        replace_existing=True
    )

# 🛑 /parar
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    try:
        scheduler.remove_job(str(chat_id))
        await update.message.reply_text("🛑 Has detenido las notificaciones automáticas.")
    except:
        await update.message.reply_text("⚠️ No había notificaciones activas.")

# 🔘 Botón inline
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "riesgo_actual":
        await send_risk(context, query.message.chat.id)

# 🏁 Main
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scheduler.start()

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("parar", stop))
    app.add_handler(CallbackQueryHandler(button))

    app.run_polling()
