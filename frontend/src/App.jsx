import React, { useState } from 'react'
import { api, getToken, setToken } from './api.js'
import { Btn, C, ErroMsg, Input, mono } from './ui.jsx'
import Fleet from './views/Fleet.jsx'
import ClientDetail from './views/ClientDetail.jsx'
import Runs from './views/Runs.jsx'
import Commands from './views/Commands.jsx'
import Updates from './views/Updates.jsx'
import Settings from './views/Settings.jsx'

const NAV = [
  { id: 'fleet', label: 'Frota' },
  { id: 'runs', label: 'Execuções' },
  { id: 'commands', label: 'Comandos' },
  { id: 'updates', label: 'Atualizações' },
  { id: 'config', label: 'Configurações' },
]

function Login({ onLogin }) {
  const [login, setLogin] = useState('admin')
  const [senha, setSenha] = useState('')
  const [erro, setErro] = useState(null)
  async function submit(e) {
    e.preventDefault(); setErro(null)
    try {
      const r = await api('POST', '/auth/login', { login, senha })
      setToken(r.access_token); onLogin()
    } catch (e) { setErro(e.message) }
  }
  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: C.bg }}>
      <form onSubmit={submit} style={{ width: 340, background: C.card, border: `1px solid ${C.line}`, borderRadius: 14, padding: 26 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
          <div style={{ width: 30, height: 30, borderRadius: 7, background: C.greenBg, border: `1px solid ${C.green}`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ width: 10, height: 10, borderRadius: '50%', background: C.green, boxShadow: `0 0 8px ${C.green}` }} />
          </div>
          <div>
            <div style={{ fontSize: 15, fontWeight: 700 }}>Backups</div>
            <div style={{ fontSize: 11, color: C.dim, fontFamily: mono }}>Futuratec · NOC</div>
          </div>
        </div>
        <div style={{ fontSize: 11, textTransform: 'uppercase', color: C.dim, margin: '10px 0 4px' }}>Login</div>
        <Input value={login} onChange={(e) => setLogin(e.target.value)} />
        <div style={{ fontSize: 11, textTransform: 'uppercase', color: C.dim, margin: '10px 0 4px' }}>Senha</div>
        <Input type="password" value={senha} onChange={(e) => setSenha(e.target.value)} autoFocus />
        <div style={{ marginTop: 18 }}><Btn type="submit" style={{ width: '100%' }}>Entrar</Btn></div>
        <ErroMsg msg={erro} />
      </form>
    </div>
  )
}

function NavItem({ item, active, onClick }) {
  return (
    <div className="navitem" onClick={onClick}
      style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 10px', borderRadius: 8, cursor: 'pointer', fontSize: 13.5, fontWeight: active ? 700 : 500, color: active ? C.fg : C.muted, background: active ? '#161c26' : 'transparent' }}>
      <div style={{ width: 7, height: 7, borderRadius: 2, background: active ? C.green : '#2b323d', flexShrink: 0 }} />
      {item.label}
    </div>
  )
}

export default function App() {
  const [logado, setLogado] = useState(!!getToken())
  const [view, setView] = useState('fleet')
  const [cliente, setCliente] = useState(null)

  if (!logado) return <Login onLogin={() => setLogado(true)} />

  function go(v) { setCliente(null); setView(v) }
  function sair() { setToken(null); setLogado(false) }

  const isClient = view === 'fleet' && cliente

  return (
    <div style={{ display: 'flex', height: '100vh', width: '100%', background: C.bg, color: C.fg, overflow: 'hidden' }}>
      {/* SIDEBAR */}
      <div style={{ width: 236, flexShrink: 0, background: C.side, borderRight: `1px solid ${C.line}`, display: 'flex', flexDirection: 'column', padding: '20px 14px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '4px 8px 22px' }}>
          <div style={{ width: 30, height: 30, borderRadius: 7, background: C.greenBg, border: `1px solid ${C.green}`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ width: 10, height: 10, borderRadius: '50%', background: C.green, boxShadow: `0 0 8px ${C.green}` }} />
          </div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, letterSpacing: '0.2px' }}>Backups</div>
            <div style={{ fontSize: 11, color: C.dim, fontFamily: mono }}>Futuratec · NOC</div>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginTop: 6 }}>
          {NAV.map((n) => (
            <NavItem key={n.id} item={n} active={view === n.id || (n.id === 'fleet' && view === 'fleet')} onClick={() => go(n.id)} />
          ))}
        </div>

        <div style={{ marginTop: 'auto', padding: '10px 8px', borderTop: `1px solid ${C.line}` }}>
          <div onClick={sair} className="link" style={{ fontSize: 12.5, color: C.muted, cursor: 'pointer', marginBottom: 12 }}>Sair</div>
          <div style={{ fontSize: 11, color: C.dim, fontFamily: mono, lineHeight: 1.6 }}>
            modelo pull · HTTPS saída<br />sem SSH · age + minisign
          </div>
        </div>
      </div>

      {/* MAIN */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '28px 34px 60px' }}>
        {isClient ? <ClientDetail nome={cliente} onBack={() => setCliente(null)} />
          : view === 'fleet' ? <Fleet onOpen={setCliente} />
          : view === 'runs' ? <Runs />
          : view === 'commands' ? <Commands />
          : view === 'updates' ? <Updates />
          : <Settings />}
      </div>
    </div>
  )
}
