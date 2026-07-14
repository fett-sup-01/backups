"""Cripto de segredos (doc secao 5, Modelo A).

O backend SO cifra, e sempre para DOIS destinatarios (cliente + recuperacao).
Nunca decifra: nao tem nenhuma chave privada. O texto puro da senha existe
apenas de passagem, na memoria, e some em seguida (doc 5.1). pyrage mantem tudo
em memoria -- nada de plaintext em disco ou argv.
"""

import base64

import pyrage

from .settings import settings

SENTINEL = "age:"  # prefixo do campo cifrado no config (doc pendencia #2, decidido inline)


def encrypt_secret(plaintext: str, client_pubkey: str) -> str:
    """Cifra `plaintext` para o cliente E para a recuperacao. Devolve
    'age:' + base64(ciphertext age binario), pronto para embutir no config JSON."""
    if not settings.recovery_age_pubkey:
        # fail-closed: sem a chave de recuperacao, um segredo gravado nao poderia
        # ser socorrido se a maquina do cliente morresse (doc 5.3 / 12).
        raise RuntimeError("RECOVERY_AGE_PUBKEY nao configurada; recuso cifrar (doc 5.3)")
    if not client_pubkey:
        raise RuntimeError("cliente sem chave age publica (enrollment incompleto)")

    recipients = [
        pyrage.x25519.Recipient.from_str(client_pubkey),
        pyrage.x25519.Recipient.from_str(settings.recovery_age_pubkey),
    ]
    ciphertext = pyrage.encrypt(plaintext.encode("utf-8"), recipients)
    return SENTINEL + base64.b64encode(ciphertext).decode("ascii")
