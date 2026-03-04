import os
import asyncio
import logging
from datetime import datetime
import requests
from telegram import Bot
from telegram.constants import ParseMode
import schedule
import time
import threading
from openai import OpenAI

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID        = os.environ.get("CHAT_ID")
OPENAI_KEY     = os.environ.get("OPENAI_KEY")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

def get_prices():
    symbols = [
        "ES=F","NQ=F","YM=F","CL=F","BZ=F","GC=F","BTC-USD",
        "^VIX","DX-Y.NYB","^BVSP","BRL=X",
        "^N225","^HSI","^AXJO","^KS11","^GDAXI","^FCHI",
        "GGAL","BMA","BBAR","YPF","PAM","EDN","TGS","TEO","TS"
    ]
    headers = {"User-Agent": "Mozilla/5.0"}
    prices = {}
    try:
        url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={','.join(symbols)}"
        resp = requests.get(url, headers=headers, timeout=15)
        for q in resp.json().get("quoteResponse", {}).get("result", []):
            prices[q["symbol"]] = {
                "p": round(q.get("regularMarketPrice", 0), 2),
                "c": round(q.get("regularMarketChangePercent", 0), 2)
            }
        log.info(f"Precios OK: {len(prices)} activos")
    except Exception as e:
        log.warning(f"Yahoo error: {e}")
    return prices

def generate_report():
    log.info("Obteniendo precios Yahoo Finance...")
    prices = get_prices()
    today = datetime.now().strftime("%A %d de %B de %Y")

    def p(sym):
        d = prices.get(sym, {})
        if not d: return "N/D"
        sign = "+" if d["c"] >= 0 else ""
        return f"{d['p']} ({sign}{d['c']}%)"

    data = f"""PRECIOS REALES HOY {datetime.now().strftime('%d/%m/%Y')}:
SP500={p("ES=F")} | NASDAQ={p("NQ=F")} | DOW={p("YM=F")}
WTI={p("CL=F")} | BRENT={p("BZ=F")} | ORO={p("GC=F")} | BTC={p("BTC-USD")}
VIX={p("^VIX")} | DXY={p("DX-Y.NYB")}
IBOVESPA={p("^BVSP")} | USD/BRL={p("BRL=X")}
NIKKEI={p("^N225")} | HANGSENG={p("^HSI")} | ASX200={p("^AXJO")} | KOSPI={p("^KS11")}
DAX={p("^GDAXI")} | CAC40={p("^FCHI")}
GGAL={p("GGAL")} | BMA={p("BMA")} | BBAR={p("BBAR")} | YPF={p("YPF")}
PAM={p("PAM")} | EDN={p("EDN")} | TGS={p("TGS")} | TEO={p("TEO")} | TS={p("TS")}"""

    prompt = f"""Hoy es {today}. Genera un informe PRE MERCADO completo en HTML usando estos precios reales:

{data}

Completa con tu conocimiento: riesgo pais Argentina, bonos GD30/AL30/GD46, contexto geopolitico actual, noticias importantes del dia, calendario economico con hora ET y Argentina.

DISENO HTML:
- Fondo #111827, cards #1c2638, bordes #2e3f58, texto #e2e8f0
- Verde #34d399, rojo #f87171, dorado #fbbf24
- Google Fonts: IBM Plex Sans, IBM Plex Mono, Bebas Neue
- Header sticky fondo oscuro, logo PREMERCADO en Bebas Neue, punto rojo parpadeante LIVE
- Cards con stripe 3px arriba (verde sube, rojo baja, dorado neutro) y barra progreso
- Panel petroleo WTI y Brent destacado fondo azul marino
- Panel riesgo pais fondo rojo oscuro numero grande
- Tabla ADRs con variacion y tendencia
- Bolsas Asia y Europa en tablas separadas con emojis de bandera
- Calendario economico lista vertical hora ET y ARG con badge impacto coloreado
- Noticias con borde izquierdo de color por categoria
- @media print print-color-adjust exact para PDF oscuro
- Mobile-first max-width 720px centrado

Responde SOLO con HTML completo. Empieza <!DOCTYPE html> termina </html>."""

    log.info("Generando HTML con OpenAI...")
    client = OpenAI(api_key=OPENAI_KEY)
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=7000,
        messages=[
            {"role": "system", "content": "Eres un experto en mercados financieros. Generates informes HTML completos y bien disenados. Respondes SOLO con HTML valido."},
            {"role": "user", "content": prompt}
        ]
    )

    html = resp.choices[0].message.content.strip()
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
        log.info("Enviando informe...")
        html = generate_report()
        filename = f"premercado_{datetime.now().strftime('%Y%m%d')}.html"
        filepath = f"/tmp/{filename}"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

        async def send_async():
            async with Bot(token=TELEGRAM_TOKEN) as bot:
                with open(filepath, "rb") as f:
                    await bot.send_document(
                        chat_id=CHAT_ID,
                        document=f,
                        filename=filename,
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
                        "chat_id": chat_id,
                        "text": "Generando informe con precios reales, dame 1 minuto..."
                    })
                    threading.Thread(target=send_report, daemon=True).start()
        except Exception as e:
            log.error(f"Polling: {e}")
            time.sleep(5)

def run_scheduler():
    schedule.every().day.at("10:00").do(send_report)
    log.info("Scheduler: 7:00 ARG (10:00 UTC)")
    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == "__main__":
    log.info("Bot iniciando...")
    if not all([TELEGRAM_TOKEN, CHAT_ID, OPENAI_KEY]):
        log.error("Faltan variables: TELEGRAM_TOKEN, CHAT_ID, OPENAI_KEY")
        exit(1)
    try:
        async def send_start():
            async with Bot(token=TELEGRAM_TOKEN) as bot:
                await bot.send_message(
                    chat_id=CHAT_ID,
                    text="Bot Pre Mercado activo con OpenAI + Yahoo Finance.\nEscribi /ahora para el informe.\nAutomatico 7:00 hs ARG."
                )
        asyncio.run(send_start())
    except Exception as e:
        log.warning(f"Start: {e}")
    threading.Thread(target=handle_telegram_updates, daemon=True).start()
    threading.Thread(target=run_scheduler, daemon=True).start()
    log.info("Corriendo...")
    while True:
        time.sleep(60)
