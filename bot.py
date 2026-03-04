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

TELEGRAM_TOKEN  = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID         = os.environ.get("CHAT_ID")
OPENAI_KEY      = os.environ.get("OPENAI_KEY")
FINNHUB_KEY     = os.environ.get("FINNHUB_KEY")
ALPHAVANTAGE_KEY = os.environ.get("ALPHAVANTAGE_KEY")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── FINNHUB — acciones y crypto ───────────────────────────
def get_finnhub(symbol):
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_KEY}"
        d = requests.get(url, timeout=8).json()
        price = d.get("c", 0)
        prev  = d.get("pc", price)
        pct   = ((price - prev) / prev * 100) if prev else 0
        if price > 0:
            return {"p": round(price, 2), "c": round(pct, 2)}
    except Exception as e:
        log.warning(f"Finnhub {symbol}: {e}")
    return None

# ── ALPHA VANTAGE — futuros y commodities ─────────────────
def get_alphavantage(symbol, function="GLOBAL_QUOTE"):
    try:
        url = f"https://www.alphavantage.co/query?function={function}&symbol={symbol}&apikey={ALPHAVANTAGE_KEY}"
        d = requests.get(url, timeout=10).json()
        quote = d.get("Global Quote", {})
        price = float(quote.get("05. price", 0))
        pct   = float(quote.get("10. change percent", "0%").replace("%",""))
        if price > 0:
            return {"p": round(price, 2), "c": round(pct, 2)}
    except Exception as e:
        log.warning(f"AlphaVantage {symbol}: {e}")
    return None

def get_all_prices():
    prices = {}

    # ADRs argentinos via Finnhub
    adrs = {
        "GGAL": "GGAL", "BMA": "BMA", "BBAR": "BBAR",
        "YPF": "YPF", "PAM": "PAM", "EDN": "EDN",
        "TGS": "TGS", "TEO": "TEO", "TS": "TS"
    }
    for sym, name in adrs.items():
        d = get_finnhub(sym)
        if d:
            prices[name] = d
            log.info(f"  {name}: {d['p']} ({d['c']:+.2f}%)")
        time.sleep(0.15)

    # Crypto via Finnhub
    btc = get_finnhub("BINANCE:BTCUSDT")
    if btc:
        prices["BTC"] = btc
        log.info(f"  BTC: {btc['p']} ({btc['c']:+.2f}%)")

    # ETF Brasil via Finnhub
    ewz = get_finnhub("EWZ")
    if ewz:
        prices["EWZ"] = ewz
        log.info(f"  EWZ (Brasil ETF): {ewz['p']} ({ewz['c']:+.2f}%)")

    # Futuros e indices via Alpha Vantage
    av_symbols = {
        "SPY":  "SP500_ETF",
        "QQQ":  "NASDAQ_ETF",
        "DIA":  "DOW_ETF",
        "USO":  "WTI_ETF",
        "BNO":  "BRENT_ETF",
        "GLD":  "ORO_ETF",
        "UUP":  "DXY_ETF",
        "VIXY": "VIX_ETF",
    }
    for sym, name in av_symbols.items():
        d = get_alphavantage(sym)
        if d:
            prices[name] = d
            log.info(f"  {name}: {d['p']} ({d['c']:+.2f}%)")
        time.sleep(0.5)  # Alpha Vantage rate limit

    log.info(f"Total precios: {len(prices)}")
    return prices

def fmt(prices, name):
    d = prices.get(name)
    if not d or d["p"] == 0:
        return "N/D"
    arrow = "▲" if d["c"] >= 0 else "▼"
    sign  = "+" if d["c"] >= 0 else ""
    return f"{d['p']} {arrow}{sign}{d['c']:.2f}%"

def generate_report():
    log.info("Obteniendo precios...")
    prices = get_all_prices()
    today = datetime.now().strftime("%A %d de %B de %Y")

    data = f"""PRECIOS REALES {datetime.now().strftime('%d/%m/%Y')}:
INDICES (ETFs): SP500={fmt(prices,'SP500_ETF')} | NASDAQ={fmt(prices,'NASDAQ_ETF')} | DOW={fmt(prices,'DOW_ETF')}
ENERGIA: WTI={fmt(prices,'WTI_ETF')} | BRENT={fmt(prices,'BRENT_ETF')}
METALES/CRIPTO: ORO={fmt(prices,'ORO_ETF')} | BTC={fmt(prices,'BTC')}
DOLAR/VOL: DXY={fmt(prices,'DXY_ETF')} | VIX={fmt(prices,'VIX_ETF')}
BRASIL ETF: EWZ={fmt(prices,'EWZ')}
ADRs ARGENTINOS:
GGAL={fmt(prices,'GGAL')} | BMA={fmt(prices,'BMA')} | BBAR={fmt(prices,'BBAR')} | YPF={fmt(prices,'YPF')}
PAM={fmt(prices,'PAM')} | EDN={fmt(prices,'EDN')} | TGS={fmt(prices,'TGS')} | TEO={fmt(prices,'TEO')} | TS={fmt(prices,'TS')}"""

    prompt = f"""Hoy es {today}. Genera informe PRE MERCADO completo en HTML con estos precios reales:

{data}

IMPORTANTE: Los ETFs son proxies de los indices reales:
- SPY ~= S&P 500 (multiplicar x10 aprox)
- QQQ ~= Nasdaq 100
- DIA ~= Dow Jones (multiplicar x100 aprox)
- USO ~= WTI Crude Oil
- GLD ~= Oro (dividir x10 aprox para precio real)
Muestra los valores reales de los indices estimados a partir de estos ETFs.

Completa con tu conocimiento:
- Nikkei, Hang Seng, ASX200, Kospi, DAX, CAC40, FTSE cierres de hoy
- Riesgo pais Argentina ~550pb
- Bonos GD30 ~80 AL30 ~75 GD46 ~56
- Contexto geopolitico actual (guerra EEUU-Israel-Iran, Ormuz cerrado dia 5)
- Noticias importantes del dia
- Calendario economico con hora ET y Argentina

DISENO HTML:
- Fondo #111827, cards #1c2638, bordes #2e3f58, texto #e2e8f0
- Verde #34d399, rojo #f87171, dorado #fbbf24
- Google Fonts IBM Plex Sans + IBM Plex Mono + Bebas Neue
- Header sticky oscuro logo PREMERCADO Bebas Neue punto rojo parpadeante LIVE
- Cards con stripe 3px arriba (verde=sube rojo=baja dorado=neutro) y barra progreso
- Panel petroleo WTI y Brent fondo #0d1f3c lado a lado precio grande
- Panel riesgo pais fondo #1e0909 numero grande rojo
- Tabla ADRs con empresa precio variacion tendencia coloreada
- Bolsas Asia y Europa separadas con emojis bandera
- Calendario lista vertical hora ET y ARG badge impacto coloreado
- Noticias borde izquierdo coloreado por categoria
- @media print print-color-adjust exact PDF oscuro
- Mobile-first max-width 720px

SOLO HTML. Empieza <!DOCTYPE html> termina </html>."""

    log.info("Generando HTML con OpenAI...")
    client = OpenAI(api_key=OPENAI_KEY)
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=7000,
        messages=[
            {"role": "system", "content": "Eres experto en mercados financieros latinoamericanos. Generas HTML completo y profesional. Solo respondes con HTML valido sin markdown."},
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
        log.info("Generando informe...")
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
                        caption=f"Pre Mercado {datetime.now().strftime('%d/%m/%Y')} — Abri en navegador. PDF: Imprimir > Graficos de fondo."
                    )
            log.info("Enviado OK")
        asyncio.run(send_async())
    except Exception as e:
        log.error(f"Error: {e}")
        try:
            async def send_err():
                async with Bot(token=TELEGRAM_TOKEN) as bot:
                    await bot.send_message(chat_id=CHAT_ID, text=f"Error: {str(e)}")
            asyncio.run(send_err())
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
                        "text": "Bot Pre Mercado activo\nFinnhub + Alpha Vantage\n\n/ahora - Generar informe\n/start - Ayuda\n\nAutomatico 7:00 hs Argentina."
                    })
                elif text == "/ahora":
                    requests.post(f"{bot_url}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": "Obteniendo precios reales, dame 3 minutos..."
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
    if not all([TELEGRAM_TOKEN, CHAT_ID, OPENAI_KEY, FINNHUB_KEY, ALPHAVANTAGE_KEY]):
        log.error("Faltan variables: TELEGRAM_TOKEN, CHAT_ID, OPENAI_KEY, FINNHUB_KEY, ALPHAVANTAGE_KEY")
        exit(1)
    try:
        async def send_start():
            async with Bot(token=TELEGRAM_TOKEN) as bot:
                await bot.send_message(chat_id=CHAT_ID,
                    text="Bot Pre Mercado v10 activo.\nFinnhub + Alpha Vantage + OpenAI\n/ahora para el informe.\nAutomatico 7:00 hs ARG.")
        asyncio.run(send_start())
    except Exception as e:
        log.warning(f"Start: {e}")
    threading.Thread(target=handle_telegram_updates, daemon=True).start()
    threading.Thread(target=run_scheduler, daemon=True).start()
    log.info("Corriendo...")
    while True:
        time.sleep(60)
