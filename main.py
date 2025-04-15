import logging
import aiohttp
import asyncio
import matplotlib.pyplot as plt
import io
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

# Configuración básica
TOKEN = '7463495309:AAFnWbMN8eYShhTt9UvygCD0TAFED-LuJhM'
logging.basicConfig(level=logging.INFO)
ATH = 105000

# Almacenamiento en memoria
riesgo_actual = None
historial = []  # Lista con datos cada hora
usuarios_config = {}  # user_id: {"modo_nocturno": True}

# Lógica de cálculo de riesgo
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

# Obtener datos desde CoinGecko
async def get_btc_data():
    url = 'https://api.coingecko.com/api/v3/coins/bitcoin?localization=false&tickers=false&market_data=true'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            market = data['market_data']
            return {
                'price': market['current_price']['usd'],
                'price_24h': market['price_change_percentage_24h_in_currency']['usd'],
                'avg_7d': market['price_change_percentage_7d_in_currency']['usd'],
                'high': market['high_24h']['usd'],
                'low': market['low_24h']['usd']
            }

# Generar gráfico y devolver archivo
def generar_grafico():
    if not historial:
        return None

    fechas = [d['timestamp'].strftime("%H:%M") for d in historial[-24:]]
    precios = [d['precio'] for d in historial[-24:]]
    riesgos = [d['riesgo'] for d in historial[-24:]]

    fig, ax1 = plt.subplots(figsize=(10, 5))

    ax1.set_xlabel('Hora')
    ax1.set_ylabel('Riesgo (1-10)', color='red')
    ax1.plot(fechas, riesgos, color='red', marker='o')
    ax1.tick_params(axis='y', labelcolor='red')
    ax1.set_ylim(1, 10)

    ax2 = ax1.twinx()
    ax2.set_ylabel('Precio BTC', color='blue')
    ax2.plot(fechas, precios, color='blue', marker='x', linestyle='--')
    ax2.tick_params(axis='y', labelcolor='blue')

    plt.title('Evolución del Riesgo y Precio BTC')
    fig.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    buf.name = "grafico.png"
    return buf

# Botones de menú
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    usuarios_config[user_id] = {"modo_nocturno": True}
    keyboard = [
        [InlineKeyboardButton("⚠️ Riesgo", callback_data='riesgo')],
        [InlineKeyboardButton("📊 Ver gráfico", callback_data='grafico')],
        [InlineKeyboardButton("🌙 Modo nocturno", callback_data='toggle_noche')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Bienvenido a Eye of God 👁️‍🗨️", reply_markup=reply_markup)

# Manejo de botones
async def botones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == 'riesgo':
        if riesgo_actual:
            await query.edit_message_text(f"⚠️ Riesgo actual BTC: {riesgo_actual}/10")
    elif query.data == 'grafico':
        imagen = generar_grafico()
        if imagen:
            await context.bot.send_photo(chat_id=query.message.chat_id, photo=InputFile(imagen))
        else:
            await query.edit_message_text("Aún no hay suficientes datos para mostrar el gráfico.")
    elif query.data == 'toggle_noche':
        if user_id in usuarios_config:
            usuarios_config[user_id]["modo_nocturno"] = not usuarios_config[user_id]["modo_nocturno"]
            estado = "activado" if usuarios_config[user_id]["modo_nocturno"] else "desactivado"
            await query.edit_message_text(f"🌙 Modo nocturno {estado}.")

# Tarea periódica de riesgo
async def check_riesgo(context: ContextTypes.DEFAULT_TYPE):
    global riesgo_actual
    data = await get_btc_data()
    price = data['price']
    price_24h = price / (1 + (data['price_24h'] / 100))
    avg_7d = price / (1 + (data['avg_7d'] / 100))
    high = data['high']
    low = data['low']

    nuevo_riesgo = calculate_risk(price, price_24h, avg_7d, high, low)

    if nuevo_riesgo != riesgo_actual:
        riesgo_actual = nuevo_riesgo
        now = datetime.now()
        historial.append({"timestamp": now, "precio": price, "riesgo": nuevo_riesgo})

        for user_id, config in usuarios_config.items():
            hora = now.hour
            if config.get("modo_nocturno") and (hora >= 0 and hora < 8):
                continue
            await context.bot.send_message(chat_id=user_id, text=f"⚠️ Riesgo actualizado: {riesgo_actual}/10")

# Main del bot
async def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(botones))

    job_queue = app.job_queue
    job_queue.run_repeating(check_riesgo, interval=3600, first=5)

    print("Bot en marcha...")
    await app.run_polling()

if __name__ == '__main__':
    asyncio.run(main())