"""Buscar vuelos bajo USD 300."""

import asyncio
from src.config import load_config
from src.adapters.google_flights import GoogleFlightsAdapter


async def main():
    routes, settings = load_config()
    adapter = GoogleFlightsAdapter(settings)

    print("Buscando vuelos bajo USD 300...\n")

    for route in routes:
        prices = await adapter.fetch_prices(route)

        # Filtrar precios bajos (considerando que pueden ser ARS mal etiquetados)
        for p in prices:
            # Si el precio es bajo (real USD) o convertido de ARS
            usd_price = p.price if p.price < 1000 else p.price / 1400

            if usd_price <= 350:  # Umbral un poco mas alto para ver mas opciones
                stops = "directo" if p.stops == 0 else f"{p.stops} escala(s)"
                date_clean = p.date.replace("\u2192", "->")
                print(f"{p.origin} -> {p.destination}")
                print(f"  Precio: {p.currency} {p.price:,.0f} (~USD {usd_price:,.0f})")
                print(f"  Aerolinea: {p.airline}")
                print(f"  Fecha: {date_clean}")
                print(f"  Escalas: {stops}")
                print()


if __name__ == "__main__":
    asyncio.run(main())
