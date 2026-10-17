[CmdletBinding()]
param(
    [int]$Port = 5013
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:APP_ENV = "homologation"
$env:PORT = [string]$Port

Push-Location $projectRoot
try {
    Write-Host "FrequenIA disponível em http://localhost:$Port"
    Write-Host "Mantenha esta janela aberta. Pressione Ctrl+C para encerrar."
    python app.py
    if ($LASTEXITCODE -ne 0) {
        throw "O backend encerrou com código $LASTEXITCODE."
    }
} finally {
    Pop-Location
}
