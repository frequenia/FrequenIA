[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$secretDirectory = Join-Path $projectRoot '.secrets'
$outputPath = Join-Path $secretDirectory 'duckdns-token.txt'

$secureToken = Read-Host 'Cole o NOVO token do DuckDNS e pressione Enter' -AsSecureString
$credential = [System.Management.Automation.PSCredential]::new('duckdns', $secureToken)
$plainToken = $credential.GetNetworkCredential().Password

try {
    if ($plainToken -notmatch '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$') {
        throw 'O valor informado nao tem o formato esperado de token do DuckDNS.'
    }

    New-Item -ItemType Directory -Force -Path $secretDirectory | Out-Null
    [System.IO.File]::WriteAllText(
        $outputPath,
        $plainToken,
        [System.Text.UTF8Encoding]::new($false)
    )
    Write-Output 'Token salvo com seguranca no arquivo local ignorado pelo Git.'
} finally {
    $plainToken = $null
    $credential = $null
    $secureToken = $null
}
