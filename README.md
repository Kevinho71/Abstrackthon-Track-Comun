# Agente de seguimiento de chats

Bot de Telegram que resume y clasifica chats de atención al cliente con Gemini, y recuerda los pendientes.
El plan por fases está en [PLAN.md](PLAN.md).

## Ejecutar en local

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # y completa TELEGRAM_BOT_TOKEN y GEMINI_API_KEY
python -m pytest            # pruebas
python -m app.main          # inicia el bot
```

Prueba enviando al bot `samples/chat_ejemplo.txt`.

## Desplegar en Railway

1. Sube el repo a GitHub y crea un proyecto en Railway desde el repo.
2. Añade un **Volume** montado en `/data`.
3. Variables: `TELEGRAM_BOT_TOKEN`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `TZ`, `ALLOWED_USER_IDS`, `DB_PATH=/data/app.db`.
4. El comando de inicio está en `railway.toml`. Mantén **una sola instancia**: dos procesos con el mismo token provocan el error `Conflict` de Telegram.
