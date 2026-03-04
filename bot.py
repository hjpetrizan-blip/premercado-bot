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
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID        = os.environ.get("CHAT_ID")
ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_KEY")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── PROMPT ──────────────────────────────────────────────
def build_prompt():
    today = datetime.now().strftime("%A %d de %B de %Y")
    return f"""
Hoy es {today}. Primero buscá en internet los precios actuales de mercado y luego generá el informe de PRE MERCADO completo en formato HTML.

Buscá específicamente:
- Futuros S&P500, Nasdaq, Dow Jones precios actuales
- WTI crude oil price today y Brent crude oil price today
- Gold price today XAU/USD
- Bitcoin price today BTC/USD
- VIX index today
- DXY dollar index today
- Nikkei, Hang Seng, Shanghai, ASX200, Kospi cierres hoy
- FTSE, DAX, CAC40 precios hoy
- Argentina riesgo pais EMBI hoy
- GD30 AL30 bonos argentinos precios hoy
- ADRs argentinos GGAL BMA BBAR YPF precios hoy
- Ibovespa USD/BRL hoy
- Noticias mercados financieros hoy

El informe debe incluir TODAS estas secciones con los datos reales que encontraste:

1. ÍNDICES FUTUROS: S&P500 (ES1!), Nasdaq 100 (NQ1!), Dow Jones (YM1!)
2. VIX y DXY
3. FUTUROS PETRÓLEO: WTI y Brent con precio, variación y rango del día
4. ORO y BITCOIN
5. BOLSAS MUNDIALES: Asia-Pacífico y Europa
6. BONOS Y RIESGO PAÍS ARGENTINA: EMBI, GD30, AL30, GD46, GD35
7. PRE ADRs ARGENTINOS: GGAL, BMA, BBAR, SUPV, YPF, PAM, EDN, TGS, TEO, TS
8. BRASIL: Ibovespa, USD/BRL, Tasa SELIC
9. CONTEXTO GEOPOLÍTICO del momento
10. CALENDARIO ECONÓMICO del día con hora ET y Argentina
11. NOTICIAS MÁS IMPORTANTES del día

DISEÑO HTML:
- Fondo oscuro azulado: #111827
- Superficie cards: #1c2638
- Verde suave: #34d399
- Rojo cálido: #f87171
- Dorado: #fbbf24
- Tipografía: IBM Plex Sans + IBM Plex Mono + Bebas Neue (Google Fonts)
- Barras de progreso en cada card
- Flechas arriba abajo para variaciones
- Mobile-first, responsive
- Stripes de color arriba de cada card
- @media print con print-color-adjust: exact para PDF oscuro
- Panel de petróleo destacado con fondo azul marino
- Riesgo país con panel rojo oscuro y número grande
- Sección de bolsas mundiales dividida en Asia y Europa
- Calendario como lista vertical con hora ET y ARG, badge de impacto
- Noticias con borde izquierdo de color según categoría
- Header sticky con logo PREMERCADO, punto LIVE rojo parpadeante

Respondé ÚNICAMENTE con el HTML completo, sin explicaciones, sin markdown.
El HTML debe empezar con <!DOCTYPE html> y terminar con </html>.
"""

# ── GENERAR INFORME CON WEB SEARCH ───────────────────────
def generate_report():
    log.info("Generando informe con web search...")
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    messages = [{"role": "user", "content": build_prompt()}]

    while True:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=8000,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=messages
        )

        log.info(f"Stop reason: {response.stop_reason}")

        if response.stop_reason == "end_turn":
            html = ""
            for block in response.content:
                if hasattr(block, "text"):
                    html += block.text
            html = html.strip()
            if html.startswith("```"):
                html = html.split("\n", 1)[1]
                html = html.rsplit("```", 1)[0]
            log.info(f"Informe generado: {len(html)} caracteres")
            return html

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    log.info(f"Buscando: {block.input.get('query', '')}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": "Search completed"
                    })
            messages.append({"role": "user", "content": tool_results})
        else:
            break

    raise Exception("No se pudo generar el informe")

# ── ENVIAR POR TELEGRAM ──────────────────────────────────
def send_report():
    try:
        log.info("Iniciando envio del informe...")
        html = generate_report()

        filename = f"premercado_{datetime.now().strftime('%Y%m%d')}.html"
        filepath = f"/tmp/{filename}"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

        today_str = datetime.now().strftime("%d/%m/%Y")
        caption = (
            f"*Pre Mercado - {today_str}*\n"
            f"Abri el archivo en tu navegador para verlo con el diseno completo.\n"
            f"Para PDF: Menu -> Imprimir -> Guardar como PDF\n"
            f"_(Activa 'Graficos de fondo' para mantener el fondo oscuro)_"
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
            log.info("Informe enviado exitosamente")

        asyncio.run(send_async())

    except Exception as e:
        log.error(f"Error enviando informe: {e}")
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

# ── POLLING TELEGRAM ─────────────────────────────────────
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
                        "text": (
                            "Bienvenido al Bot de Pre Mercado\n\n"
                            "Recibiras el informe automaticamente cada manana a las 7:00 hs (Argentina).\n\n"
                            "Comandos:\n"
                            "/ahora - Generar informe ahora mismo\n"
                            "/start - Ver este mensaje"
                        )
                    })

                elif text == "/ahora":
                    requests.post(f"{bot_url}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": "Generando el informe con datos en tiempo real, dame 2 minutos..."
                    })
                    threading.Thread(target=send_report, daemon=True).start()

        except Exception as e:
            log.error(f"Error en polling: {e}")
            time.sleep(5)

# ── SCHEDULER ────────────────────────────────────────────
def run_scheduler():
    schedule.every().day.at("10:00").do(send_report)
    log.info("Scheduler: informe diario a las 7:00 hs ARG (10:00 UTC)")
    while True:
        schedule.run_pending()
        time.sleep(30)

# ── MAIN ─────────────────────────────────────────────────
if __name__ == "__main__":
    log.info("Bot Pre Mercado iniciando...")

    if not all([TELEGRAM_TOKEN, CHAT_ID, ANTHROPIC_KEY]):
        log.error("Faltan variables de entorno: TELEGRAM_TOKEN, CHAT_ID, ANTHROPIC_KEY")
        exit(1)

    try:
        async def send_start():
            async with Bot(token=TELEGRAM_TOKEN) as bot:
                await bot.send_message(
                    chat_id=CHAT_ID,
                    text=(
                        "Bot Pre Mercado activo con web search\n\n"
                        "Recibiras el informe todos los dias a las 7:00 hs (Argentina).\n"
                        "Escribi /ahora para generarlo ahora mismo."
                    )
                )
        asyncio.run(send_start())
    except Exception as e:
        log.warning(f"Mensaje de inicio: {e}")

    threading.Thread(target=handle_telegram_updates, daemon=True).start()
    threading.Thread(target=run_scheduler, daemon=True).start()

    log.info("Bot corriendo. Esperando comandos y horario programado...")
    while True:
        time.sleep(60)
