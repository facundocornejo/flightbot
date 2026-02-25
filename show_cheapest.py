"""Script para mostrar los vuelos más baratos por ruta."""

import asyncio
from collections import defaultdict

from src.config import load_config
from src.adapters.google_flights import GoogleFlightsAdapter


async def main():
    routes, settings = load_config()
    adapter = GoogleFlightsAdapter(settings)

    # Recolectar todos los precios
    all_prices = []

    for route in routes:
        print(f"\nBuscando {route.origin} -> {route.destination}...")
        prices = await adapter.fetch_prices(route)
        for p in prices:
            all_prices.append(p)

    # Agrupar por ruta
    by_route = defaultdict(list)
    for p in all_prices:
        key = f"{p.origin} -> {p.destination}"
        by_route[key].append(p)

    # Mostrar los 5 más baratos de cada ruta
    print("\n" + "="*70)
    print("TOP 5 VUELOS MAS BARATOS POR RUTA (ida+vuelta, 8 dias)")
    print("="*70)

    for route_key in sorted(by_route.keys()):
        prices = by_route[route_key]
        # Ordenar por precio
        prices.sort(key=lambda x: x.price)

        print(f"\n{route_key}")
        print("-" * 50)

        if not prices:
            print("  No se encontraron vuelos")
            continue

        for i, p in enumerate(prices[:5], 1):
            stops_txt = "directo" if p.stops == 0 else f"{p.stops} escala(s)"
            # Limpiar fecha para Windows
            date_clean = p.date.replace("→", "->")
            print(f"  {i}. USD {p.price:,.0f} - {p.airline} - {date_clean} ({stops_txt})")


if __name__ == "__main__":
    asyncio.run(main())
