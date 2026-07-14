import React from 'react'

// ------------------------------------------------------------------ tokens
export const C = {
  bg: '#0a0d12', side: '#0d1119', card: '#11151c', line: '#1b212b', line2: '#161b23',
  inputBg: '#0d1119', inputLine: '#232a35',
  fg: '#e6e9ef', muted: '#8b93a1', dim: '#5b6472', soft: '#c3cad6',
  green: '#22c55e', greenBg: '#16351f', amber: '#f59e0b', red: '#ef4444', gray: '#5b6472',
}
export const mono = "'JetBrains Mono', ui-monospace, monospace"

// ------------------------------------------------------------------ mapeamentos
export function statusMeta(s) {
  switch (s) {
    case 'ok': return { color: C.green, label: 'Operacional', bg: 'rgba(34,197,94,0.14)' }
    case 'warning': return { color: C.amber, label: 'Atenção', bg: 'rgba(245,158,11,0.14)' }
    case 'error': return { color: C.red, label: 'Erro', bg: 'rgba(239,68,68,0.14)' }
    case 'offline': return { color: C.gray, label: 'Offline', bg: 'rgba(91,100,114,0.14)' }
    default: return { color: C.gray, label: s || '—', bg: 'rgba(91,100,114,0.14)' }
  }
}
export function runStatusMeta(s) {
  if (s === 'sucesso') return { color: C.green, label: 'sucesso' }
  if (s === 'parcial') return { color: C.amber, label: 'parcial' }
  if (s === 'falha') return { color: C.red, label: 'falha' }
  return { color: C.gray, label: s || '—' }
}
export function hdColor(p) { return p >= 85 ? C.red : p >= 65 ? C.amber : C.green }

// deriva o status de exibicao (ok/warning/error/offline) a partir de heartbeat + ultimo run
export function deriveStatus(c) {
  if (!c.ultimo_heartbeat) return 'offline'
  const ageMin = (Date.now() - new Date(c.ultimo_heartbeat).getTime()) / 60000
  if (ageMin > 30) return 'offline'
  const rs = c.ultimo_run && c.ultimo_run.status
  if (rs === 'falha') return 'error'
  if (rs === 'parcial') return 'warning'
  return 'ok'
}

// ------------------------------------------------------------------ formatacao
export function relTime(iso) {
  if (!iso) return '—'
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (isNaN(s)) return '—'
  if (s < 45) return 'agora'
  if (s < 3600) return Math.floor(s / 60) + ' min atrás'
  if (s < 86400) return Math.floor(s / 3600) + ' h atrás'
  return Math.floor(s / 86400) + ' d atrás'
}
export function fmtDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d)) return iso
  return d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}
export function fmtDur(sec) {
  if (sec == null) return '—'
  return sec < 60 ? sec + 's' : Math.round(sec / 60) + 'min'
}

// ------------------------------------------------------------------ componentes
export function Card({ children, style, className, onClick }) {
  return (
    <div className={className}
      onClick={onClick}
      style={{ background: C.card, border: `1px solid ${C.line}`, borderRadius: 12, ...style }}>
      {children}
    </div>
  )
}

export function Dot({ color, size = 9 }) {
  return <div style={{ width: size, height: size, borderRadius: '50%', background: color, boxShadow: `0 0 6px ${color}`, flexShrink: 0 }} />
}

export function Pill({ color, bg, children }) {
  return <span style={{ fontSize: 11, padding: '3px 9px', borderRadius: 20, fontWeight: 600, color, background: bg }}>{children}</span>
}

export function StatCard({ label, value, color }) {
  return (
    <div style={{ background: C.card, border: `1px solid ${C.line}`, borderRadius: 10, padding: '16px 18px' }}>
      <div style={{ fontSize: 12, color: C.muted, marginBottom: 8 }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 700, fontFamily: mono, color: color || C.fg }}>{value}</div>
    </div>
  )
}

export function HDBar({ pct }) {
  if (pct == null) return <span style={{ color: C.dim, fontFamily: mono, fontSize: 12 }}>—</span>
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ flex: 1, height: 6, borderRadius: 3, background: C.line, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: pct + '%', background: hdColor(pct) }} />
      </div>
      <div style={{ fontSize: 11.5, color: C.muted, fontFamily: mono, width: 30 }}>{pct}%</div>
    </div>
  )
}

export function Btn({ children, onClick, kind = 'primary', style, type = 'button', disabled = false }) {
  const base = { fontSize: 12.5, padding: '9px 16px', borderRadius: 8, cursor: 'pointer', fontWeight: 600, border: '1px solid transparent' }
  const kinds = {
    primary: { background: C.greenBg, border: `1px solid ${C.green}`, color: C.green },
    outline: { background: '#161c26', border: `1px solid ${C.inputLine}`, color: C.fg },
    ghost: { background: 'transparent', border: `1px solid ${C.inputLine}`, color: C.muted },
    danger: { background: 'transparent', border: `1px solid ${C.red}`, color: C.red },
  }
  const off = disabled ? { opacity: 0.45, cursor: 'not-allowed' } : {}
  const cls = disabled ? '' : (kind === 'outline' ? 'btn btn-outline' : 'btn')
  return <button type={type} className={cls} onClick={onClick} disabled={disabled} style={{ ...base, ...kinds[kind], ...off, ...style }}>{children}</button>
}

const inputStyle = {
  background: C.inputBg, color: C.fg, border: `1px solid ${C.inputLine}`,
  borderRadius: 8, padding: '9px 12px', fontSize: 12.5, width: '100%',
}
export function Input(props) { return <input {...props} style={{ ...inputStyle, ...(props.style || {}) }} /> }
export function TextArea(props) {
  return <textarea {...props} style={{ ...inputStyle, fontFamily: mono, resize: 'vertical', ...(props.style || {}) }} />
}
export function Select({ children, ...rest }) { return <select {...rest} style={{ ...inputStyle, ...(rest.style || {}) }}>{children}</select> }
export function Label({ children }) {
  return <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.05em', color: C.dim, margin: '12px 0 6px' }}>{children}</div>
}

export function Modal({ title, onClose, children, width = 520 }) {
  return (
    <div onClick={onClose}
      style={{ position: 'fixed', inset: 0, background: 'rgba(3,5,9,0.72)', display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '8vh 16px', zIndex: 50 }}>
      <div onClick={(e) => e.stopPropagation()}
        style={{ width, maxWidth: '100%', maxHeight: '84vh', overflowY: 'auto', background: C.card, border: `1px solid ${C.line}`, borderRadius: 14, padding: '20px 22px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <div style={{ fontSize: 15, fontWeight: 700 }}>{title}</div>
          <div onClick={onClose} className="link" style={{ cursor: 'pointer', color: C.muted, fontSize: 18 }}>×</div>
        </div>
        {children}
      </div>
    </div>
  )
}

// cabecalho de tabela (grid) + wrapper
export function Table({ cols, head, children }) {
  return (
    <Card style={{ overflow: 'hidden' }}>
      <div style={{ display: 'grid', gridTemplateColumns: cols, gap: 10, padding: '12px 20px', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.05em', color: C.dim, borderBottom: `1px solid ${C.line}` }}>
        {head.map((h, i) => <div key={i}>{h}</div>)}
      </div>
      {children}
    </Card>
  )
}
export function Row({ cols, children, onClick, clickable }) {
  return (
    <div className={clickable ? 'row' : undefined} onClick={onClick}
      style={{ display: 'grid', gridTemplateColumns: cols, gap: 10, alignItems: 'center', padding: '12px 20px', borderBottom: `1px solid ${C.line2}`, fontSize: 12.5, cursor: clickable ? 'pointer' : 'default' }}>
      {children}
    </div>
  )
}
export function Empty({ children }) {
  return <div style={{ padding: '18px 20px', color: C.dim, fontSize: 13 }}>{children}</div>
}
export function ErroMsg({ msg }) { return msg ? <div style={{ color: C.red, fontSize: 12.5, marginTop: 10 }}>{msg}</div> : null }
export function OkMsg({ msg }) { return msg ? <div style={{ color: C.green, fontSize: 12.5, marginTop: 10 }}>{msg}</div> : null }
