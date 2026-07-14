import React, { useState } from 'react'
import { useFetch } from '../hooks.js'
import { C, Empty, ErroMsg, fmtDate, fmtDur, mono, Row, runStatusMeta, Table } from '../ui.jsx'

const COLS = '1.2fr 1fr 0.8fr 1fr 0.8fr 0.8fr'
const FILTERS = [
  { id: 'all', label: 'Todos' },
  { id: 'sucesso', label: 'OK' },
  { id: 'parcial', label: 'Atenção' },
  { id: 'falha', label: 'Erro' },
]

export default function Runs() {
  const { data, erro } = useFetch('/admin/runs?limit=200', { pollMs: 20000 })
  const [filtro, setFiltro] = useState('all')
  const runs = (data || []).filter((r) => filtro === 'all' || r.status === filtro)

  return (
    <div>
      <div style={{ fontSize: 21, fontWeight: 700, marginBottom: 6 }}>Execuções</div>
      <div style={{ fontSize: 13, color: C.muted, marginBottom: 18 }}>Histórico consolidado de todos os clientes</div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {FILTERS.map((f) => {
          const active = filtro === f.id
          return (
            <div key={f.id} onClick={() => setFiltro(f.id)}
              style={{ fontSize: 12, padding: '7px 14px', borderRadius: 20, cursor: 'pointer', fontWeight: 600, color: active ? C.bg : C.muted, background: active ? C.green : 'transparent', border: `1px solid ${active ? C.green : C.inputLine}` }}>
              {f.label}
            </div>
          )
        })}
      </div>

      <Table cols={COLS} head={['Cliente', 'Data', 'Status', 'Jobs', 'Duração', 'Versão']}>
        {runs.map((r) => {
          const m = runStatusMeta(r.status)
          return (
            <Row key={r.id} cols={COLS}>
              <div style={{ color: C.fg, fontWeight: 600 }}>{r.cliente || '—'}</div>
              <div style={{ color: C.soft, fontFamily: mono }}>{fmtDate(r.data)}</div>
              <div style={{ color: m.color, fontFamily: mono }}>{m.label}</div>
              <div style={{ color: C.muted, fontFamily: mono }}>{r.jobs_ok ?? '?'}/{r.total_jobs ?? '?'}</div>
              <div style={{ color: C.muted, fontFamily: mono }}>{fmtDur(r.duracao_seg)}</div>
              <div style={{ color: C.muted, fontFamily: mono }}>{r.versao_script || '—'}</div>
            </Row>
          )
        })}
        {data && runs.length === 0 && <Empty>Nenhuma execução.</Empty>}
        <ErroMsg msg={erro} />
      </Table>
    </div>
  )
}
