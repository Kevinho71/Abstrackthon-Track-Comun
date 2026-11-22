from app.channels import evolution as ev


def upsert(message, jid="59170000001@s.whatsapp.net", from_me=False, msg_id="ABC1", push_name="Ana", ts=1717689097):
    return {
        "event": "messages.upsert",
        "instance": "inst1",
        "data": {
            "key": {"remoteJid": jid, "fromMe": from_me, "id": msg_id},
            "pushName": push_name,
            "message": message,
            "messageTimestamp": ts,
        },
    }


def test_normaliza_nombre_de_evento():
    assert ev.normalize_event("MESSAGES_UPSERT") == "messages.upsert"
    assert ev.normalize_event("messages.upsert") == "messages.upsert"


def test_texto_simple():
    [m] = ev.parse_messages_upsert(upsert({"conversation": "hola"}))
    assert (m.text, m.type, m.from_me, m.push_name) == ("hola", "text", False, "Ana")
    assert m.sent_at.year == 2024 and m.sent_at.tzinfo is not None


def test_texto_extendido_y_envuelto():
    [m1] = ev.parse_messages_upsert(upsert({"extendedTextMessage": {"text": "link"}}))
    assert m1.text == "link"
    wrapped = {"ephemeralMessage": {"message": {"conversation": "temporal"}}}
    [m2] = ev.parse_messages_upsert(upsert(wrapped))
    assert m2.text == "temporal"


def test_multimedia_deja_marcador():
    [img] = ev.parse_messages_upsert(upsert({"imageMessage": {"caption": "mi comprobante"}}))
    assert img.text == "[imagen] mi comprobante" and img.type == "image"
    [aud] = ev.parse_messages_upsert(upsert({"audioMessage": {}}))
    assert aud.text == "[audio]"


def test_ignora_grupos_estados_y_reacciones():
    assert ev.parse_messages_upsert(upsert({"conversation": "x"}, jid="1203@g.us")) == []
    assert ev.parse_messages_upsert(upsert({"conversation": "x"}, jid="status@broadcast")) == []
    assert ev.parse_messages_upsert(upsert({"reactionMessage": {"text": "👍"}})) == []
    assert ev.parse_messages_upsert(upsert({"protocolMessage": {}})) == []


def test_acepta_lista_y_jid_lid():
    payload = upsert({"conversation": "uno"})
    payload["data"] = [payload["data"], {**payload["data"], "key": {"remoteJid": "99@lid", "fromMe": True, "id": "Z"}}]
    out = ev.parse_messages_upsert(payload)
    assert [m.remote_jid for m in out] == ["59170000001@s.whatsapp.net", "99@lid"]
    assert out[1].from_me is True


def test_timestamp_en_formato_long():
    [m] = ev.parse_messages_upsert(upsert({"conversation": "x"}, ts={"low": 1717689097, "high": 0}))
    assert m.sent_at.year == 2024


def test_connection_update():
    payload = {"event": "connection.update", "instance": "inst1", "data": {"state": "open", "statusReason": 200}}
    u = ev.parse_connection_update(payload)
    assert (u.instance, u.state) == ("inst1", "open")
    assert ev.parse_connection_update({"instance": "inst1", "data": {}}) is None
