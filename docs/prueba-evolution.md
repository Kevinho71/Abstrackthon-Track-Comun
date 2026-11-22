# Prueba técnica de Evolution API (Fase 0)

Rellenar durante la prueba. Versión de la imagen probada: `evoapicloud/evolution-api:v2.3.7`.

## Criterios

| Criterio | Resultado |
|---|---|
| 5 números registrados con código de emparejamiento, a la primera o a la segunda | |
| 5 números registrados con QR | |
| Las 5 sesiones siguen en `open` tras 24 h | |
| Las 5 sesiones siguen en `open` tras 48 h | |
| El webhook recibe los mensajes entrantes | |
| El webhook recibe los mensajes enviados desde el teléfono (`fromMe: true`) | |
| Sin mensajes duplicados en `messages` | |
| Evolution funciona sin Redis | |

## Verificado en local contra Neon (v2.3.7)

- [x] `POST /instance/create` acepta el campo `webhook` con `url`, `events` y `headers`. Responde con `instance`, `webhook`, `settings` y `qrcode`.
- [x] Con `number` en la creación, `qrcode.pairingCode` trae un código de 8 caracteres. Con `GET /instance/connect/{instance}?number=` sobre una instancia ya creada sin número, `pairingCode` llega `null`. Por eso el número se envía al crear la instancia.
- [x] `GET /instance/connect/{instance}` devuelve `pairingCode`, `code`, `base64` y `count`.
- [x] `GET /instance/connectionState/{instance}` devuelve `instance.state` (`connecting` mientras espera el escaneo).
- [x] Los webhooks (`connection.update`, `qrcode.updated`) llegan al backend con la cabecera `x-webhook-token` y actualizan el estado en la base.
- [x] Sin la clave global, Evolution responde 401.
- [x] Evolution arranca y aplica sus migraciones sin Redis.

## Por verificar con números reales

- [ ] Nombre del evento en el payload de `messages.upsert` (`messages.upsert` o `MESSAGES_UPSERT`; el backend acepta ambos) y su estructura exacta.
- [ ] Qué trae `syncFullHistory` y cuántos meses de historial llegan al vincular.
- [ ] Que los mensajes enviados desde el teléfono llegan con `fromMe: true`.
- [ ] Licencia de Evolution y si permite el uso comercial.

## Payloads reales

Pegar aquí un `messages.upsert` entrante, uno saliente y un `connection.update`, sin datos personales.

## Observaciones

