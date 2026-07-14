# Agente de backup em frota — Windows (equivalente a agente.py).
# Modelo pull: so fala para fora (HTTPS de saida). Puxa a config, decifra os campos
# de senha com a chave privada age LOCAL, grava o <cliente>.conf e aciona o backup.ps1.
#
#   agente.ps1 enroll -Backend https://host/api -Token TOKEN
#   agente.ps1 heartbeat | loop | pull | backup
#
# NOTA: este agente ainda precisa de validacao numa maquina Windows real.
param(
  [Parameter(Position = 0)][ValidateSet('enroll', 'heartbeat', 'loop', 'pull', 'backup')][string]$Cmd,
  [string]$Backend,
  [string]$Token
)
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Dir        = Split-Path -Parent $MyInvocation.MyCommand.Path
$StateFile  = Join-Path $Dir 'agente.json'
$KeyFile    = Join-Path $Dir 'age-key.txt'
$BackupPs1  = Join-Path $Dir 'backup.ps1'
$Age        = Join-Path $Dir 'age.exe'
$AgeKeygen  = Join-Path $Dir 'age-keygen.exe'
$Minisign   = Join-Path $Dir 'minisign.exe'
$MinisignPub = Join-Path $Dir 'minisign.pub'
$DefaultHeartbeat = 600

function Log($m) { Write-Host "[agente] $m" }

function Load-State {
  if (-not (Test-Path $StateFile)) { throw 'agente nao inscrito. Rode: agente.ps1 enroll -Backend URL -Token ...' }
  Get-Content $StateFile -Raw | ConvertFrom-Json
}
function Save-State($obj) {
  $obj | ConvertTo-Json | Out-File -Encoding utf8 $StateFile
  & icacls $StateFile /inheritance:r /grant:r 'SYSTEM:F' 'Administrators:F' | Out-Null
}
function Http($method, $url, $body, $token) {
  $h = @{}
  if ($token) { $h['Authorization'] = "Bearer $token" }
  if ($null -ne $body) {
    Invoke-RestMethod -Method $method -Uri $url -Headers $h -ContentType 'application/json' -Body ($body | ConvertTo-Json)
  } else {
    Invoke-RestMethod -Method $method -Uri $url -Headers $h
  }
}
function Age-Pubkey {
  foreach ($l in Get-Content $KeyFile) { if ($l -match 'public key:\s*(age1\S+)') { return $Matches[1] } }
  throw 'chave publica nao encontrada'
}
function Script-Versao {
  if (Test-Path $BackupPs1) { foreach ($l in Get-Content $BackupPs1) { if ($l -match '^\$Versao\s*=\s*["'']([^"'']+)') { return $Matches[1] } } }
  return 'desconhecida'
}
function Decrypt-Field($field) {
  $bytes = [Convert]::FromBase64String($field.Substring(4))
  $tmp = [IO.Path]::GetTempFileName()
  [IO.File]::WriteAllBytes($tmp, $bytes)
  try { $plain = (& $Age -d -i $KeyFile $tmp) -join "`n" } finally { Remove-Item $tmp -Force }
  return $plain
}

function Cmd-Enroll {
  if (-not (Test-Path $KeyFile)) {
    Log 'gerando par de chaves age (a privada nunca sai desta maquina)'
    & $AgeKeygen -o $KeyFile 2>$null | Out-Null
    & icacls $KeyFile /inheritance:r /grant:r 'SYSTEM:F' 'Administrators:F' | Out-Null
  }
  $pub = Age-Pubkey
  $resp = Http 'POST' "$($Backend.TrimEnd('/'))/enroll" @{ enrollment_token = $Token; age_pubkey = $pub } $null
  Save-State @{ backend_url = $Backend.TrimEnd('/'); cliente = $resp.cliente; token = $resp.token; heartbeat_intervalo = $DefaultHeartbeat }
  Log "inscrito como '$($resp.cliente)'. token permanente salvo em $StateFile"
}

function Pull-Config {
  $st = Load-State
  $raw = Invoke-WebRequest -Uri "$($st.backend_url)/config/$($st.cliente)" -Headers @{ Authorization = "Bearer $($st.token)" } -UseBasicParsing
  $text = $raw.Content
  # decifra todos os "age:...." no proprio JSON
  $dec = [regex]::Replace($text, '"age:([A-Za-z0-9+/=]+)"', {
      param($m)
      $plain = Decrypt-Field ('age:' + $m.Groups[1].Value)
      '"' + ($plain -replace '\\', '\\\\' -replace '"', '\"') + '"'
    })
  $cfg = $dec | ConvertFrom-Json
  # injeta backend (url + token locais) para o backup.ps1 reportar em /runs
  $b = if ($cfg.backend) { $cfg.backend } else { [pscustomobject]@{} }
  $b | Add-Member url $st.backend_url -Force
  $b | Add-Member token $st.token -Force
  $cfg | Add-Member backend $b -Force
  $conf = Join-Path $Dir "$($st.cliente).conf"
  $cfg | ConvertTo-Json -Depth 30 | Out-File -Encoding utf8 $conf
  & icacls $conf /inheritance:r /grant:r 'SYSTEM:F' 'Administrators:F' | Out-Null
  Log "config v$($cfg._config_versao) aplicada em $conf"
}

function Process-Comandos($comandos, $cliente) {
  foreach ($c in $comandos) {
    Log "comando pendente: $($c.tipo)"
    switch ($c.tipo) {
      'rodar_agora' { Pull-Config; & powershell -NoProfile -ExecutionPolicy Bypass -File $BackupPs1 (Join-Path $Dir "$cliente.conf") }
      'check'       { & powershell -NoProfile -ExecutionPolicy Bypass -File $BackupPs1 (Join-Path $Dir "$cliente.conf") -Check }
      default       { Log "comando desconhecido: $($c.tipo)" }
    }
  }
}

function Cmd-Heartbeat {
  $st = Load-State
  $resp = Http 'POST' "$($st.backend_url)/heartbeat" @{ versao_script = (Script-Versao) } $st.token
  if ($resp.config_disponivel) { Log "config nova (v$($resp.config_versao)) -> puxando"; Pull-Config }
  if ($resp.comandos) { Process-Comandos $resp.comandos $st.cliente }
  if ($resp.update) { Log "update disponivel: v$($resp.update.versao) (aplicacao de update no Windows: a validar)" }
}

function Cmd-Loop {
  $st = Load-State
  Log "laco de heartbeat a cada $($st.heartbeat_intervalo)s (cliente=$($st.cliente))"
  while ($true) {
    try { Cmd-Heartbeat } catch { Log "erro no ciclo: $_" }
    Start-Sleep -Seconds ([int]$st.heartbeat_intervalo)
  }
}

function Cmd-Backup {
  $st = Load-State
  Pull-Config
  Log 'rodando backup.ps1 (reporta em /runs e /inventario)'
  & powershell -NoProfile -ExecutionPolicy Bypass -File $BackupPs1 (Join-Path $Dir "$($st.cliente).conf")
}

switch ($Cmd) {
  'enroll'    { Cmd-Enroll }
  'heartbeat' { Cmd-Heartbeat }
  'loop'      { Cmd-Loop }
  'pull'      { Pull-Config }
  'backup'    { Cmd-Backup }
  default     { Write-Host 'uso: agente.ps1 {enroll|heartbeat|loop|pull|backup}' }
}
