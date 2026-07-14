import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import { useFetch } from '../hooks.js'
import { Btn, C, ErroMsg, Input, mono, OkMsg } from '../ui.jsx'

function Campo({ label, hint, value, onChange }) {
  return (
    <div>
      <div style={{ fontSize: 12.5, color: C.fg, marginBottom: 4 }}>{label}</div>
      <Input type="number" min="0" value={value} onChange={(e) => onChange(e.target.value)} />
      {hint && <div style={{ fontSize: 11.5, color: C.dim, marginTop: 4 }}>{hint}</div>}
    </div>
  )
}

export default function Settings() {
  const { data, erro, reload } = useFetch('/admin/retencao')
  const [f, setF] = useState(null)
  const [msg, setMsg] = useState(null)
  const [err, setErr] = useState(null)
  const preview = data && data.preview

  useEffect(() => {
    if (data && data.config) setF({ ...data.config })
  }, [data])

  if (!f) return <div style={{ color: C.muted }}>Carregando…</div>

  const set = (k) => (v) => setF({ ...f, [k]: v })

  async function salvar() {
    setMsg(null); setErr(null)
    const body = {
      runs_reter_dias: +f.runs_reter_dias,
      inventarios_reter_dias: +f.inventarios_reter_dias,
      min_por_cliente: +f.min_por_cliente,
      auto_limpeza: !!f.auto_limpeza,
      intervalo_horas: +f.intervalo_horas,
    }
    try { await api('PUT', '/admin/retencao', body); setMsg('Política salva.'); reload() }
    catch (e) { setErr(e.message) }
  }
  async function limpar() {
    setMsg(null); setErr(null)
    try {
      const r = await api('POST', '/admin/retencao/limpar')
      setMsg(`Limpeza executada: ${r.runs_removidos} run(s) e ${r.inventarios_removidos} inventário(s) removidos.`)
      reload()
    } catch (e) { setErr(e.message) }
  }

  return (
    <div>
      <div style={{ fontSize: 21, fontWeight: 700, marginBottom: 6 }}>Configurações</div>
      <div style={{ fontSize: 13, color: C.muted, marginBottom: 18 }}>Retenção e limpeza do histórico no banco</div>

      <div style={{ background: C.card, border: `1px solid ${C.line}`, borderRadius: 12, padding: '20px 22px', maxWidth: 720 }}>
        <div style={{ fontSize: 13.5, fontWeight: 700, marginBottom: 4 }}>Retenção de execuções e inventário</div>
        <div style={{ fontSize: 12.5, color: C.muted, marginBottom: 16 }}>
          Registros mais antigos que o limite são apagados — mas as N execuções mais recentes de
          cada cliente são <b>sempre preservadas</b>, para o histórico não sumir de um cliente ocioso.
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 16 }}>
          <Campo label="Reter execuções (dias)" hint="apaga runs mais velhos que isso" value={f.runs_reter_dias} onChange={set('runs_reter_dias')} />
          <Campo label="Reter inventários (dias)" hint="apaga inventários mais velhos que isso" value={f.inventarios_reter_dias} onChange={set('inventarios_reter_dias')} />
          <Campo label="Mínimo por cliente" hint="nunca apaga as N rodadas mais recentes de cada cliente" value={f.min_por_cliente} onChange={set('min_por_cliente')} />
          <Campo label="Intervalo automático (horas)" hint="frequência da limpeza automática" value={f.intervalo_horas} onChange={set('intervalo_horas')} />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 16 }}>
          <div onClick={() => setF({ ...f, auto_limpeza: !f.auto_limpeza })} style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 40, height: 22, borderRadius: 20, background: f.auto_limpeza ? C.greenBg : C.inputBg, border: `1px solid ${f.auto_limpeza ? C.green : C.inputLine}`, position: 'relative', transition: 'all .15s' }}>
              <div style={{ position: 'absolute', top: 2, left: f.auto_limpeza ? 20 : 2, width: 16, height: 16, borderRadius: '50%', background: f.auto_limpeza ? C.green : C.dim, transition: 'all .15s' }} />
            </div>
            <span style={{ fontSize: 13 }}>Limpeza automática {f.auto_limpeza ? 'ligada' : 'desligada'}</span>
          </div>
        </div>

        <div style={{ marginTop: 18, padding: '12px 14px', background: C.inputBg, border: `1px solid ${C.line}`, borderRadius: 8, fontSize: 12.5, color: C.muted, fontFamily: mono }}>
          {preview
            ? <>agora seriam removidos: <span style={{ color: preview.runs ? C.amber : C.muted }}>{preview.runs}</span> run(s) · <span style={{ color: preview.inventarios ? C.amber : C.muted }}>{preview.inventarios}</span> inventário(s)</>
            : '…'}
          {data && data.config && data.config.ultima_limpeza &&
            <div style={{ marginTop: 4 }}>última limpeza: {new Date(data.config.ultima_limpeza).toLocaleString('pt-BR')}</div>}
        </div>

        <div style={{ display: 'flex', gap: 10, marginTop: 18 }}>
          <Btn onClick={salvar}>Salvar política</Btn>
          <Btn kind="outline" onClick={limpar}>Limpar agora</Btn>
        </div>
        <OkMsg msg={msg} /><ErroMsg msg={err || erro} />
      </div>
    </div>
  )
}
