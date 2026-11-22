#!/bin/bash
# Arranca Evolution API y el backend en un solo contenedor. Si uno se cae, el contenedor termina
# y Railway lo reinicia.

APP_PORT="${PORT:-8000}"
EVO_PORT="${EVOLUTION_INTERNAL_PORT:-8081}"
[ "$EVO_PORT" = "$APP_PORT" ] && EVO_PORT=8082

# --- Evolution: sus variables se derivan de las del proyecto ---
export DOCKER_ENV=true
export DATABASE_PROVIDER="${DATABASE_PROVIDER:-postgresql}"
export DATABASE_CONNECTION_URI="${DATABASE_CONNECTION_URI:-$EVOLUTION_DATABASE_URL}"
export AUTHENTICATION_API_KEY="${AUTHENTICATION_API_KEY:-$EVOLUTION_API_KEY}"
export SERVER_PORT="$EVO_PORT"
export SERVER_URL="http://127.0.0.1:$EVO_PORT"
# Los mensajes se guardan en la base `app`; Evolution solo conserva las sesiones.
export DATABASE_SAVE_DATA_INSTANCE=true
export DATABASE_SAVE_DATA_NEW_MESSAGE=false
export DATABASE_SAVE_MESSAGE_UPDATE=false
export DATABASE_SAVE_DATA_CONTACTS=false
export DATABASE_SAVE_DATA_CHATS=false
export DATABASE_SAVE_DATA_LABELS=false
export DATABASE_SAVE_DATA_HISTORIC=false
export CACHE_REDIS_ENABLED=false
export CACHE_LOCAL_ENABLED=true
export WEBHOOK_GLOBAL_ENABLED=false

if [ -z "$DATABASE_CONNECTION_URI" ] || [ -z "$AUTHENTICATION_API_KEY" ]; then
    echo "Faltan EVOLUTION_DATABASE_URL o EVOLUTION_API_KEY" >&2
    exit 1
fi

# --- Backend: se conecta a Evolution por la red local del contenedor ---
export EVOLUTION_URL="${EVOLUTION_URL:-http://127.0.0.1:$EVO_PORT}"
export WEBHOOK_BASE_URL="${WEBHOOK_BASE_URL:-http://127.0.0.1:$APP_PORT}"
# DATABASE_URL pertenece al backend; Evolution usa DATABASE_CONNECTION_URI.

(cd /evolution && exec /bin/bash -c ". ./Docker/scripts/deploy_database.sh && npm run start:prod") &
EVO_PID=$!

(cd /app && exec python -m app.main) &
APP_PID=$!

stop() { kill "$EVO_PID" "$APP_PID" 2>/dev/null; wait; }
trap stop TERM INT

wait -n "$EVO_PID" "$APP_PID"
CODE=$?
echo "Un proceso terminó (código $CODE); se detiene el contenedor." >&2
stop
exit "$CODE"
