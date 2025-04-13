import requests
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, CallbackQueryHandler, CallbackContext, Updater
from apscheduler.schedulers.background import BackgroundScheduler
import logging
from datetime import datetime, timedelta

TOKEN = '7463495309:AAFnWbMN8eYShhTt9UvygCD0TAFED-LuJhM'
bot = Bot(token=TOKEN)
last_risk = {}
ATH = 105000  # Máximo histórico actualizado
scheduler = BackgroundScheduler()
scheduler.start()

def get_price_data():
    now = datetime.now()
    end = int(now.timestamp())
    start = int((now - timedelta(days=8)).timestamp())

    url = f'https://api.coingecko.com/api/v3/coins/bitcoin/market_chart/range?vs_currency=usd&from={start}&to={end}'
    response = requests.get(url)
    data = response.json()
    
    prices = [p[1] for p in data['prices']]
    current_price = prices[-1]
    price_24h_ago = prices[-1450] if len(prices) > 1450 else prices[0]
    avg_7d = sum(prices) / len(prices)
    high_7d = max(prices)
    low_7d = min(prices)

    return current_price, price_24h_ago, avg_7d, high_7d, low_7d

def calculate_risk(price, price_24h_ago, avg_7d, high_7d, low_7d):
    risk = 0

    # Tendencia
    if price > avg_7d:
        risk += 1
    elif price < avg_7d:
        risk -= 1

    # Velocidad
    change_24h_pct = ((price - price_24h_ago) / price_24h_ago) * 100
    if change_24h_pct >= 5:
        risk += 2
    elif change_24h_pct >= 2:
        risk += 1
    elif change_24h_pct <= -5:
        risk -= 2
    elif change_24h_pct <= -2:
        risk -= 1

    # Proximidad ATH
    perc_of_ath = (price / ATH) * 100
    if perc_of_ath >= 90:
        risk += 3
    elif perc_of_ath >= 70:
        risk += 2
    elif perc_of_ath >= 50:
        risk += 1

    # Volatilidad
    if (high_7d - low_7d) / price > 0.1:
        risk += 1

    return max(1, min(10, risk + 5))

def risk_color(risk):
    if risk <= 3:
        return "🟢"
    elif risk <= 6:
        return "🟡"
    elif risk <= 8:
        return "🟠"
    else:
        return "🔴"

def build_risk_message(price, price_24h_ago, avg_7d, high_7d, low_7d, risk):
    return (
        f"{risk_color(risk)} *Riesgo actual: Nivel {risk}/10*\n"
        f"💰 Precio BTC: *${price:,.2f}*\n"
        f"📈 Tendencia 7d: {'🔼' if price > avg_7d else '🔽'}\n"
        f"⚡ Cambio 24h: {((price - price_24h_ago) / price_24h_ago) * 100:.2f}%\n"
        f"📊 Volatilidad 7d: {(high_7d - low_7d)/price*100:.2f}%"
    )

def send_risk(chat_id):
    try:
        price, price_24h_ago, avg_7d, high_7d, low_7d = get_price_data()
        risk = calculate_risk(price, price_24h_ago, avg_7d, high_7d, low_7d)
        msg = build_risk_message(price, price_24h_ago, avg_7d, high_7d, low_7d, risk)

        bot.send_message(
            chat_id=chat_id,
            text=msg,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Consultar riesgo actual", callback_data="riesgo_actual")]]),
            parse_mode='Markdown'
        )
        return risk
    except Exception as e:
        print(f"Error enviando riesgo: {e}")

def check_risk(context: CallbackContext):
    chat_id = context.job.context
    new_risk = send_risk(chat_id)
    if new_risk is not None:
        if last_risk.get(chat_id) == new_risk:
            return  # No cambió, no notificar
        last_risk[chat_id] = new_risk

def start(update, context):
    chat_id = update.message.chat_id
    update.message.reply_text(
        "✅ Bot activado. Te notificaré si el nivel de riesgo de BTC cambia.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Consultar riesgo actual", callback_data="riesgo_actual")]])
    )

    scheduler.add_job(
        check_risk,
        'interval',
        hours=1,
        context=chat_id,
        id=str(chat_id),
        replace_existing=True
    )

    # Enviar primera lectura de riesgo
    last_risk[chat_id] = send_risk(chat_id)

def stop(update, context):
    chat_id = update.message.chat_id
    try:
        scheduler.remove_job(str(chat_id))
        update.message.reply_text("🛑 Has detenido las notificaciones automáticas.")
    except:
        update.message.reply_text("⚠️ No tenías notificaciones activas.")

def button(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    if query.data == "riesgo_actual":
        send_risk(query.message.chat_id)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    updater = Updater(token=TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(CommandHandler('parar', stop))
    dp.add_handler(CallbackQueryHandler(button))

    updater.start_polling()
    updater.idle()
