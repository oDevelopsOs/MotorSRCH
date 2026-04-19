# Inicia todo el stack. Por defecto usa Docker (docker compose) — recomendado en VPS y CI.
# Podman solo si pasas -UsePodman (desarrollo local sin Docker) o si Docker no esta y caes en fallback.
#
# Uso:
#   .\scripts\start-all.ps1
#   .\scripts\start-all.ps1 -ComposeProfile searxng
#   .\scripts\start-all.ps1 -ComposeProfile searxng,nsqadmin
#   .\scripts\start-all.ps1 -Production -ComposeProfile searxng
#   .\scripts\start-all.ps1 -Production -DualApi -ComposeProfile searxng
#   .\scripts\start-all.ps1 -UsePodman
param(
    [Parameter(Mandatory = $false)]
    [string[]] $ComposeProfile = @(),
    [switch] $Production,
    [switch] $DualApi,
    [switch] $UsePodman
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Creado .env desde .env.example"
}

function Test-DockerUp {
    try {
        docker info 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

$compose = $null
if ($UsePodman) {
    Write-Host "Usando Podman Compose (-UsePodman)..."
    try {
        podman version 2>$null | Out-Null
    } catch {
        Write-Host "ERROR: Podman no encontrado. En VPS usa Docker Engine; en Windows instala Podman o quita -UsePodman y usa Docker Desktop."
        exit 1
    }
    $machine = podman machine list --format "{{.Name}}" 2>$null
    if (-not $machine) {
        Write-Host "Ejecuta: podman machine init && podman machine start"
        exit 1
    }
    $status = podman machine list --format "{{.LastUp}}" 2>$null
    if ($status -match "Never|^$") {
        Write-Host "Iniciando maquina Podman..."
        podman machine start
    }
    $compose = "podman"
} elseif (Test-DockerUp) {
    Write-Host "Usando Docker Compose (recomendado en VPS)..."
    $compose = "docker"
} else {
    Write-Host "AVISO: Docker no disponible. En servidor Linux instala Docker Engine y ejecuta de nuevo."
    Write-Host "       Fallback: probando Podman (desarrollo local). Para forzar Podman: -UsePodman"
    try {
        podman version 2>$null | Out-Null
    } catch {
        Write-Host "ERROR: Instala Docker Engine / Docker Desktop, o Podman con maquina iniciada (podman machine start)."
        exit 1
    }
    $machine = podman machine list --format "{{.Name}}" 2>$null
    if (-not $machine) {
        Write-Host "Ejecuta: podman machine init && podman machine start"
        exit 1
    }
    $status = podman machine list --format "{{.LastUp}}" 2>$null
    if ($status -match "Never|^$") {
        Write-Host "Iniciando maquina Podman..."
        podman machine start
    }
    $compose = "podman"
}

$profileArgs = [System.Collections.ArrayList]@()
foreach ($p in $ComposeProfile) {
    if ($p) {
        foreach ($segment in ($p -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ })) {
            [void]$profileArgs.Add("--profile")
            [void]$profileArgs.Add($segment)
        }
    }
}

Write-Host "Levantando stack (primera vez: descarga/build largo)..."
if ($profileArgs.Count -gt 0) {
    Write-Host "Perfiles: $($ComposeProfile -join ', ')"
}
if ($Production) {
    Write-Host "Modo producción: docker-compose.prod.yml"
}
if ($DualApi) {
    Write-Host "Segunda API: docker-compose.dual-api.yml"
}

$fileArgs = [System.Collections.ArrayList]@("-f", "docker-compose.yml")
if ($Production) {
    [void]$fileArgs.Add("-f")
    [void]$fileArgs.Add("docker-compose.prod.yml")
}
if ($DualApi) {
    if (-not $Production) {
        Write-Host "AVISO: -DualApi suele usarse junto con -Production"
    }
    [void]$fileArgs.Add("-f")
    [void]$fileArgs.Add("docker-compose.dual-api.yml")
}

if ($compose -eq "docker") {
    if ($profileArgs.Count -gt 0) {
        & docker compose @fileArgs @profileArgs up --build -d
    } else {
        & docker compose @fileArgs up --build -d
    }
    & docker compose @fileArgs ps
} else {
    if ($profileArgs.Count -gt 0) {
        & podman compose @fileArgs @profileArgs up --build -d
    } else {
        & podman compose @fileArgs up --build -d
    }
    & podman compose @fileArgs ps
}

Write-Host ""
Write-Host "Health checks (espera unos segundos si acabas de construir)..."
Start-Sleep -Seconds 8
if ($Production) {
    try { Invoke-RestMethod -Uri "http://127.0.0.1:8888/health" } catch { Write-Host "NGINX: $_" }
} else {
    try { Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" } catch { Write-Host "API: $_" }
    try { Invoke-RestMethod -Uri "http://127.0.0.1:8888/health" } catch { Write-Host "NGINX: $_" }
}
if (-not $Production) {
    try { Invoke-RestMethod -Uri "http://127.0.0.1:8081/health" } catch { Write-Host "Processor: $_" }
}

Write-Host ""
if ($Production) {
    Write-Host "Listo (producción compose): entrada HTTP en NGINX — http://127.0.0.1:8888  (API no publicada al host)"
} else {
    Write-Host "Listo. API: http://127.0.0.1:8000  |  NGINX: http://127.0.0.1:8888"
}
if ($ComposeProfile -match "searxng") {
    Write-Host "SearXNG (host): http://127.0.0.1:8088  —  En .env: ENABLE_SEARXNG=1 y SEARXNG_URL=http://searxng:8080"
}
Write-Host "Pruebas automaticas: .\scripts\smoke-stack.ps1"
