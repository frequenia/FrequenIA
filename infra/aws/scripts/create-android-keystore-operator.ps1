[CmdletBinding()]
param(
    [string]$KeystorePath = '.secrets/android/frequenia-pilot-release.jks',
    [string]$Alias = 'frequenia-pilot-release'
)

$ErrorActionPreference = 'Stop'
$resolvedParent = Split-Path -Parent (Join-Path (Get-Location) $KeystorePath)
if (-not (Test-Path -LiteralPath $resolvedParent)) {
    New-Item -ItemType Directory -Path $resolvedParent -Force | Out-Null
}
$absolutePath = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $KeystorePath))
if (Test-Path -LiteralPath $absolutePath) {
    throw 'Keystore ja existe; nenhum arquivo foi sobrescrito.'
}

function ConvertFrom-PrivateSecureString {
    param([Parameter(Mandatory)][Security.SecureString]$Value)
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}

$passwordSecure = Read-Host 'Senha NOVA da chave release (guarde fora deste computador)' -AsSecureString
$password = ConvertFrom-PrivateSecureString $passwordSecure
if ($password.Length -lt 12) { throw 'Use uma senha com pelo menos 12 caracteres.' }
$env:FREQUENIA_KEYSTORE_PASSWORD = $password
try {
    & keytool -genkeypair -v -storetype PKCS12 -keystore $absolutePath `
        -alias $Alias -keyalg RSA -keysize 4096 -validity 3650 `
        -dname 'CN=Equipe FrequenIA, OU=Piloto, O=Equipe FrequenIA, C=BR' `
        -storepass:env FREQUENIA_KEYSTORE_PASSWORD `
        -keypass:env FREQUENIA_KEYSTORE_PASSWORD
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao criar a chave release.' }
    Write-Output "keystore_created=1 alias=$Alias path=$absolutePath"
} finally {
    Remove-Item Env:FREQUENIA_KEYSTORE_PASSWORD -ErrorAction SilentlyContinue
    $password = $null
    $passwordSecure.Dispose()
}
