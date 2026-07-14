#!/usr/bin/env python3
"""Ferramenta de recuperacao offline (doc 5.4 / 12).

Roda na maquina de CONFIANCA do operador -- NUNCA no servidor. Quando uma maquina
de cliente morre, a chave privada age dela morre junto. Os segredos guardados no
backend foram cifrados, desde o inicio, para DOIS destinatarios: a chave do cliente
e a chave de RECUPERACAO (cuja privada mora no 1Password). Esta ferramenta:

  1. autentica no backend como operador (usuario do dashboard);
  2. le os ciphertexts antigos do cliente;
  3. decifra com a chave privada de recuperacao (do 1Password);
  4. recifra para a chave publica da maquina NOVA (+ a de recuperacao, de novo);
  5. grava os novos ciphertexts de volta no backend.

REGRA INVIOLAVEL (doc 5.4): a chave privada de recuperacao NUNCA e colada em campo
de dashboard nem enviada ao servidor. Ela so existe nesta maquina, aqui.

Requisitos: binarios `age` e `age-keygen`. Python puro (stdlib).

Uso:
  recovery.py --backend URL --login admin --password SENHA \\
              --cliente seifo --recovery-key /caminho/recovery.key
"""

import argparse
import base64
import getpass
import json
import subprocess
import sys
import urllib.error
import urllib.request

SENTINEL = "age:"


def http(method, url, body=None, token=None, timeout=30):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8")
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"detail": raw}


def recovery_pubkey(recovery_key, age_keygen):
    """Deriva a chave publica de recuperacao a partir da identidade (nao expoe a privada)."""
    p = subprocess.run([age_keygen, "-y", recovery_key], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0:
        sys.exit("ERRO ao ler a chave de recuperacao: " + p.stderr.decode(errors="replace"))
    return p.stdout.decode().strip()


def age_decrypt(campo_cifrado, recovery_key, age_bin):
    ciphertext = base64.b64decode(campo_cifrado[len(SENTINEL):])
    p = subprocess.run([age_bin, "-d", "-i", recovery_key],
                       input=ciphertext, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0:
        raise RuntimeError("falha ao decifrar com a chave de recuperacao: "
                           + p.stderr.decode(errors="replace"))
    return p.stdout


def age_encrypt(plaintext_bytes, recipients, age_bin):
    args = [age_bin, "-e"]
    for r in recipients:
        args += ["-r", r]
    p = subprocess.run(args, input=plaintext_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0:
        raise RuntimeError("falha ao recifrar: " + p.stderr.decode(errors="replace"))
    return SENTINEL + base64.b64encode(p.stdout).decode("ascii")


def main():
    ap = argparse.ArgumentParser(description="Ferramenta de recuperacao offline (recifra segredos)")
    ap.add_argument("--backend", required=True)
    ap.add_argument("--login", required=True)
    ap.add_argument("--password", help="senha do operador (se omitir, pergunta)")
    ap.add_argument("--cliente", required=True)
    ap.add_argument("--recovery-key", required=True, help="identidade age de recuperacao (do 1Password)")
    ap.add_argument("--age-bin", default="age")
    ap.add_argument("--age-keygen-bin", default="age-keygen")
    ap.add_argument("--dry-run", action="store_true", help="mostra o que faria, sem gravar")
    args = ap.parse_args()

    base = args.backend.rstrip("/")
    senha = args.password or getpass.getpass("senha do operador: ")

    # 1) login
    s, j = http("POST", base + "/auth/login", {"login": args.login, "senha": senha})
    if s != 200:
        sys.exit("ERRO no login (%s): %s" % (s, j.get("detail")))
    token = j["access_token"]

    # 2) chave publica da maquina NOVA (ja re-enrollada) + a de recuperacao
    s, det = http("GET", "%s/admin/clientes/%s" % (base, args.cliente), token=token)
    if s != 200:
        sys.exit("ERRO ao ler cliente (%s): %s" % (s, det.get("detail")))
    nova_pub = det.get("age_pubkey")
    if not nova_pub:
        sys.exit("cliente sem chave age (a maquina nova ja fez o novo enrollment?)")
    rec_pub = recovery_pubkey(args.recovery_key, args.age_keygen_bin)
    print("maquina nova: %s" % nova_pub)
    print("recuperacao : %s" % rec_pub)

    # 3) le os ciphertexts antigos
    s, secrets = http("GET", "%s/admin/clientes/%s/secrets" % (base, args.cliente), token=token)
    if s != 200:
        sys.exit("ERRO ao listar segredos (%s): %s" % (s, secrets.get("detail")))
    if not secrets:
        print("nenhum segredo para recuperar."); return

    # 4) decifra (recuperacao) e recifra (maquina nova + recuperacao)
    novos = {}
    for item in secrets:
        campo = item["campo"]
        plano = age_decrypt(item["ciphertext"], args.recovery_key, args.age_bin)
        novos[campo] = age_encrypt(plano, [nova_pub, rec_pub], args.age_bin)
        print("  recifrado: %s" % campo)

    if args.dry_run:
        print("(dry-run) %d segredo(s) seriam gravados." % len(novos)); return

    # 5) grava de volta
    s, j = http("PUT", "%s/admin/clientes/%s/secrets" % (base, args.cliente), novos, token=token)
    if s != 200:
        sys.exit("ERRO ao gravar segredos (%s): %s" % (s, j.get("detail")))
    print("OK: %d segredo(s) recifrado(s) para a maquina nova." % len(novos))


if __name__ == "__main__":
    main()
