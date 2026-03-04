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
import json

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID        = os.environ.get("CHAT_ID")
ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_KEY")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── FETCH PRECIOS YAHOO FINANCE ───────────────────────────
def get_prices():
    symbols = {
        # Futuros indices
        "ES=F":  "SP500_fut",
        "NQ=F":  "Nasdaq_fut",
        "YM=F":  "Dow_fut",
        # Commodities
        "CL=F":  "WTI",
        "BZ=F":  "Brent",
        "GC=F":  "Oro",
        "BTC-USD": "Bitcoin",
        # Volatilidad y dolar
        "^VIX":  "VIX",
        "DX-Y.NYB": "DXY",
        # Brasil
        "^BVSP": "Ibovespa",
        "BRL=X": "USDBRL",
        # Asia
        "^N225": "Nikkei",
        "^HSI":  "HangSeng",
        "000001.SS": "Shanghai",
        "^AXJO": "ASX200",
        "^KS11": "Kospi",
        # Europa
        "^FTSE": "FTSE100",
        "^GDAXI": "DAX",
        "^FCHI": "CAC40",
        # ADRs Argentina
        "GGAL":  "GGAL",
        "BMA":   "BMA",
        "BBAR":  "BBAR",
        "SUPV":  "SUPV",
        "YPF":   "YPF",
        "PAM":   "PAM",
        "EDN":   "EDN",
        "TGS":   "TGS",
        "TEO":   "TEO",
        "TS":    "TS",
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    prices = {}
    symbols_str = "%2C".join(symbols.keys())

    try:
        url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbols_str}"
        resp = requests.get(url, headers=headers, timeout=15)
        data = resp.json()
        quotes = data.get("quoteResponse", {}).get("result", [])

        for quote in quotes:
            sym = quote.get("symbol", "")
        name = symbols.get(sym, sym)
        price = quote.get("regularMarketPrice", 0)
        change = quote.get("regularMarketChange", 0)
        pct = quote.get("regularMarketChangePercent", 0)
        prev = quote.get("regularMarketPreviousClose", 0)
        high = quote.get("regularMarketDayHigh", 0)
        low  = quote.get("regularMarketDayLow", 0)
        prices[name] = {
            "price": round(price, 2),
            "change": round(change, 2),
            "pct": round(pct, 2),
            "prev": round(prev, 2),
            "high": round(high, 2),
            "low":  round(low, 2),
            "symbol": sym
        }

        log.info(f"Precios obtenidos: {len(prices)} activos de Yahoo Finance")
    except Exception as e:
        log.warning(f"Yahoo Finance error: {e}")

    return prices

def format_prices_for_prompt(prices):
    if not prices:
        return "No se pudieron obtener precios en tiempo real."
    lines = ["PRECIOS EN TIEMPO REAL (Yahoo Finance):"]
    for name, d in prices.items():
        arrow = "+" if d['pct'] >= 0 else ""
        lines.append(f"- {name}: {d['price']} ({arrow}{d['pct']}%) | High: {d['high']} Low: {d['low']}")
    return "\n".join(lines)

# ── PROMPT ───────────────────────────────────────────────
def build_prompt(prices_text):
    today = datetime.now().strftime("%A %d de %B de %Y")
    return f"""Hoy es {today}.

{prices_text}

Con estos precios reales genera el informe de PRE MERCADO completo en HTML.
Completa con tu conocimiento: riesgo pais Argentina ~550pb, bonos GD30 ~80, AL30 ~75, contexto geopolitico actual, noticias importantes del dia, calendario economico de hoy con datos de EEUU.

DISENO HTML obligatorio:
- Fondo #111827, cards #1c2638, bordes #2e3f58
- Verde #34d399, rojo #f87171, dorado #fbbf24, texto #e2e8f0
- Google Fonts: IBM Plex Sans, IBM Plex Mono, Bebas Neue
- Header sticky fondo #0a1628, logo PREMERCADO en Bebas Neue, punto rojo animado LIVE
- Cada card con stripe 3px arriba (verde=sube rojo=baja dorado=neutro)
- Barra de progreso en cada card
- Panel especial petroleo: fondo #0d1f3c, WTI y Brent lado a lado, precio grande en blanco
- Panel riesgo pais: fondo #1e0909, numero grande en rojo
- Tabla ADRs: empresa, precio USD, variacion %, tendencia con barra mini
- Seccion bolsas mundiales: Asia-Pacifico y Europa en tablas separadas con flag emoji
- Calendario economico: lista vertical, hora ET y hora Argentina, badge impacto coloreado
- Noticias: cards con borde izquierdo coloreado por categoria
- @media print con print-color-adjust exact para que PDF salga oscuro
- Mobile-first responsive max-width 720px

Responde UNICAMENTE con el HTML completo. Empieza con <!DOCTYPE html> termina con </html>. Sin texto extra ni markdown."""

# ── GENERAR INFORME ───────────────────────────────────────
def generate_report():
    log.info("Obteniendo precios de Yahoo Finance...")
    prices = get_prices()
    prices_text = format_prices_for_prompt(prices)
    log.info("Generando HTML con Claude...")

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8000,
        messages=[{"role": "user", "content": build_prompt(prices_text)}]
    )

    html = ""
    for block in resp.content:
        if hasattr(block, "text"):
            html += block.text
    html = html.strip()

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

# ── ENVIAR POR TELEGRAM ───────────────────────────────────
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
                        caption=f"Pre Mercado {today_str} - Abri en navegador. Para PDF: Imprimir > activar Graficos de fondo."
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

# ── POLLING TELEGRAM ──────────────────────────────────────
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
                        "text": "Bot Pre Mercado activo\n\nPrecios en tiempo real de Yahoo Finance.\n\n/ahora - Generar informe ahora\n/start - Ayuda\n\nInforme automatico todos los dias a las 7:00 hs Argentina."
                    })
                elif text == "/ahora":
                    requests.post(f"{bot_url}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": "Obteniendo precios de Yahoo Finance y generando informe, dame 1 minuto..."
                    })
                    threading.Thread(target=send_report, daemon=True).start()
        except Exception as e:
            log.error(f"Polling error: {e}")
            time.sleep(5)

# ── SCHEDULER ────────────────────────────────────────────
def run_scheduler():
    schedule.every().day.at("10:00").do(send_report)
    log.info("Scheduler: 7:00 ARG (10:00 UTC)")
    while True:
        schedule.run_pending()
        time.sleep(30)

# ── MAIN ─────────────────────────────────────────────────
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
                    text="Bot Pre Mercado activo con precios Yahoo Finance en tiempo real.\n\nEscribi /ahora para el informe ahora.\nAutomatico todos los dias a las 7:00 hs ARG."
                )
        asyncio.run(send_start())
    except Exception as e:
        log.warning(f"Start: {e}")
    threading.Thread(target=handle_telegram_updates, daemon=True).start()
    threading.Thread(target=run_scheduler, daemon=True).start()
    log.info("Corriendo...")
    while True:
        time.sleep(60)
