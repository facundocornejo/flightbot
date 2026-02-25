"""Configuration loading and validation.

Carga la configuración de rutas y settings desde config/routes.json.
Valida que todos los campos requeridos estén presentes y sean correctos.
"""

import json
import logging
from pathlib import Path

from src.models import AppSettings, RouteConfig

logger = logging.getLogger(__name__)

# Fuentes válidas que tienen adapter implementado
VALID_SOURCES = {"level", "sky", "google_flights"}

# Ruta al archivo de configuración (relativa a la raíz del proyecto)
CONFIG_PATH = Path(__file__).parent.parent / "config" / "routes.json"


def load_config(config_path: Path | None = None) -> tuple[list[RouteConfig], AppSettings]:
    """Load routes and settings from config file.

    Carga y valida el archivo de configuración. Devuelve una tupla con
    la lista de rutas y los settings globales.

    Args:
        config_path: Ruta al archivo JSON. Si es None, usa la ruta por defecto.

    Returns:
        Tuple of (routes, settings)

    Raises:
        FileNotFoundError: Si el archivo de configuración no existe.
        ValueError: Si la configuración es inválida.
    """
    path = config_path or CONFIG_PATH

    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path}. "
            f"Copiá config/routes.json.example a config/routes.json y editalo."
        )

    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    routes = _parse_routes(raw.get("routes", []))
    settings = _parse_settings(raw.get("settings", {}))

    logger.info(
        "Configuración cargada: %d rutas, cooldown=%dh, USD/ARS=%.0f",
        len(routes),
        settings.alert_cooldown_hours,
        settings.manual_usd_to_ars,
    )

    return routes, settings


def _parse_routes(raw_routes: list[dict]) -> list[RouteConfig]:
    """Parse and validate route configurations.

    Parsea cada ruta del JSON y verifica que tenga los campos mínimos:
    origin, destination, al menos una fuente válida, y al menos un umbral.
    """
    routes: list[RouteConfig] = []

    for i, r in enumerate(raw_routes):
        # Validar campos obligatorios
        origin = r.get("origin", "").upper().strip()
        destination = r.get("destination", "").upper().strip()

        if not origin or not destination:
            logger.warning("Ruta #%d: falta origin o destination, salteando.", i)
            continue

        # Validar fuentes
        sources = [s.lower().strip() for s in r.get("sources", [])]
        invalid = set(sources) - VALID_SOURCES
        if invalid:
            logger.warning(
                "Ruta %s→%s: fuentes inválidas %s (válidas: %s)",
                origin, destination, invalid, VALID_SOURCES,
            )
        sources = [s for s in sources if s in VALID_SOURCES]

        if not sources:
            logger.warning("Ruta %s→%s: sin fuentes válidas, salteando.", origin, destination)
            continue

        # Validar umbrales — necesita al menos uno
        threshold_usd = r.get("threshold_usd")
        threshold_ars = r.get("threshold_ars")

        if threshold_usd is None and threshold_ars is None:
            logger.warning(
                "Ruta %s→%s: sin umbrales definidos (threshold_usd o threshold_ars), salteando.",
                origin, destination,
            )
            continue

        route = RouteConfig(
            origin=origin,
            destination=destination,
            sources=sources,
            threshold_usd=float(threshold_usd) if threshold_usd is not None else None,
            threshold_ars=float(threshold_ars) if threshold_ars is not None else None,
            months_ahead=int(r.get("months_ahead", 6)),
            trip_type=r.get("trip_type", "round_trip"),
        )
        routes.append(route)

    if not routes:
        raise ValueError("No hay rutas válidas en la configuración.")

    return routes


def _parse_settings(raw: dict) -> AppSettings:
    """Parse global settings with defaults.

    Parsea los settings globales. Si falta alguno, usa el valor por defecto.
    """
    return AppSettings(
        delay_between_requests_seconds=int(raw.get("delay_between_requests_seconds", 3)),
        alert_cooldown_hours=int(raw.get("alert_cooldown_hours", 48)),
        user_agent=raw.get(
            "user_agent",
            AppSettings.user_agent,
        ),
        manual_usd_to_ars=float(raw.get("manual_usd_to_ars", 1200.0)),
        trip_duration_min_days=int(raw.get("trip_duration_min_days", 7)),
        trip_duration_max_days=int(raw.get("trip_duration_max_days", 10)),
    )
