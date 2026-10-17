[CmdletBinding()]
param(
    [switch]$ConfirmUnlock,
    [string]$RuntimeStackName = 'frequenia-pilot-runtime',
    [string]$RuntimeRegion = 'sa-east-1'
)

$ErrorActionPreference = 'Stop'
if (-not $ConfirmUnlock) {
    throw 'Use -ConfirmUnlock depois de conferir que um novo mes UTC comecou.'
}

$awsCommand = Get-Command aws -ErrorAction SilentlyContinue
$awsExe = if ($awsCommand) { $awsCommand.Source } else { 'C:\Program Files\Amazon\AWSCLIV2\aws.exe' }
if (-not (Test-Path -LiteralPath $awsExe)) { throw 'AWS CLI v2 nao encontrado.' }

function Get-Output([string]$key) {
    $value = & $awsExe cloudformation describe-stacks --stack-name $RuntimeStackName --region $RuntimeRegion `
        --query "Stacks[0].Outputs[?OutputKey=='$key'].OutputValue | [0]" --output text
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($value) -or $value -eq 'None') {
        throw "Saida $key nao encontrada."
    }
    return $value.Trim()
}

$tableName = Get-Output 'RuntimeTableName'
$roleName = Get-Output 'OperatorRoleName'
$policyArn = Get-Output 'CostLockDenyPolicyArn'
$keyPath = [System.IO.Path]::GetTempFileName()
$valuesPath = [System.IO.Path]::GetTempFileName()
try {
    @{ pk = @{ S = 'CONTROL' } } | ConvertTo-Json -Depth 4 -Compress | `
        Set-Content -LiteralPath $keyPath -Encoding utf8NoBOM
    $itemJson = & $awsExe dynamodb get-item --region $RuntimeRegion --table-name $tableName `
        --key "file://$keyPath" --consistent-read --output json
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao consultar a trava de custo.' }
    $item = $itemJson | ConvertFrom-Json
    $lockedMonth = $item.Item.locked_month.S
    if ([string]::IsNullOrWhiteSpace($lockedMonth)) {
        throw 'Nao existe mes de bloqueio registrado.'
    }
    $currentMonth = [DateTime]::UtcNow.ToString('yyyy-MM')
    if ([string]::CompareOrdinal($currentMonth, $lockedMonth) -le 0) {
        throw "A trava de $lockedMonth so pode ser removida em um mes UTC posterior."
    }

    @{ ':false' = @{ BOOL = $false }; ':now' = @{ N = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds().ToString() } } | `
        ConvertTo-Json -Depth 4 -Compress | Set-Content -LiteralPath $valuesPath -Encoding utf8NoBOM
    & $awsExe dynamodb update-item --region $RuntimeRegion --table-name $tableName `
        --key "file://$keyPath" `
        --update-expression 'SET cost_lock = :false, updated_at = :now REMOVE lock_reason, locked_month' `
        --expression-attribute-values "file://$valuesPath" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao remover a trava na tabela de controle.' }

    $attached = & $awsExe iam list-attached-role-policies --role-name $roleName `
        --query "contains(AttachedPolicies[].PolicyArn, '$policyArn')" --output text
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao consultar politicas da role operacional.' }
    if ($attached.Trim().ToLowerInvariant() -eq 'true') {
        & $awsExe iam detach-role-policy --role-name $roleName --policy-arn $policyArn
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao desanexar a politica de bloqueio.' }
    }
} finally {
    Remove-Item -LiteralPath $keyPath, $valuesPath -Force -ErrorAction SilentlyContinue
}

Write-Output "Trava de $lockedMonth removida para $currentMonth."
