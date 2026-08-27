from typing import Protocol


class LLMProvider(Protocol):
    """Interfaz minima, agnostica de proveedor -- un solo metodo. El prompt (construido en
    judge.py) ya le pide JSON como parte de las instrucciones; nada en esta interfaz asume
    la forma de request/response propia de un vendor (mensajes con roles, response_format,
    streaming, etc.), eso queda encerrado dentro de cada adapter concreto."""

    def complete(self, prompt: str) -> str: ...
