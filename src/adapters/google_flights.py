"""Google Flights price adapter via fast-flights library.

Usa la librería fast-flights (API v3: FlightQuery + create_query + get_flights)
para scrapear Google Flights. Cubre TODAS las aerolíneas en cualquier ruta.
Funciona decodificando parámetros Protobuf de las URLs de Google Flights.

Install: pip install fast-flights
Docs: https://github.com/AWeirdDev/flights
"""

import asyncio
import logging
import multiprocessing
from datetime import date, timedelta

from src.adapters.base import BaseAdapter
from src.adapters.scan_dates import DEFAULT_DAYS_BETWEEN_SCANS, build_scan_dates
from src.models import AppSettings, PriceResult, RouteConfig

logger = logging.getLogger(__name__)

# Escanear cada N días (compromiso entre cobertura y velocidad).
# Alias del default compartido en scan_dates.py (lo importan los tests).
DAYS_BETWEEN_SCANS = DEFAULT_DAYS_BETWEEN_SCANS

# Timeout por request en segundos (evita que se cuelgue indefinidamente)
# Usa multiprocessing para poder matar el proceso de verdad
REQUEST_TIMEOUT_SECONDS = 45

# Moneda solicitada a Google Flights. La API v3 permite pedirla explícita:
# USD directo evita convertir ARS con un tipo de cambio manual desactualizado
# (con la v2, manual_usd_to_ars=1500 hacía parecer ~500 USD un vuelo de 601).
REQUEST_CURRENCY = "USD"


def _serialize_flights(result: list) -> list[dict]:
    """Serialize fast-flights v3 results to plain dicts.

    Necesario porque los resultados cruzan la frontera del subproceso por
    una Queue (solo objetos picklables simples). Los segmentos de `f.flights`
    corresponden al tramo de ida: N segmentos = N-1 escalas.
    """
    flights_data: list[dict] = []
    for f in result:
        flights_data.append({
            "name": ", ".join(f.airlines) if f.airlines else None,
            "price": f.price,
            "stops": max(len(f.flights) - 1, 0),
        })
    return flights_data


def _fetch_in_subprocess(
    origin: str,
    destination: str,
    scan_date_iso: str,
    return_date_iso: str | None,
    trip: str,
    result_queue: multiprocessing.Queue,
) -> None:
    """Run get_flights in a separate process.

    Se ejecuta en un proceso hijo para poder matarlo de verdad si se cuelga.
    Los threads de Python no se pueden matar, pero los procesos sí.
    """
    try:
        from fast_flights import (
            FlightQuery,
            FlightsNotFound,
            Passengers,
            create_query,
            get_flights,
        )

        flight_queries = [
            FlightQuery(
                date=scan_date_iso,
                from_airport=origin,
                to_airport=destination,
            ),
        ]
        if return_date_iso:
            flight_queries.append(
                FlightQuery(
                    date=return_date_iso,
                    from_airport=destination,
                    to_airport=origin,
                ),
            )

        query = create_query(
            flights=flight_queries,
            trip=trip,
            seat="economy",
            passengers=Passengers(adults=1),
            language="en",
            currency=REQUEST_CURRENCY,
        )

        try:
            result = get_flights(query)
        except FlightsNotFound:
            # Google no tiene vuelos para esta fecha: lista vacía, no error
            result_queue.put(("ok", []))
            return

        result_queue.put(("ok", _serialize_flights(result)))
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

    @staticmethod
    def _build_scan_dates(route: RouteConfig, today: date) -> list[date]:
        """Build the list of departure dates to scan (delegado al helper compartido)."""
        return build_scan_dates(route, today, DAYS_BETWEEN_SCANS)

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

        # Generar fechas a escanear. Si la ruta define una ventana explícita
        # (depart_from/depart_to), se escanea día-por-día dentro de ese rango.
        # Si no, se usa el modo clásico: months_ahead + active_months.
        dates_to_scan: list[date] = self._build_scan_dates(route, today)

        # Determinar tipo de viaje y duraciones a escanear
        is_round_trip = route.trip_type == "round_trip"

        if is_round_trip:
            # Escanear cada duración entera en [min, max] días (ej: 8, 9, 10).
            # Así no nos perdemos un precio bueno por un día más o menos de estadía.
            durations = list(range(
                self.settings.trip_duration_min_days,
                self.settings.trip_duration_max_days + 1,
            ))
        else:
            durations = [0]  # one-way: la duración no aplica

        # Construir lista de consultas (fecha_salida, duración). Cada combinación
        # es un request independiente a Google Flights.
        jobs: list[tuple[date, int]] = [
            (scan_date, dur) for scan_date in dates_to_scan for dur in durations
        ]

        logger.info(
            "Google Flights: escaneando %s → %s (%d fechas × %d duración%s = %d consultas%s)",
            route.origin, route.destination,
            len(dates_to_scan), len(durations),
            "es" if len(durations) != 1 else "",
            len(jobs),
            f", vuelta {durations[0]}-{durations[-1]} días" if is_round_trip else "",
        )

        self._consecutive_failures = 0

        for scan_date, return_days in jobs:
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

                # Convertir cada vuelo encontrado a PriceResult
                for flight in flights_data:
                    price = flight.get("price")
                    if not price or price <= 0:
                        continue

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
                            price=float(price),
                            currency=REQUEST_CURRENCY,
                            stops=flight.get("stops", 0),
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
