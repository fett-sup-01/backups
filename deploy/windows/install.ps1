# Instalador do agente de backup em frota — Windows (equivalente ao install.sh).
# Nao precisa copiar nada: baixa o agente do proprio backend.
#
#   $env:BACKEND='https://SEU_HOST'; $env:TOKEN='TOKEN_EFEMERO'; irm https://SEU_HOST/install.ps1 | iex
#
# Requer PowerShell como Administrador. O unico segredo e o token efemero (uso unico).
$ErrorActionPreference = 'Stop'

$Backend = $env:BACKEND
$Token   = $env:TOKEN
$Dir     = if ($env:INSTALL_DIR) { $env:INSTALL_DIR } else { 'C:\ProgramData\Backups' }
if (-not $Backend -or -not $Token) { throw 'defina $env:BACKEND e $env:TOKEN antes de rodar' }

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { throw 'rode este PowerShell como Administrador' }

$Backend = $Backend.TrimEnd('/')
$Api  = "$Backend/api"      # o nginx faz proxy de /api -> FastAPI
$Dist = "$Backend/agent"    # arquivos do agente servidos pelo backend
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

Write-Host '==> pasta' $Dir
New-Item -ItemType Directory -Force -Path $Dir | Out-Null

Write-Host '==> baixando agente'
Invoke-WebRequest "$Dist/agente.ps1" -OutFile "$Dir\agente.ps1" -UseBasicParsing
Invoke-WebRequest "$Dist/backup.ps1" -OutFile "$Dir\backup.ps1" -UseBasicParsing
try { Invoke-WebRequest "$Dist/minisign.pub" -OutFile "$Dir\minisign.pub" -UseBasicParsing } catch { Write-Host '   (sem minisign.pub; updates desabilitados ate coloca-lo)' }

# age + minisign (binarios Windows) se ainda nao existirem
if (-not (Test-Path "$Dir\age.exe")) {
  Write-Host '==> baixando age (windows)'
  $tmp = "$env:TEMP\age.zip"
  Invoke-WebRequest 'https://github.com/FiloSottile/age/releases/download/v1.2.0/age-v1.2.0-windows-amd64.zip' -OutFile $tmp -UseBasicParsing
  Expand-Archive $tmp -DestinationPath "$env:TEMP\age-x" -Force
  Copy-Item "$env:TEMP\age-x\age\age.exe" "$Dir\age.exe" -Force
  Copy-Item "$env:TEMP\age-x\age\age-keygen.exe" "$Dir\age-keygen.exe" -Force
}
if (-not (Test-Path "$Dir\minisign.exe")) {
  Write-Host '==> baixando minisign (windows)'
  try {
    $tmp = "$env:TEMP\minisign.zip"
    Invoke-WebRequest 'https://github.com/jedisct1/minisign/releases/download/0.11/minisign-0.11-win64.zip' -OutFile $tmp -UseBasicParsing
    Expand-Archive $tmp -DestinationPath "$env:TEMP\ms-x" -Force
    Copy-Item (Get-ChildItem "$env:TEMP\ms-x" -Recurse -Filter minisign.exe | Select-Object -First 1).FullName "$Dir\minisign.exe" -Force
  } catch { Write-Host '   (minisign nao instalado; updates desabilitados)' }
}

Write-Host '==> enrollment (gera par de chaves age; troca o token efemero pelo permanente)'
& powershell -NoProfile -ExecutionPolicy Bypass -File "$Dir\agente.ps1" enroll -Backend $Api -Token $Token

# Tarefas agendadas (equivalem ao systemd service+timer)
Write-Host '==> tarefas agendadas'
$ps = (Get-Command powershell).Source
$actLoop   = New-ScheduledTaskAction -Execute $ps -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Dir\agente.ps1`" loop"
$trigLoop  = New-ScheduledTaskTrigger -AtStartup
$actBkp    = New-ScheduledTaskAction -Execute $ps -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Dir\agente.ps1`" backup"
$trigBkp   = New-ScheduledTaskTrigger -Daily -At 10pm
$princ     = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName 'BackupAgente'   -Action $actLoop -Trigger $trigLoop -Principal $princ -Force | Out-Null
Register-ScheduledTask -TaskName 'BackupDiario'   -Action $actBkp  -Trigger $trigBkp  -Principal $princ -Force | Out-Null
Start-ScheduledTask -TaskName 'BackupAgente'

Write-Host '==> primeiro pull da config'
try { & powershell -NoProfile -ExecutionPolicy Bypass -File "$Dir\agente.ps1" pull } catch { Write-Host '   (sem config ainda; o proximo heartbeat puxa)' }

Write-Host '==> pronto.'
