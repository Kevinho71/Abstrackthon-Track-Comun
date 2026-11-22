# Plan del proyecto: Agente de seguimiento de chats (Telegram + Gemini + Railway)

> Track: **Comercios**. Mejora cómo un equipo se informa y se coordina: cada conversación queda resumida, clasificada y con dueño, y nadie deja clientes colgados.

## 1. Qué es el MVP

Un bot de Telegram para agentes de call center o atención de negocios.

1. El agente le pasa un chat (archivo `.txt` exportado de WhatsApp, o texto pegado).
2. El bot devuelve un **resumen**, un **estado** y la **siguiente acción**.
3. Guarda el chat y **recuerda** al agente los pendientes y las preguntas sin responder.

**Estados:** `vendida`, `cita_agendada`, `pendiente_seguimiento`, `resuelta`, `perdida`.

**Fuera del MVP:** conexión directa a WhatsApp, dashboard web, multi-empresa, panel de supervisor. Ver Fase 7.

## 2. Decisiones tomadas

| Tema | Decisión | Motivo |
|---|---|---|
| Canal | Telegram Bot API (long polling) | Gratis y sin verificación de Meta. Un solo proceso, sin dominio ni webhook. |
| LLM | `gemini-3.5-flash-lite` vía Google AI Studio | Nivel gratuito, salida JSON con esquema, rápido y barato. |
| Lenguaje | Python 3.12 | `python-telegram-bot` y `google-genai` son maduros. |
| Base de datos | SQLite en un Volume de Railway | Sin servicio extra que consuma crédito. Migrable a Postgres. |
| Recordatorios | JobQueue de `python-telegram-bot` dentro del mismo proceso | Un solo servicio que desplegar. |
| Despliegue | Railway, un servicio tipo worker, sin puerto expuesto | Menor consumo de recursos. |

## 3. Arquitectura

```
 Agente (Telegram)
      │  .txt exportado / texto pegado / comandos / botones
      ▼
 ┌──────────────────────── Proceso único en Railway ───────────────────────┐
 │  app/main.py        arranque, handlers, JobQueue                        │
 │  app/handlers.py    comandos, documentos, botones                       │
 │  app/parser.py      normaliza el export de WhatsApp                     │
 │  app/llm.py         Gemini → JSON validado con Pydantic                 │
 │  app/db.py          SQLite (chats, agentes)                             │
 │  app/reminders.py   tarea cada N min: pendientes vencidos / sin responder │
 └──────────────┬──────────────────────────────────────────────────────────┘
                ▼
        Volume /data/app.db
```

### Modelo de datos

- `agents(telegram_id PK, name, wa_name, created_at)`. `wa_name` es el nombre del agente dentro de WhatsApp, y sirve para saber quién habló último.
- `chats(id PK, agent_id, customer, summary, status, next_action, amount, follow_up_at, unanswered, done, last_reminded_at, created_at, updated_at)`. Las fechas se guardan en UTC.

### Flujo

1. El agente envía un `.txt` o pega la conversación.
2. `parser` normaliza el texto y detecta el último autor.
3. `llm` envía la transcripción con la fecha actual (para resolver "mañana", "el lunes") y recibe un JSON.
4. Regla determinista: si el último mensaje es del propio agente (`wa_name`), no hay pregunta sin responder, sin importar lo que diga el modelo.
5. Se guarda el chat y el bot responde con la ficha y botones para corregir el estado o marcar como hecho.
6. Cada 15 minutos el worker busca pendientes con fecha vencida o sin responder y avisa al agente. Hay un enfriamiento de 2 horas entre avisos del mismo chat.

## 4. Fases

### Fase 0. Cuentas y credenciales (30 min)
- [ ] Crear el bot con @BotFather y guardar `TELEGRAM_BOT_TOKEN`.
- [ ] Crear la API key en Google AI Studio (`GEMINI_API_KEY`).
- [ ] Obtener el propio `telegram_id` (con @userinfobot) para `ALLOWED_USER_IDS`.
- [ ] Crear el repo en GitHub y la cuenta en Railway.

**Listo cuando:** tienes ambos tokens guardados en `.env` (no se sube a git).

### Fase 1. Base del proyecto y bot local (medio día)
- [ ] Estructura de carpetas, `requirements.txt`, `.env.example`, `.gitignore`.
- [ ] `/start`, `/ayuda`, `/nombre`.
- [ ] Parser de exportaciones de WhatsApp (Android e iOS) con pruebas.
- [ ] Bot corriendo en local con long polling.

**Listo cuando:** `python -m app.main` responde a `/start` y las pruebas del parser pasan.

### Fase 2. Análisis con Gemini (1 día)
- [ ] Esquema Pydantic y prompt de sistema en español.
- [ ] Salida JSON forzada (`response_mime_type` + `response_schema`).
- [ ] Reintentos con espera ante errores o límites de tasa (429).
- [ ] Recortar transcripciones largas (conservar el final) para controlar tokens.
- [ ] **Evaluación:** 30 chats de prueba (sintéticos o anonimizados) con el estado esperado anotado a mano.

**Listo cuando:** el estado coincide con el esperado en al menos el 85% de los casos y no hay JSON inválido en la muestra.

### Fase 3. Persistencia y seguimiento (medio día)
- [ ] Guardar cada análisis en SQLite.
- [ ] `/pendientes`, `/resumen`, `/hecho <id>`.
- [ ] Botones en cada ficha para corregir el estado o marcar como hecho.
- [ ] Guardar las correcciones del agente: sirven como ejemplos para mejorar el prompt.

**Listo cuando:** un agente analiza 5 chats y ve su lista de pendientes correcta.

### Fase 4. Recordatorios (medio día)
- [ ] Tarea periódica (`run_repeating`, cada 15 min por defecto).
- [ ] Reglas: `follow_up_at` vencido, o `unanswered=1`, con enfriamiento de 2 h.
- [ ] Botones en el recordatorio: "Hecho" y "Pospuesto".
- [ ] Mejoras opcionales: horario silencioso y resumen diario a las 9 am.

**Listo cuando:** un chat con seguimiento a 2 minutos dispara el aviso una sola vez y no repite al agente.

### Fase 5. Despliegue en Railway (medio día)
- [ ] Subir el repo a GitHub y crear un proyecto en Railway desde el repo.
- [ ] Servicio sin dominio público; comando de inicio `python -m app.main`.
- [ ] Añadir un **Volume** montado en `/data` y `DB_PATH=/data/app.db`.
- [ ] Variables: `TELEGRAM_BOT_TOKEN`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `TZ`, `ALLOWED_USER_IDS`, `DB_PATH`.
- [ ] Revisar logs y probar reinicios: los datos deben persistir.
- [ ] **Ejecutar una sola instancia.** Dos procesos con el mismo token de Telegram dan el error `Conflict: terminated by other getUpdates`.

**Listo cuando:** el bot responde con el computador apagado y los pendientes sobreviven a un redeploy.

### Fase 6. Piloto y métricas (1 semana)
- [ ] 2 o 3 agentes usan el bot con chats reales (previa autorización).
- [ ] Métricas: % de estados corregidos por el agente, tiempo ahorrado por chat, pendientes cerrados tras un recordatorio.
- [ ] Ajustar el prompt con las correcciones recogidas.

### Fase 7. Siguientes pasos (después del MVP)
- Conexión directa a WhatsApp Cloud API (requiere verificación de Meta).
- Dashboard web para supervisores, con estados por agente.
- Postgres, multi-empresa, exportar a CRM.
- Recordatorios por WhatsApp con plantillas.

## 5. Costos

| Concepto | MVP | Notas |
|---|---|---|
| Telegram Bot API | 0 | Gratis. Límites de velocidad: unos 30 mensajes/s en total y 1/s por chat. |
| Gemini 3.5 Flash-Lite | 0 en nivel gratuito | De pago: [0,30 USD por millón de tokens de entrada y 2,50 USD de salida](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite). Chat típico (3.000 entrada, 300 salida): unos 0,002 USD. 30.000 chats/mes: unos 50 USD. |
| Railway | 0 durante la prueba | Prueba de 30 días con un crédito único de 5 USD. Luego el plan Free (1 USD/mes de uso) o Hobby (5 USD/mes). |

### Límites que hay que conocer
- **Nivel gratuito de Gemini:** la cuota por minuto y por día no está confirmada oficialmente. Una fuente de terceros indica 30 solicitudes/min y 1.500/día. Mira tu panel de AI Studio. Con 100 chats/día por agente, unos 15 agentes agotarían la cuota.
- **Privacidad:** en el nivel gratuito de la API de Gemini, Google puede usar los datos para mejorar sus productos (confirma los términos vigentes). Para la demo usa **chats sintéticos o anonimizados**, no datos reales de clientes.
- **Railway tras la prueba:** el plan Free hace dormir los servicios inactivos, y un bot con long polling necesita estar despierto para enviar recordatorios. Para uso continuo planifica el plan Hobby (5 USD/mes). Según las [docs de Railway](https://docs.railway.com/pricing/free-trial), la prueba termina a los 30 días o al gastar los 5 USD.

## 6. Riesgos

| Riesgo | Mitigación |
|---|---|
| Datos personales de clientes | Anonimizar en la demo; `ALLOWED_USER_IDS`; plan de consentimiento y proveedor de pago para producción. |
| Clasificación errónea | Botones de corrección en cada ficha, métrica de aciertos, ejemplos en el prompt. |
| Cuota gratuita agotada | Reintentos con espera, mensaje claro al agente y opción de pasar al nivel de pago. |
| Pérdida de la base de datos | Volume en Railway y comando `/exportar` (futuro). |
| Formato del export de WhatsApp distinto por idioma o región | Parser tolerante, y si no reconoce el formato trata el texto como transcripción libre. |

## 7. Estructura de carpetas

```
hack-comunicacion/
├── PLAN.md
├── README.md
├── requirements.txt
├── railway.toml
├── .env.example
├── .gitignore
├── .python-version
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── db.py
│   ├── parser.py
│   ├── llm.py
│   ├── handlers.py
│   ├── reminders.py
│   └── main.py
├── samples/
│   └── chat_ejemplo.txt
└── tests/
    ├── test_parser.py
    └── test_db.py
```
