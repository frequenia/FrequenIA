[CmdletBinding()]
param(
    [string]$KeystorePath = '.secrets/android/frequenia-pilot-release.jks',
    [string]$Alias = 'frequenia-pilot-release',
    [string]$BaseUrl = 'https://frequenia.duckdns.org'
)

$ErrorActionPreference = 'Stop'
if ($BaseUrl -ne 'https://frequenia.duckdns.org') {
    throw 'O APK release aceita somente a URL HTTPS fixa do piloto.'
}
$absolutePath = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $KeystorePath))
if (-not (Test-Path -LiteralPath $absolutePath -PathType Leaf)) {
    throw 'Chave release nao encontrada. Execute create-android-keystore-operator.ps1.'
}

function ConvertFrom-PrivateSecureString {
    param([Parameter(Mandatory)][Security.SecureString]$Value)
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}

$passwordSecure = Read-Host 'Senha da chave release' -AsSecureString
$password = ConvertFrom-PrivateSecureString $passwordSecure
$env:FREQUENIA_ANDROID_KEYSTORE_PATH = $absolutePath
$env:FREQUENIA_ANDROID_KEY_ALIAS = $Alias
$env:FREQUENIA_ANDROID_STORE_PASSWORD = $password
$env:FREQUENIA_ANDROID_KEY_PASSWORD = $password
try {
    Push-Location mobile
    try {
        & flutter build apk --release `
            --dart-define=APP_ENV=production `
            --dart-define="BASE_URL=$BaseUrl"
        if ($LASTEXITCODE -ne 0) { throw 'Build release do APK falhou.' }
    } finally {
        Pop-Location
    }
    $apk = (Resolve-Path 'mobile/build/app/outputs/flutter-apk/app-release.apk').Path
    $stream = [System.IO.File]::OpenRead($apk)
    try {
        $sha256 = [System.Security.Cryptography.SHA256]::Create()
        try {
            $hash = [System.BitConverter]::ToString($sha256.ComputeHash($stream)).Replace('-', '').ToLowerInvariant()
        } finally {
            $sha256.Dispose()
        }
    } finally {
        $stream.Dispose()
    }
    Write-Output "release_apk_created=1 version=1.0.1+2 sha256=$hash path=$apk"
} finally {
    Remove-Item Env:FREQUENIA_ANDROID_KEYSTORE_PATH -ErrorAction SilentlyContinue
    Remove-Item Env:FREQUENIA_ANDROID_KEY_ALIAS -ErrorAction SilentlyContinue
    Remove-Item Env:FREQUENIA_ANDROID_STORE_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:FREQUENIA_ANDROID_KEY_PASSWORD -ErrorAction SilentlyContinue
    $password = $null
    $passwordSecure.Dispose()
}
