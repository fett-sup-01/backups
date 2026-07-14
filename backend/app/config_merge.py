"""Injeta os campos cifrados no config, no caminho referenciado por client_secrets.

Caminho no formato "chave.chave[idx].chave" -- ex.: "montagens[0].senha".
"""

import re

_SEG = re.compile(r"^([^\[]+)((?:\[\d+\])*)$")


def _parse(path: str):
    parts: list = []
    for seg in path.split("."):
        m = _SEG.match(seg)
        if not m:
            raise ValueError(f"caminho invalido: {path!r} (segmento {seg!r})")
        parts.append(m.group(1))
        parts.extend(int(i) for i in re.findall(r"\[(\d+)\]", m.group(2)))
    return parts


def set_path(root, path: str, value) -> None:
    parts = _parse(path)
    cur = root
    for p in parts[:-1]:
        cur = cur[p]
    cur[parts[-1]] = value
