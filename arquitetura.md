# Gerenciamento de Backup em Frota — Documento de Arquitetura

**Projeto:** Backend central + dashboard para gerenciar o backup diário dos clientes (Futuratec)
**Base atual:** `bkp.py` (v1.0) + `<cliente>.json` por cliente, rodando em cada máquina Linux
**Status deste documento:** planta de referência — alinhamento fechado, pré-desenvolvimento
**Escopo:** v1 (frota gerenciável). Análise inteligente de inventário fica para a fase 2.

---

## 1. Objetivo

Gerenciar o backup de vários clientes a partir de um ponto central, **sem SSH e sem
nenhuma conexão de entrada** nas máquinas dos clientes. Editar config, ver a saúde da
frota, disparar comandos e atualizar o script — tudo pelo dashboard. As máquinas dos
clientes só falam para fora (HTTPS de saída), o que atravessa qualquer NAT/firewall de
rede de terceiros sem port-forward, sem VPN e sem porta exposta.

---

## 2. Princípios que guiam todo o desenho

1. **Modelo pull.** O cliente busca a própria config no backend; o backend nunca inicia
   conexão com o cliente.
2. **Só HTTPS de saída** (cliente → backend). Nada de entrada. Sem SSH.
3. **Fonte da verdade é o backend.** O agente é dono do `.conf`: puxa e grava por cima.
   Edição manual na máquina do cliente é temporária e será sobrescrita no próximo pull.
4. **Segredo legível só pelo dono.** As senhas trafegam e são armazenadas cifradas; nem o
   banco nem, no futuro, um invasor do backend conseguem lê-las.
5. **O updater é sagrado.** A peça que atualiza o resto quase nunca muda e nunca se
   auto-suicida; código novo só entra assinado, testado e em rollout gradual.

---

## 3. Componentes

| Componente | Papel | Stack |
|---|---|---|
| **Agente** | Roda no cliente. Puxa config, decifra segredos, valida, roda o backup, manda heartbeat e reporta. | Python, arquivo único, mesma pasta do `bkp.py` |
| **`bkp.py`** | O motor de backup atual (montagens, rsync/cp/ssh/rclone, relatório). Não muda a lógica; ganha config vinda do agente. | Python (já existe, v1.0) |
| **Backend** | Recebe runs/inventário/heartbeat, serve config cifrada, cuida de enrollment, comandos e updates. | FastAPI + Postgres |
| **Dashboard** | Interface interna: editar config, ver frota, disparar comandos, gerenciar clientes. | React (SPA) |
| **Ferramenta de recuperação** | Offline, roda na máquina do operador. Decifra e recifra segredos quando uma máquina de cliente morre. | CLI Python + `age` |

---

## 4. Arquitetura de rede e fluxo

```
   MÁQUINA DO CLIENTE                         SEU SERVIDOR (VPS)
 ┌──────────────────────┐                 ┌──────────────────────────┐
 │  agente (Python)      │   HTTPS saída   │  nginx (TLS/Let's Encrypt)│
 │   ├─ bkp.py           │ ───────────────▶│   ├─ /api  → FastAPI      │
 │   ├─ chave privada age│   (só saída)    │   └─ /     → React build  │
 │   ├─ token permanente │                 │                          │
 │   └─ <cliente>.conf   │                 │  FastAPI ── Postgres      │
 └──────────────────────┘                 └──────────────────────────┘
        NAT/firewall                          Docker Compose

   OPERADOR (offline, só no desastre)
 ┌──────────────────────┐
 │  ferramenta recovery  │   chave privada de recuperação vem do 1Password
 │   (age)               │   NUNCA toca o servidor
 └──────────────────────┘
```

O cliente faz, em cada ciclo: **heartbeat** (leve, frequente) e **backup** (pesado, 1x/dia).
O backend responde ao heartbeat dizendo se há config nova, comando pendente ou update.

---

## 5. Modelo de segurança dos segredos (o coração do projeto)

### 5.1 Modelo A — assimétrico, o backend não decifra

- Cada cliente gera um **par de chaves `age` na instalação**. A **chave privada nunca sai
  da máquina do cliente**; só a pública vai para o backend no enrollment.
- Ao salvar uma senha no dashboard, o **backend cifra** para a chave pública do cliente e
  guarda só o ciphertext. A senha em texto puro existe apenas de passagem, na memória do
  servidor, e some em seguida. O banco nunca tem senha legível.
- No `GET /config`, o cliente recebe o ciphertext e abre com a chave privada local.
- Se o banco inteiro vazar, o atacante leva só ciphertext; as chaves privadas estão
  espalhadas nas máquinas dos clientes. O HTTPS é camada extra de transporte, mas a
  segurança **não depende** dele.

### 5.2 `age`, só nos campos de senha

- Cripto com **`age`** (multi-destinatário nativo — ver 5.3).
- Cifra **apenas os campos secretos** (`senha` das montagens, `ssh_senha` das cópias).
  A estrutura do config fica em claro, para o dashboard renderizar, mesclar e validar.

### 5.3 Recuperação (7b) — dois destinatários

- Cada segredo é cifrado, desde o início, para **dois destinatários**:
  1. a chave pública do **cliente**;
  2. a chave pública de **recuperação** (sua).
- A **chave privada de recuperação vive no 1Password** e **nunca toca o servidor**. O
  backend conhece só a pública de recuperação — com pública só se cifra, nunca se decifra.
- Consequência: mesmo comprometendo o backend inteiro, ninguém decifra nada sem o 1Password.

### 5.4 Ferramenta de recuperação offline

- O decifrar-e-recifrar acontece numa **CLI local do operador**, não num botão do dashboard.
- No desastre: pega-se a chave privada de recuperação do 1Password numa máquina de
  confiança → a ferramenta lê os ciphertexts antigos do backend → decifra com a chave de
  recuperação → recifra para a chave pública da **máquina nova** → grava de volta.
- **Regra inviolável:** a chave de recuperação nunca é colada em campo de dashboard/servidor.
  Se isso acontecesse, a chave iria para o lado do servidor e a propriedade toda morreria.

### 5.5 Assinatura de update (separada da cripto)

- `age` cifra, mas **não assina**. Para verificar o `bkp.py` antes de aplicar, usa-se
  **`minisign`** (mesmo ecossistema, formato simples).
- A **chave privada de assinatura** também mora no 1Password.
- O agente verifica a assinatura **antes** de aplicar qualquer versão nova.

### 5.6 Evolução futura (fora do v1)

Hoje o **backend cifra**. Se um dia quiser fechar a janela de milissegundos em que o
servidor vê a senha, move-se o passo de cifragem para o **front** (o navegador cifra com a
pública do cliente antes de enviar), sem mudar mais nada da arquitetura.

---

## 6. Modelo de dados (Postgres) — conceitual

| Tabela | Conteúdo |
|---|---|
| `clientes` | id, nome, chave pública `age`, hash do token permanente, versão do script, último heartbeat, status |
| `configs` | **versionada** por cliente: a parte não-secreta do config, autor da alteração, timestamp |
| `client_secrets` | valores de senha cifrados (`age`, dois destinatários), referência a qual campo de qual montagem/cópia |
| `runs` | payload do `POST /runs` (status, jobs_ok, uso do HD, erros, **versão da config aplicada**) |
| `inventarios` | payload do `POST /inventario` (metadados de estrutura — guardado no v1, analisado na fase 2) |
| `comandos` | fila on-demand por cliente ("rodar agora", "--check"), com estado |
| `updates` | versões do `bkp.py`, assinatura `minisign`, grupo de rollout (canary/geral) |
| `usuarios` | login do dashboard, papéis |
| `enrollment_tokens` | tokens efêmeros/uso único gerados pelo front, com expiração |

A **config versionada** dá histórico e rollback. O `run` carrega a **versão aplicada**, para
o dashboard mostrar se a mudança já chegou (pendente vs aplicada).

---

## 7. API

### Contrato já existente (o `bkp.py` v1.0 já fala isso)
- `POST /runs` — relatório da rodada (status, jobs_ok, destino/uso do HD, erros, log completo).
- `POST /inventario` — resumo de metadados da estrutura de origem.

### Novos endpoints do cliente
- `GET /config/{cliente}` — devolve o config mesclado, com os campos de senha cifrados
  (`age`). Autenticado por token Bearer do cliente.
- `POST /heartbeat` — "estou vivo" leve; resposta indica se há config nova, comando ou update.
- Enrollment — o cliente registra a chave pública `age` e troca o token efêmero pelo permanente.
- `GET /comando/{cliente}` (ou embutido no heartbeat) — comandos pendentes.
- Download de update — o binário/arquivo do `bkp.py` novo + sua assinatura `minisign`.

### Dashboard → backend
- Auth própria (sessão/JWT) com papéis.
- CRUD de clientes e configs, geração de token de enrollment, fila de comandos, controle de
  rollout de update.

### Duas autenticações distintas (não confundir com a cripto)
- **Cliente → backend:** token Bearer **por cliente, com escopo** (o token do seifo só
  acessa dados do seifo). É *quem está pedindo*.
- **Dashboard → backend:** auth de usuário interno.
- A cripto `age` garante *quem consegue ler* o segredo. São camadas separadas; o projeto usa
  as duas.

---

## 8. Ciclo de vida da config

```
edita no dashboard → salva nova VERSÃO → cliente puxa no próximo ciclo
   → agente valida com --check → aplica e grava <cliente>.conf
   → reporta no /runs com a versão aplicada
```

- Dashboard mostra **pendente vs aplicada** por cliente.
- **Rollback** = apontar para a versão anterior; o cliente aplica no próximo pull.

---

## 9. O agente no cliente

**Pasta única** (mesma do `bkp.py`), contendo: o agente, `bkp.py`, a chave privada `age`,
o token permanente e o `<cliente>.conf` gerado (`chmod 600`).

**Dois gatilhos via `systemd`** (substitui o cron):
- `service` do agente: loop de **heartbeat** (a cada 5–15 min) + pull de config/comandos/updates.
- `timer` do backup: dispara o `bkp.py` 1x/dia (usa `OnFailure` para registrar falha).

**Passo do agente ao rodar o backup:**
1. Puxa `GET /config/{cliente}`.
2. Decifra os campos de senha com a chave privada `age`.
3. Grava o `<cliente>.conf` final.
4. Valida com `bkp.py --check`.
5. Roda o backup; o `bkp.py` reporta em `/runs` e `/inventario` (já faz isso hoje).

---

## 10. Auto-update do `bkp.py`

- **Updater burro e estável**, separado do payload (`bkp.py`). O updater atualiza o payload;
  o updater não se auto-atualiza de forma que possa se suicidar.
- **Assinatura `minisign` verificada antes de aplicar.**
- **Canary:** a versão nova vai primeiro para 1–2 clientes de teste; passado X dias sem
  problema, libera para o resto. Controlado por cliente/grupo no dashboard.
- **Rollback:** se a versão nova falhar o `--check`, o agente **não aplica**, mantém a
  anterior e reporta no `/runs`.

---

## 11. Instalação e enrollment

1. Criar o cliente no dashboard → o front gera um **token de enrollment efêmero (uso único)**.
2. Rodar o instalador (`curl … | bash`) na máquina do cliente. Ele:
   - instala o agente + `bkp.py` na pasta;
   - **gera o par de chaves `age`**;
   - faz o enrollment: manda a **chave pública** + o token efêmero; recebe o **token permanente**;
   - deixa o `service` e o `timer` do `systemd` no lugar;
   - faz o primeiro pull da config.
3. As senhas (SMB/SSH) você preenche **no dashboard**; o cliente as baixa cifradas.

O único segredo por cliente na instalação é o token efêmero — que expira depois do uso.

---

## 12. Recuperação de máquina (nova ou a mesma)

1. Máquina do cliente morreu → a chave privada `age` dela morreu junto.
2. Instala do zero na máquina nova (novo par de chaves, novo enrollment, novo token).
3. Roda a **ferramenta offline** numa máquina de confiança:
   - chave privada de recuperação vem do **1Password**;
   - a ferramenta lê os ciphertexts antigos do backend, decifra com a chave de recuperação,
     recifra para a **chave pública nova** do cliente e grava de volta.
4. Sem redigitar nenhuma senha. A chave do 1Password nunca toca o servidor.

---

## 13. Operação do backend

- **Hospedagem:** VPS com **Docker Compose** (FastAPI + Postgres). Reproduzível, fácil de
  subir de novo.
- **TLS:** **nginx** como proxy (Let's Encrypt/certbot). nginx serve o build estático do
  React em `/` e faz proxy de `/api` para o FastAPI.
- **Backup do backend:** **script `pg_dump`** agendado, **com envio do dump para fora da
  VPS** (o backup não pode morrer junto com o servidor).
- **Restore:** procedimento definido no final do projeto (registrado como pendência — ver 15).
- **Ponto único de falha:** o backend. Como o plano de desastre é "subir tudo de novo", o
  backup/restore do backend é item de primeira classe, não enfeite.

---

## 14. Escopo v1 vs fase 2

**v1 — entregar a frota gerenciável:**
- Modelo pull completo (config cifrada, enrollment, token efêmero→permanente).
- Backend FastAPI + Postgres, dashboard React, agente Python.
- Heartbeat, comandos on-demand, saúde da frota.
- Auto-update com assinatura + canary + rollback.
- Recuperação 7b + ferramenta offline.
- Inventário: backend só **recebe e guarda**.

**Fase 2:**
- Análise inteligente do inventário (extensão de ransomware, pico de modificações,
  executável fora do lugar) cruzando o histórico acumulado.
- Eventual migração da cifragem do backend para o front.

---

## 15. Decisões travadas (resumo)

| Tema | Decisão |
|---|---|
| Linguagem/stack backend | FastAPI + Postgres |
| Modelo de rede | Pull, só HTTPS de saída, sem SSH |
| Fonte da verdade | Backend (agente sobrescreve o `.conf` local) |
| Cripto de segredos | Modelo A (assimétrico) com `age`, só campos de senha |
| Onde cifra | No backend (por enquanto) |
| Recuperação | 7b, dois destinatários, chave de recuperação no 1Password |
| Ferramenta de recuperação | CLI offline; chave nunca toca o servidor |
| Assinatura de update | `minisign`, chave no 1Password |
| Update | Updater burro + assinatura + canary + rollback |
| Heartbeat | Sim, 5–15 min |
| Frontend | React (SPA) |
| Agente | Python, arquivo único, mesma pasta do `bkp.py` |
| systemd | `service` (heartbeat/pull) + `timer` (backup) |
| Hospedagem | Docker Compose na VPS, nginx TLS |
| Backup do backend | Script `pg_dump` com envio para fora |
| Token de instalação | Efêmero/uso único, trocado por permanente |
| Inventário | Recebe e guarda no v1; análise na fase 2 |

---

## 16. Pendências (a resolver no desenvolvimento)

- **Restore do backend:** definir e testar o procedimento (marcado para o final do projeto).
- **Formato exato do config cifrado** que o `GET /config` devolve (como os campos `age`
  ficam embutidos no JSON — ex.: valor `age:...` vs bloco separado de segredos).
- **Como o `bkp.py` recebe a config do agente** (o agente grava o `.conf` e chama o script —
  confirmar que nada no `bkp.py` precisa mudar, ou mapear o mínimo que muda).
- **Detalhe do rollout/canary** no dashboard (grupos, quantos dias de "quarentena").
- **Retenção/limpeza** de `runs` e `inventarios` antigos no Postgres (o banco cresce).