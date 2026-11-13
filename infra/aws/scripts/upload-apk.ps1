[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$ApkPath,
    [Parameter(Mandatory)]
    [ValidatePattern('^[0-9A-Za-z._-]+$')]
    [string]$Version,
    [string]$StackName = 'frequenia-pilot-artifacts-sa',
    [string]$Region = 'sa-east-1',
    [string]$Profile = 'frequenia-pilot-publish'
)

$ErrorActionPreference = 'Stop'
$awsCommand = Get-Command aws -ErrorAction SilentlyContinue
$awsExe = if ($awsCommand) { $awsCommand.Source } else { 'C:\Program Files\Amazon\AWSCLIV2\aws.exe' }
if (-not (Test-Path -LiteralPath $awsExe)) { throw 'AWS CLI v2 nao encontrado.' }

$bucket = & $awsExe cloudformation describe-stacks --stack-name $StackName --region $Region --profile $Profile `
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
        --profile $Profile --content-type $contentType --content-disposition 'attachment' --only-show-errors
    if ($LASTEXITCODE -ne 0) { throw "Falha ao enviar $key." }
}

$stream = [System.IO.File]::OpenRead($resolvedApk)
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
$hashPath = [System.IO.Path]::GetTempFileName()
try {
    "$hash  frequenia-$Version.apk" | Set-Content -LiteralPath $hashPath -Encoding ascii
    & $awsExe s3 cp $hashPath "s3://$bucket/apk/frequenia-$Version.apk.sha256" --region $Region `
        --profile $Profile --sse AES256 --content-type 'text/plain' --only-show-errors
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao enviar o checksum.' }
} finally {
    Remove-Item -LiteralPath $hashPath -Force -ErrorAction SilentlyContinue
}

Write-Output "APK: https://$bucket.s3.$Region.amazonaws.com/$latestKey"
Write-Output "SHA256: $hash"
