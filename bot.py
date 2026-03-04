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

def get_prices():
    symbols = [
        "ES=F","NQ=F","YM=F","CL=F","BZ=F","GC=F","BTC-USD",
        "^VIX","DX-Y.NYB","^BVSP","BRL=X","^N225","^HSI",
        "^AXJO","^KS11","^GDAXI","^FCHI",
        "GGAL","BMA","BBAR","YPF","PAM","EDN","TGS","TEO","TS"
    ]
    headers = {"User-Agent": "Mozilla/5.0"}
    prices = {}
    try:
        url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={','.join(symbols)}"
        resp = requests.get(url, headers=headers, timeout=15)
        quotes = resp.json().get("quoteResponse", {}).get("result", [])
        for q in quotes:
            prices[q["symbol"]] = {
                "p": round(q.get("regularMarketPrice", 0), 2),
                "c": round(q.get("regularMarketChangePercent", 0), 2)
            }
        log.info(f"Precios OK: {len(prices)} activos")
    except Exception as e:
        log.warning(f"Yahoo error: {e}")
    return prices

def generate_report():
    log.info("Obteniendo precios...")
    prices = get_prices()
    today = datetime.now().strftime("%d/%m/%Y")

    # Formatear precios en forma muy compacta
    def p(sym):
        d = prices.get(sym, {})
        if not d:
            return "N/D"
        sign = "+" if d["c"] >= 0 else ""
        return f"{d['p']} ({sign}{d['c']}%)"

    data = f"""DATOS {today}:
SP500={p("ES=F")} NQ={p("NQ=F")} DOW={p("YM=F")}
WTI={p("CL=F")} BRENT={p("BZ=F")} ORO={p("GC=F")} BTC={p("BTC-USD")}
VIX={p("^VIX")} DXY={p("DX-Y.NYB")}
IBOV={p("^BVSP")} BRL={p("BRL=X")}
NIKKEI={p("^N225")} HANGSENG={p("^HSI")} ASX={p("^AXJO")} KOSPI={p("^KS11")}
DAX={p("^GDAXI")} CAC={p("^FCHI")}
GGAL={p("GGAL")} BMA={p("BMA")} BBAR={p("BBAR")} YPF={p("YPF")}
PAM={p("PAM")} EDN={p("EDN")} TGS={p("TGS")} TEO={p("TEO")} TS={p("TS")}"""

    prompt = f"""Genera informe PRE MERCADO en HTML con estos datos reales:

{data}

Agrega: riesgo pais Argentina ~550pb, bonos GD30/AL30, noticias del dia, calendario economico.

HTML con: fondo #111827, cards #1c2638, verde #34d399, rojo #f87171, dorado #fbbf24. Google Fonts IBM Plex Sans+Mono+Bebas Neue. Header sticky PREMERCADO punto LIVE. Cards con stripe color arriba y barra progreso. Panel petroleo destacado. Panel riesgo pais rojo. Tabla ADRs. Bolsas Asia y Europa. Calendario con hora ET y ARG. Noticias con borde color. print-color-adjust exact. Mobile-first 720px.

Solo HTML. Empieza <!DOCTYPE html> termina </html>."""

    log.info(f"Prompt: {len(prompt)} chars. Generando HTML...")
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=7000,
        messages=[{"role": "user", "content": prompt}]
    )

    html = "".join(b.text for b in resp.content if hasattr(b, "text")).strip()
    if "```" in html:
        for part in html.split("```"):
            if "<!DOCTYPE" in part:
                html = part.replace("html","",1).strip()
                break
    idx = html.find("<!DOCTYPE")
    if idx > 0:
        html = html[idx:]

    log.info(f"HTML listo: {len(html)} chars")
    return html

def send_report():
    try:
        html = generate_report()
        filename = f"premercado_{datetime.now().strftime('%Y%m%d')}.html"
        filepath = f"/tmp/{filename}"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)
        async def send_async():
            async with Bot(token=TELEGRAM_TOKEN) as bot:
                with open(filepath, "rb") as f:
                    await bot.send_document(
                        chat_id=CHAT_ID, document=f, filename=filename,
                        caption=f"Pre Mercado {datetime.now().strftime('%d/%m/%Y')} - Abri en navegador. PDF: Imprimir > Graficos de fondo."
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
            for update in resp.json().get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message", {})
                text = msg.get("text", "")
                chat_id = msg.get("chat", {}).get("id")
                if not chat_id:
                    continue
                if text == "/start":
                    requests.post(f"{bot_url}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": "Bot Pre Mercado activo\nPrecios en tiempo real de Yahoo Finance\n\n/ahora - Generar informe\n/start - Ayuda\n\nAutomatico 7:00 hs Argentina."
                    })
                elif text == "/ahora":
                    requests.post(f"{bot_url}/sendMessage", json={
                        "chat_id": chat_id, "text": "Generando informe con precios reales, dame 1 minuto..."
                    })
                    threading.Thread(target=send_report, daemon=True).start()
        except Exception as e:
            log.error(f"Polling: {e}")
            time.sleep(5)

def run_scheduler():
    schedule.every().day.at("10:00").do(send_report)
    log.info("Scheduler: 7:00 ARG")
    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == "__main__":
    log.info("Bot iniciando...")
    if not all([TELEGRAM_TOKEN, CHAT_ID, ANTHROPIC_KEY]):
        log.error("Faltan variables")
        exit(1)
    try:
        async def send_start():
            async with Bot(token=TELEGRAM_TOKEN) as bot:
                await bot.send_message(chat_id=CHAT_ID,
                    text="Bot Pre Mercado activo. /ahora para el informe. Automatico 7:00 hs ARG.")
        asyncio.run(send_start())
    except Exception as e:
        log.warning(f"Start: {e}")
    threading.Thread(target=handle_telegram_updates, daemon=True).start()
    threading.Thread(target=run_scheduler, daemon=True).start()
    log.info("Corriendo...")
    while True:
        time.sleep(60)
