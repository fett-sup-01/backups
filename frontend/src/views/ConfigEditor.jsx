import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'
import { useFetch } from '../hooks.js'
import { Btn, C, ErroMsg, Input, mono, Select } from '../ui.jsx'

// ---------------------------------------------------------------- helpers de UI
function F({ label, hint, children }) {
  return (
    <div style={{ marginBottom: 12 }}>
      {label && <div style={{ fontSize: 12, color: C.muted, marginBottom: 4 }}>{label}</div>}
      {children}
      {hint && <div style={{ fontSize: 11, color: C.dim, marginTop: 3 }}>{hint}</div>}
    </div>
  )
}
function Grid({ children, cols = 2 }) {
  return <div style={{ display: 'grid', gridTemplateColumns: `repeat(${cols},1fr)`, gap: 12 }}>{children}</div>
}
function Toggle({ on, onChange, label }) {
  return (
    <div onClick={() => onChange(!on)} style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 10, margin: '4px 0 12px' }}>
      <div style={{ width: 38, height: 21, borderRadius: 20, background: on ? C.greenBg : C.inputBg, border: `1px solid ${on ? C.green : C.inputLine}`, position: 'relative' }}>
        <div style={{ position: 'absolute', top: 2, left: on ? 19 : 2, width: 15, height: 15, borderRadius: '50%', background: on ? C.green : C.dim, transition: 'left .12s' }} />
      </div>
      <span style={{ fontSize: 12.5 }}>{label}</span>
    </div>
  )
}
function Section({ title, sub, children }) {
  return (
    <div style={{ background: C.card, border: `1px solid ${C.line}`, borderRadius: 12, padding: '16px 18px', marginBottom: 14 }}>
      <div style={{ fontSize: 13.5, fontWeight: 700 }}>{title}</div>
      {sub && <div style={{ fontSize: 11.5, color: C.dim, margin: '3px 0 10px' }}>{sub}</div>}
      <div style={{ marginTop: sub ? 0 : 10 }}>{children}</div>
    </div>
  )
}
function ItemCard({ title, onRemove, children }) {
  return (
    <div style={{ background: C.inputBg, border: `1px solid ${C.line}`, borderRadius: 10, padding: '12px 14px', marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <div style={{ fontSize: 12, color: C.soft, fontWeight: 600 }}>{title}</div>
        <div onClick={onRemove} className="danger" style={{ fontSize: 11.5, color: C.muted, cursor: 'pointer' }}>remover</div>
      </div>
      {children}
    </div>
  )
}

const METODOS_LINUX = ['rsync', 'ssh-rsync', 'rsync-ssh', 'cp', 'rclone', 'tar']
const METODOS_WIN = ['robocopy', 'rclone']
const num = (v) => (v === '' || v == null ? undefined : Number(v))
const splitList = (s) => s.split(/[\n,]/).map((x) => x.trim()).filter(Boolean)

// ---------------------------------------------------------------- editor
export default function ConfigEditor({ nome, plataforma = 'linux', initial, onClose, onSaved }) {
  const win = plataforma === 'windows'
  const secretsFetch = useFetch(`/admin/clientes/${nome}/secrets`)
  const [email, setEmail] = useState('')
  const [backend, setBackend] = useState({ timeout_cmd: '', reenvio_segundos: '', reenvio_intervalo: '', log_completo: true })
  const [destino, setDestino] = useState({
    tipo: win ? 'unidade' : 'hd', modo: 'rotulo', rotulo: '', hds: [''], padrao_rotulo: '',
    unidades: ['D:'], estrategia: 'presente', montar_em: '/mnt/hd_bkp', dias_rotacao: '7', reter_logs_dias: '7',
  })
  const [montagens, setMontagens] = useState([])   // linux: montagens · windows: mapeamentos
  const [copias, setCopias] = useState([])
  const [inventario, setInventario] = useState({ ativo: true, modificados_horas: '', top_arquivos: '', top_pastas: '' })
  const [erro, setErro] = useState(null)

  useEffect(() => {
    const c = initial || {}
    setEmail(c.email || '')
    setBackend({
      timeout_cmd: c.backend?.timeout_cmd ?? '', reenvio_segundos: c.backend?.reenvio_segundos ?? '',
      reenvio_intervalo: c.backend?.reenvio_intervalo ?? '', log_completo: c.backend?.log_completo ?? true,
    })
    const d = c.destino || {}
    setDestino({
      tipo: d.tipo || (win ? 'unidade' : 'hd'),
      modo: d.hds ? 'hds' : d.padrao_rotulo ? 'padrao' : 'rotulo',
      rotulo: d.rotulo || '', hds: d.hds?.length ? d.hds : [''], padrao_rotulo: d.padrao_rotulo || '',
      unidades: d.unidades?.length ? d.unidades : ['D:'],
      estrategia: d.estrategia || 'presente', montar_em: d.montar_em || '/mnt/hd_bkp',
      dias_rotacao: d.dias_rotacao ?? '7', reter_logs_dias: d.reter_logs_dias ?? '7',
    })
    const fonte = win ? (c.mapeamentos || []) : (c.montagens || [])
    setMontagens(fonte.map((m) => ({
      tipo: m.tipo || 'smb', origem: m.origem || '', ponto: m.ponto || '',
      unc: m.unc || '', letra: m.letra || '',
      usuario: m.usuario || '', senha: '', dominio: m.dominio || '', opcoes: m.opcoes || '', temSenha: false,
    })))
    setCopias((c.copias || []).map((cp) => ({
      nome: cp.nome || '', metodo: cp.metodo || (win ? 'robocopy' : 'rsync'), origem: cp.origem || '',
      excluir: Array.isArray(cp.excluir) ? cp.excluir.join(', ') : (cp.excluir || ''),
      apagar_extras: cp.apagar_extras !== false, dias_rotacao: cp.dias_rotacao ?? '', limpeza_dias: cp.limpeza_dias ?? '',
      inventario: cp.inventario !== false, ssh_host: cp.ssh_host || '', ssh_user: cp.ssh_user || '',
      ssh_senha: '', porta: cp.porta ?? '', destino: cp.destino || '', temSenha: false,
    })))
    const inv = c.inventario || {}
    setInventario({ ativo: inv.ativo !== false, modificados_horas: inv.modificados_horas ?? '', top_arquivos: inv.top_arquivos ?? '', top_pastas: inv.top_pastas ?? '' })
  }, [initial, win])

  useEffect(() => {
    const paths = (secretsFetch.data || []).map((s) => s.campo)
    if (!paths.length) return
    const base = win ? 'mapeamentos' : 'montagens'
    setMontagens((ms) => ms.map((m, i) => (paths.includes(`${base}[${i}].senha`) ? { ...m, temSenha: true } : m)))
    setCopias((cs) => cs.map((c, i) => (paths.includes(`copias[${i}].ssh_senha`) ? { ...c, temSenha: true } : c)))
  }, [secretsFetch.data, win])

  const upM = (i, patch) => setMontagens((ms) => ms.map((m, j) => (j === i ? { ...m, ...patch } : m)))
  const upC = (i, patch) => setCopias((cs) => cs.map((c, j) => (j === i ? { ...c, ...patch } : c)))

  const { conteudo, secrets } = useMemo(() => {
    const ct = { cliente: nome, plataforma }
    if (email) ct.email = email
    const b = {}
    if (num(backend.timeout_cmd) !== undefined) b.timeout_cmd = num(backend.timeout_cmd)
    if (num(backend.reenvio_segundos) !== undefined) b.reenvio_segundos = num(backend.reenvio_segundos)
    if (num(backend.reenvio_intervalo) !== undefined) b.reenvio_intervalo = num(backend.reenvio_intervalo)
    if (backend.log_completo === false) b.log_completo = false
    if (Object.keys(b).length) ct.backend = b

    const d = { tipo: destino.tipo }
    if (win) {
      if (destino.tipo === 'unidade') {
        const us = destino.unidades.filter((x) => x.trim())
        if (us.length) { d.unidades = us; d.estrategia = destino.estrategia }
        if (num(destino.dias_rotacao) !== undefined) d.dias_rotacao = num(destino.dias_rotacao)
        if (num(destino.reter_logs_dias) !== undefined) d.reter_logs_dias = num(destino.reter_logs_dias)
      }
    } else if (destino.tipo === 'hd') {
      if (destino.modo === 'rotulo' && destino.rotulo) d.rotulo = destino.rotulo
      if (destino.modo === 'hds') { const hds = destino.hds.filter((x) => x.trim()); if (hds.length) { d.hds = hds; d.estrategia = destino.estrategia } }
      if (destino.modo === 'padrao' && destino.padrao_rotulo) { d.padrao_rotulo = destino.padrao_rotulo; d.estrategia = destino.estrategia }
      if (destino.montar_em) d.montar_em = destino.montar_em
      if (num(destino.dias_rotacao) !== undefined) d.dias_rotacao = num(destino.dias_rotacao)
      if (num(destino.reter_logs_dias) !== undefined) d.reter_logs_dias = num(destino.reter_logs_dias)
    }
    ct.destino = d

    if (win) {
      ct.mapeamentos = montagens.map((m) => {
        const o = { unc: m.unc }
        if (m.letra) o.letra = m.letra
        if (m.usuario) o.usuario = m.usuario
        if (m.dominio) o.dominio = m.dominio
        return o
      })
    } else {
      ct.montagens = montagens.map((m) => {
        const o = { tipo: m.tipo, origem: m.origem, ponto: m.ponto }
        if (m.tipo === 'smb') { if (m.usuario) o.usuario = m.usuario; if (m.dominio) o.dominio = m.dominio; if (m.opcoes) o.opcoes = m.opcoes }
        return o
      })
    }

    ct.copias = copias.map((c) => {
      const o = { nome: c.nome, metodo: c.metodo, origem: c.origem }
      const espelho = c.metodo === 'rsync' || c.metodo === 'robocopy'
      if (espelho) {
        if (c.excluir) o.excluir = splitList(c.excluir)
        o.apagar_extras = !!c.apagar_extras
        if (num(c.dias_rotacao) !== undefined) o.dias_rotacao = num(c.dias_rotacao)
        if (num(c.limpeza_dias) !== undefined) o.limpeza_dias = num(c.limpeza_dias)
        o.inventario = !!c.inventario
      }
      if (c.metodo === 'ssh-rsync') { o.ssh_host = c.ssh_host; if (c.ssh_user) o.ssh_user = c.ssh_user; if (num(c.porta) !== undefined) o.porta = num(c.porta) }
      if (c.metodo === 'rsync-ssh') { o.ssh_host = c.ssh_host; if (c.ssh_user) o.ssh_user = c.ssh_user; o.destino = c.destino }
      if (c.metodo === 'rclone') o.destino = c.destino
      return o
    })

    const inv = { ativo: inventario.ativo }
    if (num(inventario.modificados_horas) !== undefined) inv.modificados_horas = num(inventario.modificados_horas)
    if (num(inventario.top_arquivos) !== undefined) inv.top_arquivos = num(inventario.top_arquivos)
    if (num(inventario.top_pastas) !== undefined) inv.top_pastas = num(inventario.top_pastas)
    ct.inventario = inv

    const sec = {}
    const base = win ? 'mapeamentos' : 'montagens'
    montagens.forEach((m, i) => { if (m.senha) sec[`${base}[${i}].senha`] = m.senha })
    copias.forEach((c, i) => { if (c.ssh_senha) sec[`copias[${i}].ssh_senha`] = c.ssh_senha })
    return { conteudo: ct, secrets: sec }
  }, [nome, plataforma, win, email, backend, destino, montagens, copias, inventario])

  const previewText = useMemo(() => {
    const p = JSON.parse(JSON.stringify(conteudo))
    const arr = win ? p.mapeamentos : p.montagens
    montagens.forEach((m, i) => { if ((m.senha || m.temSenha) && arr?.[i]) arr[i].senha = '••••••' })
    copias.forEach((c, i) => { if ((c.ssh_senha || c.temSenha) && p.copias?.[i]) p.copias[i].ssh_senha = '••••••' })
    return JSON.stringify(p, null, 2)
  }, [conteudo, montagens, copias, win])

  function problemas() {
    const p = []
    montagens.forEach((m, i) => {
      if (win) {
        if (!m.unc.trim()) p.push(`Mapeamento #${i + 1}: informe o UNC (ou remova o item)`)
      } else {
        if (!m.origem.trim()) p.push(`Montagem #${i + 1}: informe a origem (ou remova)`)
        if (!m.ponto.trim()) p.push(`Montagem #${i + 1}: informe o ponto de montagem (ou remova)`)
      }
    })
    copias.forEach((c, i) => {
      if (!c.nome.trim()) p.push(`Cópia #${i + 1}: informe o nome (ou remova)`)
      if (!c.origem.trim()) p.push(`Cópia #${i + 1}: informe a origem (ou remova)`)
      if ((c.metodo === 'rclone' || c.metodo === 'rsync-ssh') && !c.destino.trim()) p.push(`Cópia #${i + 1} (${c.metodo}): informe o destino`)
      if ((c.metodo === 'ssh-rsync' || c.metodo === 'rsync-ssh') && !c.ssh_host.trim()) p.push(`Cópia #${i + 1}: informe o ssh_host`)
    })
    return p
  }

  async function salvar() {
    setErro(null)
    const p = problemas()
    if (p.length) { setErro(p.join(' · ')); return }
    try { await api('POST', `/admin/clientes/${nome}/config`, { conteudo, secrets }); onSaved() }
    catch (e) { setErro(e.message) }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: C.bg, zIndex: 60, display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 22px', borderBottom: `1px solid ${C.line}` }}>
        <div>
          <div style={{ fontSize: 16, fontWeight: 700 }}>Configuração · {nome} <span style={{ fontSize: 12, color: win ? '#4aa3ff' : C.green }}>· {win ? 'Windows' : 'Linux'}</span></div>
          <div style={{ fontSize: 12, color: C.dim }}>backend.url e token são injetados pelo agente na máquina — não vão aqui</div>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <ErroMsg msg={erro} />
          <Btn kind="ghost" onClick={onClose}>Cancelar</Btn>
          <Btn onClick={salvar}>Salvar nova versão</Btn>
        </div>
      </div>

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 22px' }}>
          <Section title="Geral">
            <F label="E-mail do relatório" hint="vazio = não envia e-mail"><Input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="relatoriobkp@futuratec.com.br" /></F>
          </Section>

          {/* ===================== DESTINO ===================== */}
          {win ? (
            <Section title="Destino" sub="unidade (letra) onde o backup é gravado — no Windows não se monta ponto, usa-se D:, E:…">
              <F label="Tipo"><Select value={destino.tipo} onChange={(e) => setDestino({ ...destino, tipo: e.target.value })}><option value="unidade">unidade (disco/letra)</option><option value="nuvem">nuvem (só rclone)</option></Select></F>
              {destino.tipo === 'unidade' && (
                <>
                  <F label="Unidades (ordem de preferência)" hint="ex.: D:, E: — usa a primeira presente">
                    {destino.unidades.map((u, i) => (
                      <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
                        <Input value={u} placeholder="D:" onChange={(e) => setDestino({ ...destino, unidades: destino.unidades.map((x, j) => (j === i ? e.target.value : x)) })} />
                        {destino.unidades.length > 1 && <Btn kind="ghost" onClick={() => setDestino({ ...destino, unidades: destino.unidades.filter((_, j) => j !== i) })}>–</Btn>}
                      </div>
                    ))}
                    <Btn kind="ghost" onClick={() => setDestino({ ...destino, unidades: [...destino.unidades, ''] })}>+ unidade</Btn>
                  </F>
                  <F label="Estratégia" hint="presente = usa a 1ª conectada · rodizio_dia · todos"><Select value={destino.estrategia} onChange={(e) => setDestino({ ...destino, estrategia: e.target.value })}><option value="presente">presente</option><option value="rodizio_dia">rodizio_dia</option><option value="todos">todos</option></Select></F>
                  <Grid>
                    <F label="Dias de rotação" hint="7 = por dia da semana"><Input type="number" value={destino.dias_rotacao} onChange={(e) => setDestino({ ...destino, dias_rotacao: e.target.value })} /></F>
                    <F label="Reter logs (dias)"><Input type="number" value={destino.reter_logs_dias} onChange={(e) => setDestino({ ...destino, reter_logs_dias: e.target.value })} /></F>
                  </Grid>
                </>
              )}
              {destino.tipo === 'nuvem' && <div style={{ fontSize: 12, color: C.dim }}>Nuvem: sem unidade local. Configure as cópias com método <b>rclone</b>.</div>}
            </Section>
          ) : (
            <Section title="Destino" sub="para onde vai o backup">
              <Grid>
                <F label="Tipo"><Select value={destino.tipo} onChange={(e) => setDestino({ ...destino, tipo: e.target.value })}><option value="hd">hd (disco externo)</option><option value="nuvem">nuvem (só rclone)</option></Select></F>
                {destino.tipo === 'hd' && <F label="Identificação do HD"><Select value={destino.modo} onChange={(e) => setDestino({ ...destino, modo: e.target.value })}><option value="rotulo">rótulo único</option><option value="hds">vários HDs</option><option value="padrao">padrão de rótulo</option></Select></F>}
              </Grid>
              {destino.tipo === 'hd' && (
                <>
                  {destino.modo === 'rotulo' && <F label="Rótulo" hint="ex.: HDEXTBKP-01 (blkid -L)"><Input value={destino.rotulo} onChange={(e) => setDestino({ ...destino, rotulo: e.target.value })} /></F>}
                  {destino.modo === 'padrao' && <F label="Padrão de rótulo" hint="ex.: HDEXTBKP-*"><Input value={destino.padrao_rotulo} onChange={(e) => setDestino({ ...destino, padrao_rotulo: e.target.value })} /></F>}
                  {destino.modo === 'hds' && (
                    <F label="HDs (ordem de preferência)">
                      {destino.hds.map((h, i) => (
                        <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
                          <Input value={h} placeholder="HDEXTBKP-0X" onChange={(e) => setDestino({ ...destino, hds: destino.hds.map((x, j) => (j === i ? e.target.value : x)) })} />
                          {destino.hds.length > 1 && <Btn kind="ghost" onClick={() => setDestino({ ...destino, hds: destino.hds.filter((_, j) => j !== i) })}>–</Btn>}
                        </div>
                      ))}
                      <Btn kind="ghost" onClick={() => setDestino({ ...destino, hds: [...destino.hds, ''] })}>+ HD</Btn>
                    </F>
                  )}
                  {(destino.modo === 'hds' || destino.modo === 'padrao') && <F label="Estratégia" hint="presente · rodizio_dia · todos"><Select value={destino.estrategia} onChange={(e) => setDestino({ ...destino, estrategia: e.target.value })}><option value="presente">presente</option><option value="rodizio_dia">rodizio_dia</option><option value="todos">todos</option></Select></F>}
                  <Grid cols={3}>
                    <F label="Montar em"><Input value={destino.montar_em} onChange={(e) => setDestino({ ...destino, montar_em: e.target.value })} /></F>
                    <F label="Dias de rotação" hint="7 = por dia da semana"><Input type="number" value={destino.dias_rotacao} onChange={(e) => setDestino({ ...destino, dias_rotacao: e.target.value })} /></F>
                    <F label="Reter logs (dias)"><Input type="number" value={destino.reter_logs_dias} onChange={(e) => setDestino({ ...destino, reter_logs_dias: e.target.value })} /></F>
                  </Grid>
                </>
              )}
              {destino.tipo === 'nuvem' && <div style={{ fontSize: 12, color: C.dim }}>Nuvem: sem HD. Configure as cópias com método <b>rclone</b>.</div>}
            </Section>
          )}

          {/* ===================== MONTAGENS / MAPEAMENTOS ===================== */}
          {win ? (
            <Section title="Mapeamentos de rede" sub="mapeia um compartilhamento (UNC) a uma letra de unidade antes da cópia (net use)">
              {montagens.map((m, i) => (
                <ItemCard key={i} title={`#${i + 1} · ${m.unc || 'UNC'}${m.letra ? ' → ' + m.letra : ''}`} onRemove={() => setMontagens(montagens.filter((_, j) => j !== i))}>
                  <Grid>
                    <F label="Compartilhamento (UNC)" hint="\\\\host\\pasta"><Input value={m.unc} onChange={(e) => upM(i, { unc: e.target.value })} placeholder="\\\\192.168.0.10\\Dados" /></F>
                    <F label="Letra (opcional)" hint="ex.: Z: — vazio = acessa direto por UNC"><Input value={m.letra} onChange={(e) => upM(i, { letra: e.target.value })} placeholder="Z:" /></F>
                  </Grid>
                  <Grid>
                    <F label="Usuário"><Input value={m.usuario} onChange={(e) => upM(i, { usuario: e.target.value })} /></F>
                    <F label="Senha" hint={m.temSenha ? 'já definida — preencha só para trocar' : 'cifrada (age) no backend'}><Input type="password" value={m.senha} placeholder={m.temSenha ? '•••••• (mantida)' : ''} onChange={(e) => upM(i, { senha: e.target.value })} /></F>
                  </Grid>
                  <F label="Domínio (opcional)"><Input value={m.dominio} onChange={(e) => upM(i, { dominio: e.target.value })} /></F>
                </ItemCard>
              ))}
              <Btn kind="outline" onClick={() => setMontagens([...montagens, { unc: '', letra: '', usuario: '', senha: '', dominio: '', temSenha: false }])}>+ Mapeamento</Btn>
            </Section>
          ) : (
            <Section title="Montagens" sub="compartilhamentos de rede montados antes da cópia">
              {montagens.map((m, i) => (
                <ItemCard key={i} title={`#${i + 1} · ${m.tipo.toUpperCase()}`} onRemove={() => setMontagens(montagens.filter((_, j) => j !== i))}>
                  <Grid>
                    <F label="Tipo"><Select value={m.tipo} onChange={(e) => upM(i, { tipo: e.target.value })}><option value="smb">smb (Windows/CIFS)</option><option value="nfs">nfs (Linux/NAS)</option></Select></F>
                    <F label="Ponto de montagem"><Input value={m.ponto} onChange={(e) => upM(i, { ponto: e.target.value })} placeholder="/mnt/Dados" /></F>
                  </Grid>
                  <F label="Origem" hint={m.tipo === 'smb' ? '//host/Compartilhamento' : 'host:/caminho_exportado'}><Input value={m.origem} onChange={(e) => upM(i, { origem: e.target.value })} /></F>
                  {m.tipo === 'smb' && (
                    <>
                      <Grid>
                        <F label="Usuário"><Input value={m.usuario} onChange={(e) => upM(i, { usuario: e.target.value })} /></F>
                        <F label="Senha" hint={m.temSenha ? 'já definida — preencha só para trocar' : 'cifrada (age) no backend'}><Input type="password" value={m.senha} placeholder={m.temSenha ? '•••••• (mantida)' : ''} onChange={(e) => upM(i, { senha: e.target.value })} /></F>
                      </Grid>
                      <Grid>
                        <F label="Domínio (opcional)"><Input value={m.dominio} onChange={(e) => upM(i, { dominio: e.target.value })} /></F>
                        <F label="Opções (opcional)" hint="ex.: vers=3.0"><Input value={m.opcoes} onChange={(e) => upM(i, { opcoes: e.target.value })} /></F>
                      </Grid>
                    </>
                  )}
                </ItemCard>
              ))}
              <Btn kind="outline" onClick={() => setMontagens([...montagens, { tipo: 'smb', origem: '', ponto: '', usuario: '', senha: '', dominio: '', opcoes: '', temSenha: false }])}>+ Montagem</Btn>
            </Section>
          )}

          {/* ===================== COPIAS ===================== */}
          <Section title="Cópias" sub="o que copiar e como">
            {copias.map((c, i) => {
              const metodos = win ? METODOS_WIN : METODOS_LINUX
              const espelho = c.metodo === 'rsync' || c.metodo === 'robocopy'
              return (
                <ItemCard key={i} title={`#${i + 1} · ${c.nome || 'sem nome'} · ${c.metodo}`} onRemove={() => setCopias(copias.filter((_, j) => j !== i))}>
                  <Grid>
                    <F label="Nome" hint="vira a pasta no destino"><Input value={c.nome} onChange={(e) => upC(i, { nome: e.target.value })} /></F>
                    <F label="Método"><Select value={c.metodo} onChange={(e) => upC(i, { metodo: e.target.value })}>{metodos.map((x) => <option key={x} value={x}>{x}</option>)}</Select></F>
                  </Grid>
                  <F label={c.metodo === 'ssh-rsync' ? 'Origem (caminho no servidor remoto)' : 'Origem'}><Input value={c.origem} onChange={(e) => upC(i, { origem: e.target.value })} placeholder={win ? 'Z:\\Dados ou C:\\Pasta' : '/mnt/Dados'} /></F>

                  {(c.metodo === 'ssh-rsync' || c.metodo === 'rsync-ssh') && (
                    <>
                      <Grid cols={3}>
                        <F label="ssh_host"><Input value={c.ssh_host} onChange={(e) => upC(i, { ssh_host: e.target.value })} /></F>
                        <F label="ssh_user" hint="padrão root"><Input value={c.ssh_user} onChange={(e) => upC(i, { ssh_user: e.target.value })} /></F>
                        {c.metodo === 'ssh-rsync' && <F label="porta" hint="padrão 22"><Input type="number" value={c.porta} onChange={(e) => upC(i, { porta: e.target.value })} /></F>}
                      </Grid>
                      <F label="ssh_senha" hint={c.temSenha ? 'já definida — preencha só para trocar' : 'vazio = usa chave SSH'}><Input type="password" value={c.ssh_senha} placeholder={c.temSenha ? '•••••• (mantida)' : ''} onChange={(e) => upC(i, { ssh_senha: e.target.value })} /></F>
                    </>
                  )}
                  {c.metodo === 'rsync-ssh' && <F label="Destino (caminho no servidor remoto)" hint="obrigatório"><Input value={c.destino} onChange={(e) => upC(i, { destino: e.target.value })} /></F>}
                  {c.metodo === 'rclone' && <F label="Destino (remote:pasta)" hint="obrigatório · ex.: gdrive:BackupEmpresa"><Input value={c.destino} onChange={(e) => upC(i, { destino: e.target.value })} /></F>}
                  {c.metodo === 'tar' && <div style={{ fontSize: 11.5, color: C.amber }}>tar é reservado — ainda não executa.</div>}

                  {espelho && (
                    <>
                      <F label="Excluir (padrões)" hint="separe por vírgula ou linha"><Input value={c.excluir} onChange={(e) => upC(i, { excluir: e.target.value })} placeholder="*.tmp, ~$*, Thumbs.db" /></F>
                      <Grid cols={2}>
                        <F label="Dias de rotação (opcional)"><Input type="number" value={c.dias_rotacao} onChange={(e) => upC(i, { dias_rotacao: e.target.value })} /></F>
                        <F label="Limpeza (dias, opcional)"><Input type="number" value={c.limpeza_dias} onChange={(e) => upC(i, { limpeza_dias: e.target.value })} /></F>
                      </Grid>
                      <Toggle on={c.apagar_extras} onChange={(v) => upC(i, { apagar_extras: v })} label={win ? 'Apagar extras (/MIR, espelho)' : 'Apagar extras (--delete, espelho)'} />
                      <Toggle on={c.inventario} onChange={(v) => upC(i, { inventario: v })} label="Inventariar esta origem" />
                    </>
                  )}
                </ItemCard>
              )
            })}
            <Btn kind="outline" onClick={() => setCopias([...copias, { nome: '', metodo: win ? 'robocopy' : 'rsync', origem: '', excluir: '', apagar_extras: true, dias_rotacao: '', limpeza_dias: '', inventario: true, ssh_host: '', ssh_user: '', ssh_senha: '', porta: '', destino: '', temSenha: false }])}>+ Cópia</Btn>
          </Section>

          <Section title="Inventário" sub="levantamento de estrutura da origem (para análise)">
            <Toggle on={inventario.ativo} onChange={(v) => setInventario({ ...inventario, ativo: v })} label="Ativo" />
            {inventario.ativo && (
              <Grid cols={3}>
                <F label="Modificados (horas)"><Input type="number" value={inventario.modificados_horas} onChange={(e) => setInventario({ ...inventario, modificados_horas: e.target.value })} /></F>
                <F label="Top arquivos"><Input type="number" value={inventario.top_arquivos} onChange={(e) => setInventario({ ...inventario, top_arquivos: e.target.value })} /></F>
                <F label="Top pastas"><Input type="number" value={inventario.top_pastas} onChange={(e) => setInventario({ ...inventario, top_pastas: e.target.value })} /></F>
              </Grid>
            )}
          </Section>
          <div style={{ height: 40 }} />
        </div>

        {/* PREVIEW */}
        <div style={{ width: 420, flexShrink: 0, borderLeft: `1px solid ${C.line}`, background: C.side, overflowY: 'auto' }}>
          <div style={{ padding: '12px 16px', borderBottom: `1px solid ${C.line}`, fontSize: 12, color: C.muted, position: 'sticky', top: 0, background: C.side }}>
            <span style={{ color: C.green }}>●</span> {nome}.conf <span style={{ color: C.dim }}>(ao vivo · senhas mascaradas)</span>
          </div>
          <pre style={{ margin: 0, padding: '14px 16px', fontFamily: mono, fontSize: 12, lineHeight: 1.5, color: C.soft, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{previewText}</pre>
        </div>
      </div>
    </div>
  )
}
