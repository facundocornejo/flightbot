"""Price threshold checker.

Compara los precios obtenidos contra los umbrales configurados por ruta.
Soporta comparación directa por moneda y conversión usando tipo de cambio manual.
"""

import logging

from src.models import AppSettings, PriceResult, RouteConfig

logger = logging.getLogger(__name__)


def check_prices(
    results: list[PriceResult],
    routes: list[RouteConfig],
    settings: AppSettings,
) -> list[PriceResult]:
    """Filter results that are below their route's price threshold.

    Para cada PriceResult, busca la ruta correspondiente y compara el precio
    contra el umbral. Soporta conversión de moneda usando el tipo de cambio
    manual configurado en settings.manual_usd_to_ars.

    Args:
        results: Lista de precios obtenidos de todas las fuentes.
        routes: Lista de rutas con sus umbrales configurados.
        settings: Settings globales (incluye tipo de cambio manual).

    Returns:
        Lista de PriceResult que están por debajo del umbral.
    """
    alerts: list[PriceResult] = []

    # Crear lookup de rutas por origin-destination para búsqueda rápida
    route_lookup: dict[str, RouteConfig] = {
        f"{r.origin}-{r.destination}": r for r in routes
    }

    for result in results:
        route_key = f"{result.origin}-{result.destination}"
        route = route_lookup.get(route_key)

        if route is None:
            # Puede pasar si un adapter devuelve un aeropuerto distinto al configurado
            # (ej: Sky devuelve AEP en vez de EZE)
            # Intentar con variantes comunes
            alt_key = _find_alternative_route(result, route_lookup)
            if alt_key:
                route = route_lookup[alt_key]
            else:
                continue

        if _is_below_threshold(result, route, settings):
            alerts.append(result)

    logger.info(
        "Checker: %d precios analizados, %d alertas generadas.",
        len(results), len(alerts),
    )
    return alerts


def _is_below_threshold(
    result: PriceResult,
    route: RouteConfig,
    settings: AppSettings,
) -> bool:
    """Check if a price is below the route's threshold.

    Lógica de comparación:
    1. Si el precio es en USD y hay threshold_usd → comparar directo
    2. Si el precio es en ARS y hay threshold_ars → comparar directo
    3. Si hay mismatch de moneda → convertir usando tipo de cambio manual
    4. Si no hay umbral para esa moneda y no se puede convertir → ignorar
    """
    price = result.price
    currency = result.currency

    # Caso 1: Precio en USD, umbral en USD → comparación directa
    if currency == "USD" and route.threshold_usd is not None:
        if price <= route.threshold_usd:
            logger.debug(
                "✅ %s→%s %s: USD %.0f ≤ umbral USD %.0f",
                result.origin, result.destination, result.date,
                price, route.threshold_usd,
            )
            return True

    # Caso 2: Precio en ARS, umbral en ARS → comparación directa
    if currency == "ARS" and route.threshold_ars is not None:
        if price <= route.threshold_ars:
            logger.debug(
                "✅ %s→%s %s: ARS %.0f ≤ umbral ARS %.0f",
                result.origin, result.destination, result.date,
                price, route.threshold_ars,
            )
            return True

    # Caso 3: Conversión de moneda con tipo de cambio manual
    rate = settings.manual_usd_to_ars

    if currency == "USD" and route.threshold_ars is not None and rate > 0:
        # Convertir USD a ARS para comparar
        price_in_ars = price * rate
        if price_in_ars <= route.threshold_ars:
            logger.debug(
                "✅ %s→%s %s: USD %.0f (≈ ARS %.0f) ≤ umbral ARS %.0f",
                result.origin, result.destination, result.date,
                price, price_in_ars, route.threshold_ars,
            )
            return True

    if currency == "ARS" and route.threshold_usd is not None and rate > 0:
        # Convertir ARS a USD para comparar
        price_in_usd = price / rate
        if price_in_usd <= route.threshold_usd:
            logger.debug(
                "✅ %s→%s %s: ARS %.0f (≈ USD %.0f) ≤ umbral USD %.0f",
                result.origin, result.destination, result.date,
                price, price_in_usd, route.threshold_usd,
            )
            return True

    return False


def _find_alternative_route(
    result: PriceResult,
    route_lookup: dict[str, RouteConfig],
) -> str | None:
    """Try to find a matching route with alternative airport codes.

    Sky puede devolver AEP en vez de EZE (ambos son Buenos Aires).
    Este helper busca la ruta con códigos alternativos.
    """
    # Mapeo de aeropuertos equivalentes (misma ciudad)
    equivalents: dict[str, list[str]] = {
        "EZE": ["AEP"],
        "AEP": ["EZE"],
        "GIG": ["SDU"],  # Río de Janeiro: Galeão y Santos Dumont
        "SDU": ["GIG"],
    }

    # Intentar con origin alternativo
    for alt_origin in equivalents.get(result.origin, []):
        alt_key = f"{alt_origin}-{result.destination}"
        if alt_key in route_lookup:
            return alt_key

    # Intentar con destination alternativo
    for alt_dest in equivalents.get(result.destination, []):
        alt_key = f"{result.origin}-{alt_dest}"
        if alt_key in route_lookup:
            return alt_key

    return None
