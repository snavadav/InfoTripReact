# Exporta tu base de datos local de InfoTrip para subirla al servidor (docs/despliegue-aws.md, paso 6).
#
#   powershell -ExecutionPolicy Bypass -File scripts\exportar_base.ps1
#
# Lee DB_NAME, DB_USER, DB_PASSWORD, DB_HOST y DB_PORT de tu .env sin mostrarlos, y guarda el respaldo
# FUERA de OneDrive (en %USERPROFILE%\infotrip-respaldos), porque contiene datos de las cuentas.

$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot
$archivoEnv = Join-Path $raiz '.env'
if (-not (Test-Path $archivoEnv)) { throw "No encuentro $archivoEnv" }

$variables = @{}
foreach ($linea in Get-Content $archivoEnv) {
    if ($linea -match '^\s*(DB_[A-Z]+)\s*=\s*(.*?)\s*$') { $variables[$Matches[1]] = $Matches[2].Trim('"', "'") }
}
foreach ($nombre in 'DB_NAME', 'DB_USER', 'DB_PASSWORD') {
    if (-not $variables[$nombre]) { throw "Falta $nombre en .env" }
}
$servidor = if ($variables['DB_HOST']) { $variables['DB_HOST'] } else { '127.0.0.1' }
$puerto = if ($variables['DB_PORT']) { $variables['DB_PORT'] } else { '5432' }

# pg_dump de la misma versión mayor que el servidor de AWS (PostgreSQL 16) o anterior.
$pgDump = Get-ChildItem 'C:\Program Files\PostgreSQL\*\bin\pg_dump.exe' -ErrorAction SilentlyContinue |
    Sort-Object FullName | Select-Object -Last 1
if (-not $pgDump) { throw 'No encuentro pg_dump.exe en C:\Program Files\PostgreSQL\' }

$carpeta = Join-Path $env:USERPROFILE 'infotrip-respaldos'
New-Item -ItemType Directory -Force $carpeta | Out-Null
$destino = Join-Path $carpeta ("infotrip-{0}.dump" -f (Get-Date -Format 'yyyy-MM-dd-HHmm'))

$env:PGPASSWORD = $variables['DB_PASSWORD']
try {
    & $pgDump.FullName -h $servidor -p $puerto -U $variables['DB_USER'] -d $variables['DB_NAME'] `
        --format=custom --no-owner --no-privileges -f $destino
    if ($LASTEXITCODE -ne 0) { throw "pg_dump terminó con código $LASTEXITCODE" }
} finally {
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
}

$tamano = [math]::Round((Get-Item $destino).Length / 1MB, 1)
Write-Host "Listo: $destino ($tamano MB)"
Write-Host 'Siguiente: súbelo al servidor con scp (paso 6 de docs/despliegue-aws.md).'
