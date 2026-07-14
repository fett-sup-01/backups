import React, { useState } from 'react'
import { api } from '../api.js'
import { useFetch } from '../hooks.js'
import {
  Btn, C, Dot, ErroMsg, Input, Modal, mono, Pill, Row, StatCard, Table, Empty,
  deriveStatus, fmtDate, relTime, runStatusMeta, statusMeta,
} from '../ui.jsx'

const COLS = '1.8fr 0.8fr 0.7fr 1.2fr 0.9fr 0.7fr 0.4fr'

function configPill(c) {
  if (c.config_versao == null) return <Pill color={C.gray} bg="rgba(91,100,114,0.14)">Sem config</Pill>
  return c.config_pendente
    ? <Pill color={C.amber} bg="rgba(245,158,11,0.14)">Pendente</Pill>
    : <Pill color={C.green} bg="rgba(34,197,94,0.14)">Aplicada</Pill>
}

function OsPick({ value, onChange }) {
  const opt = (id, label, sub) => (
    <div onClick={() => onChange(id)} style={{ flex: 1, cursor: 'pointer', textAlign: 'center', padding: '12px 8px', borderRadius: 10, border: `1px solid ${value === id ? C.green : C.inputLine}`, background: value === id ? C.greenBg : C.inputBg }}>
      <div style={{ fontSize: 14, fontWeight: 700, color: value === id ? C.green : C.fg }}>{label}</div>
      <div style={{ fontSize: 11, color: C.dim, marginTop: 2 }}>{sub}</div>
    </div>
  )
  return <div style={{ display: 'flex', gap: 10, margin: '4px 0 14px' }}>{opt('linux', 'Linux', 'instala por bash')}{opt('windows', 'Windows', 'instala por PowerShell')}</div>
}

function NovoCliente({ onClose, onCriado }) {
  const [nome, setNome] = useState('')
  const [plataforma, setPlataforma] = useState('linux')
  const [erro, setErro] = useState(null)
  const [res, setRes] = useState(null)
  async function criar(e) {
    e.preventDefault(); setErro(null)
    const n = nome.trim()
    if (!n) { setErro('informe um nome'); return }
    try { setRes(await api('POST', '/admin/clientes', { nome: n, plataforma })); onCriado() }
    catch (e) { setErro(e.message) }
  }
  const origin = window.location.origin
  return (
    <Modal title="Novo cliente" onClose={onClose}>
      {!res ? (
        <form onSubmit={criar}>
          <div style={{ fontSize: 12.5, color: C.muted, marginBottom: 10 }}>
            Cria o cliente e gera um token de enrollment de uso único (doc §11). Nome
            obrigatório e único — é como você identifica a máquina.
          </div>
          <div style={{ fontSize: 12, color: C.muted, marginBottom: 4 }}>Sistema operacional</div>
          <OsPick value={plataforma} onChange={setPlataforma} />
          <Input placeholder="nome do cliente" value={nome} onChange={(e) => setNome(e.target.value)} autoFocus />
          <div style={{ marginTop: 14 }}><Btn type="submit" disabled={!nome.trim()}>Criar + gerar token</Btn></div>
          <ErroMsg msg={erro} />
        </form>
      ) : (
        <div>
          <div style={{ fontSize: 12.5, color: C.muted, marginBottom: 8 }}>
            Cliente <b>{res.plataforma === 'windows' ? 'Windows' : 'Linux'}</b> · token de enrollment
            (uso único, expira {fmtDate(res.expira_em)}). Rode na máquina do cliente:
          </div>
          {res.plataforma === 'windows' ? (
            <>
              <div style={{ fontSize: 11.5, color: C.dim, marginBottom: 4 }}>PowerShell (como Administrador):</div>
              <div style={{ fontFamily: mono, fontSize: 12, background: C.inputBg, border: `1px solid ${C.line}`, borderRadius: 8, padding: 12, wordBreak: 'break-all', color: C.soft }}>
                $env:BACKEND=&apos;{origin}&apos;; $env:TOKEN=&apos;{res.enrollment_token}&apos;; irm {origin}/install.ps1 | iex
              </div>
            </>
          ) : (
            <>
              <div style={{ fontSize: 11.5, color: C.dim, marginBottom: 4 }}>Terminal (root):</div>
              <div style={{ fontFamily: mono, fontSize: 12, background: C.inputBg, border: `1px solid ${C.line}`, borderRadius: 8, padding: 12, wordBreak: 'break-all', color: C.soft }}>
                curl -fsSL {origin}/install.sh | sudo bash -s -- --backend {origin} --token {res.enrollment_token}
              </div>
            </>
          )}
          <div style={{ marginTop: 14 }}><Btn kind="outline" onClick={onClose}>Fechar</Btn></div>
        </div>
      )}
    </Modal>
  )
}

export default function Clientes({ onOpen }) {
  const { data, erro, reload } = useFetch('/admin/clientes', { pollMs: 15000 })
  const [novo, setNovo] = useState(false)
  const clients = data || []

  const counts = { ok: 0, warning: 0, error: 0, offline: 0 }
  clients.forEach((c) => { counts[deriveStatus(c)]++ })

  const stats = [
    { label: 'Total de clientes', value: String(clients.length), color: C.fg },
    { label: 'Operacional', value: String(counts.ok), color: C.green },
    { label: 'Atenção', value: String(counts.warning), color: C.amber },
    { label: 'Erro', value: String(counts.error), color: C.red },
    { label: 'Offline', value: String(counts.offline), color: C.gray },
  ]

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 22 }}>
        <div>
          <div style={{ fontSize: 21, fontWeight: 700 }}>Visão geral dos clientes</div>
          <div style={{ fontSize: 13, color: C.muted, marginTop: 4 }}>
            {clients.length} clientes monitorados · modelo pull, heartbeat a cada 5–15 min
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <Btn kind="ghost" onClick={reload}>Atualizar</Btn>
          <Btn onClick={() => setNovo(true)}>+ Novo cliente</Btn>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 14, marginBottom: 26 }}>
        {stats.map((s) => <StatCard key={s.label} {...s} />)}
      </div>

      <Table cols={COLS} head={['Cliente', 'Heartbeat', 'Último backup', 'Uso do HD', 'Config', 'Versão', '']}>
        {clients.map((c) => {
          const sm = statusMeta(deriveStatus(c))
          const rm = runStatusMeta(c.ultimo_run && c.ultimo_run.status)
          return (
            <Row key={c.nome} cols={COLS} clickable onClick={() => onOpen(c.nome)}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <Dot color={sm.color} />
                <div>
                  <div style={{ fontSize: 13.5, fontWeight: 600 }}>{c.nome}</div>
                  <div style={{ fontSize: 11, color: sm.color }}>{sm.label}</div>
                </div>
              </div>
              <div style={{ fontSize: 12.5, color: C.muted, fontFamily: mono }}>{relTime(c.ultimo_heartbeat)}</div>
              <div style={{ fontSize: 12.5, color: rm.color, fontFamily: mono }}>{c.ultimo_run ? fmtDate(c.ultimo_run.data) : '—'}</div>
              <div><HDCell pct={c.hd_uso_pct} /></div>
              <div>{configPill(c)}</div>
              <div style={{ fontSize: 12, color: C.muted, fontFamily: mono }}>{c.versao_script || '—'}</div>
              <div style={{ fontSize: 16, color: C.dim, textAlign: 'right' }}>›</div>
            </Row>
          )
        })}
        {data && clients.length === 0 && <Empty>Nenhum cliente ainda. Clique em “+ Novo cliente”.</Empty>}
        <ErroMsg msg={erro} />
      </Table>

      {novo && <NovoCliente onClose={() => setNovo(false)} onCriado={reload} />}
    </div>
  )
}

function HDCell({ pct }) {
  if (pct == null) return <span style={{ color: C.dim, fontFamily: mono, fontSize: 12 }}>—</span>
  const col = pct >= 85 ? C.red : pct >= 65 ? C.amber : C.green
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ flex: 1, height: 6, borderRadius: 3, background: C.line, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: pct + '%', background: col }} />
      </div>
      <div style={{ fontSize: 11.5, color: C.muted, fontFamily: mono, width: 30 }}>{pct}%</div>
    </div>
  )
}
