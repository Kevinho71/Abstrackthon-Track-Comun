# Agente de seguimiento de chats

Servicio que recibe los chats de WhatsApp por Evolution API, los guarda, los clasifica con Gemini y recuerda los pendientes.
El plan por fases está en [PLAN.md](PLAN.md) y las alternativas evaluadas en [ALTERNATIVAS.md](ALTERNATIVAS.md).

## Ejecutar las pruebas

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pytest
```

## Ejecutar todo en local con Docker (Evolution + backend, igual que en Railway)

```powershell
copy .env.example .env      # completa las variables
docker build -t chatfollowup .
docker run --rm -p 8000:8000 --env-file .env -e PORT=8000 -e EVOLUTION_URL= -e WEBHOOK_BASE_URL= chatfollowup
```

`GET http://localhost:8000/health` responde `{"ok": true}`. La primera vez, Evolution tarda
unos minutos en aplicar sus migraciones en la base `evolution`.

## Desplegar en Railway (un solo servicio)

1. Crea un servicio desde este repositorio. `railway.toml` indica que se construye con el `Dockerfile`.
2. Variables: `DATABASE_URL`, `EVOLUTION_DATABASE_URL`, `EVOLUTION_API_KEY`, `WEBHOOK_TOKEN`, `SESSION_SECRET`, `TZ`.
3. Genera el dominio público del servicio y guárdalo en `PUBLIC_URL`.
4. No añadas más servicios ni réplicas: Evolution y el backend corren juntos en el mismo contenedor.
