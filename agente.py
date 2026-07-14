#!/usr/bin/env python3
"""Agente de backup em frota (doc secao 9).

Roda na maquina do cliente, na MESMA pasta do backup.py. Modelo pull: so fala
para fora (HTTPS de saida). Puxa a config do backend, decifra os campos de senha
com a chave privada age LOCAL, grava o <cliente>.conf e aciona o backup.py.

Python puro (stdlib). Chama os binarios do ecossistema:
  - `age`      -> decifrar os campos de senha (chave privada nunca sai da maquina)
  - `minisign` -> verificar a assinatura de um update do backup.py antes de aplicar

Arquivos de estado na pasta do agente (todos chmod 600):
  - agente.json    -> {backend_url, cliente, token permanente, heartbeat_intervalo}
  - age-key.txt    -> identidade age (privada). So a publica vai ao backend.
  - <cliente>.conf -> config final gerada (com senhas em claro), lida pelo backup.py
  - minisign.pub   -> chave publica de assinatura, p/ verificar updates

Uso:
  agente.py enroll --backend URL --token TOKEN_EFEMERO
  agente.py heartbeat        # um ciclo: heartbeat + aplica config/comandos pendentes
  agente.py loop             # laco de heartbeat (systemd service)
  agente.py pull             # so puxa e aplica a config
  agente.py backup           # puxa a config e roda o backup (systemd timer, 1x/dia)
"""

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(AGENT_DIR, "agente.json")
KEY_FILE = os.path.join(AGENT_DIR, "age-key.txt")
BACKUP_PY = os.path.join(AGENT_DIR, "backup.py")
MINISIGN_PUB = os.path.join(AGENT_DIR, "minisign.pub")  # chave publica de assinatura (fixada)

AGE_BIN = os.environ.get("AGE_BIN", "age")
AGE_KEYGEN_BIN = os.environ.get("AGE_KEYGEN_BIN", "age-keygen")
MINISIGN_BIN = os.environ.get("MINISIGN_BIN", "minisign")

SENTINEL = "age:"  # prefixo dos campos cifrados no config (mesma convencao do backend)
DEFAULT_HEARTBEAT = 600  # 10 min (doc: 5-15 min)


def log(msg):
    print("[agente] " + msg, flush=True)


# --------------------------------------------------------------------------- estado
def load_state():
    if not os.path.isfile(STATE_FILE):
        sys.exit("ERRO: agente nao inscrito. Rode: agente.py enroll --backend URL --token ...")
    with open(STATE_FILE, encoding="utf-8") as fp:
        return json.load(fp)


def save_state(state):
    _write_600(STATE_FILE, json.dumps(state, indent=2, ensure_ascii=False))


def _write_600(path, texto):
    """Grava com permissao 600 (arquivos com segredo: token, chave, .conf)."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fp:
        fp.write(texto)


# --------------------------------------------------------------------------- HTTP
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


# --------------------------------------------------------------------------- cripto (age)
def age_pubkey():
    """Le a chave publica age do arquivo de identidade (linha '# public key: age1...')."""
    with open(KEY_FILE, encoding="utf-8") as fp:
        for linha in fp:
            if "public key:" in linha.lower():
                return linha.strip().split()[-1]
    raise RuntimeError("chave publica nao encontrada em " + KEY_FILE)


def ensure_age_key():
    if os.path.isfile(KEY_FILE):
        return
    log("gerando par de chaves age (a privada nunca sai desta maquina)")
    # age-keygen escreve a identidade (privada) em -o; a pub vai como comentario no arquivo
    subprocess.run([AGE_KEYGEN_BIN, "-o", KEY_FILE], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.chmod(KEY_FILE, 0o600)


def age_decrypt(campo_cifrado):
    """Decifra 'age:<base64>' -> texto puro, com a chave privada local, via stdin."""
    ciphertext = base64.b64decode(campo_cifrado[len(SENTINEL):])
    p = subprocess.run(
        [AGE_BIN, "-d", "-i", KEY_FILE],
        input=ciphertext, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if p.returncode != 0:
        raise RuntimeError("falha ao decifrar (age): " + p.stderr.decode(errors="replace"))
    return p.stdout.decode("utf-8")


def resolve_secrets(obj):
    """Percorre a estrutura e troca todo valor 'age:...' pelo texto decifrado."""
    if isinstance(obj, dict):
        return {k: resolve_secrets(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [resolve_secrets(v) for v in obj]
    if isinstance(obj, str) and obj.startswith(SENTINEL):
        return age_decrypt(obj)
    return obj


# --------------------------------------------------------------------------- backup.py
def script_versao():
    """Le VERSAO = \"x\" do backup.py, so p/ informar no heartbeat."""
    try:
        with open(BACKUP_PY, encoding="utf-8") as fp:
            for linha in fp:
                if linha.startswith("VERSAO"):
                    return linha.split("=")[1].split("#")[0].strip().strip('"').strip("'")
    except OSError:
        pass
    return "desconhecida"


def conf_path(cliente):
    return os.path.join(AGENT_DIR, cliente + ".conf")


def roda_backup(cliente, check=False):
    args = [sys.executable, BACKUP_PY, conf_path(cliente)]
    if check:
        args.append("--check")
    return subprocess.run(args)


# --------------------------------------------------------------------------- update (doc 10)
def verify_minisign(arquivo, sigfile):
    """Verifica a assinatura minisign do arquivo com a chave publica FIXADA localmente."""
    p = subprocess.run(
        [MINISIGN_BIN, "-V", "-m", arquivo, "-p", MINISIGN_PUB, "-x", sigfile],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return p.returncode == 0


def apply_update(update_info, st):
    """Baixa a versao nova do bkp.py, verifica a assinatura minisign e o --check.
    So aplica se as DUAS coisas passarem; senao mantem a anterior (rollback, doc 10)."""
    versao = update_info.get("versao")
    if not os.path.isfile(MINISIGN_PUB):
        log("update v%s ignorado: sem minisign.pub p/ verificar (fail-safe)" % versao)
        return
    status, data = http("GET", "%s/update/%s" % (st["backend_url"], versao), token=st["token"])
    if status != 200:
        log("falha ao baixar update v%s (%s)" % (versao, status))
        return

    novo = BACKUP_PY + ".new"
    sig = novo + ".minisig"
    _write_600(novo, data["conteudo"])
    _write_600(sig, data["assinatura"])

    # 1) assinatura minisign ANTES de qualquer coisa (doc 5.5)
    if not verify_minisign(novo, sig):
        os.remove(novo); os.remove(sig)
        log("update v%s RECUSADO: assinatura minisign invalida" % versao)
        return

    # 2) gate --check: se a versao nova nao valida, nao aplica
    check_args = [sys.executable, novo, "--check"]
    conf = conf_path(st["cliente"])
    if os.path.isfile(conf):
        check_args.insert(2, conf)
    chk = subprocess.run(check_args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if chk.returncode != 0:
        os.remove(novo); os.remove(sig)
        log("update v%s RECUSADO: falhou o --check (mantem a versao anterior)" % versao)
        return

    # 3) aplica: guarda a anterior e troca atomicamente
    shutil.copy2(BACKUP_PY, BACKUP_PY + ".bak")
    os.replace(novo, BACKUP_PY)
    os.remove(sig)
    log("update v%s APLICADO (assinatura + --check ok; anterior em backup.py.bak)" % versao)


# --------------------------------------------------------------------------- comandos
def cmd_enroll(args):
    ensure_age_key()
    pub = age_pubkey()
    status, resp = http("POST", args.backend.rstrip("/") + "/enroll",
                        {"enrollment_token": args.token, "age_pubkey": pub})
    if status != 200:
        sys.exit("ERRO no enrollment (%s): %s" % (status, resp.get("detail")))
    state = {
        "backend_url": args.backend.rstrip("/"),
        "cliente": resp["cliente"],
        "token": resp["token"],
        "heartbeat_intervalo": DEFAULT_HEARTBEAT,
    }
    save_state(state)
    log("inscrito como '%s'. token permanente salvo em %s" % (resp["cliente"], STATE_FILE))


def pull_config():
    """Puxa a config, decifra os segredos, grava o <cliente>.conf. Retorna a versao."""
    st = load_state()
    cliente, token = st["cliente"], st["token"]
    status, data = http("GET", "%s/config/%s" % (st["backend_url"], cliente), token=token)
    if status != 200:
        sys.exit("ERRO ao puxar config (%s): %s" % (status, data.get("detail")))

    versao = data.get("_config_versao")
    resolvido = resolve_secrets(data)

    # O token permanente e a URL do backend sao locais (nao ficam na config versionada
    # do banco). O agente os injeta aqui p/ o backup.py reportar em /runs e /inventario.
    backend_block = dict(resolvido.get("backend") or {})
    backend_block.update({"url": st["backend_url"], "token": token})
    backend_block.setdefault("log_completo", True)
    resolvido["backend"] = backend_block

    destino = conf_path(cliente)
    tmp = destino + ".new"
    _write_600(tmp, json.dumps(resolvido, indent=2, ensure_ascii=False))

    # Valida (informativo): parse + dependencias. Nao bloqueia aplicar a config
    # (deps faltando na maquina nao invalidam a config em si). O gate de --check
    # vale para UPDATE de script (doc 10), tratado a parte.
    chk = subprocess.run([sys.executable, BACKUP_PY, tmp, "--check"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if chk.returncode != 0:
        log("aviso: backup.py --check retornou %s (config aplicada mesmo assim)" % chk.returncode)

    os.replace(tmp, destino)
    log("config v%s aplicada em %s" % (versao, destino))
    return versao


def cmd_pull(args=None):
    pull_config()
    return 0


def _processa_comandos(comandos, cliente):
    for c in comandos:
        tipo = c.get("tipo")
        log("comando pendente: %s (id=%s)" % (tipo, c.get("id")))
        if tipo == "rodar_agora":
            pull_config()
            roda_backup(cliente)
        elif tipo in ("check", "--check"):
            roda_backup(cliente, check=True)
        else:
            log("comando desconhecido ignorado: %s" % tipo)


def cmd_heartbeat(args=None):
    st = load_state()
    status, resp = http("POST", st["backend_url"] + "/heartbeat",
                        {"versao_script": script_versao()}, token=st["token"])
    if status != 200:
        log("heartbeat falhou (%s): %s" % (status, resp.get("detail")))
        return
    if resp.get("config_disponivel"):
        log("config nova disponivel (v%s) -> puxando" % resp.get("config_versao"))
        pull_config()
    comandos = resp.get("comandos") or []
    if comandos:
        _processa_comandos(comandos, st["cliente"])
    upd = resp.get("update")
    if upd:
        log("update disponivel: v%s" % upd.get("versao"))
        apply_update(upd, st)


def cmd_loop(args=None):
    st = load_state()
    intervalo = int(st.get("heartbeat_intervalo", DEFAULT_HEARTBEAT))
    log("laco de heartbeat a cada %ss (cliente=%s)" % (intervalo, st["cliente"]))
    while True:
        try:
            cmd_heartbeat()
        except Exception as e:  # nunca deixa o laco morrer por um erro de rede
            log("erro no ciclo: %r" % e)
        time.sleep(intervalo)


def cmd_backup(args=None):
    st = load_state()
    pull_config()  # garante config fresca antes de rodar
    log("rodando backup.py (reporta em /runs e /inventario)")
    return roda_backup(st["cliente"]).returncode


def main():
    p = argparse.ArgumentParser(description="Agente de backup em frota")
    sub = p.add_subparsers(dest="cmd", required=True)

    pe = sub.add_parser("enroll", help="inscreve esta maquina (troca token efemero pelo permanente)")
    pe.add_argument("--backend", required=True, help="URL base do backend (ex: https://api.exemplo.com)")
    pe.add_argument("--token", required=True, help="token de enrollment efemero (do dashboard)")
    pe.set_defaults(func=cmd_enroll)

    sub.add_parser("heartbeat", help="um ciclo de heartbeat").set_defaults(func=cmd_heartbeat)
    sub.add_parser("loop", help="laco continuo de heartbeat (systemd service)").set_defaults(func=cmd_loop)
    sub.add_parser("pull", help="puxa e aplica a config").set_defaults(func=cmd_pull)
    sub.add_parser("backup", help="puxa config e roda o backup (systemd timer)").set_defaults(func=cmd_backup)

    args = p.parse_args()
    rc = args.func(args)
    sys.exit(rc or 0)


if __name__ == "__main__":
    main()
