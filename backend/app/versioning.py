"""Comparacao de versao de script (ex.: '1.0', '1.10' > '1.9')."""


def parse_versao(v) -> tuple:
    partes = []
    for p in str(v or "0").split("."):
        digitos = "".join(ch for ch in p if ch.isdigit())
        partes.append(int(digitos) if digitos else 0)
    return tuple(partes)


def maior(a, b) -> bool:
    """True se a versao `a` for mais nova que `b`."""
    return parse_versao(a) > parse_versao(b)
