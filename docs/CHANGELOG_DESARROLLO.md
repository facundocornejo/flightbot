# Changelog de Desarrollo - Flight Price Bot

Este documento registra todos los cambios, avances y desarrollos del proyecto para mantener contexto entre sesiones.

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
