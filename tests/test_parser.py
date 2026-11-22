from pathlib import Path

from app.parser import parse

SAMPLE = Path(__file__).parent.parent / "samples" / "chat_ejemplo.txt"


def test_android_export_se_parsea_y_omite_mensajes_del_sistema():
    p = parse(SAMPLE.read_text(encoding="utf-8"))
    assert p.is_structured
    assert len(p.messages) == 7
    assert p.last_author == "Marta Ruiz"
    assert p.messages[0].author == "Marta Ruiz"
    assert "cifrados" not in p.transcript


def test_ios_export():
    p = parse("[12/11/26, 10:32:15] Ana: hola\n[12/11/26, 10:33:00] Beto: buenas")
    assert [m.author for m in p.messages] == ["Ana", "Beto"]
    assert p.last_author == "Beto"


def test_mensaje_multilinea():
    p = parse("12/11/2026, 10:03 - Ana: línea 1\nlínea 2\n12/11/2026, 10:04 - Beto: ok")
    assert p.messages[0].text == "línea 1\nlínea 2"


def test_texto_libre_sin_formato():
    p = parse("Cliente: quiero comprar\nAgente: claro, te envío precios")
    assert not p.is_structured
    assert "quiero comprar" in p.transcript
    assert p.last_author is None
