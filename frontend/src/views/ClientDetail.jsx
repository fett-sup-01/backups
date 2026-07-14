import React, { useState } from 'react'
import { api } from '../api.js'
import { useFetch } from '../hooks.js'
import {
  Btn, C, Dot, ErroMsg, Label, Modal, mono, OkMsg, Row, Table, Empty,
  deriveStatus, fmtDate, fmtDur, hdColor, relTime, runStatusMeta, statusMeta,
} from '../ui.jsx'
import ConfigEditor from './ConfigEditor.jsx'

const RUN_COLS = '1fr 0.7fr 1fr 0.8fr 0.8fr'
const SPARK_H = { sucesso: 90, parcial: 55, falha: 30 }

export default function ClientDetail({ nome, onBack }) {
  const det = useFetch(`/admin/clientes/${nome}`)
  const cfg = useFetch(`/admin/clientes/${nome}/config`)
  const runs = useFetch(`/admin/clientes/${nome}/runs?limit=10`)
  const [editar, setEditar] = useState(false)
  const [confirmar, setConfirmar] = useState(false)
  const [msg, setMsg] = useState(null)
  const [erro, setErro] = useState(null)

  const d = det.data
  const runList = runs.data || []
  const ultimoRun = runList[0] || null
  const status = deriveStatus({ ultimo_heartbeat: d && d.ultimo_heartbeat, ultimo_run: ultimoRun })
  const sm = statusMeta(status)
  const hd = ultimoRun ? ultimoRun.uso_pct : null
  const conteudo = cfg.data && cfg.data.conteudo

  async function comando(tipo, label) {
    setMsg(null); setErro(null)
    try { await api('POST', `/admin/clientes/${nome}/comandos?tipo=${tipo}`); setMsg(`Comando “${label}” enfileirado — entregue no próximo heartbeat.`) }
    catch (e) { setErro(e.message) }
  }
  async function toggleCanary() {
    setMsg(null); setErro(null)
    try { await api('POST', `/admin/clientes/${nome}/canary?ativo=${!d.canary}`); det.reload() }
    catch (e) { setErro(e.message) }
  }
  async function remover() {
    setErro(null)
    try { await api('DELETE', `/admin/clientes/${nome}`); onBack() }
    catch (e) { setErro(e.message); setConfirmar(false) }
  }

  const spark = runList.slice(0, 7).reverse()

  return (
    <div>
      <div onClick={onBack} className="link" style={{ display: 'inline-flex', gap: 6, fontSize: 12.5, color: C.muted, cursor: 'pointer', marginBottom: 16 }}>← Clientes</div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 22 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <Dot color={sm.color} size={14} />
          <div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>{nome}</div>
            <div style={{ fontSize: 12.5, color: sm.color, marginTop: 2 }}>
              {sm.label}{d && d.plataforma ? ' · ' + (d.plataforma === 'windows' ? 'Windows' : 'Linux') : ''}{d && d.canary ? ' · canary' : ''}
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <Btn kind="outline" onClick={() => comando('rodar_agora', 'rodar agora')}>Rodar agora</Btn>
          <Btn kind="outline" onClick={() => comando('check', '--check')}>--check</Btn>
          <Btn kind="ghost" onClick={toggleCanary}>{d && d.canary ? 'Sair do canary' : 'Marcar canary'}</Btn>
          <Btn onClick={() => setEditar(true)}>Editar config</Btn>
          <Btn kind="danger" onClick={() => setConfirmar(true)}>Remover</Btn>
        </div>
      </div>
      <OkMsg msg={msg} /><ErroMsg msg={det.erro || erro} />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 14, margin: '14px 0 22px' }}>
        <MiniCard label="Heartbeat" value={relTime(d && d.ultimo_heartbeat)} />
        <MiniCard label="Uso do HD" value={hd == null ? '—' : hd + '%'} color={hd == null ? C.fg : hdColor(hd)} />
        <MiniCard label="Versão bkp.py" value={(d && d.versao_script) || '—'} />
        <MiniCard label="Config" value={cfg.data ? (cfg.data.versao == null ? 'Sem config' : 'v' + cfg.data.versao) : '…'} color={C.soft} small />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.1fr 0.9fr', gap: 16, marginBottom: 22 }}>
        <div style={{ background: C.card, border: `1px solid ${C.line}`, borderRadius: 12, padding: '18px 20px' }}>
          <div style={{ fontSize: 13.5, fontWeight: 700, marginBottom: 6 }}>Configuração</div>
          {!conteudo ? <Empty>Sem config salva. Use “Editar config”.</Empty> : (
            <>
              <Label>Destino</Label>
              <div style={{ fontFamily: mono, fontSize: 12.5, color: C.soft, background: C.inputBg, border: `1px solid ${C.line}`, borderRadius: 8, padding: '10px 12px', marginBottom: 6 }}>
                tipo: {conteudo.destino?.tipo || '—'} · rotulo: {conteudo.destino?.rotulo || conteudo.destino?.padrao_rotulo || '—'}<br />
                montar_em: {conteudo.destino?.montar_em || '—'} · dias_rotacao: {conteudo.destino?.dias_rotacao ?? 7}
              </div>
              <Label>Montagens</Label>
              {(conteudo.montagens || []).map((m, i) => (
                <div key={i} style={{ fontFamily: mono, fontSize: 12, color: C.muted, padding: '7px 0', borderBottom: `1px solid ${C.line2}` }}>
                  <span style={{ color: C.fg }}>{m.tipo}</span> · {m.origem} → {m.ponto}
                </div>
              ))}
              {(conteudo.montagens || []).length === 0 && <div style={{ color: C.dim, fontSize: 12 }}>—</div>}
              <Label>Cópias</Label>
              {(conteudo.copias || []).map((cp, i) => (
                <div key={i} style={{ fontFamily: mono, fontSize: 12, color: C.muted, padding: '7px 0', borderBottom: `1px solid ${C.line2}` }}>
                  <span style={{ color: C.fg }}>{cp.nome}</span> · {cp.metodo} · {cp.origem}
                </div>
              ))}
              {(conteudo.copias || []).length === 0 && <div style={{ color: C.dim, fontSize: 12 }}>—</div>}
            </>
          )}
        </div>

        <div style={{ background: C.card, border: `1px solid ${C.line}`, borderRadius: 12, padding: '18px 20px' }}>
          <div style={{ fontSize: 13.5, fontWeight: 700, marginBottom: 14 }}>Últimas execuções</div>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 6, height: 70, marginBottom: 6 }}>
            {spark.map((r, i) => {
              const m = runStatusMeta(r.status)
              return <div key={i} title={`${fmtDate(r.data)} · ${r.status}`} style={{ flex: 1, height: (SPARK_H[r.status] || 40) + '%', background: m.color, borderRadius: '3px 3px 0 0', minHeight: 6 }} />
            })}
            {spark.length === 0 && <div style={{ color: C.dim, fontSize: 12 }}>sem execuções ainda</div>}
          </div>
          <div style={{ fontSize: 11, color: C.dim, textAlign: 'center' }}>últimas {spark.length || 0} rodadas</div>
        </div>
      </div>

      <Table cols={RUN_COLS} head={['Data', 'Status', 'Jobs', 'Duração', 'Versão aplicada']}>
        {runList.map((r) => {
          const m = runStatusMeta(r.status)
          return (
            <Row key={r.id} cols={RUN_COLS}>
              <div style={{ color: C.soft, fontFamily: mono }}>{fmtDate(r.data)}</div>
              <div style={{ color: m.color, fontFamily: mono }}>{m.label}</div>
              <div style={{ color: C.muted, fontFamily: mono }}>{r.jobs_ok ?? '?'}/{r.total_jobs ?? '?'}</div>
              <div style={{ color: C.muted, fontFamily: mono }}>{fmtDur(r.duracao_seg)}</div>
              <div style={{ color: C.muted, fontFamily: mono }}>{r.versao_config == null ? '—' : 'v' + r.versao_config}</div>
            </Row>
          )
        })}
        {runs.data && runList.length === 0 && <Empty>Nenhuma execução reportada.</Empty>}
      </Table>

      {editar && (
        <ConfigEditor nome={nome} plataforma={(d && d.plataforma) || 'linux'} initial={conteudo} onClose={() => setEditar(false)}
          onSaved={() => { cfg.reload(); det.reload(); setEditar(false); setMsg('Config salva — o cliente aplica no próximo pull.') }} />
      )}

      {confirmar && (
        <Modal title="Remover cliente" onClose={() => setConfirmar(false)} width={440}>
          <div style={{ fontSize: 13, color: C.soft, lineHeight: 1.5 }}>
            Isto apaga <b>{nome}</b> e todo o histórico (config, execuções, inventário,
            segredos e comandos). Não dá para desfazer.
          </div>
          <div style={{ display: 'flex', gap: 10, marginTop: 18 }}>
            <Btn kind="danger" onClick={remover}>Excluir definitivamente</Btn>
            <Btn kind="ghost" onClick={() => setConfirmar(false)}>Cancelar</Btn>
          </div>
        </Modal>
      )}
    </div>
  )
}

function MiniCard({ label, value, color, small }) {
  return (
    <div style={{ background: C.card, border: `1px solid ${C.line}`, borderRadius: 10, padding: '14px 16px' }}>
      <div style={{ fontSize: 11.5, color: C.muted, marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: small ? 14 : 16, fontWeight: 600, fontFamily: small ? 'inherit' : mono, color: color || C.fg }}>{value}</div>
    </div>
  )
}
