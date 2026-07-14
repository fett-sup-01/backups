import React, { useState } from 'react'
import { api } from '../api.js'
import { useFetch } from '../hooks.js'
import { Btn, C, Empty, ErroMsg, Input, Label, Modal, mono, Row, Select, Table, TextArea } from '../ui.jsx'

const VER_COLS = '0.7fr 1fr 0.8fr 0.7fr 1fr 0.7fr'
const APL_COLS = '1.4fr 0.8fr 0.8fr 1fr'

function parseVer(v) {
  return String(v || '0').split('.').map((p) => parseInt(p.replace(/\D/g, ''), 10) || 0)
}
function maior(a, b) {
  const A = parseVer(a), B = parseVer(b)
  for (let i = 0; i < Math.max(A.length, B.length); i++) {
    if ((A[i] || 0) !== (B[i] || 0)) return (A[i] || 0) > (B[i] || 0)
  }
  return false
}
function grupoStatus(g) {
  return g === 'geral'
    ? { label: 'estável', color: C.green }
    : { label: 'em teste (canary)', color: C.amber }
}

// alvo do cliente: maior versao aplicavel (geral, ou canary se ele for canary) e mais nova
function alvoDe(cliente, updates) {
  const aplicaveis = updates.filter((u) => u.grupo_rollout === 'geral' || (u.grupo_rollout === 'canary' && cliente.canary))
  let alvo = cliente.versao_script || null
  for (const u of aplicaveis) if (maior(u.versao, alvo || '0')) alvo = u.versao
  return alvo
}

export default function Updates() {
  const ups = useFetch('/admin/updates', { pollMs: 20000 })
  const cli = useFetch('/admin/clientes', { pollMs: 20000 })
  const [novo, setNovo] = useState(false)
  const [erro, setErro] = useState(null)
  const updates = ups.data || []
  const clientes = cli.data || []

  async function promover(versao) {
    setErro(null)
    try { await api('POST', `/admin/updates/${versao}/promover`); ups.reload(); cli.reload() }
    catch (e) { setErro(e.message) }
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
        <div style={{ fontSize: 21, fontWeight: 700 }}>Atualizações do bkp.py</div>
        <Btn onClick={() => setNovo(true)}>+ Registrar versão</Btn>
      </div>
      <div style={{ fontSize: 13, color: C.muted, marginBottom: 18 }}>
        Assinatura minisign verificada no agente antes de aplicar · rollout por grupo (canary → geral)
      </div>
      <ErroMsg msg={erro || ups.erro} />

      <Table cols={VER_COLS} head={['Versão', 'Assinatura', 'Grupo', 'Clientes', 'Status', '']}>
        {updates.map((v) => {
          const st = grupoStatus(v.grupo_rollout)
          return (
            <Row key={v.versao} cols={VER_COLS}>
              <div style={{ fontFamily: mono, fontWeight: 700 }}>{v.versao}</div>
              <div style={{ color: C.green, fontFamily: mono, fontSize: 12 }}>✓ minisign ok</div>
              <div style={{ color: C.muted }}>{v.grupo_rollout}</div>
              <div style={{ fontFamily: mono, color: C.muted }}>{v.clientes_count}</div>
              <div style={{ color: st.color, fontWeight: 600 }}>{st.label}</div>
              {v.grupo_rollout === 'canary'
                ? <div onClick={() => promover(v.versao)} className="link" style={{ fontSize: 11.5, color: C.muted, cursor: 'pointer', textAlign: 'right' }}>promover →</div>
                : <div />}
            </Row>
          )
        })}
        {ups.data && updates.length === 0 && <Empty>Nenhuma versão registrada.</Empty>}
      </Table>

      <div style={{ fontSize: 13.5, fontWeight: 700, margin: '24px 0 12px' }}>Versão aplicada por cliente</div>
      <Table cols={APL_COLS} head={['Cliente', 'Aplicada', 'Alvo', 'Situação']}>
        {clientes.map((c) => {
          const alvo = alvoDe(c, updates)
          const emDia = !alvo || alvo === (c.versao_script || null)
          return (
            <Row key={c.nome} cols={APL_COLS}>
              <div style={{ fontWeight: 600 }}>{c.nome}</div>
              <div style={{ fontFamily: mono, color: C.muted }}>{c.versao_script || '—'}</div>
              <div style={{ fontFamily: mono, color: C.muted }}>{alvo || '—'}</div>
              <div style={{ color: emDia ? C.green : C.amber }}>{emDia ? 'Em dia' : 'Aguardando pull'}</div>
            </Row>
          )
        })}
        {cli.data && clientes.length === 0 && <Empty>Sem clientes.</Empty>}
      </Table>

      {novo && <RegistrarVersao onClose={() => setNovo(false)} onSalvo={() => { ups.reload(); setNovo(false) }} />}
    </div>
  )
}

function RegistrarVersao({ onClose, onSalvo }) {
  const [versao, setVersao] = useState('')
  const [conteudo, setConteudo] = useState('')
  const [assinatura, setAssinatura] = useState('')
  const [grupo, setGrupo] = useState('canary')
  const [erro, setErro] = useState(null)

  async function salvar() {
    setErro(null)
    try { await api('POST', '/admin/updates', { versao, conteudo, assinatura, grupo_rollout: grupo }); onSalvo() }
    catch (e) { setErro(e.message) }
  }
  return (
    <Modal title="Registrar versão do bkp.py" onClose={onClose} width={640}>
      <div style={{ fontSize: 12, color: C.muted, marginBottom: 8 }}>
        Assine offline com minisign (chave no 1Password). Cole o conteúdo e a assinatura (.minisig).
      </div>
      <div style={{ display: 'flex', gap: 10 }}>
        <Input placeholder="versão, ex: 1.1" value={versao} onChange={(e) => setVersao(e.target.value)} />
        <Select value={grupo} onChange={(e) => setGrupo(e.target.value)} style={{ width: 160 }}>
          <option value="canary">canary</option>
          <option value="geral">geral</option>
        </Select>
      </div>
      <Label>backup.py (conteúdo)</Label>
      <TextArea rows={8} value={conteudo} onChange={(e) => setConteudo(e.target.value)} />
      <Label>Assinatura minisign (.minisig)</Label>
      <TextArea rows={4} value={assinatura} onChange={(e) => setAssinatura(e.target.value)} />
      <div style={{ marginTop: 12 }}><Btn onClick={salvar}>Registrar</Btn></div>
      <ErroMsg msg={erro} />
    </Modal>
  )
}
