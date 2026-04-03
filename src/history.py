"""Alert history persistence for the public dashboard.

Guarda un historial de alertas enviadas en docs/data/alerts.json.
GitHub Pages sirve ese archivo para que el dashboard lo consuma.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.models import PriceResult

logger = logging.getLogger(__name__)

HISTORY_FILE = Path(__file__).parent.parent / "docs" / "data" / "alerts.json"

# Máximo de días de historial (evita que el archivo crezca indefinidamente)
MAX_HISTORY_DAYS = 90


def save_alerts_to_history(alerts: list[tuple[PriceResult, bool]]) -> None:
    """Append new alerts to the history file for the dashboard.

    Recibe una lista de tuplas (PriceResult, is_price_drop). Lee el archivo
    existente, agrega las nuevas alertas, poda las viejas, y guarda.

    Args:
        alerts: Lista de (resultado, es_baja_de_precio) a persistir.
    """
    if not alerts:
        logger.info("Sin alertas nuevas para el historial del dashboard.")
        return

    # Crear directorio si no existe
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Leer historial existente
    existing: list[dict] = []
    if HISTORY_FILE.exists():
        try:
            data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            existing = data.get("alerts", [])
        except (json.JSONDecodeError, KeyError):
            logger.warning("alerts.json corrupto, empezando historial nuevo.")
            existing = []

    # Construir set de claves existentes para deduplicar
    existing_keys = {(a["route_key"], a["fetched_at"]) for a in existing}

    # Agregar nuevas alertas
    new_count = 0
    for result, is_drop in alerts:
        key = (result.route_key, result.fetched_at)
        if key in existing_keys:
            continue

        existing.append({
            "source": result.source,
            "airline": result.airline,
            "origin": result.origin,
            "destination": result.destination,
            "date": result.date,
            "price": result.price,
            "currency": result.currency,
            "stops": result.stops,
            "fetched_at": result.fetched_at,
            "route_key": result.route_key,
            "is_price_drop": is_drop,
        })
        existing_keys.add(key)
        new_count += 1

    # Podar entradas viejas (> MAX_HISTORY_DAYS)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=MAX_HISTORY_DAYS)).isoformat()
    existing = [a for a in existing if a.get("fetched_at", "") >= cutoff]

    # Guardar
    output = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "alerts": existing,
    }
    HISTORY_FILE.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info(
        "Dashboard: %d alertas nuevas guardadas (%d total en historial).",
        new_count, len(existing),
    )
