"""Enviar los 4 vuelos mas baratos a Telegram."""

import asyncio
import os
from dotenv import load_dotenv

from src.models import PriceResult
from src.notifier import send_alert

load_dotenv()

# Los 4 vuelos mas baratos encontrados
VUELOS = [
    PriceResult(
        source="google_flights",
        airline="JetSMART",
        origin="EZE",
        destination="GIG",
        date="15 abril -> 23 abril 2026",
        price=337833,
        currency="ARS",
        stops=0,
        tags=["Precio mas bajo encontrado"],
    ),
    PriceResult(
        source="google_flights",
        airline="JetSMART",
        origin="EZE",
        destination="GIG",
        date="12 abril -> 20 abril 2026",
        price=375629,
        currency="ARS",
        stops=0,
    ),
    PriceResult(
        source="google_flights",
        airline="JetSMART",
        origin="EZE",
        destination="GIG",
        date="6 abril -> 14 abril 2026",
        price=391794,
        currency="ARS",
        stops=0,
    ),
    PriceResult(
        source="google_flights",
        airline="Unknown",
        origin="EZE",
        destination="SSA",
        date="31 marzo -> 8 abril 2026",
        price=616968,
        currency="ARS",
        stops=0,
    ),
]


async def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("Error: Falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en .env")
        return

    print(f"Enviando {len(VUELOS)} alertas a Telegram...")

    for i, vuelo in enumerate(VUELOS, 1):
        # Agregar precio en USD al mensaje
        usd_price = vuelo.price / 1400
        print(f"  {i}. {vuelo.origin} -> {vuelo.destination}: ARS {vuelo.price:,.0f} (~USD {usd_price:.0f})")

        success = await send_alert(token, chat_id, vuelo)
        if success:
            print(f"     Enviado OK")
        else:
            print(f"     Error al enviar")

        # Pequeno delay entre mensajes
        await asyncio.sleep(1)

    print("\nListo!")


if __name__ == "__main__":
    asyncio.run(main())
