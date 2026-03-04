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
FINNHUB_KEY    = os.environ.get("FINNHUB_KEY")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

def get_finnhub(symbol):
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_KEY}"
        r = requests.get(url, timeout=8)
        d = r.json()
        price = d.get("c", 0)
        prev  = d.get("pc", price)
        pct   = ((price - prev) / prev * 100) if prev else 0
        return {"p": round(price, 2), "c": round(pct, 2)}
    except Exception as e:
        log.warning(f"Finnhub {symbol}: {e}")
        return None

def get_all_prices():
    symbols = {
        # Futuros indices
        "ES1!":    "SP500",
        "NQ1!":    "NASDAQ",
        "YM1!":    "DOW",
        # Commodities
        "CL1!":    "WTI",
        "BZ1!":    "BRENT",
        "GC1!":    "ORO",
        "BINANCE:BTCUSDT": "BTC",
        # Macro
        "^VIX":    "VIX",
        # ADRs Argentina
        "GGAL":    "GGAL",
        "BMA":     "BMA",
        "BBAR":    "BBAR",
        "YPF":     "YPF",
        "PAM":     "PAM",
        "EDN":     "EDN",
        "TGS":     "TGS",
        "TEO":     "TEO",
        "TS":      "TS",
        # Brasil
        "EWZ":     "IBOVESPA_ETF",
        # Europa ETFs
        "EWG":     "DAX_ETF",
        "EWQ":     "CAC_ETF",
        "EWU":     "FTSE_ETF",
    }
    prices = {}
    for sym, name in symbols.items():
        d = get_finnhub(sym)
        if d and d["p"] > 0:
            prices[name] = d
            log.info(f"  {name}: {d['p']} ({d['c']:+.2f}%)")
        time.sleep(0.15)
    log.info(f"Precios obtenidos: {len(prices)}/{len(symbols)}")
    return prices

def fmt(prices, name):
    d = prices.get(name)
    if not d or d["p"] == 0:
        return "N/D"
    sign = "+" if d["c"] >= 0 else ""
    return f"{d['p']} ({sign}{d['c']:.2f}%)"

def generate_report():
    log.info("Obteniendo precios Finnhub...")
    prices = get_all_prices()
    today = datetime.now().strftime("%A %d de %B de %Y")

    data = f"""PRECIOS REALES {datetime.now().strftime('%d/%m/%Y')} — Fuente: Finnhub
FUTUROS: SP500={fmt(prices,'SP500')} | NASDAQ={fmt(prices,'NASDAQ')} | DOW={fmt(prices,'DOW')}
ENERGIA: WTI={fmt(prices,'WTI')} | BRENT={fmt(prices,'BRENT')}
METALES/CRIPTO: ORO={fmt(prices,'ORO')} | BTC={fmt(prices,'BTC')}
ADRs ARGENTINOS: GGAL={fmt(prices,'GGAL')} | BMA={fmt(prices,'BMA')} | BBAR={fmt(prices,'BBAR')} | YPF={fmt(prices,'YPF')}
PAM={fmt(prices,'PAM')} | EDN={fmt(prices,'EDN')} | TGS={fmt(prices,'TGS')} | TEO={fmt(prices,'TEO')} | TS={fmt(prices,'TS')}
ETFs REF: Brasil ETF={fmt(prices,'IBOVESPA_ETF')} | DAX ETF={fmt(prices,'DAX_ETF')} | CAC ETF={fmt(prices,'CAC_ETF')}"""

    prompt = f"""Hoy es {today}. Genera informe PRE MERCADO completo en HTML con estos precios reales:

{data}

Completa con tu conocimiento actualizado:
- VIX nivel de miedo actual
- DXY dolar index
- Riesgo pais Argentina ~550pb
- Bonos GD30 ~80 AL30 ~75 GD46 ~56
- Nikkei, Hang Seng, ASX200, Kospi cierres de hoy
- Contexto geopolitico actual (guerra EEUU-Israel-Iran, Ormuz)
- Noticias importantes del dia
- Calendario economico de hoy con hora ET y Argentina

DISENO HTML obligatorio:
- Fondo #111827, cards #1c2638, bordes #2e3f58, texto #e2e8f0
- Verde #34d399, rojo #f87171, dorado #fbbf24
- Google Fonts IBM Plex Sans + IBM Plex Mono + Bebas Neue
- Header sticky oscuro logo PREMERCADO Bebas Neue punto rojo parpadeante LIVE
- Cards con stripe 3px arriba (verde=sube rojo=baja dorado=neutro) y barra progreso
- Panel petroleo WTI y Brent fondo #0d1f3c lado a lado precio grande blanco
- Panel riesgo pais fondo #1e0909 numero grande rojo #f87171
- Tabla ADRs empresa precio variacion % tendencia con color
- Seccion bolsas Asia y Europa con emojis bandera
- Calendario lista vertical hora ET y ARG badge impacto coloreado
- Noticias borde izquierdo coloreado por categoria
- @media print print-color-adjust exact PDF oscuro
- Mobile-first max-width 720px

Responde SOLO con HTML. Empieza <!DOCTYPE html> termina </html>."""

    log.info("Generando HTML con OpenAI...")
    client = OpenAI(api_key=OPENAI_KEY)
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=7000,
        messages=[
            {"role": "system", "content": "Eres experto en mercados financieros latinoamericanos. Generas HTML completo y bien disenado. Solo respondes con HTML valido sin markdown ni explicaciones."},
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
                        chat_id=CHAT_ID,
                        document=f,
                        filename=filename,
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
                        "text": "Bot Pre Mercado activo\nPrecios en tiempo real de Finnhub\n\n/ahora - Generar informe\n/start - Ayuda\n\nAutomatico 7:00 hs Argentina."
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
    if not all([TELEGRAM_TOKEN, CHAT_ID, OPENAI_KEY, FINNHUB_KEY]):
        log.error("Faltan variables: TELEGRAM_TOKEN, CHAT_ID, OPENAI_KEY, FINNHUB_KEY")
        exit(1)
    try:
        async def send_start():
            async with Bot(token=TELEGRAM_TOKEN) as bot:
                await bot.send_message(
                    chat_id=CHAT_ID,
                    text="Bot Pre Mercado activo con Finnhub.\nEscribi /ahora para el informe.\nAutomatico 7:00 hs ARG."
                )
        asyncio.run(send_start())
    except Exception as e:
        log.warning(f"Start: {e}")
    threading.Thread(target=handle_telegram_updates, daemon=True).start()
    threading.Thread(target=run_scheduler, daemon=True).start()
    log.info("Corriendo...")
    while True:
        time.sleep(60)
