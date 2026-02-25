# Setup Guide — Step by Step

> Guía paso a paso para configurar tu propia instancia del bot. Está pensada para developers principiantes que nunca usaron GitHub Actions ni crearon un bot de Telegram.

## Paso 1: Clonar el repositorio

```bash
# En tu terminal (Git Bash o PowerShell en Windows)
git clone https://github.com/TU_USUARIO/flight-price-bot.git
cd flight-price-bot
```

## Paso 2: Crear entorno virtual de Python

```bash
# Crear entorno virtual
python -m venv venv

# Activar (elegí según tu terminal):
# PowerShell (Windows):
.\venv\Scripts\Activate.ps1

# Git Bash (Windows):
source venv/Scripts/activate

# Linux/Mac:
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

## Paso 3: Crear el bot de Telegram

1. Abrí **Telegram** (celular o PC)
2. Buscá **@BotFather** (tiene tilde azul de verificación)
3. Mandá `/start` y después `/newbot`
4. Elegí un **nombre** para tu bot (ej: "Flight Price Alert")
5. Elegí un **username** (debe terminar en `bot`, ej: `mi_vuelos_bot`)
6. BotFather te va a responder con un **token** tipo `7123456789:AAHxyz...`
7. **Copiá ese token** — lo vas a necesitar

## Paso 4: Obtener tu Chat ID

1. Mandá cualquier mensaje a tu bot recién creado (ej: "hola")
2. Abrí esta URL en el navegador (reemplazá `TU_TOKEN` por el token del paso anterior):
   ```
   https://api.telegram.org/botTU_TOKEN/getUpdates
   ```
3. En el JSON que aparece, buscá `"chat":{"id": NUMERO}`
4. Ese `NUMERO` es tu **Chat ID** — copialo

## Paso 5: Configurar variables de entorno (local)

```bash
# Crear archivo .env copiando el ejemplo
cp .env.example .env
```

Editá el archivo `.env` con un editor de texto:
```
TELEGRAM_BOT_TOKEN=7123456789:AAHxyz_tu_token_real_aqui
TELEGRAM_CHAT_ID=123456789
DRY_RUN=true
```

## Paso 6: Configurar rutas y umbrales

Editá `config/routes.json`:

- **origin/destination**: Códigos IATA de aeropuertos (ej: EZE, BCN, REC)
- **sources**: Qué fuentes usar (`level`, `sky`, `google_flights`)
- **threshold_usd/threshold_ars**: Precio máximo para alertar
- **months_ahead**: Cuántos meses hacia adelante buscar
- **manual_usd_to_ars**: Tipo de cambio actual USD → ARS

## Paso 7: Probar localmente

```bash
# Ejecutar en modo prueba (no envía a Telegram, imprime en consola)
python -m src.main --dry-run
```

Si ves alertas impresas en la consola, ¡funciona!

Para probar con Telegram real:
```bash
# Cambiar DRY_RUN a false en .env
# O simplemente:
python -m src.main
```

## Paso 8: Subir a GitHub

```bash
git add .
git commit -m "Initial setup: flight price alert bot"
git remote add origin https://github.com/TU_USUARIO/flight-price-bot.git
git push -u origin main
```

## Paso 9: Configurar GitHub Secrets

1. Andá a tu repositorio en **github.com**
2. Click en **Settings** (pestaña arriba a la derecha del repo)
3. En el menú izquierdo: **Secrets and variables** → **Actions**
4. Click en **New repository secret**
5. Agregá estos dos secrets:

   | Name | Value |
   |------|-------|
   | `TELEGRAM_BOT_TOKEN` | El token del paso 3 |
   | `TELEGRAM_CHAT_ID` | El número del paso 4 |

## Paso 10: Verificar que GitHub Actions funciona

1. Andá a la pestaña **Actions** de tu repo
2. Click en **Check Flight Prices** en el sidebar
3. Click en **Run workflow** → **Run workflow**
4. Esperá 2-3 minutos a que termine
5. Si todo sale bien, deberías recibir alertas en Telegram (si hay precios bajo tus umbrales)

## Paso 11: ¡Listo!

El bot va a ejecutarse automáticamente cada 6 horas. Si querés cambiar la frecuencia, editá el cron en `.github/workflows/check-prices.yml`:

```yaml
# Cada 6 horas (default)
- cron: '0 */6 * * *'

# Cada 12 horas
- cron: '0 */12 * * *'

# Una vez al día a las 9 AM UTC (6 AM Argentina)
- cron: '0 9 * * *'
```

## Actualizar tipo de cambio

Cuando quieras actualizar el tipo de cambio USD/ARS:

1. Editá `config/routes.json`
2. Cambiá el valor de `manual_usd_to_ars`
3. Commiteá y pusheá

```bash
git add config/routes.json
git commit -m "Update USD/ARS exchange rate"
git push
```
