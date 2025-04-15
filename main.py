import logging
import aiohttp
import matplotlib.pyplot as plt
import io
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)
from datetime import datetime

TOKEN = "7463495309:AAFnWbMN8eYShhTt9UvygCD0TAFED-LuJhM"  # <-- reemplaza con tu token real
ATH = 105000

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 📡 Obtener datos históricos de BTC desde 2016
async def fetch_btc_historical_data():
    url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=max"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            prices = data['prices']
            return prices  # Lista de precios [(timestamp, price), ...]

# 🔢 Generar gráfico de precios históricos
async def generate_btc_chart(prices):
    # Convertimos los datos de tiempo y precio
    times = [datetime.utcfromtimestamp(p[0] / 1000) for p in prices]
    prices_usd = [p[1] for p in prices]

    # Crear la gráfica
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(times, prices_usd, label='Precio BTC', color='b')

    # Mejoras en el gráfico
    ax.set_title("Evolución del Precio de BTC (2016 - Actualidad)")
    ax.set_xlabel("Fecha")
    ax.set_ylabel("Precio en USD")
    ax.grid(True)
    fig.autofmt_xdate()

    # Guardar el gráfico en un buffer de memoria y enviarlo al usuario
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    return buf

# 🟢 Comando para ver la gráfica
async def ver_grafica(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    await update.message.reply_text("🔄 Generando la gráfica de BTC...")

    prices = await fetch_btc_historical_data()  # Obtenemos los datos históricos

    # Generamos la gráfica
    buf = await generate_btc_chart(prices)
    await update.message.reply_photo(photo=buf, caption="📊 Gráfico de precios de BTC desde 2016")

# 🧭 Menú de opciones con el botón para ver gráfica
async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📉 Ver gráfica de BTC", callback_data="ver_grafica")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📋 Menú de opciones:", reply_markup=reply_markup)

# 🧭 Manejo de botones
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "ver_grafica":
        await ver_grafica(update, context)

# 🚀 Lanzar bot
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", show_menu))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
