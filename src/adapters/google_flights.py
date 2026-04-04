"""Google Flights price adapter via fast-flights library.

Usa la librería fast-flights para scrapear Google Flights. Cubre TODAS
las aerolíneas en cualquier ruta. Funciona decodificando parámetros
Protobuf de las URLs de Google Flights.

Install: pip install fast-flights
Docs: https://github.com/AWeirdDev/flights
"""

import asyncio
import logging
import multiprocessing
import re
from datetime import date, timedelta

from src.adapters.base import BaseAdapter
from src.models import AppSettings, PriceResult, RouteConfig

logger = logging.getLogger(__name__)

# Escanear cada N días (compromiso entre cobertura y velocidad)
DAYS_BETWEEN_SCANS = 7

# Timeout por request en segundos (evita que se cuelgue indefinidamente)
# Usa multiprocessing para poder matar el proceso de verdad
REQUEST_TIMEOUT_SECONDS = 45

# Modo de fetch: "common" es el más rápido y funciona en GitHub Actions
# Si falla consistentemente, cambiar a "fallback" (usa Playwright serverless)
FETCH_MODE = "common"


def _parse_price(price_str: str | None) -> float | None:
    """Parse price string from fast-flights to float.

    fast-flights devuelve precios como strings tipo "$1,234", "ARS 500,000",
    "€ 450", etc. Este parser extrae el número.

    Ejemplos:
        "$1,234" → 1234.0
        "ARS 500,000" → 500000.0
        "€450" → 450.0
        None → None
    """
    if not price_str:
        return None

    # Remover todo excepto dígitos, puntos y comas
    cleaned = re.sub(r"[^\d.,]", "", str(price_str))

    if not cleaned:
        return None

    # Manejar formato con coma como separador de miles (1,234 o 500,000)
    # y punto como separador decimal (1,234.56)
    if "," in cleaned and "." in cleaned:
        # Tiene ambos: 1,234.56 → quitar comas
        cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        # Solo comas: podría ser 1,234 (miles) o 1,50 (decimal europeo)
        parts = cleaned.split(",")
        if len(parts[-1]) == 3:
            # Separador de miles: 1,234 o 500,000
            cleaned = cleaned.replace(",", "")
        else:
            # Separador decimal europeo: 1,50
            cleaned = cleaned.replace(",", ".")

    try:
        return float(cleaned)
    except ValueError:
        logger.warning("No se pudo parsear precio: '%s' → '%s'", price_str, cleaned)
        return None


def _parse_stops(stops_str: str | int | None) -> int:
    """Parse stops from fast-flights to int.

    fast-flights puede devolver "Nonstop", "1 stop", "2 stops", o un int.
    """
    if stops_str is None:
        return 0
    if isinstance(stops_str, int):
        return stops_str

    stops_lower = str(stops_str).lower()
    if "nonstop" in stops_lower or "direct" in stops_lower:
        return 0

    # Buscar número en el string
    match = re.search(r"(\d+)", str(stops_str))
    return int(match.group(1)) if match else 0


def _detect_currency(price_str: str | None) -> str:
    """Detect currency from price string.

    Intenta detectar la moneda del precio según el símbolo o prefijo.
    Por defecto asume USD para rutas internacionales desde Argentina.
    """
    if not price_str:
        return "USD"

    price_upper = str(price_str).upper()
    if "ARS" in price_upper or "AR$" in price_upper:
        return "ARS"
    if "€" in price_upper or "EUR" in price_upper:
        return "EUR"
    # USD es el default para Google Flights en rutas internacionales
    return "USD"


def _fetch_in_subprocess(
    origin: str,
    destination: str,
    scan_date_iso: str,
    return_date_iso: str | None,
    trip: str,
    fetch_mode: str,
    result_queue: multiprocessing.Queue,
) -> None:
    """Run get_flights in a separate process.

    Se ejecuta en un proceso hijo para poder matarlo de verdad si se cuelga.
    Los threads de Python no se pueden matar, pero los procesos sí.
    """
    try:
        from fast_flights import FlightData, Passengers, get_flights

        flight_data_list = [
            FlightData(
                date=scan_date_iso,
                from_airport=origin,
                to_airport=destination,
            ),
        ]
        if return_date_iso:
            flight_data_list.append(
                FlightData(
                    date=return_date_iso,
                    from_airport=destination,
                    to_airport=origin,
                ),
            )

        result = get_flights(
            flight_data=flight_data_list,
            trip=trip,
            seat="economy",
            passengers=Passengers(adults=1),
            fetch_mode=fetch_mode,
        )

        # Serializar resultados porque no podemos pasar objetos complejos entre procesos
        flights_data = []
        if result and result.flights:
            for f in result.flights:
                flights_data.append({
                    "name": str(f.name) if f.name else None,
                    "price": str(f.price) if f.price else None,
                    "stops": str(f.stops) if f.stops is not None else None,
                })
        result_queue.put(("ok", flights_data))
    except Exception as e:
        result_queue.put(("error", str(e)))


class GoogleFlightsAdapter(BaseAdapter):
    """Adapter for Google Flights via fast-flights library."""

    def __init__(self, settings: AppSettings) -> None:
        super().__init__(settings)
        self._available = True  # Se pone en False si fast-flights no está instalado
        self._consecutive_failures = 0
        # Máximo de fallos consecutivos antes de abortar esta ruta
        self._max_consecutive_failures = 5

    @property
    def source_name(self) -> str:
        return "google_flights"

    async def _fetch_single_date(
        self,
        route: RouteConfig,
        scan_date: date,
        return_days: int,
        is_round_trip: bool,
    ) -> list[dict]:
        """Fetch flights for a single date using a subprocess with hard timeout.

        Usa multiprocessing en vez de threads para poder matar el proceso
        si se cuelga (los threads de Python no se pueden matar).
        """
        trip = "round-trip" if is_round_trip else "one-way"
        return_date_iso = None
        if is_round_trip:
            return_date_iso = (scan_date + timedelta(days=return_days)).isoformat()

        result_queue: multiprocessing.Queue = multiprocessing.Queue()
        proc = multiprocessing.Process(
            target=_fetch_in_subprocess,
            args=(
                route.origin,
                route.destination,
                scan_date.isoformat(),
                return_date_iso,
                trip,
                FETCH_MODE,
                result_queue,
            ),
        )
        proc.start()

        # Esperar resultado con timeout real (mata el proceso si se cuelga)
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(result_queue.get, timeout=REQUEST_TIMEOUT_SECONDS),
                timeout=REQUEST_TIMEOUT_SECONDS + 5,
            )
        except (asyncio.TimeoutError, Exception):
            # Matar el proceso de verdad
            if proc.is_alive():
                proc.kill()
                proc.join(timeout=5)
            logger.warning(
                "Google Flights: timeout (%ds) en %s→%s fecha %s, salteando...",
                REQUEST_TIMEOUT_SECONDS, route.origin, route.destination, scan_date,
            )
            return []
        finally:
            # Asegurar que el proceso hijo no quede zombie
            if proc.is_alive():
                proc.kill()
                proc.join(timeout=5)

        status, data = result
        if status == "error":
            logger.warning(
                "Google Flights: error en %s→%s fecha %s: %s",
                route.origin, route.destination, scan_date, data,
            )
            return []

        return data

    async def fetch_prices(self, route: RouteConfig) -> list[PriceResult]:
        """Fetch prices from Google Flights for specific dates.

        Escanea fechas durante months_ahead meses. Para round-trip, usa la
        duración configurada en settings (trip_duration_min/max_days).
        """
        # Intentar importar fast_flights (verificar que está instalado)
        try:
            import fast_flights  # noqa: F401
        except ImportError:
            if self._available:
                logger.error(
                    "fast-flights no está instalado. "
                    "Ejecutá: pip install fast-flights"
                )
                self._available = False
            return []

        results: list[PriceResult] = []
        today = date.today()
        total_days = route.months_ahead * 30

        # Generar fechas a escanear usando el intervalo configurado
        dates_to_scan: list[date] = []
        current = today + timedelta(days=1)  # Empezar desde mañana
        while (current - today).days <= total_days:
            # Si hay active_months, solo incluir fechas en esos meses
            if not route.active_months or current.month in route.active_months:
                dates_to_scan.append(current)
            current += timedelta(days=DAYS_BETWEEN_SCANS)

        # Determinar tipo de viaje y duración
        is_round_trip = route.trip_type == "round_trip"

        # Usar duración promedio para round-trip
        return_days = (self.settings.trip_duration_min_days + self.settings.trip_duration_max_days) // 2

        logger.info(
            "Google Flights: escaneando %s → %s (%d fechas%s)",
            route.origin, route.destination,
            len(dates_to_scan),
            f", vuelta +{return_days} días" if is_round_trip else "",
        )

        self._consecutive_failures = 0

        for scan_date in dates_to_scan:
            # Si hay muchos fallos consecutivos, abortar esta ruta
            if self._consecutive_failures >= self._max_consecutive_failures:
                logger.warning(
                    "Google Flights: %d fallos consecutivos en %s→%s, abortando ruta.",
                    self._consecutive_failures, route.origin, route.destination,
                )
                break

            try:
                flights_data = await self._fetch_single_date(
                    route, scan_date, return_days, is_round_trip,
                )

                if not flights_data:
                    self._consecutive_failures += 1
                else:
                    self._consecutive_failures = 0

                # Parsear cada vuelo encontrado
                for flight in flights_data:
                    price = _parse_price(flight.get("price"))
                    if price is None:
                        continue

                    currency = _detect_currency(flight.get("price"))

                    # Formatear fecha con duración del viaje
                    date_display = scan_date.isoformat()
                    if is_round_trip:
                        return_date = scan_date + timedelta(days=return_days)
                        date_display = f"{scan_date.isoformat()} → {return_date.isoformat()}"

                    results.append(
                        PriceResult(
                            source=self.source_name,
                            airline=flight.get("name") or "Unknown",
                            origin=route.origin,
                            destination=route.destination,
                            date=date_display,
                            price=price,
                            currency=currency,
                            stops=_parse_stops(flight.get("stops")),
                        )
                    )

            except Exception as e:
                self._consecutive_failures += 1
                logger.warning(
                    "Google Flights: error al consultar %s→%s fecha %s: %s",
                    route.origin, route.destination, scan_date, e,
                )

            # Delay entre requests para evitar rate limiting de Google
            await asyncio.sleep(self.settings.delay_between_requests_seconds)

        logger.info(
            "Google Flights: encontrados %d precios para %s → %s",
            len(results), route.origin, route.destination,
        )
        return results
