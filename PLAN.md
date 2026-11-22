# Plan del proyecto: Agente de seguimiento de chats (WhatsApp con Evolution API, Gemini, web y Telegram, todo en Railway)

> Track: **Comercios**. Cada conversación de WhatsApp queda guardada, resumida, clasificada y con dueño, y nadie deja clientes colgados.
> Alternativas evaluadas y criterios de cambio: [ALTERNATIVAS.md](ALTERNATIVAS.md).

## 1. Qué se construye

Un servicio web para negocios y call centers que atienden clientes por WhatsApp.

1. Una persona entra a la web, crea su cuenta y pulsa **«Conectar WhatsApp»**. Vincula su número escaneando un QR o escribiendo un código de emparejamiento, igual que en «Dispositivos vinculados». Sigue usando WhatsApp en su teléfono sin cambios.
2. Cada mensaje de sus chats individuales llega por webhook desde Evolution API y se guarda en la base de datos. No hay exportación manual.
3. Cuando una conversación lleva 10 minutos sin mensajes nuevos, Gemini sugiere un **resumen**, un **estado**, la **siguiente acción** y una **fecha de seguimiento**.
4. La persona confirma o cambia el estado en la web.
5. Los recordatorios (seguimiento vencido, cliente esperando respuesta) aparecen en la web y llegan a su **Telegram**.

**Estados:** `vendida`, `cita_agendada`, `pendiente_seguimiento`, `resuelta`, `perdida`.

El sistema solo **escucha**. No envía mensajes por WhatsApp desde las sesiones de los clientes.

## 2. Decisiones

| Tema | Decisión |
|---|---|
| Conexión con WhatsApp | Evolution API autoalojada en Railway. Una instancia por número conectado. |
| Registro del número | QR y código de emparejamiento, ambos disponibles, con botón «reintentar» que no crea otra instancia. |
| Entrada de mensajes | Webhook `messages.upsert` de Evolution hacia el backend, por la red privada de Railway. |
| Envío de mensajes | Ninguno por WhatsApp. Los avisos al agente van por Telegram. |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, `httpx`, `python-telegram-bot`, `google-genai`. |
| Base de datos | Postgres en Railway, con dos bases: `app` y `evolution`. Las pruebas usan SQLite. |
| Panel | Web servida por FastAPI (Jinja2 + HTMX). |
| LLM | `gemini-3.5-flash-lite` con salida JSON validada con Pydantic. |
| Quién decide el estado | La IA sugiere (`suggested_status`) y la persona confirma (`status`). |
| Despliegue | Todo en un proyecto de Railway: `app` (público), `evolution` (privado) y `postgres`. |
| Segunda etapa | Adaptador para la Cloud API oficial de Meta con coexistencia (Tech Provider), como plan «oficial». |

## 3. Arquitectura en Railway

```
 Navegador ──HTTPS──► app (FastAPI, dominio público)
                        │  /api/connections        crea la instancia y pide el QR
                        │  /webhook/evolution      recibe los eventos
                        │  web + tareas + bot de Telegram
                        │
          red privada   │ http://evolution.railway.internal:8080
                        ▼
                   evolution (sin dominio público)
                        │  sesión de WhatsApp por instancia (Baileys)
                        ▼
                   postgres ── base `evolution` (sesiones)
                            └─ base `app` (cuentas, conexiones, conversaciones, mensajes)
```

- Evolution no tiene dominio público. Solo el backend le habla, con la clave global `AUTHENTICATION_API_KEY`.
- Evolution envía los eventos al backend por la red privada, con un token propio en la URL del webhook.
- Los servicios corren en una sola instancia cada uno.

### Flujo de un mensaje

```
Cliente ► WhatsApp ► sesión de Evolution ──POST messages.upsert──► /webhook/evolution
   guarda en messages (única por instancia + id del mensaje) ► actualiza la conversación
   ► tarea cada minuto: 10 min de silencio ► Gemini ► suggested_status ► web y Telegram
```

### Flujo de registro del número

```
Web ► POST /api/connections {nombre, número}
    ► backend: crea la instancia en Evolution, configura el webhook, pide el QR / código
    ► web muestra QR y código, y consulta el estado cada 2 s
    ► evento connection.update (state = open) ► la conexión pasa a «conectado»
    ► si se cae: connection.update (close) ► la web ofrece «reconectar»
```

### Modelo de datos

- `accounts(id, email, password_hash, name, telegram_id, link_token, tz, created_at)`.
- `connections(id, account_id, instance_name UNIQUE, phone, state, created_at, connected_at)`. `state`: `creating`, `qr`, `connecting`, `open`, `closed`.
- `conversations(id, connection_id, remote_jid, customer_name, summary, suggested_status, status, next_action, amount, follow_up_at, unanswered, done, last_message_at, last_analyzed_at, last_reminded_at)`. Única por `(connection_id, remote_jid)`.
- `messages(id, conversation_id, wa_message_id, direction, text, type, sent_at)`. Única por `(conversation_id, wa_message_id)`.
- `corrections(id, conversation_id, suggested_status, final_status, at)`.

Las fechas se guardan en UTC.

## 4. Fases

### Fase 0. Infra en Railway y prueba técnica de Evolution (1–2 días, con la persona responsable)
- [ ] Proyecto de Railway con Postgres. Crear las bases `app` y `evolution`.
- [ ] Servicio `evolution` con una versión fija de la imagen oficial (no `latest`), sin dominio público. Variables: `SERVER_URL`, `AUTHENTICATION_API_KEY`, `DATABASE_PROVIDER=postgresql`, `DATABASE_CONNECTION_URI` (base `evolution`), guardado de instancias en base de datos y webhooks globales desactivados.
- [ ] Probar sin Redis. Si hay desconexiones o QR que no aparecen, añadirlo.
- [ ] Servicio `app` con dominio público y las variables de la sección 8.
- [ ] **Prueba técnica** con 5 números distintos, usando el código de emparejamiento y el QR:
  - Se registran a la primera o a la segunda.
  - Las 5 sesiones siguen conectadas 24–48 horas.
  - El webhook recibe los mensajes entrantes y los enviados desde el teléfono, sin duplicados.
  - Se anota qué trae `syncFullHistory` y el formato exacto del evento `messages.upsert`.
- [ ] Si Evolution no cumple, repetir la prueba con las alternativas de [ALTERNATIVAS.md](ALTERNATIVAS.md).

**Listo cuando:** la prueba se cumple y los resultados quedan anotados en `docs/prueba-evolution.md`.

### Fase 1. Núcleo de datos, cliente de Evolution y webhook (código)
- [x] Esquema en SQLAlchemy con las tablas de la sección 3 (`app/db.py`). Las tablas se crean al arrancar; Alembic se añade con el primer cambio de esquema en producción.
- [x] Cliente de Evolution (`httpx`): crear instancia, configurar webhook, pedir QR o código, consultar estado, cerrar sesión y borrar instancia (`app/channels/evolution.py`).
- [x] `POST /webhook/evolution` con verificación del token, extracción del texto de `messages.upsert`, filtrado de grupos y estados, y guardado idempotente (`app/channels/webhook.py`).
- [x] Conversación creada o actualizada por `(connection_id, remote_jid)`, con `last_message_at` y `unanswered` (`app/core/ingest.py`).
- [x] Manejo de `connection.update` y `qrcode.updated` para el estado de la conexión.
- [x] Pruebas con payloads de ejemplo de Evolution (`tests/`).
- [ ] Ejecutar las pruebas contra Postgres. Hasta ahora corren sobre SQLite.
- [ ] Contrastar los payloads y los endpoints con la versión real de Evolution (lista en `docs/prueba-evolution.md`).

**Listo cuando:** un payload `messages.upsert` repetido deja una sola fila en `messages` y la conversación queda actualizada.

### Fase 2. Cuentas y registro del número
- [ ] Registro e inicio de sesión (contraseña con hash, sesión por cookie).
- [ ] Pantalla «Conectar WhatsApp»: número, QR y código de emparejamiento, estados claros (generando, esperando escaneo, conectado, error) y botón «reintentar».
- [ ] Reconexión cuando llega `connection.update` con `close`.
- [ ] Aviso en el registro de que la conexión no es oficial y de que conviene empezar con un número secundario.

**Listo cuando:** una persona registra su número desde la web y sus mensajes aparecen en la base de datos.

### Fase 3. Análisis con Gemini
- [ ] Tarea cada minuto: conversaciones con 10 minutos de silencio y mensajes nuevos desde el último análisis.
- [ ] `llm.analyze` sobre la conversación completa (recortando el inicio si es larga) y guardado en `suggested_status`, resumen, acción y fecha.
- [ ] Regla determinista: si el último mensaje es del negocio, `unanswered = false`.
- [ ] Botón «Analizar ahora».
- [ ] **Evaluación:** 30 conversaciones anonimizadas con el estado esperado anotado a mano.

**Listo cuando:** el estado coincide en al menos el 85 % de los casos y no hay JSON inválido.

### Fase 4. Web
- [ ] Tablero por estado.
- [ ] Bandeja de sugerencias por confirmar: aceptar o cambiar el estado, guardado en `corrections`.
- [ ] Lista «Hoy» con seguimientos vencidos y clientes esperando respuesta.
- [ ] Vista de la conversación con el resumen y los mensajes.

**Listo cuando:** una persona confirma 5 conversaciones y las ve en su tablero.

### Fase 5. Recordatorios y Telegram
- [ ] Vinculación de Telegram con `/start <link_token>` desde la cuenta.
- [ ] Tarea cada 15 minutos: seguimiento vencido o `unanswered = true`, con enfriamiento de 2 horas.
- [ ] Aviso por Telegram con botones «Hecho», «En 1 h» y enlace a la conversación.
- [ ] Horario silencioso y resumen diario a las 9 am.

**Listo cuando:** un seguimiento a 2 minutos dispara un solo aviso en la web y en Telegram.

### Fase 6. Piloto
- [ ] 2 o 3 personas con su número real, con consentimiento de sus clientes.
- [ ] Métricas: % de estados corregidos, tiempo ahorrado por chat, pendientes cerrados tras un recordatorio, sesiones caídas por semana.
- [ ] Ajustar el prompt con las correcciones recogidas.

### Fase 7. Conexión oficial y planes
- [ ] Verificación del negocio en Meta y App Review como Tech Provider.
- [ ] Adaptador de la Cloud API con Embedded Signup y coexistencia.
- [ ] Planes en la web: **Conexión rápida** (Evolution) y **Conexión oficial** (Cloud API).

### Fase 8. Después
- Varios usuarios por cuenta y panel de supervisor.
- Transcripción de audios con Gemini.
- Exportación a CRM.

## 5. Costos

| Concepto | Costo |
|---|---|
| Evolution API | Gratis. Se paga el servicio en Railway. Revisar su licencia antes de usarla comercialmente. |
| Railway (app, evolution, postgres) | Plan Hobby desde 5 USD al mes más el uso. El consumo real se mide en la Fase 0. |
| Gemini Flash-Lite | Unos 0,002 USD por análisis. Una cuenta con 100 conversaciones al día: unos 6 USD al mes. En producción se usa el nivel de pago, porque en el gratuito Google puede usar los datos. |
| Telegram Bot API | Gratis. |
| WhatsApp Cloud API oficial (Fase 7) | Recibir no se cobra. Se cobran los mensajes de plantilla enviados. Tarifas de terceros para «Resto de Latinoamérica» (incluye Bolivia): marketing 0,0740 USD, utilidad y servicio 0,0113 USD. Confirmar en Meta. |

**Precio sugerido para el plan «Conexión rápida»:** el costo por número (Gemini más la parte de infraestructura) ronda los 6–10 USD al mes. Una hipótesis de partida es cobrar entre 15 y 20 USD al mes por número, y validarla en el piloto.

## 6. Riesgos

| Riesgo | Mitigación |
|---|---|
| WhatsApp bloquea un número vinculado por una conexión no oficial | Solo se escucha, sin enviar. Aviso al registrarse. Plan «Conexión oficial» en la Fase 7. |
| El registro del número falla o se pierde la sesión | Versión fija de Evolution, QR y código de emparejamiento, reconexión automática y la prueba de la Fase 0. |
| Un cambio de protocolo de WhatsApp rompe Evolution | Actualizar la versión solo tras repetir la prueba. Alternativas en [ALTERNATIVAS.md](ALTERNATIVAS.md). |
| Licencia de Evolution incompatible con el uso comercial | Leer la licencia en la Fase 0. Si no sirve, cambiar de proveedor con el mismo adaptador. |
| Datos personales de clientes | Consentimiento, acceso por cuenta, Gemini de pago y anonimización en las pruebas. |
| Clasificación errónea | La IA solo sugiere. La persona confirma y se mide el acierto. |
| Entregas duplicadas del webhook | Clave única por instancia e id del mensaje. |
| Evolution expuesto a internet | Sin dominio público. Solo accesible por la red privada de Railway. |

## 7. Estructura de carpetas

```
Track-Comun/
├── PLAN.md
├── ALTERNATIVAS.md
├── README.md
├── requirements.txt
├── railway.toml
├── .env.example
├── docs/
│   └── prueba-evolution.md
├── app/
│   ├── main.py             FastAPI y arranque de tareas
│   ├── config.py
│   ├── db.py               modelos y sesión de SQLAlchemy
│   ├── core/
│   │   └── ingest.py       guardar mensajes y actualizar conversaciones
│   ├── channels/
│   │   ├── evolution.py    cliente HTTP y lectura de payloads
│   │   ├── webhook.py      rutas del webhook
│   │   └── telegram.py     avisos y botones
│   ├── llm.py
│   ├── reminders.py
│   └── web/                rutas y plantillas
└── tests/
```

## 8. Variables de entorno

`DATABASE_URL`, `EVOLUTION_URL`, `EVOLUTION_API_KEY`, `WEBHOOK_TOKEN`, `PUBLIC_URL`, `SESSION_SECRET`, `TELEGRAM_BOT_TOKEN`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `TZ`, `SILENCE_MINUTES`, `REMINDER_INTERVAL_MIN`, `REMINDER_COOLDOWN_MIN`.
