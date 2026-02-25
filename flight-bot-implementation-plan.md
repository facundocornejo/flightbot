# Flight Price Alert Bot — Plan de Implementación para Claude Code

> **¿Qué es este documento?** Es el plan maestro para construir un bot de alertas de precios de vuelos. Fue diseñado por un senior dev con contexto completo de las APIs investigadas. Debe ejecutarse con Claude Code usando plan mode (Opus 4.6 para decisiones de arquitectura, Sonnet 4.5(o 4.6 cuando sea de una complejidad un poco mayor)
para implementación).
>
> **Idioma:** Todo el código, nombres de variables, funciones, docstrings y README van en **inglés**. Los comentarios dentro del código y las explicaciones al developer van en **español**.

---

## INSTRUCCIONES PARA CLAUDE CODE

### Configuración de modelos
- **Plan mode (Opus 4.6):** Usar para decisiones de arquitectura, diseño de interfaces, estructura de datos, y revisión de código. Activar con `/plan` antes de cada fase.
- **Implementación (Sonnet 4.6):** Usar para escribir el código, tests, y archivos de configuración.

### Workflow por fase
1. Entrar en plan mode → Opus diseña la fase
2. Revisar y aprobar el plan
3. Sonnet ejecuta la implementación
4. Opus revisa el resultado antes de pasar a la siguiente fase

### Reglas generales
- Cada archivo creado debe pasar linting (`ruff check`) antes de continuar
- Commits atómicos: un commit por cada unidad lógica completada
- No avanzar a la siguiente fase sin verificar que la anterior funciona
- Si algo falla, reportar el error exacto antes de intentar arreglarlo

---

## FASE 0 — Setup del entorno local y repositorio

### Objetivo
Tener el repo creado, el entorno Python configurado, y la estructura de carpetas lista.

### Pasos exactos (Windows con Git Bash o PowerShell)

```bash
# 1. Crear directorio del proyecto
mkdir flight-price-bot
cd flight-price-bot

# 2. Inicializar git
git init

# 3. Crear entorno virtual de Python
python -m venv venv

# 4. Activar entorno virtual
# En PowerShell:
.\venv\Scripts\Activate.ps1
# En Git Bash:
source venv/Scripts/activate

# 5. Actualizar pip
pip install --upgrade pip

# 6. Crear requirements.txt inicial
```

### requirements.txt
```
httpx>=0.27.0
fast-flights>=2.2
python-dotenv>=1.0.0
ruff>=0.8.0
pytest>=8.0.0
```

```bash
# 7. Instalar dependencias
pip install -r requirements.txt

# 8. Crear estructura de carpetas
```

### Estructura de carpetas
```
flight-price-bot/
├── .github/
│   └── workflows/
│       └── check-prices.yml
├── src/
│   ├── __init__.py
│   ├── main.py                 # Entry point
│   ├── config.py               # Carga y valida configuración
│   ├── models.py               # PriceResult dataclass y tipos compartidos
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── base.py             # Clase base abstracta para adapters
│   │   ├── level.py            # Level Airlines — API GET sin auth
│   │   ├── sky.py              # Sky Airline — API POST con API key pública
│   │   └── google_flights.py   # Google Flights via fast-flights
│   ├── engine.py               # Orquestación: ejecuta adapters, agrega resultados
│   ├── checker.py              # Compara precios vs umbrales del config
│   ├── notifier.py             # Envía notificaciones a Telegram
│   └── state.py                # Manejo de estado para evitar alertas duplicadas
├── config/
│   └── routes.json             # Configuración de rutas y umbrales
├── data/                       # Directorio para datos persistentes (gitignored excepto .gitkeep)
│   └── .gitkeep
├── tests/
│   ├── __init__.py
│   ├── test_level_adapter.py
│   ├── test_sky_adapter.py
│   ├── test_checker.py
│   └── test_notifier.py
├── docs/
│   ├── architecture.md
│   ├── api-investigation.md
│   └── setup-guide.md
├── CLAUDE.md                   # Instrucciones para Claude Code
├── requirements.txt
├── .env.example
├── .gitignore
├── LICENSE                     # MIT
└── README.md
```

### CLAUDE.md (instrucciones para Claude Code)
```markdown
# CLAUDE.md — Flight Price Alert Bot

## Proyecto
Bot de alertas de precios de vuelos que consulta múltiples fuentes (Level API, Sky API, Google Flights) y envía notificaciones via Telegram cuando los precios bajan de un umbral configurable.

## Convenciones
- Python 3.11+, type hints obligatorios en funciones públicas
- Código, variables, funciones, docstrings: inglés
- Comentarios explicativos: español
- Linter: ruff (ejecutar `ruff check src/` antes de cada commit)
- Tests: pytest (ejecutar `pytest tests/` para verificar)

## Comandos útiles
- `python -m src.main` — Ejecutar el bot (requiere .env con tokens de Telegram)
- `python -m src.main --dry-run` — Ejecutar sin enviar notificaciones (imprime en consola)
- `ruff check src/` — Linting
- `pytest tests/ -v` — Tests

## Arquitectura
Adapter pattern: cada fuente de datos (Level, Sky, Google Flights) tiene su propio módulo en `src/adapters/` que devuelve objetos `PriceResult` estandarizados. El engine los agrega, el checker los compara contra umbrales, y el notifier envía las alertas.

## Variables de entorno (.env)
- TELEGRAM_BOT_TOKEN — Token del bot de Telegram
- TELEGRAM_CHAT_ID — ID del chat donde enviar alertas
- DRY_RUN — "true" para modo de prueba sin enviar mensajes
```

### .gitignore
```
venv/
__pycache__/
*.pyc
.env
data/alert_state.json
data/price_history.json
.ruff_cache/
```

### .env.example
```
TELEGRAM_BOT_TOKEN=tu_token_aqui
TELEGRAM_CHAT_ID=tu_chat_id_aqui
DRY_RUN=true
```

---

## FASE 1 — Modelos de datos y configuración

### Objetivo
Definir los tipos de datos compartidos y el sistema de configuración.

### src/models.py
```python
"""Shared data models for the flight price alert bot."""

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class PriceResult:
    """Resultado estandarizado de precio de vuelo, independiente de la fuente."""

    source: str          # "level", "sky", "google_flights"
    airline: str         # "Level", "Sky Airline", "LATAM", etc.
    origin: str          # Código IATA del aeropuerto de origen
    destination: str     # Código IATA del aeropuerto de destino
    date: str            # Fecha del vuelo en formato YYYY-MM-DD
    price: float         # Precio del vuelo
    currency: str        # "USD" o "ARS"
    stops: int = 0       # Cantidad de escalas
    flight_number: str = ""          # Número de vuelo (opcional)
    seats_remaining: int | None = None  # Asientos disponibles (solo Sky)
    tags: list[str] = field(default_factory=list)  # Tags adicionales (ej: "IsMinimumPriceMonth")
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class RouteConfig:
    """Configuración de una ruta a monitorear."""

    origin: str
    destination: str
    sources: list[str]          # ["level", "sky", "google_flights"]
    threshold_usd: float | None = None
    threshold_ars: float | None = None
    months_ahead: int = 6       # Cuántos meses hacia adelante escanear
    trip_type: str = "round_trip"  # "round_trip" o "one_way"


@dataclass
class AlertState:
    """Estado de una alerta enviada previamente, para evitar duplicados."""

    route_key: str      # "EZE-BCN"
    date: str           # Fecha del vuelo
    price: float        # Precio alertado
    currency: str
    alerted_at: str     # Cuándo se envió la alerta
```

### Tabla de cobertura: qué fuente sirve para qué ruta

**CRÍTICO:** Level solo vuela a Europa. Sky solo vuela a destinos limitados. Google Flights cubre todo pero es menos confiable.

```
RUTA              | LEVEL | SKY | GOOGLE FLIGHTS | NOTAS
EZE → BCN         |  ✅   |  ❌  |      ✅        | Level es la fuente principal
EZE → ORY         |  ✅   |  ❌  |      ✅        | Level es la fuente principal
EZE → REC         |  ❌   |  ❌  |      ✅        | Solo Google Flights (cubre Gol, LATAM, etc.)
EZE → GIG         |  ❌   |  ❌  |      ✅        | Solo Google Flights
EZE → SSA         |  ❌   |  ✅  |      ✅        | Sky es fuente principal, GF como backup
ROS → REC         |  ❌   |  ❌  |      ✅        | Solo Google Flights (verificar si hay vuelos)
```

### config/routes.json
```json
{
  "routes": [
    {
      "origin": "EZE",
      "destination": "BCN",
      "sources": ["level", "google_flights"],
      "threshold_usd": 550,
      "months_ahead": 8,
      "trip_type": "round_trip"
    },
    {
      "origin": "EZE",
      "destination": "ORY",
      "sources": ["level", "google_flights"],
      "threshold_usd": 550,
      "months_ahead": 8,
      "trip_type": "round_trip"
    },
    {
      "origin": "EZE",
      "destination": "REC",
      "sources": ["google_flights"],
      "threshold_ars": 800000,
      "months_ahead": 6,
      "trip_type": "round_trip"
    },
    {
      "origin": "EZE",
      "destination": "GIG",
      "sources": ["google_flights"],
      "threshold_ars": 800000,
      "months_ahead": 6,
      "trip_type": "round_trip"
    },
    {
      "origin": "EZE",
      "destination": "SSA",
      "sources": ["sky", "google_flights"],
      "threshold_ars": 500000,
      "months_ahead": 6,
      "trip_type": "round_trip"
    },
    {
      "origin": "ROS",
      "destination": "REC",
      "sources": ["google_flights"],
      "threshold_ars": 800000,
      "months_ahead": 6,
      "trip_type": "round_trip"
    }
  ],
  "settings": {
    "delay_between_requests_seconds": 3,
    "alert_cooldown_hours": 48,
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
  }
}
```

**`alert_cooldown_hours: 48`**: Después de enviar una alerta para una ruta+fecha, no volver a alertar sobre el mismo precio (o menor) durante 48 horas. Esto evita que te lleguen 4 mensajes iguales por día.

### src/config.py
Debe implementar:
- `load_routes() -> list[RouteConfig]` — Lee `config/routes.json` y devuelve lista tipada
- `load_settings() -> dict` — Lee la sección `settings`
- Validación: verificar que cada ruta tiene al menos un source, que los thresholds son números positivos, que los sources son valores válidos ("level", "sky", "google_flights")

---

## FASE 2 — Adapter de Level Airlines

### Objetivo
Implementar el adapter más simple primero (GET sin auth) para validar la arquitectura.

### src/adapters/base.py
```python
"""Base class for all flight price adapters."""

from abc import ABC, abstractmethod
from src.models import PriceResult, RouteConfig


class BaseAdapter(ABC):
    """Clase base abstracta. Todos los adapters deben implementar fetch_prices."""

    @abstractmethod
    async def fetch_prices(self, route: RouteConfig) -> list[PriceResult]:
        """Consulta precios para una ruta dada. Devuelve lista de PriceResult."""
        ...

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Nombre identificador de la fuente (ej: 'level', 'sky')."""
        ...
```

### src/adapters/level.py — Especificaciones exactas

**Endpoint:**
```
GET https://www.flylevel.com/nwe/flights/api/calendar/?triptype=RT&origin={ORIGIN}&destination={DEST}&month={MM}&year={YYYY}&currencyCode=USD&originType=flights
```

**No requiere headers especiales.** Pero usar User-Agent del config por buena práctica.

**Lógica de escaneo mensual:**
- Leer `months_ahead` del RouteConfig
- Desde el mes actual hasta `months_ahead` meses en el futuro
- Hacer UN request por mes (la API devuelve ~60 días: el mes pedido + el siguiente)
- Para evitar duplicados entre meses solapados: usar un set de fechas ya procesadas

**Ejemplo:** Si `months_ahead = 8` y estamos en febrero 2026, escanear meses 2,3,4,5,6,7,8,9 de 2026. Son 8 requests, con ~3s de delay = 24 segundos total para Level.

**Parseo de respuesta:**
```python
# La respuesta tiene esta estructura:
# {"data": {"dayPrices": [{"date": "2026-12-01", "price": 522, "minimumPriceGroup": 0, "tags": null}, ...]}}

# Para cada dayPrice:
PriceResult(
    source="level",
    airline="Level",
    origin=route.origin,        # "EZE"
    destination=route.destination,  # "BCN"
    date=day["date"],           # "2026-12-01"
    price=day["price"],         # 522
    currency="USD",             # Level siempre devuelve USD
    stops=0,                    # Level vuela directo EZE-BCN
    tags=day.get("tags") or [],
)
```

**Manejo de errores:**
- Si el request falla (timeout, 500, etc.): loggear warning, devolver lista vacía, no crashear
- Si la respuesta no tiene la estructura esperada: loggear error con el body recibido

### Test: tests/test_level_adapter.py
- Mock del response HTTP con datos reales (copiar un fragmento del JSON de la investigación)
- Verificar que el parser devuelve los PriceResult correctos
- Verificar que maneja errores sin crashear

---

## FASE 3 — Adapter de Sky Airline

### Especificaciones exactas

**Endpoint:**
```
POST https://api.skyairline.com/shopping-lowest-fares/lowest-fares/v1/search
```

**Headers requeridos:**
```python
headers = {
    "Content-Type": "application/json",
    "ocp-apim-subscription-key": "4c998b33d2aa4e8aba0f9a63d4c04d7d",  # API key pública de Azure APIM
    "channel": "WEB",
    "homemarket": "AR",
    "pointofsale": "AR",
}
```

**Body:**
```python
body = {
    "currency": "ARS",
    "passengerCount": [{"ptc": "ADT", "quantity": 1}],
    "itineraryParts": [
        {
            "origin": "BUE",        # Sky usa código de ciudad, no aeropuerto
            "destination": "SSA",
            "departureDate": "2026-03-09",  # Fecha central de búsqueda
            "dateFlexibility": 14,          # ±14 días = ventana de 28 días
        }
    ],
}
```

**Lógica de escaneo:**
- `dateFlexibility: 14` da una ventana de ~28 días por request
- Para cubrir `months_ahead` meses: calcular cuántos requests necesitamos
- Ejemplo: 6 meses = ~180 días ÷ 28 días por request = ~7 requests
- Centrar cada request 28 días después del anterior
- Delay de 3 segundos entre requests

**Mapeo de códigos de aeropuerto:**
- Sky usa códigos de CIUDAD para origin: `BUE` (Buenos Aires), no `EZE` o `AEP`
- La respuesta puede devolver `EZE` o `AEP` como origin real
- Implementar un mapeo: `{"EZE": "BUE", "AEP": "BUE", "ROS": "ROS"}`

**Parseo de respuesta:**
```python
# Filtrar solo itineraryParts con isAvailable == True
# Para cada parte disponible:
PriceResult(
    source="sky",
    airline="Sky Airline",
    origin=part["origin"],              # "EZE"
    destination=part["destination"],     # "SSA"
    date=part["departureDate"],          # "2026-02-27"
    price=part["pricingInfo"]["baseFareWithTaxes"],  # 401362.5
    currency="ARS",
    stops=part["stops"],                 # 0
    flight_number=part["segments"][0]["flightNumber"] if part["segments"] else "",
    seats_remaining=part["pricingInfo"]["seatsRemaining"]["number"],  # 9
)
```

**Manejo de errores especial para Sky:**
- Si recibe 401 o 403: la API key probablemente fue rotada
  - Loggear error crítico
  - Enviar alerta Telegram ONE TIME: "⚠️ Sky Airline API key may have been rotated. Bot cannot check Sky prices until key is updated."
  - No reintentar hasta que se actualice la key

---

## FASE 4 — Adapter de Google Flights (fast-flights)

### Especificaciones

**Instalación:** `pip install fast-flights`

**Uso:**
```python
from fast_flights import FlightData, Passengers, get_flights

result = get_flights(
    flight_data=[
        FlightData(date="2026-03-15", from_airport="EZE", to_airport="REC"),
    ],
    trip="one-way",  # Usar one-way para simplificar; el precio round-trip se puede estimar x2
    seat="economy",
    passengers=Passengers(adults=1),
    fetch_mode="common",  # IMPORTANTE: en GitHub Actions usar "common", no "fallback"
)
```

**IMPORTANTE sobre `fetch_mode` en GitHub Actions:**
- `"common"`: Hace HTTP request directo. Es el más rápido y ligero. Puede fallar si Google bloquea.
- `"fallback"`: Intenta common primero, si falla usa Playwright serverless externo. Más confiable pero puede ser lento o fallar en CI.
- `"force-fallback"`: Siempre usa Playwright serverless. Más confiable pero más lento.

**Recomendación:** Empezar con `"common"`. Si falla consistentemente en GitHub Actions, cambiar a `"fallback"`.

**Lógica de escaneo:**
- fast-flights requiere UNA fecha por request (no tiene calendario)
- Para no gastar demasiados requests: escanear solo ciertos días
- Estrategia: escanear 1 día por semana durante `months_ahead` meses
  - 6 meses × 4 semanas = 24 requests por ruta
  - Con 6 rutas = 144 requests totales
  - Con 3 segundos delay = ~7 minutos (dentro del timeout de 10 min de GitHub Actions)
- Alternativamente: escanear solo los días más relevantes (viernes y lunes) = 2 días por semana

**Parseo de respuesta:**
```python
for flight in result.flights:
    PriceResult(
        source="google_flights",
        airline=flight.name,          # "LATAM", "Gol", etc.
        origin=route.origin,
        destination=route.destination,
        date=flight_date,             # La fecha que se pasó al request
        price=extract_price(flight.price),  # Parsear "$1,234" → 1234.0
        currency="USD",               # Google Flights en general muestra USD para rutas internacionales
        stops=parse_stops(flight.stops),    # Parsear "1 stop" → 1
    )
```

**Nota sobre parseo de precios:** `flight.price` puede venir como string tipo `"$1,234"` o `"ARS 500,000"`. Hay que implementar un parser robusto.

**Manejo de errores:**
- Si fast-flights falla: loggear warning, continuar con otras fuentes
- Si Google bloquea (rate limit): reducir frecuencia, no reintentar inmediatamente
- fast-flights puede cambiar su API entre versiones: pinear la versión en requirements.txt

---

## FASE 5 — Engine, Checker, y State Manager

### src/engine.py
Orquesta la ejecución de todos los adapters:
1. Leer config de rutas
2. Para cada ruta, instanciar los adapters correspondientes
3. Ejecutar cada adapter con delay entre requests
4. Agregar todos los PriceResult en una lista unificada
5. Pasar al checker

### src/checker.py
Compara precios contra umbrales:
1. Para cada PriceResult, buscar el threshold correspondiente en la config
2. **Lógica de comparación por moneda:**
   - Si el PriceResult es en USD y la ruta tiene `threshold_usd` → comparar directo
   - Si el PriceResult es en ARS y la ruta tiene `threshold_ars` → comparar directo
   - Si hay mismatch de moneda → skipear esa comparación (no hacer conversión automática para evitar errores con tipo de cambio desactualizado)
3. Si el precio está por debajo del threshold → agregarlo a la lista de alertas
4. Antes de alertar: verificar contra el state manager que no se haya alertado recientemente

### src/state.py — Evitar alertas duplicadas
**Problema:** Si el cron corre cada 6 horas y un precio sigue bajo, no queremos 4 alertas iguales por día.

**Solución:** Archivo JSON simple en `data/alert_state.json`:
```json
{
  "EZE-BCN-2026-12-01": {
    "price": 511,
    "currency": "USD",
    "alerted_at": "2026-02-24T18:00:00Z"
  }
}
```

**Lógica:**
- Key: `{origin}-{destination}-{date}`
- Antes de enviar una alerta, verificar si ya existe una entrada con:
  - El mismo key
  - Un precio igual o menor
  - Dentro del `alert_cooldown_hours` (default 48 horas)
- Si existe → no alertar (ya avisamos)
- Si el precio BAJÓ más desde la última alerta → alertar de nuevo ("Price dropped further!")
- Si pasó el cooldown → alertar de nuevo (refrescar)
- Después de alertar: actualizar el state

**En GitHub Actions:** El state file NO se commitea al repo. Se pierde entre ejecuciones. Esto significa que en el peor caso recibirás una alerta repetida si el runner cambia. Para el MVP esto es aceptable. En v2 se podría usar GitHub Actions cache o un storage externo.

**Alternativa simple para MVP:** Usar GitHub Actions cache para persistir `data/alert_state.json` entre ejecuciones:
```yaml
- uses: actions/cache@v4
  with:
    path: data/alert_state.json
    key: alert-state-${{ github.run_id }}
    restore-keys: alert-state-
```

---

## FASE 6 — Notificador de Telegram

### Paso a paso para crear el bot (primera vez)

1. Abrir Telegram en el celular o PC
2. Buscar `@BotFather` (tiene tilde de verificación azul)
3. Enviar `/start` y después `/newbot`
4. Escribir un nombre para el bot (ej: "Flight Price Alert")
5. Escribir un username (debe terminar en `bot`, ej: `mi_flight_alert_bot`)
6. BotFather responde con un **token** tipo `7123456789:AAHxyz...` — COPIARLO
7. Ir al repo en GitHub → Settings → Secrets and variables → Actions → New repository secret
   - Name: `TELEGRAM_BOT_TOKEN`
   - Value: pegar el token
8. Para obtener tu chat ID:
   - Enviar cualquier mensaje al bot que acabás de crear (ej: "hola")
   - Abrir en el navegador: `https://api.telegram.org/bot<TU_TOKEN>/getUpdates`
   - Buscar en el JSON: `"chat":{"id": NUMERO}` — ese NUMERO es tu chat ID
9. Agregar otro secret en GitHub:
   - Name: `TELEGRAM_CHAT_ID`
   - Value: el número del paso anterior

### src/notifier.py
Implementar usando `httpx` directamente (sin librería de Telegram, para mantenerlo simple):

```python
TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

async def send_alert(token: str, chat_id: str, price_result: PriceResult) -> bool:
    """Envía una alerta de precio bajo por Telegram. Devuelve True si se envió correctamente."""
    ...
```

### Formato del mensaje
```
🔥 ALERTA DE PRECIO — {origin} → {destination}

💰 {currency} {price:,.0f} ({airline})
📅 {date}
✈️ {stops} escala(s) | Vuelo {flight_number}
🪑 {seats_remaining} asientos restantes  ← solo si viene de Sky
🏷️ {tags}  ← solo si tiene tags como IsMinimumPriceMonth

📊 Fuente: {source}
⏰ Consultado: {fetched_at}
```

### Modo dry-run
Si `DRY_RUN=true` en `.env` o `--dry-run` en CLI:
- Imprimir el mensaje en consola en vez de enviarlo a Telegram
- Útil para testing local sin configurar el bot

---

## FASE 7 — Entry point y CLI

### src/main.py
```python
"""Entry point del bot de alertas de precios de vuelos."""

import argparse
import asyncio
import logging
import os
from dotenv import load_dotenv

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

async def main(dry_run: bool = False):
    """Flujo principal: cargar config → consultar fuentes → comparar → alertar."""
    # 1. Cargar configuración
    # 2. Inicializar adapters
    # 3. Para cada ruta, ejecutar los adapters correspondientes
    # 4. Agregar resultados
    # 5. Comparar contra umbrales
    # 6. Enviar alertas (o imprimir si dry_run)
    # 7. Actualizar estado
    pass

if __name__ == "__main__":
    load_dotenv()  # Carga .env para ejecución local
    parser = argparse.ArgumentParser(description="Flight Price Alert Bot")
    parser.add_argument("--dry-run", action="store_true", help="No enviar alertas, solo imprimir en consola")
    args = parser.parse_args()
    
    dry_run = args.dry_run or os.getenv("DRY_RUN", "false").lower() == "true"
    asyncio.run(main(dry_run=dry_run))
```

---

## FASE 8 — GitHub Actions

### .github/workflows/check-prices.yml
```yaml
name: Check Flight Prices

on:
  schedule:
    # Cada 6 horas: 00:00, 06:00, 12:00, 18:00 UTC
    - cron: '0 */6 * * *'
  workflow_dispatch:  # Permite ejecutarlo manualmente desde la UI de GitHub

jobs:
  check-prices:
    runs-on: ubuntu-latest
    timeout-minutes: 10  # Evita que un proceso colgado consuma minutos gratis

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt

      # Restaurar estado de alertas previas (evita duplicados)
      - name: Restore alert state
        uses: actions/cache@v4
        with:
          path: data/alert_state.json
          key: alert-state
          restore-keys: alert-state

      - name: Run price checker
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python -m src.main

      # Guardar estado actualizado
      - name: Save alert state
        uses: actions/cache/save@v4
        if: always()
        with:
          path: data/alert_state.json
          key: alert-state-${{ github.run_id }}
```

### Cómo configurar los secrets (primera vez)
1. Ir a tu repositorio en github.com
2. Click en **Settings** (arriba a la derecha, pestaña del repo, no del perfil)
3. En el menú izquierdo: **Secrets and variables** → **Actions**
4. Click en **New repository secret**
5. Agregar:
   - `TELEGRAM_BOT_TOKEN` = el token que te dio BotFather
   - `TELEGRAM_CHAT_ID` = el número de tu chat ID
6. Click en **Add secret** para cada uno

### Cómo ejecutar manualmente
1. Ir a tu repositorio → pestaña **Actions**
2. Click en **Check Flight Prices** en el sidebar izquierdo
3. Click en **Run workflow** → **Run workflow**
4. Esperar ~2-3 minutos a que termine

---

## FASE 9 — Testing y validación

### Estrategia de tests

**tests/test_level_adapter.py:**
- Mockear `httpx.get` con respuesta JSON real (fragmento del documento de investigación)
- Verificar que devuelve PriceResult correctos
- Verificar manejo de error (respuesta vacía, timeout, 500)

**tests/test_sky_adapter.py:**
- Mockear `httpx.post` con respuesta JSON real
- Verificar parseo correcto de precios en ARS
- Verificar filtrado de `isAvailable: false`
- Verificar manejo de 401/403 (API key expirada)

**tests/test_checker.py:**
- Probar que detecta precios bajo el umbral
- Probar que ignora precios sobre el umbral
- Probar comparación por moneda correcta (USD vs ARS)

**tests/test_notifier.py:**
- Mockear la API de Telegram
- Verificar formato del mensaje
- Verificar que dry-run NO llama a la API

### Validación end-to-end local
```bash
# 1. Configurar .env con DRY_RUN=true
echo "DRY_RUN=true" > .env

# 2. Ejecutar
python -m src.main --dry-run

# Debería imprimir en consola algo como:
# [INFO] Checking Level: EZE → BCN (months 2-10)
# [INFO] Level: Found 60 prices for EZE → BCN
# [INFO] Checking Google Flights: EZE → REC
# [INFO] 🔥 ALERT: EZE → BCN on 2027-01-26 at USD 511 (Level) — below threshold USD 550
# [DRY RUN] Would send Telegram alert: ...
```

---

## FASE 10 — Portfolio README y documentación

### README.md — Secciones obligatorias

1. **Título + badges**
   ```markdown
   # ✈️ Flight Price Alert Bot
   
   ![Python](https://img.shields.io/badge/Python-3.11+-blue)
   ![License](https://img.shields.io/badge/License-MIT-green)
   ![Automated](https://img.shields.io/badge/Automated-GitHub%20Actions-orange)
   ```

2. **One-liner:** "Automated bot that monitors flight prices from multiple sources and sends Telegram alerts when prices drop below your thresholds."

3. **Problem statement**

4. **Features** (como prosa, no bullets)

5. **Architecture diagram** (Mermaid)
   ```mermaid
   graph TD
       A[GitHub Actions Cron] --> B[Main Engine]
       B --> C[Level API Adapter]
       B --> D[Sky API Adapter]
       B --> E[Google Flights Adapter]
       C --> F[Price Normalizer]
       D --> F
       E --> F
       F --> G[Threshold Checker]
       G --> H[State Manager]
       H --> I[Telegram Notifier]
   ```

6. **API Investigation** — contar brevemente cómo se usaron DevTools para descubrir las APIs. Incluir la tabla de aerolíneas investigadas (viable vs no viable). Esto demuestra habilidades de reverse engineering.

7. **Setup guide** — cómo forkear y configurar tu propia instancia

8. **Cost analysis:** $0 breakdown

9. **Lessons learned**

10. **Future improvements** — web dashboard, más aerolíneas, histórico de precios con gráficos, ML para predicción de precios

### docs/api-investigation.md
Documento detallado explicando:
- Cómo se usaron Chrome DevTools (pestaña Network, filtro Fetch/XHR)
- Qué se analizó en cada aerolínea (headers, auth, cookies, bot protection)
- Por qué algunas aerolíneas no fueron viables (tabla con detalles técnicos)
- Cómo se identificaron las APIs abiertas de Level y Sky

Este documento es el más valioso para el portfolio porque muestra metodología de investigación técnica.

---

## RESUMEN DE TIMING

| Fase | Tarea | Modelo | Duración estimada |
|------|-------|--------|-------------------|
| 0 | Setup entorno y repo | Sonnet | 10 min |
| 1 | Modelos y config | Opus (plan) + Sonnet (código) | 15 min |
| 2 | Level adapter | Opus (plan) + Sonnet (código) | 20 min |
| 3 | Sky adapter | Opus (plan) + Sonnet (código) | 20 min |
| 4 | Google Flights adapter | Opus (plan) + Sonnet (código) | 25 min |
| 5 | Engine, Checker, State | Opus (plan) + Sonnet (código) | 30 min |
| 6 | Telegram notifier | Sonnet | 15 min |
| 7 | Main entry point | Sonnet | 10 min |
| 8 | GitHub Actions | Sonnet | 15 min |
| 9 | Tests y validación | Sonnet | 20 min |
| 10 | README y docs | Sonnet | 20 min |
| **Total** | | | **~3 horas** |
