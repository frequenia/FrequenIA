[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet('start', 'renew', 'stop', 'status')]
    [string]$Action,
    [string]$StackName = 'frequenia-pilot-runtime',
    [string]$Region = 'sa-east-1'
)

$ErrorActionPreference = 'Stop'
$awsCommand = Get-Command aws -ErrorAction SilentlyContinue
$awsExe = if ($awsCommand) { $awsCommand.Source } else { 'C:\Program Files\Amazon\AWSCLIV2\aws.exe' }
if (-not (Test-Path -LiteralPath $awsExe)) { throw 'AWS CLI v2 nao encontrado.' }

$functionName = & $awsExe cloudformation describe-stacks --stack-name $StackName --region $Region `
    --query "Stacks[0].Outputs[?OutputKey=='SessionControlFunctionName'].OutputValue | [0]" --output text
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($functionName) -or $functionName -eq 'None') {
    throw 'Funcao de controle de sessao nao encontrada.'
}

$payloadPath = [System.IO.Path]::GetTempFileName()
$responsePath = [System.IO.Path]::GetTempFileName()
try {
    @{ action = $Action } | ConvertTo-Json -Compress | Set-Content -LiteralPath $payloadPath -Encoding utf8NoBOM
    & $awsExe lambda invoke --region $Region --function-name $functionName `
        --cli-binary-format raw-in-base64-out --payload "fileb://$payloadPath" $responsePath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao invocar o controle de sessao.' }
    Get-Content -Raw -LiteralPath $responsePath | ConvertFrom-Json | ConvertTo-Json -Depth 8
} finally {
    Remove-Item -LiteralPath $payloadPath, $responsePath -Force -ErrorAction SilentlyContinue
}
