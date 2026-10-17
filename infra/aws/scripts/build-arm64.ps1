[CmdletBinding()]
param(
    [string]$ImageName = "frequenia:pilot",
    [string]$OutputPath = "infra/aws/dist/frequenia-arm64.tar.gz"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$outputFullPath = [System.IO.Path]::GetFullPath((Join-Path $projectRoot $OutputPath))
$outputDirectory = Split-Path -Parent $outputFullPath
$tarPath = [System.IO.Path]::ChangeExtension($outputFullPath, $null)
if ($tarPath.EndsWith(".tar")) {
    $tarPath = $tarPath
} else {
    $tarPath = "$tarPath.tar"
}

if ((Test-Path -LiteralPath $outputFullPath) -or (Test-Path -LiteralPath $tarPath)) {
    throw "O caminho de saida ja existe. Informe um OutputPath novo para preservar o artefato anterior."
}

New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null

$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
$dockerInWsl = -not [bool]$dockerCommand
if ($dockerInWsl -and -not (Get-Command wsl -ErrorAction SilentlyContinue)) {
    throw "Docker com buildx e necessario para criar a imagem ARM64."
}

function Invoke-LocalDocker {
    param([Parameter(ValueFromRemainingArguments)][string[]]$DockerArguments)
    if ($dockerInWsl) {
        & wsl -d Ubuntu -u root -- docker @DockerArguments
    } else {
        & $dockerCommand.Source @DockerArguments
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Docker falhou durante a validacao ARM64."
    }
}

function Convert-ToWslPath {
    param([string]$WindowsPath)
    $absolute = [System.IO.Path]::GetFullPath($WindowsPath)
    if ($absolute -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "Caminho Windows invalido para o WSL."
    }
    return '/mnt/' + $Matches[1].ToLowerInvariant() + '/' + $Matches[2].Replace('\', '/')
}

Push-Location $projectRoot
try {
    Invoke-LocalDocker buildx inspect | Out-Null
    Invoke-LocalDocker buildx build --platform linux/arm64 --file Dockerfile.arm64 --tag $ImageName --load .

    $architecture = Invoke-LocalDocker image inspect $ImageName --format '{{.Architecture}}'
    if (($architecture | Out-String).Trim() -ne 'arm64') {
        throw "A imagem gerada nao possui arquitetura arm64."
    }

    $imageDigest = (Invoke-LocalDocker image inspect $ImageName --format '{{.Id}}' | Out-String).Trim()
    if ($imageDigest -notmatch '^sha256:[0-9a-f]{64}$') {
        throw "Digest da imagem ARM64 invalido."
    }

    $containerId = (Invoke-LocalDocker create --platform linux/arm64 $ImageName | Out-String).Trim()
    if ($containerId -notmatch '^[0-9a-f]{64}$') { throw "Container de inventario invalido." }
    $inventoryRoot = Join-Path $outputDirectory (".inventory-" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $inventoryRoot | Out-Null
    try {
        $dockerInventoryPath = $inventoryRoot
        if ($dockerInWsl) {
            $dockerInventoryPath = Convert-ToWslPath $inventoryRoot
        }
        Invoke-LocalDocker cp "${containerId}:/app" $dockerInventoryPath
        $inventoryApp = Join-Path $inventoryRoot 'app'
        $files = @(Get-ChildItem -LiteralPath $inventoryApp -File -Recurse | ForEach-Object {
            '/app/' + $_.FullName.Substring($inventoryApp.Length).TrimStart('\', '/').Replace('\', '/')
        })
    } finally {
        Invoke-LocalDocker rm $containerId | Out-Null
        if ((Test-Path -LiteralPath $inventoryRoot) -and
            ([System.IO.Path]::GetFullPath($inventoryRoot)).StartsWith(([System.IO.Path]::GetFullPath($outputDirectory)).TrimEnd('\') + '\')) {
            Remove-Item -LiteralPath $inventoryRoot -Recurse -Force
        }
    }
    if ($files.Count -eq 0) { throw "Inventario da imagem ARM64 vazio." }
    $requiredFiles = @(
        '/app/supabase/migrations/026_biometric_governance_lifecycle.sql',
        '/app/services/daily_journey.py',
        '/app/services/biometric_governance.py',
        '/app/tools/dispatch_attachment_scan_jobs.py',
        '/app/tools/run_attachment_scan_worker.py'
    )
    foreach ($requiredFile in $requiredFiles) {
        if ($files -notcontains $requiredFile) {
            throw "Arquivo obrigatorio ausente da imagem: $requiredFile"
        }
    }
    $forbiddenFiles = @($files | Where-Object { $_ -match '(?i)(^|/)(\.env($|\.)|\.secrets|credentials|__pycache__|output|tmp|dump|backup|\.git)(/|$)' })
    if ($forbiddenFiles.Count -gt 0) {
        throw "Imagem ARM64 contem caminho proibido: $($forbiddenFiles[0])"
    }

    Write-Output "Execucao ARM64 nao realizada neste host; somente inventario e arquitetura validados."
    $dockerTarPath = $tarPath
    if ($dockerInWsl) {
        $dockerTarPath = Convert-ToWslPath $tarPath
    }
    Invoke-LocalDocker save --output $dockerTarPath $ImageName

    @'
import gzip
import shutil
import sys

source, destination = sys.argv[1:3]
with open(source, "rb") as src, gzip.open(destination, "wb", compresslevel=6) as dst:
    shutil.copyfileobj(src, dst, length=1024 * 1024)
'@ | python - $tarPath $outputFullPath
    if ($LASTEXITCODE -ne 0) { throw "Falha ao compactar a imagem ARM64." }
} finally {
    Pop-Location
    if (Test-Path -LiteralPath $tarPath) {
        Remove-Item -LiteralPath $tarPath -Force
    }
}

$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $outputFullPath).Hash.ToLowerInvariant()
Write-Output "Imagem: $outputFullPath"
Write-Output "SHA256: $hash"
Write-Output "Digest de configuracao: $imageDigest"
Write-Output "Arquivos no /app: $($files.Count)"

