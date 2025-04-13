import logging
import aiohttp
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, JobQueue

TOKEN = "7463495309:AAFnWbMN8eYShhTt9UvygCD0TAFED-LuJhM"  # Reemplaza con tu token de bot

user_last_risk = {}

RISK_COLORS = {
    1: "🟢", 2: "🟢", 3: "🟢",
    4: "🟡", 5: "🟡", 6: "🟡",
    7: "🟠", 8: "🟠",
    9: "🔴", 10: "🔴"
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ATH real proporcionado por ti
ATH = 105000

async def fetch_btc_data():
    url = "https://api.coingecko.com/api/v3/coins/bitcoin?localization=false&tickers=false&market_data=true&community_data=false&developer_data=false&sparkline=false"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            market_data = data["market_data"]
            return {
                "price": market_data["current_price"]["usd"],
                "price_24h": market_data["price_change_24h_in_currency"]["usd"],
                "avg_7d": market_data["price_change_percentage_7d_in_currency"]["usd"],  # %
                "high": market_data["high_24h"]["usd"],
                "low": market_data["low_24h"]["usd"]
            }

# 🔢 Lógica de riesgo
def calculate_risk(price, price_24h, avg_7d_pct, high, low):
    risk = 0
    change_pct = ((price - price_24h) / price_24h) * 100

    avg_7d_price = price / (1 + (avg_7d_pct / 100))  # estimación precio medio 7 días
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

async def notify_risk(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.chat_id
    previous_risk = user_last_risk.get(user_id)

    data = await fetch_btc_data()
    price = data["price"]
    price_24h = price - data["price_24h"]
    avg_7d_pct = data["avg_7d"]
    high = data["high"]
    low = data["low"]

    risk = calculate_risk(price, price_24h, avg_7d_pct, high, low)

    if risk != previous_risk:
        user_last_risk[user_id] = risk
        color = RISK_COLORS[risk]
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"⚠️ *Riesgo BTC*: {risk}/10 {color}\n"
                f"💵 *Precio actual*: ${price:,.2f}"
            ),
            parse_mode="Markdown"
        )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    await update.message.reply_text("🔔 Te notificaré cada hora si cambia el riesgo de BTC.")

    context.job_queue.run_repeating(
        notify_risk,
        interval=3600,
        first=5,
        chat_id=user_id,
        name=str(user_id),
    )

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    current_jobs = context.job_queue.get_jobs_by_name(str(user_id))
    for job in current_jobs:
        job.schedule_removal()
    user_last_risk.pop(user_id, None)
    await update.message.reply_text("🛑 Notificaciones de riesgo detenidas.")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("parar", stop))
    app.run_polling()

if __name__ == "__main__":
    main()
