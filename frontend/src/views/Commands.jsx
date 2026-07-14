import React, { useState } from 'react'
import { api } from '../api.js'
import { useFetch } from '../hooks.js'
import { Btn, C, Empty, ErroMsg, fmtDate, mono, Row, Select, Table } from '../ui.jsx'

const COLS = '1.2fr 1fr 1fr 1fr 0.6fr'
const TIPOS = [
  { v: 'rodar_agora', label: 'rodar agora' },
  { v: 'check', label: '--check' },
]

function estadoColor(e) {
  if (e === 'pendente') return C.amber
  if (e === 'enviado') return C.soft
  return C.dim
}

export default function Commands() {
  const cmds = useFetch('/admin/comandos', { pollMs: 10000 })
  const cli = useFetch('/admin/clientes')
  const clientes = cli.data || []
  const [nome, setNome] = useState('')
  const [tipo, setTipo] = useState('rodar_agora')
  const [erro, setErro] = useState(null)

  const alvo = nome || (clientes[0] && clientes[0].nome) || ''

  async function enfileirar() {
    setErro(null)
    if (!alvo) { setErro('sem clientes'); return }
    try { await api('POST', `/admin/clientes/${alvo}/comandos?tipo=${tipo}`); cmds.reload() }
    catch (e) { setErro(e.message) }
  }
  async function cancelar(id) {
    setErro(null)
    try { await api('DELETE', `/admin/comandos/${id}`); cmds.reload() }
    catch (e) { setErro(e.message) }
  }

  return (
    <div>
      <div style={{ fontSize: 21, fontWeight: 700, marginBottom: 6 }}>Comandos on-demand</div>
      <div style={{ fontSize: 13, color: C.muted, marginBottom: 18 }}>Fila entregue no próximo heartbeat de cada cliente</div>

      <div style={{ background: C.card, border: `1px solid ${C.line}`, borderRadius: 12, padding: '16px 20px', marginBottom: 20 }}>
        <div style={{ fontSize: 12.5, fontWeight: 600, marginBottom: 12 }}>Novo comando</div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <Select value={alvo} onChange={(e) => setNome(e.target.value)} style={{ width: 'auto', minWidth: 200 }}>
            {clientes.map((c) => <option key={c.nome} value={c.nome}>{c.nome}</option>)}
          </Select>
          <Select value={tipo} onChange={(e) => setTipo(e.target.value)} style={{ width: 'auto' }}>
            {TIPOS.map((t) => <option key={t.v} value={t.v}>{t.label}</option>)}
          </Select>
          <Btn onClick={enfileirar}>Enfileirar</Btn>
        </div>
        <ErroMsg msg={erro} />
      </div>

      <Table cols={COLS} head={['Cliente', 'Tipo', 'Status', 'Criado em', '']}>
        {(cmds.data || []).map((c) => (
          <Row key={c.id} cols={COLS}>
            <div style={{ fontWeight: 600 }}>{c.cliente}</div>
            <div style={{ fontFamily: mono, color: C.muted }}>{c.tipo}</div>
            <div style={{ color: estadoColor(c.estado) }}>{c.estado}</div>
            <div style={{ fontFamily: mono, color: C.dim }}>{fmtDate(c.criado_em)}</div>
            {c.estado === 'pendente'
              ? <div onClick={() => cancelar(c.id)} className="danger" style={{ fontSize: 11.5, color: C.muted, cursor: 'pointer', textAlign: 'right' }}>cancelar</div>
              : <div />}
          </Row>
        ))}
        {cmds.data && cmds.data.length === 0 && <Empty>Fila vazia.</Empty>}
      </Table>
    </div>
  )
}
