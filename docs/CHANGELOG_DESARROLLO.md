# Changelog de Desarrollo - Flight Price Bot

Este documento registra todos los cambios, avances y desarrollos del proyecto para mantener contexto entre sesiones.

---

## 2026-02-26 - Optimización de Rendimiento y Fix de Bugs

### Problema Inicial
El workflow de GitHub Actions falló por timeout (excedió 10 minutos). El job fue cancelado automáticamente.

**Causa raíz identificada:**
- 12 rutas × 20 fechas (cada 3 días) = 240 requests
- 2 segundos de delay entre requests = 8 min solo de delays
- Sin timeout individual por request (si Google se colgaba, esperaba infinitamente)

### Cambios Implementados

#### 1. Optimización del Adapter de Google Flights
**Archivo:** `src/adapters/google_flights.py`

| Cambio | Antes | Después |
|--------|-------|---------|
| Intervalo de escaneo | Cada 3 días | Cada 5 días |
| Timeout por request | Sin límite | 30 segundos |
| Fechas por ruta | ~20 | ~12 |

```python
# Nuevas constantes agregadas
DAYS_BETWEEN_SCANS = 5
REQUEST_TIMEOUT_SECONDS = 30
```

El timeout usa `asyncio.wait_for()` - si un request tarda más de 30s, lo salta y continúa.

#### 2. Paralelismo en el Engine
**Archivo:** `src/engine.py`

- Agregado `asyncio.Semaphore(2)` para procesar 2 rutas en paralelo
- Reduce tiempo total de ejecución ~50%
- Límite de 2 evita rate-limiting de Google

#### 3. Timeout del Workflow
**Archivo:** `.github/workflows/check-prices.yml`

| Antes | Después |
|-------|---------|
| 10 minutos | 20 minutos |

#### 4. Configuración de Umbrales y Tipo de Cambio
**Archivo:** `config/routes.json`

| Parámetro | Antes | Después |
|-----------|-------|---------|
| `threshold_usd` (todas las rutas) | 350-400 | **300** |
| `manual_usd_to_ars` | 1400 | **1450** |

**Nota:** Ahora solo se alertan vuelos menores a USD 300.

#### 5. Fix de Bug: Precios $0
**Archivo:** `src/checker.py`

**Problema:** Cuando Google Flights no devolvía precio, el parser retornaba 0, lo cual pasaba el filtro de umbral (`0 <= 300` = true).

**Solución:** Agregada validación al inicio de `_is_below_threshold()`:
```python
if price <= 0:
    logger.debug("precio inválido, ignorando")
    return False
```

### Resultados Post-Optimización

| Métrica | Antes | Después |
|---------|-------|---------|
| Tiempo de ejecución | >10 min (timeout) | ~7 min |
| Requests por ruta | ~20 | ~12 |
| Alertas con precio $0 | Sí (bug) | No (corregido) |
| Rutas en paralelo | 1 | 2 |

### Commits Realizados
1. `4ba24c4` - Optimizar rendimiento y ajustar umbrales de alerta
2. `93bd79f` - Ignorar precios $0 (errores de parsing de Google Flights)

### Decisiones Tomadas

#### Dividir en múltiples workflows: **NO**
Se evaluó dividir en 2 workflows (Rio vs Norte de Brasil) pero se decidió mantener unificado porque:
- 7 minutos está muy lejos del límite de 20 min
- Complejidad innecesaria para 12 rutas
- Menos archivos que mantener
- Sin riesgo de conflictos en el estado de alertas

**Cuándo reconsiderar:** Si se agregan 30+ rutas o se necesitan frecuencias muy distintas por región.

### Frecuencia de Ejecución
El workflow corre **4 veces por día** (cada 6 horas):

| UTC | Argentina |
|-----|-----------|
| 00:00 | 21:00 |
| 06:00 | 03:00 |
| 12:00 | 09:00 |
| 18:00 | 15:00 |

### Estado Actual
- **GitHub Actions:** Configurado y funcionando
- **Repositorio:** https://github.com/facundocornejo/flightbot (público)
- **Próximo run:** Según schedule del cron
- **Umbral de alerta:** USD 300
- **Tipo de cambio:** 1450 ARS/USD

---

## 2026-02-25 - Sesión Inicial: Setup y Primera Búsqueda

### Resumen
Primera sesión de configuración del bot. Se configuró Telegram, se ejecutaron búsquedas de vuelos a Brasil, y se enviaron las primeras alertas reales.

### Configuración de Telegram
- **Bot creado:** @Sir_bolsillosbot
- **Token:** Configurado en `.env`
- **Chat ID:** 1614596199
- **Estado:** Funcionando correctamente

### Cambios Realizados

#### 1. CLAUDE.md actualizado
- Agregado header estándar para Claude Code
- Agregada sección "Testing a Single Adapter" con comandos para tests individuales
- Agregada sección "Adding a New Adapter" con pasos para extender el bot
- Agregada sección "Configuration" explicando routes.json y state

#### 2. Tipo de cambio actualizado
- **Anterior:** 1200 ARS/USD
- **Nuevo:** 1400 ARS/USD
- **Archivo:** `config/routes.json` → `manual_usd_to_ars: 1400.0`

#### 3. Soporte para duración de viaje (round-trip)
**Archivos modificados:**
- `src/models.py` - Agregados campos `trip_duration_min_days` y `trip_duration_max_days` a AppSettings
- `src/config.py` - Carga de nuevos campos desde config
- `src/adapters/google_flights.py` - Modificado para especificar fecha de regreso en búsquedas round-trip

**Configuración actual:**
```json
"trip_duration_min_days": 7,
"trip_duration_max_days": 10
```
El adapter usa el promedio (8 días) para las búsquedas.

#### 4. Fix de encoding para Windows
- `src/notifier.py` - Agregado manejo de UnicodeEncodeError para emojis en consola Windows (cp1252)

#### 5. Rutas configuradas para Brasil
**Destinos actuales (desde EZE):**
| Destino | Código | Umbral USD |
|---------|--------|------------|
| Rio de Janeiro | GIG | 350 |
| Maceió | MCZ | 400 |
| Salvador de Bahía | SSA | 400 |
| Natal | NAT | 400 |
| Fortaleza | FOR | 400 |
| Recife | REC | 400 |

**Meses de búsqueda:** 2 (marzo y abril 2026)

### Resultados de Búsqueda (25/02/2026)

#### Precios encontrados por ruta:
| Destino | Precios | Mejor precio ARS | USD aprox |
|---------|---------|------------------|-----------|
| Rio (GIG) | 1,034 | 337,833 | **241** |
| Maceió (MCZ) | 644 | 787,661 | 563 |
| Salvador (SSA) | 1,032 | 616,968 | 441 |
| Natal (NAT) | 702 | 734,023 | 524 |
| Fortaleza (FOR) | 1,053 | 622,520 | 445 |
| Recife (REC) | 921 | 667,803 | 477 |

**Total de precios analizados:** 5,386
**Alertas generadas:** 39 vuelos bajo el umbral

#### TOP 4 Vuelos enviados a Telegram:
1. **EZE → Rio (GIG)** - ARS 337,833 (~USD 241) - JetSMART - 15 abr → 23 abr - Directo
2. **EZE → Rio (GIG)** - ARS 375,629 (~USD 268) - JetSMART - 12 abr → 20 abr - Directo
3. **EZE → Rio (GIG)** - ARS 391,794 (~USD 280) - JetSMART - 6 abr → 14 abr - Directo
4. **EZE → Salvador (SSA)** - ARS 616,968 (~USD 441) - Directo - 31 mar → 8 abr

### Scripts Auxiliares Creados
- `show_cheapest.py` - Muestra los 5 vuelos más baratos por ruta
- `find_cheap.py` - Busca vuelos bajo un umbral específico
- `send_top4.py` - Envía los 4 mejores vuelos a Telegram manualmente

### Issues Conocidos

#### 1. Detección de moneda en Google Flights
Google Flights devuelve precios en ARS (porque detecta ubicación Argentina) pero el parser los etiqueta como USD.
**Workaround:** Se divide por el tipo de cambio manual (1400) para obtener USD real.

#### 2. Errores de parseo (USD 0)
Algunas búsquedas devuelven precio 0 cuando Google Flights no carga resultados correctamente.
**Estado:** No crítico, se filtran en el checker.

#### 3. ROS → MCZ sin vuelos
No hay vuelos directos Rosario → Maceió.

### Estado Actual del Proyecto
- **DRY_RUN:** false (envía alertas reales)
- **Bot Telegram:** Funcionando
- **Google Flights adapter:** Funcionando
- **Level adapter:** Funcionando (no usado en config actual)
- **Sky adapter:** Funcionando pero sin vuelos disponibles a destinos actuales
- **GitHub Actions:** No configurado aún (no hay repo remoto)

### Próximos Pasos Sugeridos
1. [ ] Crear repositorio en GitHub
2. [ ] Configurar secrets en GitHub Actions (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
3. [ ] Activar cron cada 6 horas
4. [ ] Agregar más destinos si se desea
5. [ ] Considerar agregar filtro por aerolínea específica
6. [ ] Mejorar detección de moneda en el parser

---

## Comandos Útiles

```bash
# Ejecutar en modo prueba (no envía a Telegram)
python -m src.main --dry-run

# Ejecutar en modo real (envía a Telegram)
python -m src.main

# Ver vuelos más baratos por ruta
python show_cheapest.py

# Enviar los 4 mejores a Telegram
python send_top4.py

# Linting
ruff check src/

# Tests
pytest tests/ -v
```

---

## Estructura de Archivos Clave

```
flight-price-bot/
├── .env                    # Tokens de Telegram (NO commitear)
├── config/
│   └── routes.json         # Rutas, umbrales, tipo de cambio
├── data/
│   └── alert_state.json    # Estado de alertas enviadas
├── src/
│   ├── adapters/
│   │   ├── google_flights.py  # Adapter principal para Brasil
│   │   ├── level.py           # Adapter para Europa (Level Airlines)
│   │   └── sky.py             # Adapter para Sky Airline
│   ├── checker.py          # Compara precios vs umbrales
│   ├── engine.py           # Orquestación principal
│   ├── notifier.py         # Envío a Telegram
│   └── state.py            # Manejo de duplicados
└── docs/
    └── CHANGELOG_DESARROLLO.md  # Este archivo
```
