[CmdletBinding()]
param(
    [string]$DeviceId,
    [string]$BaseUrl,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$mobileRoot = Join-Path $projectRoot "mobile"
$envFile = Join-Path $projectRoot ".env"

if (-not (Test-Path -LiteralPath $envFile)) {
    throw "Arquivo .env não encontrado. Copie .env.example para .env e configure os segredos locais."
}

$flutterCommand = Get-Command flutter -ErrorAction SilentlyContinue
if (-not $flutterCommand) {
    $fallbackFlutter = "C:\Flutter\flutter\bin\flutter.bat"
    if (-not (Test-Path -LiteralPath $fallbackFlutter)) {
        throw "Flutter não encontrado no PATH nem em $fallbackFlutter."
    }
    $flutterExecutable = $fallbackFlutter
} else {
    $flutterExecutable = $flutterCommand.Source
}

Push-Location $projectRoot
try {
    $composeArguments = @("compose", "up", "--detach")
    if (-not $SkipBuild) {
        $composeArguments += "--build"
    }
    & docker @composeArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose encerrou com código $LASTEXITCODE."
    }

    $healthUrl = "http://localhost:5013/health"
    $deadline = (Get-Date).AddMinutes(4)
    do {
        try {
            $response = Invoke-WebRequest -Uri $healthUrl -TimeoutSec 5 -UseBasicParsing
            if ($response.StatusCode -eq 200) {
                break
            }
        } catch {
            Start-Sleep -Seconds 3
        }
    } while ((Get-Date) -lt $deadline)

    if (-not $response -or $response.StatusCode -ne 200) {
        & docker compose logs --tail 100 backend
        throw "O backend não ficou saudável em até quatro minutos."
    }

    $devicesJson = & $flutterExecutable devices --machine
    if ($LASTEXITCODE -ne 0) {
        throw "Não foi possível consultar os dispositivos Flutter."
    }
    $devices = @($devicesJson | ConvertFrom-Json)
    $androidDevices = @(
        $devices | Where-Object {
            $_.targetPlatform -like "android*" -or $_.platformType -eq "android"
        }
    )

    if ($DeviceId) {
        $selectedDevice = $androidDevices | Where-Object { $_.id -eq $DeviceId } | Select-Object -First 1
        if (-not $selectedDevice) {
            throw "O dispositivo Android '$DeviceId' não está disponível. Execute 'flutter devices'."
        }
    } else {
        $selectedDevice = $androidDevices | Select-Object -First 1
    }

    if (-not $selectedDevice) {
        throw "Nenhum dispositivo Android disponível. Inicie um emulador ou conecte um celular com depuração USB."
    }

    if (-not $BaseUrl) {
        if ($selectedDevice.emulator -eq $true) {
            $BaseUrl = "http://10.0.2.2:5013"
        } else {
            throw "Para celular físico, informe -BaseUrl http://IP_DA_MAQUINA:5013."
        }
    }

    Push-Location $mobileRoot
    try {
        & $flutterExecutable pub get
        if ($LASTEXITCODE -ne 0) {
            throw "flutter pub get encerrou com código $LASTEXITCODE."
        }
        & $flutterExecutable run -d $selectedDevice.id `
            --dart-define=APP_ENV=development `
            --dart-define=BASE_URL=$BaseUrl
        if ($LASTEXITCODE -ne 0) {
            throw "flutter run encerrou com código $LASTEXITCODE."
        }
    } finally {
        Pop-Location
    }
} finally {
    Pop-Location
}
