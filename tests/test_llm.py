import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app import config, llm

OK = json.dumps({"cliente": "Ana", "resumen": "Preguntó el horario.", "estado": "resuelta",
                 "pregunta_sin_responder": False})
NOW = datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc)


class FakeClient:
    """Simula la API: cada modelo falla las veces indicadas y luego responde bien."""
    def __init__(self, failing: dict[str, int]):
        self.failing, self.calls = dict(failing), []
        self.aio = SimpleNamespace(models=SimpleNamespace(generate_content=self._generate))

    async def _generate(self, model, contents, config):
        self.calls.append(model)
        if self.failing.get(model, 0) > 0:
            self.failing[model] -= 1
            raise RuntimeError("503 UNAVAILABLE")
        return SimpleNamespace(text=OK)


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_MODEL", "principal")
    monkeypatch.setattr(config, "GEMINI_FALLBACK_MODEL", "respaldo")

    def _install(failing):
        fake = FakeClient(failing)
        monkeypatch.setattr(llm, "_get_client", lambda: fake)
        return fake
    return _install


@pytest.mark.asyncio
async def test_usa_el_modelo_principal_si_responde(setup):
    fake = setup({})
    res = await llm.analyze("Cliente: hola", NOW, backoff_seconds=0)
    assert res.estado == "resuelta" and fake.calls == ["principal"]


@pytest.mark.asyncio
async def test_reintenta_el_principal_antes_de_pasar_al_respaldo(setup):
    fake = setup({"principal": 1})
    await llm.analyze("Cliente: hola", NOW, backoff_seconds=0)
    assert fake.calls == ["principal", "principal"]


@pytest.mark.asyncio
async def test_pasa_al_respaldo_si_el_principal_sigue_saturado(setup):
    fake = setup({"principal": 5})
    await llm.analyze("Cliente: hola", NOW, backoff_seconds=0)
    assert fake.calls == ["principal", "principal", "respaldo"]


@pytest.mark.asyncio
async def test_falla_si_todos_los_intentos_fallan(setup):
    setup({"principal": 5, "respaldo": 5})
    with pytest.raises(RuntimeError, match="No se pudo analizar"):
        await llm.analyze("Cliente: hola", NOW, backoff_seconds=0)


@pytest.mark.asyncio
async def test_sin_respaldo_solo_usa_el_principal(setup, monkeypatch):
    monkeypatch.setattr(config, "GEMINI_FALLBACK_MODEL", "")
    fake = setup({"principal": 5})
    with pytest.raises(RuntimeError):
        await llm.analyze("Cliente: hola", NOW, backoff_seconds=0)
    assert fake.calls == ["principal", "principal"]
