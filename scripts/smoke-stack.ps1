# Pruebas de humo del stack (API, NGINX, processor, opcional SearXNG, /search, /resolve).
# Requiere el stack en marcha: .\scripts\start-all.ps1 -ComposeProfile searxng
# Salida: código 0 si todo OK, distinto de 0 si falla alguna comprobación obligatoria.
#
# Uso:
#   .\scripts\smoke-stack.ps1
#   .\scripts\smoke-stack.ps1 -SkipSearxng
#   .\scripts\smoke-stack.ps1 -ApiBase "http://127.0.0.1:8000"
#   Compose producción (solo NGINX al host): -ApiBase "http://127.0.0.1:8888" -SkipProcessor

param(
    [string] $ApiBase = "http://127.0.0.1:8000",
    [string] $NginxBase = "http://127.0.0.1:8888",
    [string] $ProcessorBase = "http://127.0.0.1:8081",
    [string] $SearxngBase = "http://127.0.0.1:8088",
    [switch] $SkipSearxng,
    [switch] $SkipProcessor
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

$script:failed = 0

function Test-JsonHasKey {
    param([string]$Json, [string]$Key)
    try {
        $o = $Json | ConvertFrom-Json
        return $null -ne ($o.PSObject.Properties.Name -match "^$Key$")
    } catch {
        return $false
    }
}

function Step-Get {
    param([string]$Name, [string]$Uri)
    try {
        $r = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 60
        $code = [int]$r.StatusCode
        if ($code -lt 200 -or $code -gt 299) {
            Write-Host "[FAIL] $Name -> HTTP $code ($Uri)"
            $script:failed++
            return $null
        }
        Write-Host "[ OK ] $Name -> HTTP $code"
        return $r.Content
    } catch {
        Write-Host "[FAIL] $Name -> $($_.Exception.Message) ($Uri)"
        $script:failed++
        return $null
    }
}

Write-Host "=== MotorDeBusqueda smoke (PowerShell) ==="
Write-Host ""

Step-Get "API health" "$ApiBase/health"
Step-Get "NGINX health" "$NginxBase/health"
if (-not $SkipProcessor) {
    Step-Get "Processor health" "$ProcessorBase/health"
} else {
    Write-Host "[SKIP] Processor health (puerto no publicado; p. ej. docker-compose.prod)"
}

$envPath = Join-Path $root ".env"
$wantSearxng = $false
if (Test-Path $envPath) {
    foreach ($line in Get-Content $envPath) {
        if ($line -match '^\s*ENABLE_SEARXNG\s*=\s*1\s*$') { $wantSearxng = $true }
    }
}

if (-not $SkipSearxng -and $wantSearxng) {
    Step-Get "SearXNG (host)" $SearxngBase
} elseif (-not $SkipSearxng) {
    Write-Host "[SKIP] SearXNG (ENABLE_SEARXNG no es 1 en .env)"
}

$searchBody = Step-Get "GET /search" "$ApiBase/search?q=smoke+test&limit=3"
if ($null -ne $searchBody) {
    if (-not (Test-JsonHasKey -Json $searchBody -Key "results")) {
        Write-Host "[FAIL] /search JSON sin clave 'results'"
        $script:failed++
    } else {
        Write-Host "[ OK ] /search JSON contiene 'results'"
    }
}

$resolveBody = Step-Get "GET /resolve" "$ApiBase/resolve?q=smoke+test&limit=3"
if ($null -ne $resolveBody) {
    if (-not (Test-JsonHasKey -Json $resolveBody -Key "results")) {
        Write-Host "[FAIL] /resolve JSON sin clave 'results'"
        $script:failed++
    } else {
        Write-Host "[ OK ] /resolve JSON contiene 'results'"
    }
}

Write-Host ""
if ($script:failed -gt 0) {
    Write-Host "=== SMOKE FALLIDO ($($script:failed) error(es)) ==="
    exit 1
}
Write-Host "=== SMOKE OK ==="
exit 0
