import os
import asyncio
import logging
from datetime import datetime
import anthropic
import requests
from telegram import Bot
from telegram.constants import ParseMode
import schedule
import time
import threading

# ── CONFIG ──────────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID          = os.environ.get("CHAT_ID")
ANTHROPIC_KEY    = os.environ.get("ANTHROPIC_KEY")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── PROMPT ──────────────────────────────────────────────
def build_prompt():
    today = datetime.now().strftime("%A %d de %B de %Y")
    return f"""
Hoy es {today}. Generá el informe de PRE MERCADO completo en formato HTML.

El informe debe incluir TODAS estas secciones, buscando los datos más actualizados posibles:

1. ÍNDICES FUTUROS: S&P500 (ES1!), Nasdaq 100 (NQ1!), Dow Jones (YM1!) — valores, variación % y puntos
2. VIX (índice del miedo) y DXY (dólar index)
3. FUTUROS PETRÓLEO: WTI (CL1! NYMEX) y Brent (BZ1! ICE) — precio, variación, rango del día
4. ORO (XAU/USD) y BITCOIN (BTC/USD)
5. BOLSAS MUNDIALES:
   - Asia-Pacífico (Nikkei, Hang Seng, Shanghai, ASX200, Kospi, Straits Times) con sus cierres
   - Europa (FTSE, DAX, CAC40, Stoxx600, IBEX) — si ya cerraron o están operando
6. BONOS Y RIESGO PAÍS ARGENTINA: EMBI (riesgo país), GD30, AL30, GD46, GD35
7. PRE ADRs ARGENTINOS: GGAL, BMA, BBAR, SUPV, YPF, PAM, EDN, TGS, TEO, TS
8. BRASIL: Ibovespa, USD/BRL, Tasa SELIC
9. CONTEXTO GEOPOLÍTICO/BÉLICO del momento
10. CALENDARIO ECONÓMICO del día con hora ET y Argentina
11. NOTICIAS MÁS IMPORTANTES del día para los mercados

DISEÑO HTML — usá exactamente este estilo:
- Fondo oscuro azulado: #111827
- Superficie cards: #1c2638
- Verde suave: #34d399
- Rojo cálido: #f87171
- Dorado: #fbbf24
- Tipografía: IBM Plex Sans + IBM Plex Mono + Bebas Neue (Google Fonts)
- Barras de progreso en cada card
- Flechas ▲ ▼ para variaciones
- Mobile-first, responsive
- Stripes de color arriba de cada card (verde=sube, rojo=baja, dorado=neutro)
- @media print con print-color-adjust: exact para que el PDF salga oscuro
- Panel de petróleo destacado con fondo azul marino
- Riesgo país con panel rojo oscuro y número grande
- Sección de bolsas mundiales con tabla por región (Asia / Europa)
- Calendario como lista vertical con hora ET y ARG, badge de impacto
- Noticias con borde izquierdo de color según categoría
- Header sticky con logo PREMERCADO en Bebas Neue, punto LIVE rojo parpadeante
- Banner de alerta bélica/geopolítica debajo del header si corresponde

Respondé ÚNICAMENTE con el HTML completo, sin explicaciones, sin markdown, sin ```html.
El HTML debe empezar con <!DOCTYPE html> y terminar con </html>.
"""

# ── GENERAR INFORME ──────────────────────────────────────
def generate_report():
    log.info("Generando informe pre mercado...")
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    
    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=8000,
        messages=[{"role": "user", "content": build_prompt()}]
    )
    
    html = message.content[0].text.strip()
    if html.startswith("```"):
        html = html.split("\n", 1)[1]
        html = html.rsplit("```", 1)[0]
    
    log.info(f"Informe generado: {len(html)} caracteres")
    return html

# ── ENVIAR POR TELEGRAM ──────────────────────────────────
def send_report():
    try:
        log.info("Iniciando envío del informe...")
        html = generate_report()
        
        # Guardar HTML como archivo
        filename = f"premercado_{datetime.now().strftime('%Y%m%d')}.html"
        filepath = f"/tmp/{filename}"
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)
        
        # Enviar archivo HTML por Telegram
        bot = Bot(token=TELEGRAM_TOKEN)
        
        today_str = datetime.now().strftime("%d/%m/%Y")
        caption = (
            f"📊 *Pre Mercado — {today_str}*\n"
            f"Abrí el archivo en tu navegador para verlo con el diseño completo.\n"
            f"Para guardarlo como PDF: Menú → Imprimir → Guardar como PDF\n"
            f"_(Activá 'Gráficos de fondo' para mantener el fondo oscuro)_"
        )
        
        async def send_async():
            async with Bot(token=TELEGRAM_TOKEN) as bot:
                with open(filepath, "rb") as f:
                    await bot.send_document(
                        chat_id=CHAT_ID,
                        document=f,
                        filename=filename,
                        caption=caption,
                        parse_mode=ParseMode.MARKDOWN
                    )
                log.info("✅ Informe enviado exitosamente")
        
        asyncio.run(send_async())
        
    except Exception as e:
        log.error(f"❌ Error enviando informe: {e}")
        # Notificar error por Telegram
        try:
            async def send_error():
                async with Bot(token=TELEGRAM_TOKEN) as bot:
                    await bot.send_message(
                        chat_id=CHAT_ID,
                        text=f"⚠️ Error generando el pre mercado: {str(e)}"
                    )
            asyncio.run(send_error())
        except:
            pass

# ── COMANDO /start y /ahora ──────────────────────────────
def handle_telegram_updates():
    """Polling simple para responder comandos /start y /ahora"""
    offset = None
    bot_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
    
    while True:
        try:
            params = {"timeout": 30}
            if offset:
                params["offset"] = offset
            
            resp = requests.get(f"{bot_url}/getUpdates", params=params, timeout=35)
            updates = resp.json().get("result", [])
            
            for update in updates:
                offset = update["update_id"] + 1
                msg = update.get("message", {})
                text = msg.get("text", "")
                chat_id = msg.get("chat", {}).get("id")
                
                if not chat_id:
                    continue
                
                if text == "/start":
                    requests.post(f"{bot_url}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": (
                            "👋 *Bienvenido al Bot de Pre Mercado*\n\n"
                            "📊 Recibirás el informe automáticamente cada mañana a las *7:00 hs (Argentina)*.\n\n"
                            "Comandos disponibles:\n"
                            "• /ahora — Generar informe ahora mismo\n"
                            "• /start — Ver este mensaje\n\n"
                            "¡Que te vaya bien en el mercado! 🚀"
                        ),
                        "parse_mode": "Markdown"
                    })
                
                elif text == "/ahora":
                    requests.post(f"{bot_url}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": "⏳ Generando el informe, dame un minuto..."
                    })
                    # Generar en thread separado
                    threading.Thread(target=send_report, daemon=True).start()
                    
        except Exception as e:
            log.error(f"Error en polling: {e}")
            time.sleep(5)

# ── SCHEDULER ────────────────────────────────────────────
def run_scheduler():
    # Enviar todos los días a las 7:00 hs Argentina (UTC-3) = 10:00 UTC
    schedule.every().day.at("10:00").do(send_report)
    log.info("✅ Scheduler configurado: informe diario a las 7:00 hs ARG (10:00 UTC)")
    
    while True:
        schedule.run_pending()
        time.sleep(30)

# ── MAIN ─────────────────────────────────────────────────
if __name__ == "__main__":
    log.info("🚀 Bot Pre Mercado iniciando...")
    
    # Verificar variables de entorno
    if not all([TELEGRAM_TOKEN, CHAT_ID, ANTHROPIC_KEY]):
        log.error("❌ Faltan variables de entorno: TELEGRAM_TOKEN, CHAT_ID, ANTHROPIC_KEY")
        exit(1)
    
    # Mensaje de inicio
    try:
        async def send_start():
            async with Bot(token=TELEGRAM_TOKEN) as bot:
                await bot.send_message(
                    chat_id=CHAT_ID,
                    text=(
                        "✅ *Bot Pre Mercado activo*\n\n"
                        "📅 Recibirás el informe todos los días a las *7:00 hs (Argentina)*.\n"
                        "Escribí /ahora para generarlo en este momento.\n"
                        "Escribí /start para ver la ayuda."
                    ),
                    parse_mode=ParseMode.MARKDOWN
                )
        asyncio.run(send_start())
    except Exception as e:
        log.warning(f"No se pudo enviar mensaje de inicio: {e}")
    
    # Arrancar polling de comandos en thread separado
    threading.Thread(target=handle_telegram_updates, daemon=True).start()
    
    # Arrancar scheduler en thread separado
    threading.Thread(target=run_scheduler, daemon=True).start()
    
    log.info("✅ Bot corriendo. Esperando comandos y horario programado...")
    
    # Mantener el proceso vivo
    while True:
        time.sleep(60)
