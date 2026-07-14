#!/usr/bin/env python3
# -*- coding: utf-8 -*-
######################################################################################################
# Backup diario - PADRAO Futuratec (Python)
# Toda a logica fica AQUI. O que muda de cliente para cliente fica no .json.
# No cliente ficam apenas 2 arquivos: este backup.py e o <cliente>.json
#
# Uso:   ./backup.py                  (usa o unico .json desta pasta)
#        ./backup.py belsinos.json    (informa qual .json usar)
#        ./backup.py --check          (valida tudo SEM copiar nem enviar)
#        ./backup.py --debug          (tambem imprime tudo na tela em tempo real)
#
# Log completo p/ backend (sempre ativo, independente do --debug):
#   - cada job em "jobs[].log" traz a saida completa do rsync/cp/rclone
#     (rsync roda com -v --stats, entao vem arquivo a arquivo + estatisticas)
#   - "erros" traz todo comando que falhou na rodada (montagem, ssh, rsync, etc.)
#   - "log_completo" traz TODOS os comandos executados, comando a comando
#     (equivale a rodar o script inteiro em modo --debug)
#   - senhas (sshpass / mount cifs) sao sempre mascaradas antes de gravar/enviar
#   Opcoes no .json, dentro de "backend": {"log_completo": true/false (default true),
#                                            "max_log_chars": 200000 (limite por job)}
#
# Inventario de estrutura (enviado a parte, em POST /inventario):
#   Para cada job com origem local (rsync, rsync-ssh, cp), o script varre a pasta
#   de origem e monta um RESUMO de metadados - NAO le conteudo de arquivo nenhum:
#     - contagem de arquivos/pastas e tamanho total
#     - repartido por extensao (contagem + tamanho de cada uma)
#     - maiores arquivos e maiores subpastas (top N)
#     - arquivos modificados nas ultimas N horas (o que mudou desde ontem)
#   O script NAO decide o que e "arquivo estranho" - so entrega os dados. Quem
#   cruza isso e classifica (extensao de ransomware, executavel fora do lugar,
#   pico de modificacoes, etc.) e a IA/logica do backend, olhando o historico.
#   Opcoes no .json, em "inventario": {"ativo": true (default),
#     "modificados_horas": 24, "top_arquivos": 20, "top_pastas": 20,
#     "top_extensoes": 40, "top_modificados": 50, "max_arquivos_escaneados": 500000}
#
#   Em "destino" (varios HDs externos - opcional; sem isso, usa 'rotulo' unico como antes):
#     "hds": ["HDBKPEXT-01","HDBKPEXT-02","HDBKPEXT-03"]  -> lista, na ordem de preferencia
#        OU
#     "padrao_rotulo": "HDBKPEXT-*"   -> acha sozinho qualquer HD com rotulo que casa
#     "estrategia": "presente"        -> presente | rodizio_dia | todos
#        presente     : usa o 1o HD da lista que estiver conectado agora (o cliente
#                       pluga qualquer um; o script se vira). RECOMENDADO.
#        rodizio_dia  : escolhe pelo dia da semana (HD1=Seg, HD2=Ter...); se o HD do
#                       dia nao estiver plugado, cai para o 1o que estiver conectado.
#        todos        : espelha o backup para TODOS os HDs conectados (redundancia);
#                       gera um relatorio/e-mail/envio por HD.
#     "dias_rotacao": 7   -> quantas copias diarias o HD comporta (rodizio):
#        7 (padrao) : 1 pasta por dia da semana (Seg/Ter/...), como sempre foi.
#        N < 7      : rodizio de N pastas (dia_01..dia_0N) - o HD guarda so as
#                     ultimas N copias. Use quando o HD nao tem espaco p/ 7 dias.
#        Pode ser por copia tambem (em "copias[].dias_rotacao").
#        ATENCAO ao reduzir depois de ja ter rodado: as pastas antigas (Seg/Ter/...)
#        ou dia_0X que sobraram NAO sao apagadas sozinhas - remova-as uma vez na mao
#        para liberar espaco. E mantenha o --delete ligado (nao use 'limpeza_dias'
#        junto de rodizio curto, senao cada pasta acumula e o HD enche.)
#
# Opcoes NOVAS (todas opcionais - sem elas, o script se comporta como antes):
#   Por copia (em "copias[]"):
#     "limpeza_dias": 90   -> modo acumulativo: o rsync NAO apaga no dia a dia
#                             (protege contra exclusao/ransomware que se propaga
#                             para o destino) e so faz a limpeza dos arquivos que
#                             sumiram na origem quando passam N dias desde a
#                             ultima limpeza daquele destino. Sem esta chave, o
#                             comportamento historico continua (--delete sempre).
#   Em "backend":
#     "timeout_cmd": 0         -> tempo max (seg) de cada comando externo; 0 = sem
#                                 limite (padrao). Evita rsync/NFS travado eternamente.
#     "reenvio_segundos": 300  -> por quanto tempo insistir no envio ao backend
#     "reenvio_intervalo": 30  -> espera entre as tentativas de envio
#   Em "destino":
#     "reter_logs_dias": 7     -> quantos dias de log local manter (padrao 7)
#
# Historico (VERSAO):
#   1.0 - versao de referencia (base Futuratec) + trava de execucao unica,
#         timeout de comando, tratamento do rsync cod 24, sync antes do umount,
#         reenvio ao backend com retentativa e fila de pendentes, limpeza
#         periodica (limpeza_dias), retencao de logs e checagem de permissao.
#
# Por - Marcelo Cassel / Futuratec Tecnologias Unificadas
######################################################################################################

import os
import re
import sys
import json
import glob
import time
import fcntl
import fnmatch
import socket
import shutil
import datetime
import subprocess
import urllib.request

######################################################################################################
# Configuracao - carrega o .json do cliente
######################################################################################################
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MODO_CHECK = "--check" in sys.argv or "-c" in sys.argv
DEBUG      = "--debug" in sys.argv or "-x" in sys.argv
CONFIG = next((a for a in sys.argv[1:] if not a.startswith("-")), None)
if not CONFIG:
    achados = glob.glob(os.path.join(BASE_DIR, "*.json"))
    if len(achados) == 1:
        CONFIG = achados[0]
    else:
        sys.exit("ERRO: informe o arquivo de config. Ex: ./backup.py cliente.json")
if not os.path.isfile(CONFIG):
    sys.exit("ERRO: config nao encontrado: %s" % CONFIG)

def _sem_comentarios(texto):
    """Remove comentarios estilo // e /* */ de um JSON (JSONC), PRESERVANDO tudo
    que estiver dentro de aspas. Isso e essencial aqui: caminhos SMB comecam com
    '//' (ex: //192.168.0.1/Pasta) e NAO podem ser confundidos com comentario."""
    saida = []
    i, n = 0, len(texto)
    em_string = escape = False
    while i < n:
        ch = texto[i]
        if em_string:
            saida.append(ch)
            if escape:            escape = False
            elif ch == "\\":      escape = True
            elif ch == '"':       em_string = False
            i += 1
        elif ch == '"':
            em_string = True; saida.append(ch); i += 1
        elif ch == "/" and i + 1 < n and texto[i + 1] == "/":
            while i < n and texto[i] not in "\r\n":   # comentario ate o fim da linha
                i += 1
        elif ch == "/" and i + 1 < n and texto[i + 1] == "*":
            i += 2
            while i + 1 < n and not (texto[i] == "*" and texto[i + 1] == "/"):
                i += 1
            i += 2                                    # pula o */ final
        else:
            saida.append(ch); i += 1
    return "".join(saida)

with open(CONFIG, encoding="utf-8") as fp:
    _bruto = fp.read()
try:
    CFG = json.loads(_sem_comentarios(_bruto))
except json.JSONDecodeError as e:
    # erro amigavel (em vez de traceback) apontando linha/coluna do problema no .json
    sys.exit("ERRO: config invalido em %s -> %s" % (CONFIG, e))

CLIENTE   = CFG.get("cliente", "cliente")
EMAIL     = CFG.get("email", "")
BACKEND   = CFG.get("backend", {}) or {}
DESTINO   = CFG.get("destino", {}) or {}
MONTAGENS = CFG.get("montagens", []) or []
COPIAS    = CFG.get("copias", []) or []
INVENTARIO_CFG = CFG.get("inventario", {}) or {}   # config do levantamento de estrutura (ver cabecalho)

######################################################################################################
# Variaveis - Diversos
######################################################################################################
VERSAO = "1.0"                                    # aparece no envio ao backend (auditoria de versao)

HD_ROTULO = DESTINO.get("rotulo", "")
HD_MOUNT  = DESTINO.get("montar_em", "/mnt/hd_bkp")
DESTINO_TIPO = DESTINO.get("tipo", "hd")          # hd | nuvem

# Tempo maximo (segundos) de cada comando externo. 0 = sem limite (padrao, igual
# ao comportamento antigo). Serve para nao travar a noite toda num rsync/NFS morto.
TIMEOUT_CMD = int(BACKEND.get("timeout_cmd", 0))
_LOCK_FP = None                                   # segura o lock de execucao unica (nao deixar coletar)

DIAS_SEMANA = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]
DIA = DIAS_SEMANA[datetime.date.today().weekday()]   # vira o {dia} dos destinos
DATA = datetime.datetime.now().strftime("%d-%m-%Y")

DIR_LOG = "/var/log/backup_diario"
os.makedirs(DIR_LOG, exist_ok=True)
LOG = os.path.join(DIR_LOG, "%s-%s.log" % (CLIENTE, DATA))

def _caminho_log(rotulo=None):
    """Nome do arquivo de log. No modo 'todos' (varios HDs), inclui o rotulo p/
    nao um HD sobrescrever o relatorio do outro."""
    if rotulo:
        return os.path.join(DIR_LOG, "%s-%s-%s.log" % (CLIENTE, rotulo, DATA))
    return os.path.join(DIR_LOG, "%s-%s.log" % (CLIENTE, DATA))

# Acumuladores (usados no relatorio e no envio ao backend)
RESULTADOS = []          # cada item: {nome, metodo, status, tamanho, duracao, obs, log}
STATUS_GERAL = "sucesso"
RUN_ID = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
DEV_HD = ""
HD_FS = ""               # sistema de arquivos do HD (ntfs, ext4, ...) - detectado
HDS_SELECIONADOS = []    # HDs escolhidos p/ esta rodada: [(rotulo, dev, fs), ...] (ver seleciona_hds)

# RAW_LOG guarda TODO comando executado (montagem, rsync, ssh, etc.) e sua saida
# completa, sempre - equivale a rodar tudo em modo --debug o tempo todo, mesmo
# sem passar --debug na linha de comando. Senhas sao mascaradas antes de guardar.
RAW_LOG = []
MAX_LOG_JOB = int(BACKEND.get("max_log_chars", 200000))   # limite por job, no payload do backend

INVENTARIOS = []          # resumo de estrutura por job (enviado a parte, em /inventario)

######################################################################################################
# Funcoes - utilitarios
######################################################################################################
def _mascara_cmd(cmd):
    """Evita vazar senha/token de cliente nos logs e no envio ao backend.
    Trata: sshpass -p <senha> ... e opcoes de montagem 'username=...,password=...'."""
    out = []
    mascarar_proximo = False
    for i, a in enumerate(cmd):
        if mascarar_proximo:
            out.append("***")
            mascarar_proximo = False
            continue
        if a == "-p" and i > 0 and cmd[i - 1] == "sshpass":
            out.append(a)
            mascarar_proximo = True
            continue
        if "password=" in a:
            a = re.sub(r"password=[^,]*", "password=***", a)
        out.append(a)
    return out

def sh(cmd, timeout=None):
    """Executa um comando (lista) e devolve (codigo, saida).
    Sempre guarda o comando e a saida completa no RAW_LOG (senha mascarada) -
    e o que da a visao 'nivel --debug' de tudo que rodou, mesmo sem -x/--debug.
    Com --debug, alem de guardar, tambem imprime na tela (equivale ao 'bash -x').
    timeout: segundos p/ abortar o comando (default = TIMEOUT_CMD do .json; 0 = sem limite).
    Comando abortado por timeout volta com codigo 124 (mesma convencao do 'timeout' do GNU)."""
    cmd_log = " ".join(_mascara_cmd(cmd))
    if DEBUG:
        print("+ " + cmd_log)
    limite = timeout if timeout is not None else (TIMEOUT_CMD or None)
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=limite)
        cod, saida = p.returncode, p.stdout.decode("utf-8", "ignore")
    except subprocess.TimeoutExpired as e:
        cod = 124
        saida = (e.output.decode("utf-8", "ignore") if e.output else "")
        saida += "\n*** comando abortado por timeout (%ss) ***" % limite
    RAW_LOG.append({"cmd": cmd_log, "cod": cod, "saida": saida.strip()})
    if DEBUG and saida.strip():
        print(saida.rstrip())
    return cod, saida

def linha_log(texto=""):
    with open(LOG, "a", encoding="utf-8") as fp:
        fp.write(texto + "\n")

def humaniza(n):
    n = float(n or 0)
    for u in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return "%d %s" % (n, u) if u == "B" else "%.1f %s" % (n, u)
        n /= 1024
    return "%.1f PB" % n

def slot_rotacao(dias=7):
    """Nome da pasta do rodizio conforme a profundidade (quantos dias cabem no HD):
      - 7 (ou mais / nao informado): mantem o padrao antigo -> nome do dia da semana
        (Seg/Ter/Qua...), que ja e um rodizio de 7 pastas.
      - N < 7: rodizio de N pastas (dia_01..dia_0N), avancando 1 por dia do calendario
        e reciclando a cada N dias. Assim o HD guarda so as ultimas N copias.
    Ex.: dias=3 -> hoje 'dia_02', amanha 'dia_03', depois 'dia_01' (recicla)."""
    dias = int(dias or 7)
    if dias >= 7:
        return DIA
    dias = max(1, dias)
    idx = datetime.date.today().toordinal() % dias + 1
    return "dia_%02d" % idx

def _dias_rotacao(c):
    """Profundidade do rodizio para esta copia: usa 'dias_rotacao' da copia, senao
    o de 'destino', senao 7 (padrao = comportamento antigo, 1 pasta por dia da semana)."""
    v = c.get("dias_rotacao", DESTINO.get("dias_rotacao", 7))
    try:
        v = int(v)
    except (TypeError, ValueError):
        v = 7
    return v if v > 0 else 7

def aplica_dia(caminho, dias=7):
    """Troca {dia} pela pasta do rodizio (ver slot_rotacao). Sem 'dias', usa 7 =
    nome do dia da semana, identico ao comportamento antigo."""
    return caminho.replace("{dia}", slot_rotacao(dias))

######################################################################################################
# Funcoes - Montagem
######################################################################################################
def _rotulos_candidatos():
    """Lista ordenada de rotulos a considerar, conforme o .json:
    - 'hds': [...]              -> a propria lista, na ordem de preferencia
    - 'padrao_rotulo': 'X-*'    -> todos os rotulos PRESENTES que casam, ordenados
    - 'rotulo' unico (modo antigo) -> [rotulo]"""
    if DESTINO.get("hds"):
        return list(DESTINO["hds"])
    if DESTINO.get("padrao_rotulo"):
        cod, saida = sh(["blkid", "-o", "value", "-s", "LABEL"])
        achados = [l.strip() for l in saida.splitlines() if l.strip()]
        return sorted(set(l for l in achados if fnmatch.fnmatch(l, DESTINO["padrao_rotulo"])))
    if HD_ROTULO:
        return [HD_ROTULO]
    return []

def _detecta_rotulo(rotulo):
    """Devolve (device, fs) de um rotulo, ou ('', '') se nao estiver conectado."""
    cod, saida = sh(["blkid", "-L", rotulo])
    dev = saida.strip()
    fs = ""
    if dev:
        cod, tipo = sh(["blkid", "-s", "TYPE", "-o", "value", dev])
        fs = tipo.strip().lower()
    return dev, fs

def _hds_presentes(rotulos):
    """Filtra a lista de rotulos, devolvendo so os que estao conectados agora:
    [(rotulo, dev, fs), ...] na mesma ordem."""
    out = []
    for r in rotulos:
        dev, fs = _detecta_rotulo(r)
        if dev:
            out.append((r, dev, fs))
    return out

def seleciona_hds():
    """Resolve QUAIS HDs usar nesta rodada, conforme destino.estrategia.
    Devolve [(rotulo, dev, fs), ...]: 1 item (presente/rodizio_dia) ou N (todos)."""
    rotulos = _rotulos_candidatos()
    presentes = _hds_presentes(rotulos)
    if not presentes:
        return []
    estrategia = DESTINO.get("estrategia", "presente")
    if estrategia == "todos":
        return presentes                       # espelha p/ todos os conectados
    if estrategia == "rodizio_dia" and len(rotulos) > 1:
        alvo = rotulos[datetime.date.today().weekday() % len(rotulos)]
        for item in presentes:
            if item[0] == alvo:
                return [item]                  # o HD do dia esta plugado -> usa ele
        return [presentes[0]]                  # nao esta -> usa qualquer um conectado
    return [presentes[0]]                      # 'presente' (padrao): 1o conectado

def detecta_hd():
    """Seleciona o(s) HD(s) desta rodada (ver seleciona_hds) e guarda em
    HDS_SELECIONADOS. Deixa DEV_HD/HD_FS/HD_ROTULO apontando para o primeiro
    (usado no relatorio e no fluxo de HD unico). Devolve True se achou ao menos um.
    Compativel com o modo antigo: com 'rotulo' unico, funciona igual a antes."""
    global DEV_HD, HD_FS, HD_ROTULO, HDS_SELECIONADOS
    HDS_SELECIONADOS = seleciona_hds()
    if not HDS_SELECIONADOS:
        return False
    HD_ROTULO, DEV_HD, HD_FS = HDS_SELECIONADOS[0]
    return True

def monta_hd():
    """Monta o HD criando o ponto se preciso, sem remontar se ja estiver montado,
    e escolhendo a melhor forma conforme o sistema de arquivos (NTFS -> ntfs-3g)."""
    os.makedirs(HD_MOUNT, exist_ok=True)
    if os.path.ismount(HD_MOUNT):
        return 0
    if HD_FS == "ntfs":
        cod, _ = sh(["mount", "-t", "ntfs-3g", "-o", "big_writes", DEV_HD, HD_MOUNT])
    else:
        cod, _ = sh(["mount", DEV_HD, HD_MOUNT])
    return cod

def desmonta_hd():
    if os.path.ismount(HD_MOUNT):
        sh(["sync"])          # garante que tudo foi gravado antes de soltar (importante em NTFS/ntfs-3g)
        sh(["umount", HD_MOUNT])

def monta_compartilhamentos():
    for m in MONTAGENS:
        ponto = m["ponto"]
        os.makedirs(ponto, exist_ok=True)
        if os.path.ismount(ponto):
            continue                      # ja montado (ex: sobrou de outra rodada) -> nao remonta
        if m["tipo"] == "smb":
            opt = "username=%s,password=%s" % (m.get("usuario", ""), m.get("senha", ""))
            if m.get("dominio"):
                opt += ",domain=%s" % m["dominio"]
            if m.get("opcoes"):
                opt += "," + m["opcoes"]
            sh(["mount", "-t", "cifs", "-o", opt, m["origem"], ponto])
        elif m["tipo"] == "nfs":
            sh(["mount", "-t", "nfs", m["origem"], ponto])

def desmonta_compartilhamentos():
    for m in MONTAGENS:
        if os.path.ismount(m["ponto"]):
            sh(["umount", m["ponto"]])

######################################################################################################
# Funcoes - Copia
#   metodos: rsync | ssh-rsync | rsync-ssh | cp | tar (reservado) | rclone
######################################################################################################
# Metodos reconhecidos (evita "string magica" espalhada e facilita a validacao):
METODOS_RSYNC   = ("rsync", "ssh-rsync", "rsync-ssh")   # usam rsync por baixo
METODOS_LOCAIS  = ("rsync", "cp")                        # origem e destino locais
METODOS_VALIDOS = ("rsync", "ssh-rsync", "rsync-ssh", "cp", "tar", "rclone")

def _marca_limpeza(destino):
    """Arquivo-marcador (em DIR_LOG) que guarda a data da ultima limpeza (--delete)
    daquele destino. A chave e o proprio caminho de destino, 'higienizado'."""
    chave = re.sub(r"[^A-Za-z0-9]+", "_", destino).strip("_")[:120]
    return os.path.join(DIR_LOG, "%s-%s.limpeza" % (CLIENTE, chave))

def _deve_apagar(c, destino):
    """Decide se o rsync roda com --delete nesta rodada.
    - Padrao historico: apaga sempre (apagar_extras=true, sem 'limpeza_dias').
    - Com 'limpeza_dias' no .json: modo acumulativo. No dia a dia NAO apaga
      (assim uma exclusao/ransomware na origem nao se propaga imediatamente para
      o destino); so faz a limpeza dos arquivos que sumiram na origem quando
      passam N dias desde a ultima limpeza daquele destino."""
    if not c.get("apagar_extras", True):
        return False
    dias = int(c.get("limpeza_dias", 0) or 0)
    if dias <= 0:
        return True                       # comportamento historico: --delete toda rodada
    marca = _marca_limpeza(destino)
    try:
        ultima = os.path.getmtime(marca)
    except OSError:
        ultima = 0
    if (time.time() - ultima) >= dias * 86400:
        try:
            with open(marca, "w") as fp:  # registra que a limpeza aconteceu agora
                fp.write(datetime.datetime.now().isoformat())
        except OSError:
            pass
        return True                       # passou o intervalo -> limpa nesta rodada
    return False                          # dentro do intervalo -> rodada acumulativa

def _arquivo_mais_recente(pasta, padrao="*"):
    itens = glob.glob(os.path.join(pasta, padrao))
    itens = [i for i in itens if os.path.isfile(i)]
    return max(itens, key=os.path.getmtime) if itens else None

def destino_padrao(nome, dias=7):
    """Padrao unico da casa: <HD>/Backup_diario/<slot do rodizio>/<nome da copia>.
    O slot e o dia da semana (Seg/Ter...) quando cabe 7 dias, ou dia_01..dia_0N
    quando o HD so comporta N dias (ver slot_rotacao)."""
    return os.path.join(HD_MOUNT, "Backup_diario", slot_rotacao(dias), nome)

def _rsync_base(c, destino=None):
    """Flags padrao do rsync (modo leve p/ HD NTFS: sem dono/grupo/perm).
    -v e --stats ficam sempre ligados para trazer o log completo (arquivo a
    arquivo + estatisticas + erros), independente do --debug do script.
    Sem '-l' de proposito: o destino em HD externo e sempre NTFS, que nao suporta
    symlink no estilo Linux; o rsync entao pula os links (aparecem so no log -v).
    'destino' e usado apenas para decidir a limpeza periodica (ver _deve_apagar)."""
    cmd = ["rsync", "-rt", "-v", "--stats", "--no-o", "--no-g", "--no-p", "--modify-window=1"]
    if _deve_apagar(c, destino or ""):
        cmd.append("--delete")
    for ex in ([c["excluir"]] if isinstance(c.get("excluir"), str) else c.get("excluir", [])):
        cmd += ["--exclude", ex]
    return cmd

def _ssh_opts(c):
    """Devolve (prefixo, opcao_-e). Com senha usa sshpass; sem senha usa chave."""
    porta = str(c.get("porta", 22))
    esh = "ssh -p %s -o StrictHostKeyChecking=accept-new" % porta
    pre = ["sshpass", "-p", c["ssh_senha"]] if c.get("ssh_senha") else []
    return pre, esh

def _status_rsync(cod):
    """Traduz o codigo de saida do rsync em (status, obs).
    O codigo 24 ('arquivos sumiram durante a copia') e normal em servidor de
    arquivos em uso - tratamos como sucesso com aviso, para nao derrubar o status."""
    if cod == 0:
        return "sucesso", ""
    if cod == 24:
        return "sucesso", "aviso: arquivos sumiram durante a copia (rsync cod 24)"
    return "falha", "rsync terminou com codigo %d" % cod

def _tamanho_de_stats(saida, destino_fallback):
    """Pega o tamanho da saida do rsync --stats (evita um 'du -sh' que reescaneia
    tudo de novo). Se nao achar, cai no du de sempre."""
    m = re.search(r"[Tt]otal file size:\s*([\d.,]+)", saida or "")
    if m:
        try:
            return humaniza(int(re.sub(r"[.,]", "", m.group(1))))
        except ValueError:
            pass
    return _tamanho_pasta(destino_fallback)

def executa_copia(c):
    nome   = c.get("nome", "job")
    metodo = c.get("metodo", "rsync")
    dias   = _dias_rotacao(c)                # profundidade do rodizio (7 = padrao antigo)
    origem = aplica_dia(c.get("origem", ""), dias)
    # Destino segue o padrao automatico; so usa destino manual se o .json trouxer.
    destino = aplica_dia(c["destino"], dias) if c.get("destino") else destino_padrao(nome, dias)
    ini = time.time()
    status, tamanho, obs, saida_cmd = "sucesso", "0", "", ""
    origem_remota = (metodo == "ssh-rsync")     # ssh-rsync = origem no host remoto

    def falhar(msg):
        _registra(nome, metodo, "falha", "0", int(time.time() - ini), msg)

    # ---- Guardas: so copia se o caminho estiver realmente montado/presente ----
    destino_local = (metodo != "rsync-ssh")     # rsync-ssh = destino remoto
    if destino_local and DESTINO_TIPO == "hd" and not os.path.ismount(HD_MOUNT):
        return falhar("HD (%s) nao esta montado" % HD_MOUNT)
    if not origem_remota:                        # origem local -> da pra checar
        share = _share_da_origem(origem)
        if share and not os.path.ismount(share):
            return falhar("share da origem nao montado (%s)" % share)
        if not os.path.exists(origem):
            return falhar("origem inexistente (%s)" % origem)

    try:
        if metodo == "rsync":                    # copia local
            os.makedirs(destino, exist_ok=True)
            cod, saida_cmd = sh(_rsync_base(c, destino) + [origem.rstrip("/") + "/", destino.rstrip("/") + "/"])
            status, obs = _status_rsync(cod)
            tamanho = _tamanho_de_stats(saida_cmd, destino)

        elif metodo == "ssh-rsync":              # origem remota (SSH) -> HD local
            os.makedirs(destino, exist_ok=True)
            pre, esh = _ssh_opts(c)
            remoto = "%s@%s:%s" % (c.get("ssh_user", "root"), c.get("ssh_host", ""),
                                   origem.rstrip("/") + "/")
            cod, saida_cmd = sh(pre + _rsync_base(c, destino) + ["-e", esh, remoto, destino.rstrip("/") + "/"])
            status, obs = _status_rsync(cod)
            tamanho = _tamanho_de_stats(saida_cmd, destino)

        elif metodo == "rsync-ssh":              # origem local -> destino remoto (SSH)
            if not c.get("destino"):
                return falhar("rsync-ssh exige 'destino' remoto no .json")
            pre, esh = _ssh_opts(c)
            remoto = "%s@%s:%s" % (c.get("ssh_user", "root"), c.get("ssh_host", ""),
                                   destino.rstrip("/") + "/")
            cod, saida_cmd = sh(pre + _rsync_base(c, remoto) + ["-e", esh, origem.rstrip("/") + "/", remoto])
            status, obs = _status_rsync(cod)
            tamanho = _tamanho_de_stats(saida_cmd, origem)

        elif metodo == "cp":                     # copia simples
            # OBS (semantica): 'cp -rv origem destino' cria destino/<basename(origem)>/...
            # (a origem vira uma subpasta dentro do destino) - diferente do rsync com
            # barra final, que espelha o CONTEUDO. Comportamento mantido de proposito.
            os.makedirs(destino, exist_ok=True)
            cod, saida_cmd = sh(["cp", "-rv", "--preserve=timestamps", origem, destino])
            status = "sucesso" if cod == 0 else "falha"
            tamanho = _tamanho_pasta(destino)
            if cod != 0:
                obs = "cp terminou com codigo %d" % cod

        elif metodo == "tar":                    # RESERVADO - a validar (nao executa)
            status, obs = "a-validar", "metodo tar reservado (a validar)"

        elif metodo == "rclone":                 # nuvem
            cod, saida_cmd = sh(["rclone", "sync", origem, destino, "-v", "--stats-one-line"])
            status = "sucesso" if cod == 0 else "falha"
            tamanho = _tamanho_pasta(origem)
            if cod != 0:
                obs = "rclone terminou com codigo %d" % cod

        else:
            status, obs = "falha", "metodo desconhecido: %s" % metodo
    except Exception as e:
        status, obs = "falha", "erro: %s" % e

    dur = int(time.time() - ini)
    _registra(nome, metodo, status, tamanho, dur, obs, saida_cmd)

def _registra(nome, metodo, status, tamanho, duracao, obs="", log=""):
    global STATUS_GERAL
    log = (log or "").strip()
    if len(log) > MAX_LOG_JOB:
        log = "...(log truncado, mostrando o final)...\n" + log[-MAX_LOG_JOB:]
    RESULTADOS.append({"nome": nome, "metodo": metodo, "status": status,
                       "tamanho": tamanho, "duracao": duracao, "obs": obs, "log": log})

def _share_da_origem(origem):
    """Descobre qual ponto de montagem contem a origem (o mais especifico)."""
    escolhido = None
    for m in MONTAGENS:
        p = m["ponto"].rstrip("/")
        if origem == p or origem.startswith(p + "/"):
            if escolhido is None or len(p) > len(escolhido):
                escolhido = p
    return escolhido

def _tamanho_pasta(p):
    cod, saida = sh(["du", "-sh", p])
    return saida.split()[0] if cod == 0 and saida.strip() else "0"

######################################################################################################
# Funcoes - Inventario de estrutura (metadados p/ analise no backend, ver cabecalho)
#   So le nome/tamanho/data de cada arquivo (nunca conteudo). Nao classifica nada
#   como "suspeito" - isso e trabalho da IA/logica do lado do backend.
######################################################################################################
def _extensao(nome):
    ext = os.path.splitext(nome)[1].lower()
    return ext if ext else "(sem extensao)"

def inventario_pasta(pasta, cfg=None):
    """Varre 'pasta' e devolve um resumo: contagem, tamanho total, por extensao,
    maiores arquivos, maiores subpastas e o que foi modificado nas ultimas N horas."""
    cfg = cfg or INVENTARIO_CFG
    agora = time.time()
    limite_recente = agora - cfg.get("modificados_horas", 24) * 3600
    max_scan = cfg.get("max_arquivos_escaneados", 500000)
    base = pasta.rstrip("/")

    total_arquivos = 0
    total_pastas = 0
    tamanho_total = 0
    por_extensao = {}       # ext -> {"arquivos": n, "tamanho": bytes}
    pastas_tamanho = {}     # subpasta de 1o nivel -> bytes
    maiores_arquivos = []   # [(tamanho, caminho_relativo, mtime)]
    modificados = []        # [(mtime, caminho_relativo, tamanho)]
    erros = []
    truncado = False

    for raiz, subdirs, arquivos in os.walk(pasta, onerror=lambda e: erros.append(str(e))):
        total_pastas += len(subdirs)
        for nome in arquivos:
            if total_arquivos >= max_scan:
                truncado = True
                break
            caminho = os.path.join(raiz, nome)
            try:
                st = os.stat(caminho)
            except OSError as e:
                erros.append("%s: %s" % (caminho, e))
                continue

            total_arquivos += 1
            tamanho_total += st.st_size
            ext = _extensao(nome)
            reg = por_extensao.setdefault(ext, {"arquivos": 0, "tamanho": 0})
            reg["arquivos"] += 1
            reg["tamanho"] += st.st_size

            rel = os.path.relpath(caminho, base)
            maiores_arquivos.append((st.st_size, rel, st.st_mtime))
            primeiro_nivel = rel.split(os.sep, 1)[0]
            pastas_tamanho[primeiro_nivel] = pastas_tamanho.get(primeiro_nivel, 0) + st.st_size
            if st.st_mtime >= limite_recente:
                modificados.append((st.st_mtime, rel, st.st_size))
        if truncado:
            erros.append("varredura truncada em %d arquivos (max_arquivos_escaneados)" % max_scan)
            break

    maiores_arquivos.sort(key=lambda x: x[0], reverse=True)
    modificados.sort(key=lambda x: x[0], reverse=True)
    extensoes_ord = sorted(por_extensao.items(), key=lambda kv: kv[1]["tamanho"], reverse=True)
    pastas_ord = sorted(pastas_tamanho.items(), key=lambda kv: kv[1], reverse=True)

    def _iso(mtime):
        return datetime.datetime.fromtimestamp(mtime).isoformat()

    return {
        "arquivos": total_arquivos,
        "pastas": total_pastas,
        "tamanho_bytes": tamanho_total,
        "tamanho": humaniza(tamanho_total),
        "truncado": truncado,
        "extensoes": [{"ext": ext, "arquivos": v["arquivos"], "tamanho_bytes": v["tamanho"]}
                      for ext, v in extensoes_ord[:cfg.get("top_extensoes", 40)]],
        "maiores_arquivos": [{"caminho": rel, "tamanho_bytes": tam, "modificado": _iso(mt)}
                             for tam, rel, mt in maiores_arquivos[:cfg.get("top_arquivos", 20)]],
        "maiores_pastas": [{"pasta": p, "tamanho_bytes": tam, "tamanho": humaniza(tam)}
                           for p, tam in pastas_ord[:cfg.get("top_pastas", 20)]],
        "modificados_recentes": [{"caminho": rel, "tamanho_bytes": tam, "modificado": _iso(mt)}
                                 for mt, rel, tam in modificados[:cfg.get("top_modificados", 50)]],
        "erros": erros[:100],
    }

def registra_inventario(c):
    """Roda o inventario da origem de um job, se fizer sentido (origem local e existente),
    e guarda em INVENTARIOS. Nunca derruba o backup por causa disso."""
    nome = c.get("nome", "job")
    metodo = c.get("metodo", "rsync")
    if c.get("inventario") is False:
        return
    if metodo not in ("rsync", "rsync-ssh", "cp"):
        return    # origem remota (ssh-rsync) ou nuvem (rclone) - sem varredura local por enquanto
    origem = aplica_dia(c.get("origem", ""), _dias_rotacao(c))
    if not origem or not os.path.isdir(origem):
        return
    try:
        resumo = inventario_pasta(origem)
        resumo.update({"nome": nome, "metodo": metodo, "origem": origem})
        INVENTARIOS.append(resumo)
    except Exception as e:
        INVENTARIOS.append({"nome": nome, "metodo": metodo, "origem": origem,
                            "erro": "falha ao gerar inventario: %s" % e})

def copia(inventariar=True):
    global STATUS_GERAL, HORA_INICIO, HORA_FIM, INICIO, FIM
    HORA_INICIO = datetime.datetime.now().strftime("%H:%M")
    INICIO = time.time()

    for c in COPIAS:
        executa_copia(c)
        if inventariar and INVENTARIO_CFG.get("ativo", True):
            registra_inventario(c)

    HORA_FIM = datetime.datetime.now().strftime("%H:%M")
    FIM = time.time()

    ok = sum(1 for r in RESULTADOS if r["status"] == "sucesso")
    if ok == 0 and RESULTADOS:
        STATUS_GERAL = "falha"
    elif ok < len(RESULTADOS):
        STATUS_GERAL = "parcial"

######################################################################################################
# Funcoes - Relatorio (no padrao Futuratec)
######################################################################################################
def param_relatorio():
    global TOTAL_HD, USADO_HD, USO_HD
    try:
        u = shutil.disk_usage(HD_MOUNT)
        TOTAL_HD = humaniza(u.total)
        USADO_HD = humaniza(u.used)
        USO_HD = "%d%%" % round(u.used * 100 / u.total)
    except Exception:
        TOTAL_HD = USADO_HD = USO_HD = "-"

def _prepara_logs():
    """Zera o relatorio de hoje (para ficar limpo) e mantem apenas os ultimos
    'reter_logs_dias' (default 7) de logs deste cliente. NAO mexe nos arquivos
    de pendencia (*-falhou.json) nem nos marcadores de limpeza (*.limpeza)."""
    dias = int(DESTINO.get("reter_logs_dias", 7))
    limite = time.time() - dias * 86400
    for f in glob.glob(os.path.join(DIR_LOG, CLIENTE + "-*.log")):
        try:
            if f == LOG or os.path.getmtime(f) < limite:
                os.remove(f)
        except OSError:
            pass

def relatorio_final():
    _prepara_logs()
    ok = sum(1 for r in RESULTADOS if r["status"] == "sucesso")
    L = linha_log
    L()
    L("#########################################################")
    L("     %s      |     Data - %s" % (CLIENTE, DATA))
    L("---------------------------------------------------------")
    L("                       Backup Diario")
    L("#########################################################")
    L("---------------------------------------------------------")
    L(" Duracao do Backup :")
    L("---------------------------------------------------------")
    L(" Inicio do Backup : ..............................%s." % HORA_INICIO)
    L(" Termino do Backup : .............................%s." % HORA_FIM)
    L(" Tempo Total da Copia : .......%d minutos, %d segundos."
      % (int(FIM - INICIO) // 60, int(FIM - INICIO) % 60))
    L(" Destino do Backup : .....................%s." % DESTINO_DESC)
    L("---------------------------------------------------------")
    for r in RESULTADOS:
        L("#########################################################")
        L(" JOB : %s  (%s)" % (r["nome"], r["metodo"]))
        L("---------------------------------------------------------")
        L(" Resultado : .....................................%s." % r["status"])
        L(" Tamanho : .......................................%s." % r["tamanho"])
        L(" Duracao : .......................................%d seg." % r["duracao"])
        if r["status"] == "falha" and r.get("obs"):
            L(" Motivo : ........................................%s." % r["obs"])
        L("---------------------------------------------------------")
    L("#########################################################")
    L(" COPIA EXTERNA :")
    L("---------------------------------------------------------")
    L(" HD Externo utilizado : .....................%s." % HD_ROTULO)
    L(" Espaco total do dispositivo : ..............%s." % TOTAL_HD)
    L(" Espaco Utilizado : .........................%s." % USADO_HD)
    L(" Percentual Utilizado : .....................%s." % USO_HD)
    L("---------------------------------------------------------")
    L(" Status geral : .............................%s (%d/%d)." % (STATUS_GERAL, ok, len(RESULTADOS)))
    L("---------------------------------------------------------")
    L("#########################################################")
    L("            FUTURATEC Tecnologias Unificadas")
    L("                       51 3581.5549")
    L("#########################################################")

def relatorio_erro():
    _prepara_logs()
    L = linha_log
    L()
    L("#########################################################")
    L("     %s      |     Data - %s" % (CLIENTE, DATA))
    L("---------------------------------------------------------")
    L("                       Backup Diario")
    L("#########################################################")
    L("#                                                       #")
    L("#                    *** ATENCAO ***                    #")
    L("#                                                       #")
    L("#              Nenhum dispositivo externo               #")
    L("#          foi detectado para efetuar o backup.         #")
    L("#                                                       #")
    L("#########################################################")
    L("            FUTURATEC Tecnologias Unificadas")
    L("                       51 3581.5549")
    L("#########################################################")

######################################################################################################
# Funcoes - E-mail
######################################################################################################
def envia_email():
    if not EMAIL or not shutil.which("mutt"):
        return
    corpo = ("Backup diario concluido (status: %s).\n"
             "Confira o relatorio em anexo.\n"
             "Duvidas, entre em contato com a Futuratec Tecnologias Unificadas.\n"
             "Fone - 51 3581.5547 / 3581.5549" % STATUS_GERAL)
    assunto = "%s - Backup diario [%s]." % (CLIENTE, STATUS_GERAL)
    p = subprocess.Popen(["mutt", "-s", assunto, "-a", LOG, "--"] + EMAIL.split(),
                         stdin=subprocess.PIPE)
    p.communicate(corpo.encode("utf-8"))

def envia_email_erro():
    if not EMAIL or not shutil.which("mutt"):
        return
    corpo = ("Nenhum HD Externo para backup foi localizado!\n\n"
             "Duvidas, entre em contato com a Futuratec Tecnologias Unificadas.\n"
             "Fone - 51 3581.5547 / 3581.5549")
    p = subprocess.Popen(["mutt", "-s", "%s - ERRO no backup!" % CLIENTE, "--"] + EMAIL.split(),
                         stdin=subprocess.PIPE)
    p.communicate(corpo.encode("utf-8"))

######################################################################################################
# Funcoes - Backend (FASE 2 - dormente enquanto backend.url estiver vazio)
######################################################################################################
def _post_backend(sufixo, dados):
    """POST cru para <url><sufixo> (ex: /runs, /inventario). Lanca excecao se falhar."""
    url = BACKEND.get("url", "").rstrip("/")
    req = urllib.request.Request(url + sufixo, data=dados, method="POST")
    req.add_header("Content-Type", "application/json")
    if BACKEND.get("token"):
        req.add_header("Authorization", "Bearer " + BACKEND["token"])
    urllib.request.urlopen(req, timeout=60)

def _envia_com_retentativa(sufixo, dados):
    """Insiste no envio por ate 'reenvio_segundos' (default 300), esperando
    'reenvio_intervalo' (default 30) entre as tentativas. Devolve True se
    conseguiu; False se estourou o tempo (ai o chamador grava em disco)."""
    prazo     = int(BACKEND.get("reenvio_segundos", 300))
    intervalo = int(BACKEND.get("reenvio_intervalo", 30))
    limite = time.time() + max(prazo, 0)
    while True:
        try:
            _post_backend(sufixo, dados)
            return True
        except Exception:
            if time.time() >= limite:
                return False
            time.sleep(max(intervalo, 1))

def _grava_pendente(nome, dados):
    """Guarda o payload em disco (chmod 600) para reenviar numa proxima rodada."""
    try:
        caminho = os.path.join(DIR_LOG, nome)
        fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as fp:
            fp.write(dados)
    except OSError:
        pass

def _reenvia_pendentes():
    """Antes de mandar a rodada atual, tenta reenviar o que ficou guardado quando
    o backend estava fora (arquivos *-falhou.json). Some com o arquivo ao acertar."""
    if not BACKEND.get("url"):
        return
    for caminho in sorted(glob.glob(os.path.join(DIR_LOG, "*-falhou.json"))):
        sufixo = "/inventario" if "inventario-falhou.json" in caminho else "/runs"
        try:
            with open(caminho, "rb") as fp:
                dados = fp.read()
        except OSError:
            continue
        if _envia_com_retentativa(sufixo, dados):
            try: os.remove(caminho)
            except OSError: pass

def envia_backend():
    if not BACKEND.get("url"):
        return
    _reenvia_pendentes()                            # primeiro escoa a fila antiga
    erros = [c for c in RAW_LOG if c["cod"] != 0]   # todos os comandos que deram erro na rodada
    payload = {
        "cliente": CLIENTE, "hostname": socket.gethostname(), "run_id": RUN_ID,
        "versao_script": VERSAO,
        "versao_config": CFG.get("_config_versao"),   # versao da config aplicada (gravada pelo agente)
        "data": datetime.datetime.now().isoformat(), "status": STATUS_GERAL,
        "total_jobs": len(RESULTADOS),
        "jobs_ok": sum(1 for r in RESULTADOS if r["status"] == "sucesso"),
        "destino": {"rotulo": HD_ROTULO, "total": globals().get("TOTAL_HD", "-"),
                    "usado": globals().get("USADO_HD", "-"), "uso_pct": globals().get("USO_HD", "-")},
        "jobs": RESULTADOS,      # cada job ja inclui "log" = saida completa do rsync/cp/rclone
        "erros": erros,          # todo comando com codigo != 0 (montagem, ssh, rsync, etc.)
    }
    if BACKEND.get("log_completo", True):
        payload["log_completo"] = RAW_LOG   # comando a comando, nivel --debug, senha ja mascarada

    dados = json.dumps(payload).encode("utf-8")
    if not _envia_com_retentativa("/runs", dados):
        # Backend fora depois de insistir: grava local p/ reenviar na proxima rodada.
        _grava_pendente("%s-%s-envio-falhou.json" % (CLIENTE, RUN_ID), dados)

def envia_inventario():
    """Manda o resumo de estrutura (metadados) para um endpoint separado do /runs,
    assim o backend/IA pode analisar isso num fluxo proprio, sem misturar com o
    relatorio de execucao do backup."""
    if not BACKEND.get("url") or not INVENTARIOS:
        return
    payload = {
        "cliente": CLIENTE, "hostname": socket.gethostname(), "run_id": RUN_ID,
        "versao_script": VERSAO,
        "data": datetime.datetime.now().isoformat(),
        "jobs": INVENTARIOS,
    }
    dados = json.dumps(payload).encode("utf-8")
    if not _envia_com_retentativa("/inventario", dados):
        _grava_pendente("%s-%s-inventario-falhou.json" % (CLIENTE, RUN_ID), dados)

######################################################################################################
# Funcoes - Validacao (--check): confere tudo SEM copiar nem enviar
######################################################################################################
def modo_check():
    problemas = 0
    def ck(ok, desc):
        nonlocal problemas
        print("  [ OK ]   " + desc if ok else "  [FALHA]  " + desc)
        if not ok: problemas += 1

    print("==========================================================")
    print(" VALIDACAO - %s   (%s)" % (CLIENTE, CONFIG))
    print(" (nao copia nada, nao envia ao backend)")
    print("==========================================================\n-- Dependencias --")
    ck(bool(shutil.which("rsync")), "rsync")
    ck(bool(shutil.which("mount.cifs")), "cifs-utils")
    if EMAIL: ck(bool(shutil.which("mutt")), "mutt")
    metodos = [c.get("metodo") for c in COPIAS]
    if any(m in ("ssh-rsync", "rsync-ssh") for m in metodos):
        ck(bool(shutil.which("ssh")), "ssh")
        if any(c.get("ssh_senha") for c in COPIAS):
            ck(bool(shutil.which("sshpass")), "sshpass (necessario p/ SSH com senha)")
    if "rclone" in metodos:
        ck(bool(shutil.which("rclone")), "rclone")

    print("\n-- HD externo --")
    candidatos = _rotulos_candidatos()
    if candidatos or DESTINO_TIPO == "hd":
        estrategia = DESTINO.get("estrategia", "presente")
        print("  [info]   estrategia: %s   candidatos: %s" %
              (estrategia, ", ".join(candidatos) or "(nenhum)"))
        # mostra, um a um, quais estao plugados agora
        presentes = _hds_presentes(candidatos)
        conectados = {r for r, _, _ in presentes}
        for r in candidatos:
            ck(r in conectados, "HD '%s' conectado" % r)
        achou = detecta_hd()      # aplica a estrategia e escolhe o(s) da rodada
        if achou:
            escolhidos = ", ".join(r for r, _, _ in HDS_SELECIONADOS)
            print("  [info]   sera(ao) usado(s) nesta rodada: %s" % escolhidos)
            # testa a montagem do primeiro (representa o fluxo real)
            monta_hd()
            ck(os.path.ismount(HD_MOUNT), "HD montado em %s (%s)" % (HD_MOUNT, HD_FS or "?"))
        else:
            ck(False, "nenhum HD da lista esta conectado")
    else:
        print("  [info]   sem rotulo de HD (cliente so-nuvem)")

    print("\n-- Rodizio / retencao --")
    rot_padrao = int(DESTINO.get("dias_rotacao", 7) or 7)
    print("  [info]   dias de rodizio (destino): %d  ->  pasta de hoje: '%s'" %
          (rot_padrao, slot_rotacao(rot_padrao)))
    for c in COPIAS:
        if c.get("dias_rotacao"):
            print("  [info]   %s: rodizio proprio de %s dias -> pasta '%s'" %
                  (c.get("nome"), c.get("dias_rotacao"), slot_rotacao(_dias_rotacao(c))))

    print("\n-- Compartilhamentos --")
    monta_compartilhamentos()
    for m in MONTAGENS:
        ck(os.path.ismount(m["ponto"]), "%s -> %s" % (m["origem"], m["ponto"]))

    print("\n-- Origens das copias --")
    for c in COPIAS:
        dias = _dias_rotacao(c)
        if c.get("metodo") == "ssh-rsync":
            print("  [info]   %s (ssh-rsync): origem remota %s@%s:%s" %
                  (c.get("nome"), c.get("ssh_user", "root"), c.get("ssh_host", "?"),
                   aplica_dia(c.get("origem", ""), dias)))
            continue
        origem = aplica_dia(c.get("origem", ""), dias)
        ck(os.path.exists(origem), "%s (%s): %s" % (c.get("nome"), c.get("metodo"), origem))

    desmonta_compartilhamentos()
    desmonta_hd()

    print("\n-- Backend --")
    print("  [info]   url=%s" % (BACKEND.get("url") or "(vazio - roda local, sem envio)"))
    print("  [info]   inventario de estrutura: %s" %
          ("ativo" if INVENTARIO_CFG.get("ativo", True) else "desativado"))

    print("\n-- Seguranca --")
    try:
        modo = os.stat(CONFIG).st_mode
        # Alerta se o config (que guarda senhas/token) for legivel por grupo/outros.
        ck(not (modo & 0o077), "permissao do config restrita  (ajuste: chmod 600 %s)"
           % os.path.basename(CONFIG))
    except OSError:
        pass

    print("\n==========================================================")
    if problemas == 0:
        print(" RESULTADO: tudo certo. Pode agendar.")
        sys.exit(0)
    print(" RESULTADO: %d problema(s). Ajuste o .json antes de agendar." % problemas)
    sys.exit(2)

######################################################################################################
# Rotina
######################################################################################################
def _trava_execucao():
    """Impede que duas rodadas do mesmo cliente rodem juntas (ex.: cron atrasado
    caindo em cima da rodada anterior, ou execucao manual durante o cron).
    Se ja houver uma em andamento, sai sem barulho."""
    global _LOCK_FP
    caminho = os.path.join(DIR_LOG, "%s.lock" % CLIENTE)
    _LOCK_FP = open(caminho, "w")           # mantido aberto o processo todo (segura o lock)
    try:
        fcntl.flock(_LOCK_FP, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit("Ja existe um backup de '%s' em andamento. Saindo." % CLIENTE)

def _reset_acumuladores():
    """Zera os acumuladores para uma nova passada (usado no modo 'todos', onde
    cada HD gera seu proprio relatorio/envio, independente dos outros)."""
    global RESULTADOS, RAW_LOG, INVENTARIOS, STATUS_GERAL
    RESULTADOS = []
    RAW_LOG = []
    INVENTARIOS = []
    STATUS_GERAL = "sucesso"

def _backup_num_hd(rotulo, dev, fs, inventariar):
    """Executa o backup completo em UM HD ja selecionado (montar -> copiar ->
    relatorio -> e-mail -> backend -> desmontar). Devolve o status desse HD.
    As montagens de rede (shares) ficam de fora - sao montadas uma vez so em main()."""
    global DEV_HD, HD_FS, HD_ROTULO, LOG, DESTINO_DESC, STATUS_GERAL
    global TOTAL_HD, USADO_HD, USO_HD
    HD_ROTULO, DEV_HD, HD_FS = rotulo, dev, fs
    LOG = _caminho_log(rotulo if len(HDS_SELECIONADOS) > 1 else None)
    DESTINO_DESC = "HD Externo (%s)" % rotulo
    monta_hd()
    if not os.path.ismount(HD_MOUNT):
        STATUS_GERAL = "falha"
        TOTAL_HD = USADO_HD = USO_HD = "-"
        relatorio_erro()
        envia_email_erro()
        envia_backend()
        return "falha"
    copia(inventariar=inventariar)
    param_relatorio()
    relatorio_final()
    envia_email()
    envia_backend()
    if inventariar:
        envia_inventario()      # origem e a mesma p/ todos os HDs -> manda so uma vez
    desmonta_hd()
    return STATUS_GERAL

def main():
    global DESTINO_DESC, TOTAL_HD, USADO_HD, USO_HD, STATUS_GERAL

    if MODO_CHECK:
        modo_check()

    _trava_execucao()          # a partir daqui, so uma rodada por cliente

    if DESTINO_TIPO == "hd":
        if detecta_hd():
            # Um HD (presente/rodizio_dia) ou varios (estrategia 'todos').
            monta_compartilhamentos()          # shares de rede: uma vez so p/ todos os HDs
            statuses = []
            for i, (rot, dev, fs) in enumerate(HDS_SELECIONADOS):
                statuses.append(_backup_num_hd(rot, dev, fs, inventariar=(i == 0)))
            desmonta_compartilhamentos()
            STATUS_GERAL = "sucesso" if all(s == "sucesso" for s in statuses) else \
                           ("falha" if all(s == "falha" for s in statuses) else "parcial")
        else:
            relatorio_erro()
            envia_email_erro()
            STATUS_GERAL = "falha"
            envia_backend()
    else:  # nuvem
        DESTINO_DESC = "Nuvem"
        TOTAL_HD = USADO_HD = USO_HD = "-"
        monta_compartilhamentos()
        copia()
        relatorio_final()
        envia_email()
        envia_backend()
        envia_inventario()
        desmonta_compartilhamentos()

    sys.exit(0 if STATUS_GERAL == "sucesso" else 1)

if __name__ == "__main__":
    main()
