# Alternativas y criterios de cambio

Qué se eligió en [PLAN.md](PLAN.md), qué otras opciones existen y cuándo conviene cambiar. Las cifras de terceros no están confirmadas oficialmente y deben revisarse antes de decidir.

## 1. Conexión con WhatsApp

La elegida es **Evolution API autoalojada**. Todas las opciones no oficiales vinculan el número como «dispositivo vinculado» y pueden provocar el bloqueo del número, porque van contra los términos de WhatsApp.

| Opción | Tipo | Registro del número | Costo | Ventajas | Desventajas |
|---|---|---|---|---|---|
| **Evolution API** (elegida) | Autoalojada, basada en Baileys | QR o código; eventos `qrcode.updated` y `connection.update` | Gratis, más el servidor | Una instancia por número, REST y webhooks, muy usada en Latinoamérica | Reportes de QR que no aparece o no conecta y de bucles de reconexión. Licencia por confirmar |
| **WAHA** | Autoalojada, motores WEBJS, NOWEB (Baileys) y GOWS (Go) | QR por sesión | Gratis. Fuentes de terceros dicen que las sesiones ilimitadas son gratis desde 2026.6, con suscripción opcional de unos 5 USD al mes | Tres motores intercambiables. GOWS es el más eficiente | Estado de licencia y límites por confirmar en su sitio |
| **Evolution Go** | Autoalojada, en Go | QR | Gratis | Más ligera que la versión de Node | Proyecto distinto y más joven |
| **OpenWA, CodeChat, WaSphere** | Autoalojadas | QR | Gratis | OpenWA trae panel y múltiples sesiones. WaSphere firma los webhooks | Menos documentadas |
| **Green API** | SaaS no oficial | QR | Plan gratuito de desarrollo (1 instancia, 3 chats). Business: unos 12 USD al mes por número | Nada que alojar | Cada cliente paga por número y los chats pasan por un tercero |
| **Whapi.Cloud, UltraMsg, Maytapi** | SaaS no oficial | QR | UltraMsg: unos 39 USD al mes por instancia. Whapi: unos 29 USD al mes, con cifras que no coinciden entre sus páginas | Nada que alojar | Más caros por número. Webhooks sin verificar |
| **Librerías** (Baileys, whatsapp-web.js, WPPConnect, whatsmeow, Neonize, Venom) | Código propio | Se programa | Gratis | Control total | Hay que construir sesiones, reconexión, QR y almacenamiento |
| **Cloud API oficial de Meta con Tech Provider** | Oficial | Embedded Signup; la coexistencia se activa si el número ya usa la app WhatsApp Business | Recibir no se cobra. Se cobran las plantillas enviadas | Sin riesgo de bloqueo | Exige verificación del negocio y App Review, que tardan días o semanas |

### Cuándo cambiar
- Si Evolution no cumple la prueba de la Fase 0 (registro, 24–48 h de sesión estable, mensajes enviados desde el teléfono en el webhook), repetir la prueba con **WAHA** (motores GOWS y NOWEB) y con **Evolution Go**.
- Si la licencia de Evolution no permite el uso comercial, pasar a la opción que sí lo permita.
- Si los bloqueos de números superan el nivel aceptable en el piloto, priorizar la Cloud API oficial.
- El proyecto aísla al proveedor detrás de un adaptador (`app/channels/`), de modo que cambiar de proveedor no afecta a la base de datos, el análisis ni la web.

## 2. Hosting

| Opción | Cuándo conviene |
|---|---|
| **Railway** (elegida) | Un solo lugar para app, Evolution y Postgres, con red privada. |
| VPS con Docker (Hetzner, DigitalOcean) | Si el consumo de Evolution en Railway sale caro o hace falta más control de la IP. |
| Render, Fly.io | Si Railway da problemas de red o de volúmenes. |

## 3. Base de datos

| Opción | Cuándo conviene |
|---|---|
| **Postgres en Railway** (elegida) | Datos relacionales, varios servicios y consultas por cuenta. |
| SQLite en un Volume | Solo para pruebas locales. No sirve con varios servicios. |
| Neon u otro Postgres gestionado | Si se quiere separar la base de Railway o usar ramas de base de datos. |

## 4. Modelo de lenguaje

| Opción | Cuándo conviene |
|---|---|
| **Gemini Flash-Lite** (elegida) | Barato, con salida JSON con esquema y suficiente para clasificar. |
| Gemini Flash o un modelo mayor | Si el acierto no llega al 85 % en la evaluación de la Fase 3. |
| Claude Haiku | Si se prefiere un proveedor con mejores garantías de privacidad en la API de pago. Comparar costo y acierto con la misma evaluación. |

## 5. Avisos al agente

| Opción | Cuándo conviene |
|---|---|
| **Telegram** (elegida) | Gratis, con botones. Requiere que el agente lo use. |
| Notificaciones push de la web | Si los agentes no quieren instalar Telegram. Requiere una web instalable (PWA). |
| Correo electrónico | Como resumen diario, no para avisos urgentes. |
| WhatsApp con plantillas | Cuesta por aviso y exige plantillas aprobadas. Solo con la Cloud API oficial. |

## 6. Panel web

| Opción | Cuándo conviene |
|---|---|
| **FastAPI con Jinja2 y HTMX** (elegida) | Un solo servicio, sin compilar un frontend. |
| React o Next.js | Si el panel crece (arrastrar tarjetas, tiempo real, muchos filtros). Se añadiría como servicio aparte. |
| Metabase o Grafana | Solo para métricas internas, no para el panel del agente. |
