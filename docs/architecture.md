# Architecture

## System Design

```
GitHub Actions Cron (every 6 hours)
        │
        ▼
   src/main.py (entry point)
        │
        ▼
   src/config.py (load routes.json)
        │
        ▼
   src/engine.py (orchestration)
        │
   ┌────┼────────────┐
   │    │            │
   ▼    ▼            ▼
 Level  Sky     Google Flights
Adapter Adapter    Adapter
   │    │            │
   └────┼────────────┘
        │
        ▼
   src/checker.py (compare vs thresholds)
        │
        ▼
   src/state.py (deduplicate alerts)
        │
        ▼ (if below threshold & not duplicate)
   src/notifier.py (Telegram)
```

## Adapter Pattern

Each data source implements `BaseAdapter` with a single method: `fetch_prices(route) -> list[PriceResult]`. This ensures:

- **Isolation**: Each adapter handles its own API specifics (auth, request format, response parsing)
- **Fault tolerance**: If one adapter fails, others continue working
- **Extensibility**: Adding a new airline = adding one new file in `src/adapters/`

## State Management

The alert state (`data/alert_state.json`) prevents duplicate notifications:

- **Key**: `{origin}-{destination}-{date}` (e.g., "EZE-BCN-2026-12-01")
- **Cooldown**: Configurable (default 48h). Same alert won't be sent twice within this period
- **Price drops**: If the price drops FURTHER after an alert, a new "price dropped!" alert is sent
- **Cleanup**: Records older than 7 days are automatically purged
- **Persistence**: GitHub Actions cache preserves state between runs

## Currency Handling

Rather than relying on potentially outdated exchange rate APIs, the bot uses a **manual exchange rate** (`manual_usd_to_ars` in config). The checker supports:

1. Direct comparison (USD price vs USD threshold, ARS price vs ARS threshold)
2. Cross-currency comparison using the manual rate
3. Both thresholds can be set per route for maximum flexibility
