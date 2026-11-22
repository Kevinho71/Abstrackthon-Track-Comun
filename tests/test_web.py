import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import config
from app.channels.evolution import EvolutionError
from app.db import Connection, Message, session_scope
from app.main import create_app

TOKEN = "token-de-prueba"


class FakeEvolution:
    def __init__(self):
        self.created: list[dict] = []
        self.deleted: list[str] = []
        self.fail_create = False
        self.missing: set[str] = set()  # instancias que Evolution "ya no conoce"
        self._state = "connecting"

    async def create_instance(self, name, webhook_url, number=None, token=None):
        if self.fail_create:
            raise EvolutionError("caído")
        self.created.append({"name": name, "url": webhook_url, "number": number, "token": token})
        self.missing.discard(name)
        return {"qrcode": {"pairingCode": "ABCD1234"}}

    async def connect(self, name, number=None):
        if name in self.missing:
            raise EvolutionError("404")
        return {"pairingCode": "ABCD1234", "code": "2@x", "base64": "iVBORw0KGgo=", "count": 1}

    async def state(self, name):
        return self._state

    async def delete_instance(self, name):
        self.deleted.append(name)
        self.missing.add(name)
        return {}


@pytest.fixture(autouse=True)
def _config(monkeypatch):
    monkeypatch.setattr(config, "WEBHOOK_BASE_URL", "http://127.0.0.1:8000")


@pytest.fixture
def evo():
    return FakeEvolution()


@pytest.fixture
def make_client(tmp_path, evo):
    clients = []

    def _make():
        app = create_app(f"sqlite:///{tmp_path / 'w.db'}", validate=False, evolution=evo)
        c = TestClient(app, follow_redirects=False)
        c.__enter__()
        clients.append(c)
        return c

    yield _make
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def client(make_client):
    return make_client()


def signup(c, email="ana@ejemplo.com", password="clave-segura-1", name="Ana"):
    return c.post("/register", data={"email": email, "password": password, "name": name})


def connect(c, phone="+591 7000 0001"):
    r = c.post("/connections", data={"phone": phone})
    assert r.status_code == 303, r.text
    return int(r.headers["location"].rsplit("/", 1)[1])


# --------------------------------------------------------------------------- cuentas
def test_sin_sesion_redirige_al_login(client):
    assert client.get("/").headers["location"] == "/login"
    assert client.get("/connections/new").headers["location"] == "/login"
    assert client.post("/connections", data={"phone": "59170000001"}).headers["location"] == "/login"


def test_registro_y_sesion(client):
    r = signup(client)
    assert r.status_code == 303 and r.headers["location"] == "/"
    page = client.get("/")
    assert page.status_code == 200 and "Mis números" in page.text and "Ana" in page.text


def test_registro_valida_datos(client):
    assert "correo válido" in signup(client, email="no-es-correo").text
    assert "al menos 8" in signup(client, password="corta").text
    signup(client)
    client.post("/logout")
    r = signup(client)
    assert r.status_code == 400 and "Ya existe" in r.text


def test_correo_no_distingue_mayusculas(client):
    signup(client, email="Ana@Ejemplo.com")
    client.post("/logout")
    r = client.post("/login", data={"email": "ANA@ejemplo.COM", "password": "clave-segura-1"})
    assert r.status_code == 303


def test_login_y_logout(client):
    signup(client)
    client.post("/logout")
    assert client.get("/").headers["location"] == "/login"
    bad = client.post("/login", data={"email": "ana@ejemplo.com", "password": "otra"})
    assert bad.status_code == 400 and "incorrectos" in bad.text
    unknown = client.post("/login", data={"email": "nadie@ejemplo.com", "password": "x"})
    assert unknown.status_code == 400 and "incorrectos" in unknown.text
    ok = client.post("/login", data={"email": "ana@ejemplo.com", "password": "clave-segura-1"})
    assert ok.status_code == 303 and client.get("/").status_code == 200


def test_la_contrasena_no_se_guarda_en_claro(client):
    signup(client, password="clave-segura-1")
    with session_scope(client.app.state.session_factory) as s:
        from app.db import Account

        stored = s.scalar(select(Account.password_hash))
    assert "clave-segura-1" not in stored and stored.startswith("scrypt$")


# --------------------------------------------------------------------------- conexiones
def test_crear_conexion_envia_numero_normalizado_y_token(client, evo):
    signup(client)
    cid = connect(client, "+591 7000-0001")
    assert evo.created[0]["number"] == "59170000001"
    assert evo.created[0]["token"] == TOKEN
    assert evo.created[0]["url"] == "http://127.0.0.1:8000/webhook/evolution"
    assert evo.created[0]["name"].startswith("acc1-")
    page = client.get(f"/connections/{cid}")
    assert page.status_code == 200 and "+59170000001" in page.text


def test_numero_invalido_no_crea_nada(client, evo):
    signup(client)
    r = client.post("/connections", data={"phone": "123"})
    assert r.status_code == 400 and "código de país" in r.text and evo.created == []


def test_error_de_evolution_no_deja_conexion_a_medias(client, evo):
    signup(client)
    evo.fail_create = True
    r = client.post("/connections", data={"phone": "59170000001"})
    assert r.status_code == 400 and "No pudimos iniciar" in r.text
    with session_scope(client.app.state.session_factory) as s:
        assert s.scalar(select(func.count()).select_from(Connection)) == 0


def test_numero_repetido_y_limite(client):
    signup(client)
    connect(client, "59170000001")
    r = client.post("/connections", data={"phone": "59170000001"})
    assert r.status_code == 400 and "ya está conectado" in r.text
    for i in range(2, 6):
        connect(client, f"5917000000{i}")
    r = client.post("/connections", data={"phone": "59170000009"})
    assert r.status_code == 400 and "hasta 5" in r.text


def test_qr_muestra_codigo_e_imagen(client):
    signup(client)
    cid = connect(client)
    html = client.get(f"/connections/{cid}/qr").text
    assert "ABCD-1234" in html and "data:image/png;base64,iVBORw0KGgo=" in html


def test_reintentar_reutiliza_la_instancia(client, evo):
    signup(client)
    cid = connect(client)
    html = client.post(f"/connections/{cid}/retry").text
    assert "ABCD-1234" in html and len(evo.created) == 1


def test_reintentar_recrea_la_instancia_si_evolution_la_perdio(client, evo):
    signup(client)
    cid = connect(client)
    evo.missing.add(evo.created[0]["name"])
    html = client.post(f"/connections/{cid}/retry").text
    assert "ABCD-1234" in html
    assert len(evo.created) == 2 and evo.created[1]["name"] == evo.created[0]["name"]


def test_panel_sigue_el_estado(client, evo):
    signup(client)
    cid = connect(client)
    assert 'data-state="connecting"' in client.get(f"/connections/{cid}/panel").text
    evo._state = "open"
    panel = client.get(f"/connections/{cid}/panel").text
    assert 'data-state="open"' in panel and "Conectado" in panel
    assert client.get(f"/connections/{cid}/qr").text == ""


def test_el_webhook_actualiza_lo_que_ve_el_usuario(client):
    signup(client)
    cid = connect(client)
    with session_scope(client.app.state.session_factory) as s:
        name = s.get(Connection, cid).instance_name
    client.post("/webhook/evolution", headers={"x-webhook-token": config.WEBHOOK_TOKEN},
                json={"event": "connection.update", "instance": name, "data": {"state": "open"}})
    client.post("/webhook/evolution", headers={"x-webhook-token": config.WEBHOOK_TOKEN},
                json={"event": "messages.upsert", "instance": name, "data": {
                    "key": {"remoteJid": "59170000009@s.whatsapp.net", "fromMe": False, "id": "X1"},
                    "message": {"conversation": "hola"}, "messageTimestamp": 1717689097}})
    home = client.get("/").text
    assert "Conectado" in home and "1 conversaciones · 1 mensajes" in home


def test_desconectar_borra_la_instancia_y_conserva_los_mensajes(client, evo):
    signup(client)
    cid = connect(client)
    with session_scope(client.app.state.session_factory) as s:
        name = s.get(Connection, cid).instance_name
    client.post("/webhook/evolution", headers={"x-webhook-token": config.WEBHOOK_TOKEN},
                json={"event": "messages.upsert", "instance": name, "data": {
                    "key": {"remoteJid": "59170000009@s.whatsapp.net", "fromMe": False, "id": "X1"},
                    "message": {"conversation": "hola"}, "messageTimestamp": 1717689097}})
    r = client.post(f"/connections/{cid}/disconnect")
    assert r.status_code == 303 and evo.deleted == [name]
    with session_scope(client.app.state.session_factory) as s:
        assert s.get(Connection, cid).state == "closed"
        assert s.scalar(select(func.count()).select_from(Message)) == 1


def test_una_cuenta_no_ve_las_conexiones_de_otra(make_client):
    a = make_client()
    signup(a, email="a@ejemplo.com")
    cid = connect(a)
    b = make_client()
    signup(b, email="b@ejemplo.com")
    for path in (f"/connections/{cid}", f"/connections/{cid}/panel", f"/connections/{cid}/qr"):
        assert b.get(path).status_code == 404
    assert b.post(f"/connections/{cid}/retry").status_code == 404
    assert b.post(f"/connections/{cid}/disconnect").status_code == 404
    assert "59170000001" not in b.get("/").text
