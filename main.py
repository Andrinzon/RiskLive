import logging
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler)
from datetime import datetime
import matplotlib.pyplot as plt
import io
import matplotlib.dates as mdates

# === CONFIGURACIÓN ===
TOKEN = "7804851171:AAEp5TCO3e_-RsWSwGnyaHVpuZU5XA3KQC4"
ATH = 105000

# === VARIABLES GLOBALES ===
user_last_risk = {}
user_history = {}
user_alerts = {}
user_levels = {}
night_mode_enabled = {}

RISK_COLORS = {
    1: "🟢", 2: "🟢", 3: "🟢",
    4: "🟡", 5: "🟡", 6: "🟡",
    7: "🟠", 8: "🟠",
    9: "🔴", 10: "🔴"
}

# === FUNCIONES ===
async def fetch_price():
    url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            return data["bitcoin"]["usd"]

def calculate_risk(price, ath=ATH):
    distance = ath - price
    percent = (distance / ath) * 100
    if percent < 2:
        return 10
    elif percent < 5:
        return 9
    elif percent < 10:
        return 8
    elif percent < 15:
        return 7
    elif percent < 20:
        return 6
    elif percent < 30:
        return 5
    elif percent < 40:
        return 4
    elif percent < 50:
        return 3
    elif percent < 60:
        return 2
    return 1

async def notify_risk(context: ContextTypes.DEFAULT_TYPE):
    for user_id in user_last_risk.keys():
        now = datetime.now()
        if night_mode_enabled.get(user_id, False):
            if 0 <= now.hour < 8:
                continue

        price = await fetch_price()
        risk = calculate_risk(price)

        history = user_history.setdefault(user_id, [])
        history.append({"time": now.strftime("%H:%M"), "price": price, "risk": risk})
        if len(history) > 50:
            history.pop(0)

        if risk != user_last_risk[user_id]:
            user_last_risk[user_id] = risk
            color = RISK_COLORS[risk]
            texto = f"⚠️ *Riesgo BTC*: {risk}/10 {color}\n💵 *Precio actual*: ${price:,.2f}"

            alerta = user_alerts.get(user_id)
            if alerta:
                if ("riesgo" in alerta and risk >= alerta["riesgo"]) or \
                   ("precio" in alerta and price >= alerta["precio"]):
                    texto += "\n🔔 ¡Alerta activada!"

            niveles = user_levels.get(user_id)
            if niveles:
                if price <= niveles["soporte"]:
                    texto += "\n🟢 Precio tocó el *soporte*."
                if price >= niveles["resistencia"]:
                    texto += "\n🔴 Precio tocó la *resistencia*."

            await context.bot.send_message(chat_id=user_id, text=texto, parse_mode="Markdown")

# === COMANDOS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    user_last_risk[user_id] = -1
    night_mode_enabled[user_id] = False

    keyboard = [
        [InlineKeyboardButton("📊 Riesgo", callback_data='riesgo')],
        [InlineKeyboardButton("🖼️ Ver gráfica", callback_data='grafico')],
        [InlineKeyboardButton("🌙 Modo Nocturno", callback_data='toggle_night')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("👁 Bienvenido al *Eye of God*. Elige una opción:", parse_mode="Markdown", reply_markup=reply_markup)

async def parar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    user_last_risk.pop(user_id, None)
    await update.message.reply_text("🛑 Has detenido las notificaciones de riesgo.")

async def riesgo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price = await fetch_price()
    risk = calculate_risk(price)
    color = RISK_COLORS[risk]
    await update.message.reply_text(f"⚠️ *Riesgo BTC*: {risk}/10 {color}\n💵 *Precio actual*: ${price:,.2f}", parse_mode="Markdown")

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "riesgo":
        await riesgo(update, context)
    elif query.data == "grafico":
        await enviar_grafico(update, context)
    elif query.data == "toggle_night":
        user_id = query.message.chat_id
        current = night_mode_enabled.get(user_id, False)
        night_mode_enabled[user_id] = not current
        estado = "activado" if not current else "desactivado"
        await query.edit_message_text(f"🌙 Modo nocturno {estado}.")

async def enviar_grafico(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    history = user_history.get(user_id, [])
    if not history:
        await update.message.reply_text("❗ Aún no hay suficientes datos para generar la gráfica.")
        return

    times = [p['time'] for p in history]
    prices = [p['price'] for p in history]
    risks = [p['risk'] for p in history]

    plt.figure(figsize=(10, 5))
    plt.plot(times, prices, label='Precio BTC', color='blue')
    plt.plot(times, risks, label='Riesgo', color='red')
    plt.title('Histórico de Precio y Riesgo')
    plt.xlabel('Hora')
    plt.ylabel('Valor')
    plt.xticks(rotation=45)
    plt.legend()
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()

    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=buf)

# === NUEVAS FUNCIONES ===
async def set_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    if len(context.args) != 2:
        await update.message.reply_text("Uso: /alerta <tipo> <valor>\nEj: /alerta riesgo 7 o /alerta precio 50000")
        return
    tipo, valor = context.args
    if tipo not in ["riesgo", "precio"]:
        await update.message.reply_text("Tipo inválido. Usa 'riesgo' o 'precio'.")
        return
    try:
        user_alerts[user_id] = {tipo: float(valor)}
        await update.message.reply_text(f"🔔 Alerta configurada: {tipo} = {valor}")
    except ValueError:
        await update.message.reply_text("El valor debe ser un número.")

async def set_niveles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    if len(context.args) != 2:
        await update.message.reply_text("Uso: /niveles <soporte> <resistencia>\nEj: /niveles 50000 60000")
        return
    try:
        soporte, resistencia = map(float, context.args)
        user_levels[user_id] = {"soporte": soporte, "resistencia": resistencia}
        await update.message.reply_text(f"📉 Soporte: {soporte}\n📈 Resistencia: {resistencia}")
    except ValueError:
        await update.message.reply_text("Ambos valores deben ser números.")

async def simular(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    history = user_history.get(user_id, [])
    if len(history) < 2:
        await update.message.reply_text("❗ No hay datos suficientes para simular.")
        return

    buy_risk = 3
    sell_risk = 8
    bought = None
    result = []

    for punto in history:
        if not bought and punto["risk"] <= buy_risk:
            bought = punto
        elif bought and punto["risk"] >= sell_risk:
            profit = punto["price"] - bought["price"]
            result.append((bought["time"], punto["time"], bought["price"], punto["price"], profit))
            bought = None

    if not result:
        await update.message.reply_text("📉 No se generaron señales de compra/venta con riesgo 3→8.")
        return

    mensaje = "📈 *Simulación de Señales (riesgo 3→8)*\n\n"
    for r in result:
        mensaje += f"🟢 Compra: {r[0]} (${r[2]:,.2f})\n🔴 Venta: {r[1]} (${r[3]:,.2f})\n💰 Ganancia: ${r[4]:,.2f}\n\n"

    await update.message.reply_text(mensaje, parse_mode="Markdown")

# === MAIN ===
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("parar", parar))
    app.add_handler(CommandHandler("riesgo", riesgo))
    app.add_handler(CommandHandler("alerta", set_alert))
    app.add_handler(CommandHandler("niveles", set_niveles))
    app.add_handler(CommandHandler("simular", simular))
    app.add_handler(CallbackQueryHandler(button))

    app.job_queue.run_repeating(notify_risk, interval=3600, first=10)

    app.run_polling()

if __name__ == '__main__':
    main()
