import os
import asyncio
import logging
from datetime import datetime
import requests
from telegram import Bot
import schedule
import time
import threading
from openai import OpenAI

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID        = os.environ.get("CHAT_ID")
OPENAI_KEY     = os.environ.get("OPENAI_KEY")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

def get_price_single(symbol):
    """Obtiene precio de un simbolo via Yahoo Finance v8"""
    try:
        url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://finance.yahoo.com"
        }
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        meta = data["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice", 0)
        pct   = meta.get("regularMarketChangePercent", 0)
        return {"p": round(price, 2), "c": round(pct, 2)}
    except Exception as e:
        log.warning(f"Error {symbol}: {e}")
        return None

def get_all_prices():
    symbols = {
        "ES=F":     "SP500",
        "NQ=F":     "NASDAQ",
        "YM=F":     "DOW",
        "CL=F":     "WTI",
        "BZ=F":     "BRENT",
        "GC=F":     "ORO",
        "BTC-USD":  "BTC",
        "^VIX":     "VIX",
        "DX-Y.NYB": "DXY",
        "^BVSP":    "IBOVESPA",
        "BRL=X":    "USDBRL",
        "^N225":    "NIKKEI",
        "^HSI":     "HANGSENG",
        "^AXJO":    "ASX200",
        "^KS11":    "KOSPI",
        "^GDAXI":   "DAX",
        "^FCHI":    "CAC40",
        "GGAL":     "GGAL",
        "BMA":      "BMA",
        "BBAR":     "BBAR",
        "YPF":      "YPF",
        "PAM":      "PAM",
        "EDN":      "EDN",
        "TGS":      "TGS",
        "TEO":      "TEO",
        "TS":       "TS",
    }
    prices = {}
    for sym, name in symbols.items():
        d = get_price_single(sym)
        if d:
            prices[name] = d
            log.info(f"  {name}: {d['p']} ({d['c']}%)")
        time.sleep(0.3)  # evitar rate limit de Yahoo
    log.info(f"Total precios: {len(prices)}/{len(symbols)}")
    return prices

def fmt(prices, name):
    d = prices.get(name)
    if not d:
        return "N/D"
    sign = "+" if d["c"] >= 0 else ""
    return f"{d['p']} ({sign}{d['c']}%)"

def generate_report():
    log.info("Obteniendo precios...")
    prices = get_all_prices()
    today = datetime.now().strftime("%A %d de %B de %Y")

    data = f"""PRECIOS REALES {datetime.now().strftime('%d/%m/%Y')}:
SP500={fmt(prices,'SP500')} | NASDAQ={fmt(prices,'NASDAQ')} | DOW={fmt(prices,'DOW')}
WTI={fmt(prices,'WTI')} | BRENT={fmt(prices,'BRENT')} | ORO={fmt(prices,'ORO')} | BTC={fmt(prices,'BTC')}
VIX={fmt(prices,'VIX')} | DXY={fmt(prices,'DXY')}
IBOVESPA={fmt(prices,'IBOVESPA')} | USD/BRL={fmt(prices,'USDBRL')}
NIKKEI={fmt(prices,'NIKKEI')} | HANGSENG={fmt(prices,'HANGSENG')} | ASX200={fmt(prices,'ASX200')} | KOSPI={fmt(prices,'KOSPI')}
DAX={fmt(prices,'DAX')} | CAC40={fmt(prices,'CAC40')}
GGAL={fmt(prices,'GGAL')} | BMA={fmt(prices,'BMA')} | BBAR={fmt(prices,'BBAR')} | YPF={fmt(prices,'YPF')}
PAM={fmt(prices,'PAM')} | EDN={fmt(prices,'EDN')} | TGS={fmt(prices,'TGS')} | TEO={fmt(prices,'TEO')} | TS={fmt(prices,'TS')}"""

    prompt = f"""Hoy es {today}. Genera informe PRE MERCADO completo en HTML con estos precios reales:

{data}

Completa con: riesgo pais Argentina ~550pb, bonos GD30 ~80 AL30 ~75 GD46 ~56, contexto geopolitico actual, noticias importantes del dia, calendario economico con hora ET y Argentina.

DISENO HTML obligatorio:
- Fondo #111827, cards #1c2638, bordes #2e3f58, texto #e2e8f0
- Verde #34d399, rojo #f87171, dorado #fbbf24
- Google Fonts IBM Plex Sans + IBM Plex Mono + Bebas Neue
- Header sticky oscuro, logo PREMERCADO en Bebas Neue, punto rojo parpadeante LIVE
- Cada card con stripe 3px arriba (verde=sube rojo=baja dorado=neutro) y barra progreso
- Panel petroleo WTI y Brent: fondo #0d1f3c lado a lado precio grande
- Panel riesgo pais: fondo #1e0909 numero grande en rojo #f87171
- Tabla ADRs con empresa precio variacion tendencia
- Seccion bolsas Asia y Europa separadas con emojis bandera
- Calendario lista vertical hora ET y ARG badge impacto coloreado
- Noticias cards borde izquierdo coloreado por categoria
- @media print print-color-adjust exact para PDF oscuro
- Mobile-first max-width 720px

Responde SOLO con HTML. Empieza <!DOCTYPE html> termina </html>."""

    log.info("Generando HTML con OpenAI...")
    client = OpenAI(api_key=OPENAI_KEY)
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=7000,
        messages=[
            {"role": "system", "content": "Eres experto en mercados financieros. Generas HTML completo y bien disenado. Solo respondes con HTML valido, sin markdown."},
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
        log.info("Generando y enviando...")
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
                        "text": "Generando informe con precios reales, dame 2 minutos..."
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
                    text="Bot Pre Mercado activo.\nEscribi /ahora para el informe.\nAutomatico 7:00 hs ARG."
                )
        asyncio.run(send_start())
    except Exception as e:
        log.warning(f"Start: {e}")
    threading.Thread(target=handle_telegram_updates, daemon=True).start()
    threading.Thread(target=run_scheduler, daemon=True).start()
    log.info("Corriendo...")
    while True:
        time.sleep(60)
