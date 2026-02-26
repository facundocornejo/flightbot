"""Main orchestration engine.

Coordina la ejecución de todos los adapters, agrega resultados,
filtra por umbrales, verifica duplicados, y envía alertas.
Es el "cerebro" del bot.
"""

import asyncio
import logging

# Límite de rutas procesadas en paralelo (evita rate-limiting de Google)
MAX_CONCURRENT_ROUTES = 2

from src.adapters import GoogleFlightsAdapter, LevelAdapter, SkyAdapter
from src.adapters.base import BaseAdapter
from src.checker import check_prices
from src.models import AppSettings, PriceResult, RouteConfig
from src.notifier import print_alert, send_alert, send_error_alert
from src.state import AlertStateManager

logger = logging.getLogger(__name__)


async def run(
    routes: list[RouteConfig],
    settings: AppSettings,
    telegram_token: str | None = None,
    telegram_chat_id: str | None = None,
    dry_run: bool = False,
) -> None:
    """Execute the full price checking pipeline.

    Flujo completo:
    1. Inicializar adapters y state manager
    2. Para cada ruta, ejecutar los adapters correspondientes
    3. Agregar todos los resultados
    4. Filtrar por umbrales
    5. Verificar duplicados (state manager)
    6. Enviar alertas (o imprimir en dry-run)
    7. Guardar estado

    Args:
        routes: Lista de rutas a monitorear.
        settings: Configuración global.
        telegram_token: Token del bot (None en dry-run).
        telegram_chat_id: Chat ID de Telegram (None en dry-run).
        dry_run: Si True, imprime en consola en vez de enviar Telegram.
    """
    # Inicializar state manager para control de duplicados
    state = AlertStateManager(cooldown_hours=settings.alert_cooldown_hours)

    # Inicializar adapters (uno por tipo de fuente)
    adapters: dict[str, BaseAdapter] = {
        "level": LevelAdapter(settings),
        "sky": SkyAdapter(settings),
        "google_flights": GoogleFlightsAdapter(settings),
    }

    # === Paso 1: Recolectar precios de todas las fuentes (en paralelo con límite) ===
    all_results: list[PriceResult] = []
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_ROUTES)

    async def process_route(route: RouteConfig) -> list[PriceResult]:
        """Procesa una ruta con todas sus fuentes, respetando el semáforo."""
        async with semaphore:
            route_results: list[PriceResult] = []
            logger.info(
                "━━━ Procesando ruta: %s → %s (fuentes: %s) ━━━",
                route.origin, route.destination, ", ".join(route.sources),
            )

            for source_name in route.sources:
                adapter = adapters.get(source_name)
                if adapter is None:
                    logger.warning("Adapter '%s' no encontrado, salteando.", source_name)
                    continue

                try:
                    results = await adapter.fetch_prices(route)
                    route_results.extend(results)
                    logger.info(
                        "%s: %d precios obtenidos para %s→%s",
                        source_name, len(results), route.origin, route.destination,
                    )
                except Exception as e:
                    logger.error(
                        "%s: error fatal al consultar %s→%s: %s",
                        source_name, route.origin, route.destination, e,
                    )
            return route_results

    # Ejecutar todas las rutas en paralelo (máximo MAX_CONCURRENT_ROUTES a la vez)
    route_results_list = await asyncio.gather(*[process_route(r) for r in routes])
    for route_results in route_results_list:
        all_results.extend(route_results)

    logger.info("Total de precios recolectados: %d", len(all_results))

    # === Paso 2: Filtrar por umbrales ===
    alerts = check_prices(all_results, routes, settings)
    logger.info("Alertas que pasaron el filtro de umbral: %d", len(alerts))

    # === Paso 3: Filtrar duplicados y enviar alertas ===
    sent_count = 0
    skipped_count = 0

    for alert in alerts:
        if not state.should_alert(alert):
            skipped_count += 1
            continue

        # Verificar si el precio bajó (para mensaje diferente)
        is_drop = _is_price_drop(alert, state)

        if dry_run:
            print_alert(alert, is_price_drop=is_drop)
        else:
            if telegram_token and telegram_chat_id:
                success = await send_alert(
                    telegram_token, telegram_chat_id, alert, is_price_drop=is_drop,
                )
                if success:
                    sent_count += 1

        # Registrar la alerta como enviada (incluso en dry-run para testing)
        state.record_alert(alert)

    # === Paso 4: Verificar si Sky tuvo problemas de API key ===
    sky_adapter = adapters.get("sky")
    if isinstance(sky_adapter, SkyAdapter) and sky_adapter.api_key_failed:
        error_msg = (
            "La API key de Sky Airline fue rechazada (401/403). "
            "Probablemente fue rotada. El bot no puede consultar precios de Sky "
            "hasta que se actualice la key en src/adapters/sky.py"
        )
        if dry_run:
            print(f"\n⚠️ {error_msg}")
        elif telegram_token and telegram_chat_id:
            await send_error_alert(telegram_token, telegram_chat_id, error_msg)

    # === Paso 5: Guardar estado ===
    state.save()

    # Resumen final
    logger.info(
        "━━━ Resumen: %d alertas enviadas, %d duplicadas salteadas ━━━",
        sent_count if not dry_run else 0,
        skipped_count,
    )


def _is_price_drop(alert: PriceResult, state: AlertStateManager) -> bool:
    """Check if this alert represents a price drop from a previous alert.

    Verifica si ya habíamos alertado esta ruta+fecha a un precio mayor.
    Si es así, el mensaje dirá "BAJÓ MÁS" en vez de "ALERTA DE PRECIO".
    """
    existing = state._state.get(alert.route_key)
    if existing is None:
        return False
    return alert.price < existing.price
