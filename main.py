import logging
import aiohttp
import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, JobQueue

TOKEN = "7463495309:AAFnWbMN8eYShhTt9UvygCD0TAFED-LuJhM"

user_last_risk = {}
RISK_COLORS = {
    1: "🟢", 2: "🟢", 3: "🟢",
    4: "🟡", 5: "🟡", 6: "🟡",
    7: "🟠", 8: "🟠",
    9: "🔴", 10: "🔴"
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def fetch_btc_price():
    url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            return data["bitcoin"]["usd"]

async def fetch_ath():
    url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=max"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            prices = data["prices"]
            ath = max(price[1] for price in prices)
            return ath

def calculate_risk(current_price, previous_price, ath):
    price_change = current_price - previous_price
    price_speed = price_change / previous_price if previous_price > 0 else 0
    distance_to_ath = current_price / ath if ath else 0

    risk_score = (
        (distance_to_ath * 5) +
        (max(price_speed, 0) * 100 * 0.5)
    )

    return min(max(int(round(risk_score)), 1), 10)

async def notify_risk(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.chat_id
    data = context.job.data

    current_price = await fetch_btc_price()
    previous_price = data.get("previous_price", current_price)
    ath = data.get("ath", current_price)  # fallback si no hay ATH
    previous_risk = user_last_risk.get(user_id, None)

    risk = calculate_risk(current_price, previous_price, ath)

    if risk != previous_risk:
        user_last_risk[user_id] = risk
        color = RISK_COLORS[risk]
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"⚠️ *Riesgo BTC*: {risk}/10 {color}\n"
                f"💵 *Precio actual*: ${current_price:,.2f}\n"
                f"📈 *Máximo histórico*: ${ath:,.2f}"
            ),
            parse_mode="Markdown"
        )

    context.job.data["previous_price"] = current_price

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id

    await update.message.reply_text("🔔 Bot iniciado. Calculando el ATH de BTC...")

    ath = await fetch_ath()
    current_price = await fetch_btc_price()

    await update.message.reply_text(
        f"📊 Máximo histórico de BTC cargado: ${ath:,.2f}\nEmpezando monitoreo..."
    )

    context.job_queue.run_repeating(
        notify_risk,
        interval=3600,
        first=5,
        chat_id=user_id,
        name=str(user_id),
        data={"previous_price": current_price, "ath": ath}
    )

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.run_polling()

if __name__ == "__main__":
    main()
