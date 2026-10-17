[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$ApkPath,
    [Parameter(Mandatory)]
    [ValidatePattern('^[0-9A-Za-z._-]+$')]
    [string]$Version,
    [string]$StackName = 'frequenia-pilot-artifacts-sa',
    [string]$Region = 'sa-east-1'
)

$ErrorActionPreference = 'Stop'
$awsCommand = Get-Command aws -ErrorAction SilentlyContinue
$awsExe = if ($awsCommand) { $awsCommand.Source } else { 'C:\Program Files\Amazon\AWSCLIV2\aws.exe' }
if (-not (Test-Path -LiteralPath $awsExe)) { throw 'AWS CLI v2 nao encontrado.' }

$bucket = & $awsExe cloudformation describe-stacks --stack-name $StackName --region $Region `
    --query "Stacks[0].Outputs[?OutputKey=='BucketName'].OutputValue | [0]" --output text
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($bucket) -or $bucket -eq 'None') {
    throw 'Bucket de APK nao encontrado.'
}

$resolvedApk = (Resolve-Path -LiteralPath $ApkPath).Path
$versionedKey = "apk/frequenia-$Version.apk"
$latestKey = 'apk/frequenia-latest.apk'
$contentType = 'application/vnd.android.package-archive'

foreach ($key in $versionedKey, $latestKey) {
    & $awsExe s3 cp $resolvedApk "s3://$bucket/$key" --region $Region --sse AES256 `
        --content-type $contentType --content-disposition 'attachment' --only-show-errors
    if ($LASTEXITCODE -ne 0) { throw "Falha ao enviar $key." }
}

$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $resolvedApk).Hash.ToLowerInvariant()
$hashPath = [System.IO.Path]::GetTempFileName()
try {
    "$hash  frequenia-$Version.apk" | Set-Content -LiteralPath $hashPath -Encoding ascii
    & $awsExe s3 cp $hashPath "s3://$bucket/apk/frequenia-$Version.apk.sha256" --region $Region `
        --sse AES256 --content-type 'text/plain' --only-show-errors
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao enviar o checksum.' }
} finally {
    Remove-Item -LiteralPath $hashPath -Force -ErrorAction SilentlyContinue
}

Write-Output "APK: https://$bucket.s3.$Region.amazonaws.com/$latestKey"
Write-Output "SHA256: $hash"
