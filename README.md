# 📊 Bot Pre Mercado — Telegram

Bot que genera y envía automáticamente el informe de pre mercado todos los días a las 7:00 hs (Argentina).

## Comandos disponibles
- `/start` — Bienvenida e instrucciones
- `/ahora` — Genera el informe en este momento

---

## 🚀 Deploy en Railway (gratis, 5 minutos)

### Paso 1 — Crear cuenta en Railway
1. Entrá a **railway.app**
2. Registrate con tu cuenta de GitHub (o creá una cuenta de GitHub si no tenés)

### Paso 2 — Subir el código a GitHub
1. Entrá a **github.com** y creá un repositorio nuevo llamado `premercado-bot`
2. Marcalo como **Privado**
3. Subí estos 3 archivos:
   - `bot.py`
   - `requirements.txt`
   - `Procfile`

   (Podés arrastrarlos directo desde la web de GitHub)

### Paso 3 — Crear el servicio en Railway
1. En Railway, click en **"New Project"**
2. Elegí **"Deploy from GitHub repo"**
3. Seleccioná `premercado-bot`
4. Railway lo detecta solo y empieza a deployar

### Paso 4 — Agregar las variables de entorno
En Railway, entrá a tu proyecto → **Variables** → agregá estas tres:

| Variable | Valor |
|----------|-------|
| `TELEGRAM_TOKEN` | El token de @BotFather |
| `CHAT_ID` | Tu ID numérico de Telegram |
| `ANTHROPIC_KEY` | Tu API key de Anthropic (sk-ant-...) |

### Paso 5 — Listo! 🎉
El bot se reinicia automáticamente con las variables y te manda un mensaje confirmando que está activo.

---

## ⏰ Horario
El informe llega todos los días a las **7:00 hs Argentina** (10:00 UTC).

---

## 🔒 Seguridad
- Nunca compartas el token del bot ni la API key
- Si los compartiste por error, regeneralos:
  - Token: @BotFather → `/revoke`
  - API key: console.anthropic.com → API Keys → Revoke

---

## 💰 Costo estimado
- Railway: **gratis** hasta 500 hs/mes (suficiente)
- Anthropic API: ~**$0.10 por informe** (claude-opus-4-6, ~8000 tokens)
- Costo mensual estimado: **~$3 USD/mes**
