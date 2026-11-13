[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet('policy', 'profile', 'disable', 'readiness')]
    [string]$Action,
    [string]$BaseUrl = 'https://frequenia.duckdns.org'
)

$ErrorActionPreference = 'Stop'

if ($BaseUrl -ne 'https://frequenia.duckdns.org') {
    throw 'Este operador aceita somente a URL HTTPS fixa do piloto.'
}

function ConvertFrom-PrivateSecureString {
    param([Parameter(Mandatory)][Security.SecureString]$Value)
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try {
        [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

function Invoke-PilotJson {
    param(
        [Parameter(Mandatory)][ValidateSet('GET', 'POST')][string]$Method,
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][Microsoft.PowerShell.Commands.WebRequestSession]$Session,
        [hashtable]$Payload
    )
    $arguments = @{
        Uri         = "$BaseUrl$Path"
        Method      = $Method
        WebSession  = $Session
        ErrorAction = 'Stop'
    }
    if ($null -ne $Payload) {
        $arguments.ContentType = 'application/json'
        $arguments.Body = $Payload | ConvertTo-Json -Compress
    }
    Invoke-RestMethod @arguments
}

Write-Host 'Use uma conta administrador ou RH vinculada a empresa do piloto.'
Write-Host 'CPF e senha nao serao exibidos nem gravados pelo script.'
$cpfSecure = Read-Host 'CPF' -AsSecureString
$passwordSecure = Read-Host 'Senha' -AsSecureString
$cpf = ConvertFrom-PrivateSecureString $cpfSecure
$password = ConvertFrom-PrivateSecureString $passwordSecure
$webSession = [Microsoft.PowerShell.Commands.WebRequestSession]::new()

try {
    $login = Invoke-PilotJson -Method POST -Path '/login' -Session $webSession -Payload @{
        cpf = $cpf
        senha = $password
    }
    if ($login.ok -ne $true) {
        throw 'Login nao confirmado.'
    }

    $login.access_token = $null
    $login.refresh_token = $null
    $cpf = $null
    $password = $null
    $cpfSecure.Dispose()
    $passwordSecure.Dispose()

    if ($Action -eq 'policy') {
        $result = Invoke-PilotJson -Method POST `
            -Path '/api/admin/governanca-biometrica/politicas' `
            -Session $webSession `
            -Payload @{
                versao = 'pilot-dev-1.1.0'
                referencia_base_legal = 'LGPD-art11-I-consentimento-especifico-piloto-dev-v1.1'
                versao_aviso = '1.1'
                referencia_documental = 'DECISAO-PILOTO-BIOMETRIA-LGPD-v1.1-2026-10-25'
                canal_atendimento = 'frequenia@gmail.com'
                retencao_dias = 1825
                vigencia_inicio = '2026-10-25T00:00:00-03:00'
                vigencia_fim = '2026-11-24T00:00:00-03:00'
            }
        if (-not $result.politica) { throw 'API nao confirmou a politica.' }
        Write-Output 'policy_created=1 version=pilot-dev-1.1.0 retention_days=1825'
    } elseif ($Action -eq 'profile') {
        $result = Invoke-PilotJson -Method POST `
            -Path '/api/admin/governanca-biometrica/perfis' `
            -Session $webSession `
            -Payload @{
                versao = 'pilot-dev-1.1.0'
                modelo = 'ArcFace'
                versao_modelo = 'deepface-0.0.99'
                dimensao = 512
                metrica = 'cosine_distance'
                limiar = 0.68
                versao_liveness = 'deepface-0.0.99'
                vigencia_inicio = '2026-10-25T00:00:00-03:00'
                vigencia_fim = '2026-11-24T00:00:00-03:00'
                referencia_relatorio = 'FASE-33-v1.1-2026-10-25'
            }
        if (-not $result.perfil) { throw 'API nao confirmou o perfil.' }
        Write-Output 'profile_created=1 version=pilot-dev-1.1.0 threshold=0.68'
    } elseif ($Action -eq 'disable') {
        $result = Invoke-PilotJson -Method POST `
            -Path '/api/admin/governanca-biometrica/perfis/desativar' `
            -Session $webSession `
            -Payload @{
                versao = 'pilot-dev-1.1.0'
                motivo_codigo = 'rollback_operacional'
            }
        if (-not $result.perfil) { throw 'API nao confirmou a desativacao.' }
        Write-Output 'profile_disabled=1 version=pilot-dev-1.1.0'
    } else {
        $result = Invoke-PilotJson -Method GET `
            -Path '/api/admin/governanca-biometrica/readiness' `
            -Session $webSession
        $policy = [int]($result.dependencies.policy -eq $true)
        $profile = [int]($result.dependencies.profile -eq $true)
        $compatible = [int]($result.dependencies.compatible -eq $true)
        Write-Output "readiness_policy=$policy readiness_profile=$profile readiness_compatible=$compatible"
    }
} catch {
    Write-Error 'Operacao nao concluida. Nenhum segredo foi exibido.'
    exit 1
} finally {
    $cpf = $null
    $password = $null
    if ($cpfSecure) { $cpfSecure.Dispose() }
    if ($passwordSecure) { $passwordSecure.Dispose() }
    $login = $null
    $webSession.Cookies = [Net.CookieContainer]::new()
}
