# Prueba técnica de Evolution API (Fase 0)

Rellenar durante la prueba. Versión de la imagen probada: `______`.

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

## Por verificar contra la versión desplegada

- [ ] `POST /instance/create` acepta el campo `webhook` (si no, usar `POST /webhook/set/{instance}`, ya implementado en `EvolutionClient.set_webhook`).
- [ ] Nombre del evento en el payload: `messages.upsert` o `MESSAGES_UPSERT` (el backend acepta ambos).
- [ ] Respuesta de `GET /instance/connect/{instance}` con y sin `?number=`: campos `base64`, `code`, `pairingCode`.
- [ ] Respuesta de `GET /instance/connectionState/{instance}`.
- [ ] Qué trae `syncFullHistory` y cuántos meses de historial llegan al vincular.
- [ ] Licencia de Evolution y si permite el uso comercial.

## Payloads reales

Pegar aquí un `messages.upsert` entrante, uno saliente y un `connection.update`, sin datos personales.

## Observaciones

