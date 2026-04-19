# Desarrollo local con Podman (Windows / WSL machine)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

Write-Host "Comprobando Podman..."
podman version
$machine = podman machine list --format "{{.Name}}" 2>$null
if (-not $machine) {
    Write-Host "Inicializa la maquina: podman machine init && podman machine start"
    exit 1
}
$status = podman machine list --format "{{.LastUp}}" 2>$null
if ($status -match "Never|^$") {
    Write-Host "Iniciando maquina Podman..."
    podman machine start
}

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Creado .env desde .env.example"
}

Write-Host "Levantando stack (primera vez: descarga/build largo)..."
podman compose up --build -d

Write-Host "Estado:"
podman compose ps

Write-Host ""
Write-Host "Health checks:"
Start-Sleep -Seconds 5
try { Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" } catch { Write-Host "API aun no lista: $_" }
try { Invoke-RestMethod -Uri "http://127.0.0.1:8081/health" } catch { Write-Host "Processor aun no lista: $_" }
