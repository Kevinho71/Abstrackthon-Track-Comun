# Un solo servicio: Evolution API y el backend en el mismo contenedor.
# La imagen base ya trae Node y Evolution en /evolution. Se fija la versión.
FROM evoapicloud/evolution-api:v2.3.7

USER root
RUN apk add --no-cache python3 py3-pip \
    && python3 -m venv /opt/venv

WORKDIR /app
COPY requirements.txt .
RUN /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY start.sh .
RUN chmod +x start.sh

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# Railway enruta el dominio público solo al puerto $PORT (el backend).
# Evolution escucha en 127.0.0.1:EVOLUTION_INTERNAL_PORT y no se expone.
ENTRYPOINT ["/bin/bash", "/app/start.sh"]
