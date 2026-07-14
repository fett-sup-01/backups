# Motor de backup — Windows (robocopy). Equivalente ao backup.py (Linux).
# Le o <cliente>.conf gerado pelo agente, mapeia unidades de rede, escolhe a
# unidade de destino, roda robocopy por copia e reporta em /runs.
#
#   backup.ps1 <cliente>.conf [-Check]
#
# ATENCAO (v1): este motor ainda precisa de validacao numa maquina Windows real.
param([Parameter(Position = 0, Mandatory = $true)][string]$Config, [switch]$Check)
$ErrorActionPreference = 'Continue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Versao = '1.0-win'
$cfg = Get-Content $Config -Raw | ConvertFrom-Json
$RunId = (Get-Date -Format 'yyyyMMdd-HHmmss')
$dias = if ($cfg.destino.dias_rotacao) { [int]$cfg.destino.dias_rotacao } else { 7 }

function Slot-Rotacao($n) {
  if ($n -eq 7) { return @('Domingo', 'Segunda', 'Terca', 'Quarta', 'Quinta', 'Sexta', 'Sabado')[[int](Get-Date).DayOfWeek] }
  return 'dia_{0:D2}' -f (([int](Get-Date).DayOfYear % $n) + 1)
}

# --- mapeia unidades de rede (net use) ---
if ($cfg.mapeamentos) {
  foreach ($m in $cfg.mapeamentos) {
    $alvo = if ($m.letra) { $m.letra } else { $m.unc }
    $args = @('use', $alvo, $m.unc)
    if ($m.usuario) {
      $u = if ($m.dominio) { "$($m.dominio)\$($m.usuario)" } else { $m.usuario }
      $args += @("/user:$u")
      if ($m.senha) { $args += $m.senha }
    }
    Write-Host "[bkp] net use $alvo $($m.unc)"
    if (-not $Check) { & net @args 2>&1 | Out-Null }
  }
}

# --- escolhe a unidade de destino presente ---
$destDrive = $null
foreach ($u in @($cfg.destino.unidades)) { if (Test-Path "$u\") { $destDrive = $u; break } }
if ($Check) {
  Write-Host '== VALIDACAO Windows =='
  Write-Host ("  destino presente: " + ($(if ($destDrive) { $destDrive } else { 'NENHUM' })))
  Write-Host ("  robocopy: " + $(if (Get-Command robocopy -EA SilentlyContinue) { 'ok' } else { 'FALTA' }))
  exit 0
}
if (-not $destDrive) { Write-Host '[bkp] ERRO: nenhuma unidade de destino conectada'; exit 1 }

$dia = Slot-Rotacao $dias
$base = Join-Path "$destDrive\" "Backup_diario\$dia"
New-Item -ItemType Directory -Force -Path $base | Out-Null

# --- copias (robocopy) ---
$jobs = @()
foreach ($c in $cfg.copias) {
  $destPasta = Join-Path $base $c.nome
  $rc = @($c.origem, $destPasta, '/E', '/R:1', '/W:1', '/NP', '/NFL', '/NDL')
  if ($c.apagar_extras) { $rc += '/MIR' }
  if ($c.excluir) { $rc += '/XF'; $rc += @($c.excluir) }
  Write-Host "[bkp] robocopy $($c.origem) -> $destPasta"
  & robocopy @rc | Out-Null
  $code = $LASTEXITCODE
  # robocopy: 0-7 = ok (0 nada a copiar, 1 copiou, etc.), >=8 = erro
  $status = if ($code -ge 8) { 'falha' } else { 'sucesso' }
  $jobs += @{ nome = $c.nome; metodo = $c.metodo; status = $status; robocopy_code = $code }
}

$okCount = ($jobs | Where-Object { $_.status -eq 'sucesso' }).Count
$statusGeral = if ($okCount -eq $jobs.Count) { 'sucesso' } elseif ($okCount -eq 0) { 'falha' } else { 'parcial' }

# --- uso do disco de destino ---
$usoPct = '-'
try {
  $d = Get-PSDrive ($destDrive.TrimEnd(':'))
  if ($d.Used -and $d.Free) { $usoPct = ('{0}%' -f [math]::Round($d.Used * 100 / ($d.Used + $d.Free))) }
} catch { }

# --- reporta em /runs (se backend configurado) ---
if ($cfg.backend -and $cfg.backend.url) {
  $payload = @{
    cliente = $cfg.cliente; hostname = $env:COMPUTERNAME; run_id = $RunId
    versao_script = $Versao; versao_config = $cfg._config_versao
    plataforma = 'windows'; data = (Get-Date).ToString('o'); status = $statusGeral
    total_jobs = $jobs.Count; jobs_ok = $okCount
    destino = @{ unidade = $destDrive; uso_pct = $usoPct }
    jobs = $jobs
  }
  try {
    Invoke-RestMethod -Method Post -Uri "$($cfg.backend.url)/runs" -Headers @{ Authorization = "Bearer $($cfg.backend.token)" } -ContentType 'application/json' -Body ($payload | ConvertTo-Json -Depth 20) | Out-Null
    Write-Host '[bkp] reportado em /runs'
  } catch { Write-Host "[bkp] falha ao reportar: $_" }
}
Write-Host "[bkp] fim: $statusGeral ($okCount/$($jobs.Count))"
exit $(if ($statusGeral -eq 'sucesso') { 0 } else { 1 })
