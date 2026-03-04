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

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID        = os.environ.get("CHAT_ID")
ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_KEY")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

def build_prompt():
    today = datetime.now().strftime("%A %d de %B de %Y")
    return f"""Hoy es {today}. Genera el informe de PRE MERCADO completo en HTML.

Usa tus conocimientos actuales y busca SOLO los datos mas importantes: precios futuros S&P500, Nasdaq, Dow, WTI, Brent, oro, bitcoin, VIX, riesgo pais Argentina, principales ADRs argentinos, Ibovespa, bolsas Asia y Europa, noticias clave del dia.

DISENO HTML obligatorio:
- Fondo #111827, cards #1c2638, bordes #2e3f58
- Verde #34d399, rojo #f87171, dorado #fbbf24, texto #e2e8f0
- Google Fonts: IBM Plex Sans, IBM Plex Mono, Bebas Neue
- Header sticky fondo #0a1628, logo PREMERCADO en Bebas Neue, punto rojo parpadeante LIVE
- Cada card con stripe de 3px arriba (verde=sube, rojo=baja, dorado=neutro)
- Barra de progreso debajo de cada card
- Panel especial petroleo: fondo #0d1f3c, WTI y Brent lado a lado, precio grande
- Panel riesgo pais: fondo #1e0909, numero grande en rojo
- Tabla ADRs con columnas empresa, precio USD, variacion, tendencia
- Seccion bolsas mundiales: Asia-Pacifico y Europa en tablas separadas
- Calendario economico: lista vertical, hora ET y ARG, badge impacto colored
- Noticias: cards con borde izquierdo de color segun categoria
- @media print print-color-adjust exact para PDF oscuro
- Mobile-first, max-width 720px centrado

Responde UNICAMENTE con HTML completo. Empieza con <!DOCTYPE html> termina con </html>. Sin texto extra."""

def generate_report():
    log.info("Generando informe...")
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    # Una sola busqueda rapida para datos clave
    search_data = ""
    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": "Give me today's prices: S&P500 futures, Nasdaq futures, WTI oil, Brent oil, gold, bitcoin, VIX, Argentina country risk EMBI. Just the numbers."}]
        )
        for block in resp.content:
            if hasattr(block, "text") and block.text:
                search_data = block.text
        log.info("Busqueda completada")
    except Exception as e:
        log.warning(f"Busqueda fallida: {e}")

    # Generar HTML
    prompt = build_prompt()
    if search_data:
        prompt += f"\n\nDATOS ACTUALES ENCONTRADOS:\n{search_data}"

    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}]
    )

    html = ""
    for block in resp.content:
        if hasattr(block, "text"):
            html += block.text
    html = html.strip()

    # Limpiar markdown si quedó
    if "```" in html:
        parts = html.split("```")
        for part in parts:
            if "<!DOCTYPE" in part:
                html = part.replace("html", "", 1).strip()
                break
    idx = html.find("<!DOCTYPE")
    if idx > 0:
        html = html[idx:]

    log.info(f"HTML listo: {len(html)} chars")
    return html

def send_report():
    try:
        log.info("Iniciando envio...")
        html = generate_report()

        filename = f"premercado_{datetime.now().strftime('%Y%m%d')}.html"
        filepath = f"/tmp/{filename}"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

        today_str = datetime.now().strftime("%d/%m/%Y")

        async def send_async():
            async with Bot(token=TELEGRAM_TOKEN) as bot:
                with open(filepath, "rb") as f:
                    await bot.send_document(
                        chat_id=CHAT_ID,
                        document=f,
                        filename=filename,
                        caption=f"Pre Mercado {today_str} - Abri en navegador. PDF: Imprimir > Graficos de fondo activado."
                    )
            log.info("Enviado OK")

        asyncio.run(send_async())

    except Exception as e:
        log.error(f"Error: {e}")
        try:
            async def send_error():
                async with Bot(token=TELEGRAM_TOKEN) as bot:
                    await bot.send_message(chat_id=CHAT_ID, text=f"Error: {str(e)}")
            asyncio.run(send_error())
        except:
            pass

def handle_telegram_updates():
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
                        "text": "Bot Pre Mercado activo\n\n/ahora - Generar informe ahora\n/start - Ayuda\n\nInforme automatico todos los dias a las 7:00 hs Argentina."
                    })
                elif text == "/ahora":
                    requests.post(f"{bot_url}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": "Generando informe, dame 1 minuto..."
                    })
                    threading.Thread(target=send_report, daemon=True).start()
        except Exception as e:
            log.error(f"Polling error: {e}")
            time.sleep(5)

def run_scheduler():
    schedule.every().day.at("10:00").do(send_report)
    log.info("Scheduler listo: 7:00 ARG")
    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == "__main__":
    log.info("Bot iniciando...")
    if not all([TELEGRAM_TOKEN, CHAT_ID, ANTHROPIC_KEY]):
        log.error("Faltan variables de entorno")
        exit(1)

    try:
        async def send_start():
            async with Bot(token=TELEGRAM_TOKEN) as bot:
                await bot.send_message(
                    chat_id=CHAT_ID,
                    text="Bot Pre Mercado activo. Escribi /ahora para el informe. Automatico a las 7:00 hs ARG."
                )
        asyncio.run(send_start())
    except Exception as e:
        log.warning(f"Start msg: {e}")

    threading.Thread(target=handle_telegram_updates, daemon=True).start()
    threading.Thread(target=run_scheduler, daemon=True).start()

    log.info("Corriendo...")
    while True:
        time.sleep(60)
