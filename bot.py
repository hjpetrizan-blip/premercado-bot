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

# CONFIG
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID        = os.environ.get("CHAT_ID")
ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_KEY")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

def build_prompt():
    today = datetime.now().strftime("%A %d de %B de %Y")
    return f"""Hoy es {today}.

Genera el informe de PRE MERCADO en HTML con datos actuales de mercado.

Busca los precios actuales de: futuros S&P500 Nasdaq Dow Jones, WTI Brent petroleo, oro, bitcoin, VIX, DXY, bolsas asiaticas y europeas, riesgo pais Argentina, ADRs argentinos GGAL BMA YPF, Ibovespa, noticias del dia.

El HTML debe tener este diseno exacto:
- Fondo #111827, cards #1c2638, verde #34d399, rojo #f87171, dorado #fbbf24
- Google Fonts: IBM Plex Sans, IBM Plex Mono, Bebas Neue
- Header sticky con logo PREMERCADO y punto LIVE rojo parpadeante
- Cards con stripe de color arriba (verde sube, rojo baja)
- Barras de progreso y flechas en variaciones
- Panel destacado para petroleo WTI y Brent
- Panel rojo oscuro para riesgo pais con numero grande
- Tabla de ADRs argentinos
- Seccion bolsas Asia y Europa
- Calendario economico del dia con hora ET y Argentina
- Noticias con borde izquierdo de color
- @media print con print-color-adjust exact para PDF oscuro
- Mobile-first responsive

Responde SOLO con el HTML completo comenzando con <!DOCTYPE html> y terminando con </html>. Sin markdown ni explicaciones."""

def generate_report():
    log.info("Generando informe...")
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    # Primero hacer busquedas separadas
    searches = [
        "S&P500 Nasdaq Dow Jones futures price today",
        "WTI Brent crude oil price today",
        "gold bitcoin VIX DXY price today",
        "Argentina riesgo pais EMBI bonos GD30 hoy",
        "GGAL BMA YPF ADR price today Ibovespa",
        "Nikkei Hang Seng DAX FTSE market today"
    ]

    search_results = ""
    for query in searches:
        try:
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=[{"role": "user", "content": f"Search for: {query}. Return only the key prices and numbers found."}]
            )
            for block in resp.content:
                if hasattr(block, "text") and block.text:
                    search_results += f"\n{block.text}"
            log.info(f"Busqueda OK: {query}")
        except Exception as e:
            log.warning(f"Busqueda fallida '{query}': {e}")

    # Ahora generar el HTML con los datos encontrados
    final_prompt = build_prompt()
    if search_results:
        final_prompt += f"\n\nDATOS ENCONTRADOS EN BUSQUEDAS:\n{search_results}"

    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8000,
        messages=[{"role": "user", "content": final_prompt}]
    )

    html = ""
    for block in resp.content:
        if hasattr(block, "text"):
            html += block.text

    html = html.strip()
    if "```" in html:
        html = html.split("```html")[-1].split("```")[0].strip()
    if not html.startswith("<!DOCTYPE"):
        idx = html.find("<!DOCTYPE")
        if idx >= 0:
            html = html[idx:]

    log.info(f"HTML generado: {len(html)} caracteres")
    return html

def send_report():
    try:
        log.info("Enviando informe...")
        html = generate_report()

        filename = f"premercado_{datetime.now().strftime('%Y%m%d')}.html"
        filepath = f"/tmp/{filename}"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

        today_str = datetime.now().strftime("%d/%m/%Y")
        caption = (
            f"*Pre Mercado - {today_str}*\n"
            f"Abri el archivo en tu navegador.\n"
            f"Para PDF: Menu Imprimir, activar Graficos de fondo."
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
            log.info("Informe enviado OK")

        asyncio.run(send_async())

    except Exception as e:
        log.error(f"Error: {e}")
        try:
            async def send_error():
                async with Bot(token=TELEGRAM_TOKEN) as bot:
                    await bot.send_message(
                        chat_id=CHAT_ID,
                        text=f"Error generando el pre mercado: {str(e)}"
                    )
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
                        "text": "Bot Pre Mercado activo\n\n/ahora - Generar informe ahora\n/start - Ver ayuda\n\nRecibiras el informe todos los dias a las 7:00 hs Argentina."
                    })
                elif text == "/ahora":
                    requests.post(f"{bot_url}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": "Generando informe con datos en tiempo real, dame 2 minutos..."
                    })
                    threading.Thread(target=send_report, daemon=True).start()
        except Exception as e:
            log.error(f"Error polling: {e}")
            time.sleep(5)

def run_scheduler():
    schedule.every().day.at("10:00").do(send_report)
    log.info("Scheduler: 7:00 hs ARG (10:00 UTC)")
    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == "__main__":
    log.info("Bot iniciando...")
    if not all([TELEGRAM_TOKEN, CHAT_ID, ANTHROPIC_KEY]):
        log.error("Faltan variables: TELEGRAM_TOKEN, CHAT_ID, ANTHROPIC_KEY")
        exit(1)

    try:
        async def send_start():
            async with Bot(token=TELEGRAM_TOKEN) as bot:
                await bot.send_message(
                    chat_id=CHAT_ID,
                    text="Bot Pre Mercado activo\n\nEscribi /ahora para generar el informe ahora mismo.\nCada dia a las 7:00 hs lo recibis automaticamente."
                )
        asyncio.run(send_start())
    except Exception as e:
        log.warning(f"Inicio: {e}")

    threading.Thread(target=handle_telegram_updates, daemon=True).start()
    threading.Thread(target=run_scheduler, daemon=True).start()

    log.info("Bot corriendo...")
    while True:
        time.sleep(60)
