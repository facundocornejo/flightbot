# TODO — flight-price-bot

## Sesión 2026-07-08: auditoría + fix del mes mudo

- [x] Auditoría completa (bot muerto desde 2026-06-10, runs en verde)
- [x] Causa raíz: fast-flights 3.0 rompió la API; `>=2.2` instalaba la rota
- [x] Migrar adapter a fast-flights 3.0.2 (FlightQuery/create_query, USD directo)
- [x] Pin exacto `fast-flights==3.0.2` en requirements.txt
- [x] Anti-silencio: 0 precios → alerta Telegram + exit 2 (run rojo en Actions)
- [x] Default de config → routes-recife.json (routes.json no existía)
- [x] Tests del adapter activo (24/24 verdes, ruff limpio)
- [x] Verificar run real en Actions post-fix (run 28990402594: 534 precios, 8 alertas a Telegram, 2m49s)

## Pendientes (auditoría — decisiones de Facu)

- [x] ~~Clon de Río tiene el mismo bug~~ → ya estaba arreglado por otra sesión (commit eff2819,
      2026-07-08 23:49: v3 + anti-silencio + adapter Amadeus; run verificado con 178 precios).
      Nota: Río pinea `fast-flights>=3.0.2,<4`, este repo `==3.0.2` — unificar criterio algún día
- [ ] ¿Borrar scripts obsoletos? `find_cheap.py`, `send_top4.py`, `show_cheapest.py`
- [ ] ¿Borrar/reescribir `AGENTS.md`? (plantilla Node/Jest engañosa en repo Python)
- [ ] ¿Retirar adapters Level/Sky? (sin uso en ninguna config; Sky tiene API key hardcodeada)
- [ ] Revisar `manual_usd_to_ars` (1500 parece alto; ya no afecta a Google Flights que viene en USD)
- [ ] `rutasnuevas.txt`: notas de destinos por mes — ¿convertir en config nueva?
