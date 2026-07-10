# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Estado actual (2026-07-10)

- **Nueva 2ª fuente: Travelpayouts/Aviasales Data API** (`src/adapters/travelpayouts.py`,
  portada del clon de Río): precios cacheados de búsquedas reales (48h), en modo RELAJADO
  (`travelpayouts_match_trip_duration: false` — cualquier fecha de vuelta cuenta como señal
  de tendencia). Verificada en vivo: 12 precios EZE/AEP→REC, mínimo AEP→REC USD 330 directo.
  Requiere secret `TRAVELPAYOUTS_TOKEN` en GitHub (token por cuenta, compartido con el bot
  de Río). Sin token la fuente se saltea con un log.

- **Bot operativo post-incidente**: estuvo mudo 2026-06-10 → 2026-07-08 (fast-flights 3.0 rompió
  la API; los runs quedaban en verde con 0 precios). Fix en commit `122da20`: migración a la API
  v3 con `fast-flights==3.0.2` pineado exacto, precios pedidos en USD directo, y anti-silencio
  (0 precios → alerta Telegram + exit 2 → run rojo). Verificado en Actions: 534 precios, 8 alertas.
- **Pendientes** (ver `tasks/todo.md`): decisiones de limpieza (scripts sueltos obsoletos,
  adapters Level/Sky sin uso), bug esporádico "list index out of range" del parser v3 (vigilar),
  unificar criterio de pin con el clon de Río (`brasil-rio-` usa `>=3.0.2,<4`, ya arreglado aparte).
- **Bumps de fast-flights**: siempre a mano y con probe local previa (ver tasks/todo.md).

## Model usage (Opus 4.6 / Sonnet 4.6 solamente)
- Default: **Sonnet 4.6** (`claude-sonnet-4-6`) — edits de código, tests, scripts, refactors chicos, ejecutar comandos, lectura/grep de código.
- Escalar a **Opus 4.6** (`/model claude-opus-4-6`) solo para: planning no-trivial, diseño arquitectónico, debugging no-obvio, decisiones de diseño.
- **No usar ningún otro modelo** — en particular NO usar Opus 4.7 (`opus`) ni Haiku. Si Claude Code arranca con otro default, cambiar con `/model claude-sonnet-4-6`.

## Project
Automated Telegram bot that checks flight prices from multiple sources (Level API, Sky Airline API, Google Flights via fast-flights) and sends alerts when prices drop below configurable thresholds. Runs on GitHub Actions cron (every 6 hours), costs $0.

## Conventions
- Python 3.11+, type hints required on all public functions
- Code, variables, functions, class names, docstrings: **English**
- Inline comments and explanations: **Spanish**
- Linter: ruff (`ruff check src/`)
- Tests: pytest (`pytest tests/ -v`)
- Async: use `httpx` (async) for HTTP calls, `asyncio` for orchestration

## Key Commands
```bash
python -m src.main              # Run the bot (requires .env with Telegram tokens)
python -m src.main --dry-run    # Run without sending Telegram alerts (prints to console)
ruff check src/                 # Linting
pytest tests/ -v                # Run tests
```

## Architecture
Adapter pattern: each data source has its own module in `src/adapters/` returning standardized `PriceResult` objects. The engine orchestrates adapters, the checker compares against thresholds, and the notifier sends Telegram alerts. A state manager prevents duplicate alerts within a configurable cooldown period.

## Environment Variables (.env)
- `TELEGRAM_BOT_TOKEN` — Bot token from @BotFather
- `TELEGRAM_CHAT_ID` — Your chat ID for receiving alerts
- `DRY_RUN` — Set to "true" for testing without sending messages

## Data Sources
1. **Level Airlines** — GET, no auth, returns USD prices for Europe routes
2. **Sky Airline** — POST, public API key (Azure APIM), returns ARS prices for regional routes
3. **Google Flights** — via `fast-flights` library, covers all airlines worldwide

## Testing a Single Adapter
```bash
pytest tests/test_level_adapter.py -v    # Test Level adapter only
pytest tests/test_sky_adapter.py -v      # Test Sky adapter only
pytest tests/test_checker.py -v          # Test price threshold logic
pytest tests/test_checker.py::test_cross_currency_usd_to_ars -v  # Single test
```

## Adding a New Adapter
1. Create `src/adapters/<airline>.py` implementing `BaseAdapter` from `src/adapters/base.py`
2. Implement `async fetch_prices(route: RouteConfig) -> list[PriceResult]`
3. Register the adapter in `src/engine.py` (see existing adapter initialization)
4. Add the source name to routes in `config/routes-recife.json` (or the active config)

## Configuration
Routes and thresholds are in `config/routes-recife.json` (active, used by the cron workflow) and `config/routes-norte.json` (dormant). The `manual_usd_to_ars` setting controls cross-currency threshold comparison; note that since fast-flights 3.x the Google Flights adapter requests prices directly in USD, so thresholds compare without conversion. Alert state is persisted in `data/alert_state.json` (auto-generated, gitignored, cached by GitHub Actions).
