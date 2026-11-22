"""Normaliza la exportación de chats de WhatsApp (Android e iOS) a una transcripción simple."""
import re
from dataclasses import dataclass, field

from app.config import MAX_TRANSCRIPT_CHARS

_TIME = r"\d{1,2}:\d{2}(?::\d{2})?(?:\s?[ap]\.?\s?m\.?)?"
_DATE = r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}"
# Android: 12/11/2026, 10:32 - Ana: hola
_ANDROID = re.compile(rf"^({_DATE}),?\s+({_TIME})\s+-\s+(.*)$", re.I)
# iOS: [12/11/26, 10:32:15] Ana: hola
_IOS = re.compile(rf"^\[({_DATE}),?\s+({_TIME})\]\s+(.*)$", re.I)
_INVISIBLE = dict.fromkeys(map(ord, "‎‏‪‫‬ ﻿"), " ")


@dataclass
class Message:
    author: str
    text: str


@dataclass
class ParsedChat:
    messages: list[Message] = field(default_factory=list)
    raw: str = ""

    @property
    def is_structured(self) -> bool:
        return bool(self.messages)

    @property
    def last_author(self) -> str | None:
        return self.messages[-1].author if self.messages else None

    @property
    def transcript(self) -> str:
        if self.messages:
            text = "\n".join(f"{m.author}: {m.text}" for m in self.messages)
        else:
            text = self.raw
        if len(text) > MAX_TRANSCRIPT_CHARS:
            text = "[...conversación recortada...]\n" + text[-MAX_TRANSCRIPT_CHARS:]
        return text


def parse(text: str) -> ParsedChat:
    text = text.translate(_INVISIBLE)
    messages: list[Message] = []
    for line in text.splitlines():
        m = _ANDROID.match(line) or _IOS.match(line)
        if m:
            body = m.group(3)
            if ": " in body:
                author, content = body.split(": ", 1)
                messages.append(Message(author.strip(), content.strip()))
            # Sin "Autor: " es un mensaje del sistema (cifrado, cambios de grupo): se omite.
        elif messages and line.strip():
            messages[-1].text += "\n" + line.strip()  # continuación de un mensaje multilínea
    return ParsedChat(messages=messages, raw=text.strip())
