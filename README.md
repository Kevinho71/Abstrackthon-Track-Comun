# Agente de seguimiento de chats

Servicio que recibe los chats de WhatsApp por Evolution API, los guarda, los clasifica con Gemini y recuerda los pendientes.
El plan por fases está en [PLAN.md](PLAN.md) y las alternativas evaluadas en [ALTERNATIVAS.md](ALTERNATIVAS.md).

## Ejecutar en local

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # completa EVOLUTION_API_KEY y WEBHOOK_TOKEN
python -m pytest            # pruebas
python -m app.main          # inicia el backend en http://localhost:8000
```

`GET /health` responde `{"ok": true}`. Evolution envía sus eventos a
`POST /webhook/evolution?token=<WEBHOOK_TOKEN>`.

## Desplegar en Railway

1. Proyecto con Postgres y dos bases: `app` y `evolution`.
2. Servicio `evolution` con una versión fija de la imagen oficial y **sin dominio público**.
3. Servicio `app` desde este repositorio, con dominio público. El comando de inicio está en `railway.toml`.
4. Variables del servicio `app`: `DATABASE_URL`, `EVOLUTION_URL` (red privada), `EVOLUTION_API_KEY`, `WEBHOOK_TOKEN`, `PUBLIC_URL`, `WEBHOOK_BASE_URL`, `TZ`.
5. Una sola instancia de cada servicio.
