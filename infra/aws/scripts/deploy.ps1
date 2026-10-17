[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[^@\s]+@[^@\s]+\.[^@\s]+$')]
    [string]$NotificationEmail,

    [Parameter(Mandatory)]
    [ValidatePattern('^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$')]
    [string]$DuckDnsSubdomain,

    [Parameter(Mandatory)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$DuckDnsTokenFile,

    [Parameter(Mandatory)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$RuntimeEnvFile,

    [Parameter(Mandatory)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$ContainerArchivePath,

    [ValidateSet('t4g.small', 't4g.medium', 't3.small', 't3.medium')]
    [string]$InstanceType = 't4g.small',

    [ValidateRange(5, 100)]
    [decimal]$MonthlyBudgetUsd = 5,

    [string]$RuntimeRegion = 'sa-east-1',
    [string]$BillingRegion = 'us-east-1'
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$infraRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$generatedRoot = Join-Path $infraRoot '.generated'
New-Item -ItemType Directory -Force -Path $generatedRoot | Out-Null

$awsCommand = Get-Command aws -ErrorAction SilentlyContinue
if ($awsCommand) {
    $awsExe = $awsCommand.Source
} elseif (Test-Path -LiteralPath 'C:\Program Files\Amazon\AWSCLIV2\aws.exe') {
    $awsExe = 'C:\Program Files\Amazon\AWSCLIV2\aws.exe'
} else {
    throw 'AWS CLI v2 nao encontrado.'
}

function Invoke-Aws {
    param([Parameter(ValueFromRemainingArguments)][string[]]$Arguments)
    & $awsExe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "AWS CLI falhou: aws $($Arguments -join ' ')"
    }
}

function Get-StackOutput {
    param([string]$StackName, [string]$Region, [string]$OutputKey)
    $value = & $awsExe cloudformation describe-stacks --stack-name $StackName --region $Region `
        --query "Stacks[0].Outputs[?OutputKey=='$OutputKey'].OutputValue | [0]" --output text
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($value) -or $value -eq 'None') {
        throw "Saida $OutputKey nao encontrada na stack $StackName."
    }
    return $value.Trim()
}

function Write-RuntimeEnvironment {
    param(
        [string]$SourcePath,
        [string]$DestinationPath,
        [string]$AttachmentBucket,
        [string]$DuckDnsName,
        [string]$Region,
        [string]$AttachmentQueueUrl
    )

    $allowedNames = @(
        'FLASK_SECRET_KEY', 'JWT_SECRET_KEY', 'JWT_ACCESS_TOKEN_MINUTES',
        'JWT_REFRESH_TOKEN_DAYS', 'PASSWORD_RESET_TOKEN_MINUTES',
        'EMAILJS_TIMEOUT_SECONDS', 'FACE_VERIFICATION_MAX_COSINE_DISTANCE',
        'FACIAL_ATTEMPT_MAX_AGE_SECONDS', 'DATABASE_URL',
        'CLOUDINARY_CLOUD_NAME', 'CLOUDINARY_API_KEY', 'CLOUDINARY_API_SECRET',
        'EMAILJS_SERVICE_ID', 'EMAILJS_TEMPLATE_ID', 'EMAILJS_PUBLIC_KEY',
        'EMAILJS_PRIVATE_KEY', 'TOMTOM_API_KEY', 'TOMTOM_TIMEOUT_SECONDS',
        'BIOMETRIC_AWAY_POLICY', 'JOURNEY_DEFAULT_TIMEZONE',
        'JOURNEY_OPEN_GRACE_HOURS', 'JOURNEY_EARLY_TOLERANCE_MINUTES',
        'JOURNEY_LATE_TOLERANCE_MINUTES'
    )
    $values = [ordered]@{}
    foreach ($line in Get-Content -LiteralPath $SourcePath) {
        if ($line -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
            $name = $Matches[1]
            if ($allowedNames -contains $name) {
                $values[$name] = $Matches[2]
            }
        }
    }

    foreach ($requiredName in @('FLASK_SECRET_KEY', 'JWT_SECRET_KEY', 'DATABASE_URL')) {
        if (-not $values.Contains($requiredName) -or [string]::IsNullOrWhiteSpace($values[$requiredName])) {
            throw "$requiredName deve estar configurado no arquivo de ambiente local."
        }
    }
    if ($values['FLASK_SECRET_KEY'].Length -lt 32) {
        throw 'FLASK_SECRET_KEY deve ter ao menos 32 caracteres.'
    }
    if ($values['FLASK_SECRET_KEY'] -eq $values['JWT_SECRET_KEY']) {
        throw 'FLASK_SECRET_KEY e JWT_SECRET_KEY devem ser diferentes.'
    }
    if ($values['DATABASE_URL'] -match '(?i)(localhost|127\.0\.0\.1|host\.docker\.internal)') {
        throw 'DATABASE_URL de producao nao pode apontar para o computador local.'
    }

    $values['APP_ENV'] = 'production'
    $values['PORT'] = '5000'
    $values['CORS_ALLOWED_ORIGINS'] = "https://$DuckDnsName.duckdns.org"
    $values['ATTACHMENT_STORAGE_PROVIDER'] = 's3'
    $values['ATTACHMENT_S3_BUCKET'] = $AttachmentBucket
    $values['ATTACHMENT_S3_REGION'] = $Region
    $values['ATTACHMENT_SCANNER_PROVIDER'] = 'clamav'
    $values['CLAMAV_HOST'] = 'frequenia-clamav'
    $values['CLAMAV_PORT'] = '3310'
    $values['CLAMAV_TIMEOUT_SECONDS'] = '20'
    $values['ATTACHMENT_RETENTION_DAYS'] = '90'
    $values['ATTACHMENT_INFECTED_RETENTION_DAYS'] = '30'
    $values['ATTACHMENT_SCAN_MODE'] = 'async'
    $values['ATTACHMENT_QUEUE_PROVIDER'] = 'sqs'
    $values['ATTACHMENT_QUEUE_URL'] = $AttachmentQueueUrl
    $values['ATTACHMENT_QUEUE_VISIBILITY_SECONDS'] = '120'
    $values['ATTACHMENT_QUEUE_MAX_RECEIVES'] = '5'
    if (-not $values.Contains('BIOMETRIC_AWAY_POLICY')) {
        $values['BIOMETRIC_AWAY_POLICY'] = 'bloquear'
    }

    $lines = foreach ($entry in $values.GetEnumerator()) {
        "$($entry.Key)=$($entry.Value)"
    }
    [System.IO.File]::WriteAllLines(
        $DestinationPath,
        $lines,
        [System.Text.UTF8Encoding]::new($false)
    )
}

$awsVersion = (& $awsExe --version 2>&1 | Out-String)
if ($awsVersion -notmatch 'aws-cli/2\.') {
    throw "AWS CLI v2 e obrigatorio. Encontrado: $awsVersion"
}
$caller = (& $awsExe sts get-caller-identity --output json | ConvertFrom-Json)
if ($LASTEXITCODE -ne 0) { throw 'Falha ao confirmar a identidade AWS.' }
if ([string]$caller.Arn -match ':root$') {
    throw 'A publicacao recusa credenciais root. Use uma identidade temporaria com MFA e privilegio minimo.'
}
$account = [string]$caller.Account
$maskedAccount = ('*' * [Math]::Max(0, $account.Length - 4)) + $account.Substring([Math]::Max(0, $account.Length - 4))
Write-Output "Identidade AWS: conta $maskedAccount; principal $(([string]$caller.Arn -split '/')[-1])"

$runtimeBootstrapStack = 'frequenia-pilot-artifacts-sa'
$billingBootstrapStack = 'frequenia-pilot-artifacts-us'
$attachmentStack = 'frequenia-pilot-attachments'
$runtimeStack = 'frequenia-pilot-runtime'
$billingStack = 'frequenia-pilot-budget'

Invoke-Aws cloudformation deploy `
    --stack-name $runtimeBootstrapStack `
    --template-file (Join-Path $infraRoot 'bootstrap.yaml') `
    --region $RuntimeRegion `
    --parameter-overrides PublicApkDownloads=true `
    --tags Project=FrequenIA Environment=pilot CostControl=usd-5 `
    --no-fail-on-empty-changeset

Invoke-Aws cloudformation deploy `
    --stack-name $billingBootstrapStack `
    --template-file (Join-Path $infraRoot 'bootstrap.yaml') `
    --region $BillingRegion `
    --parameter-overrides PublicApkDownloads=false `
    --tags Project=FrequenIA Environment=pilot CostControl=usd-5 `
    --no-fail-on-empty-changeset

$runtimeBucket = Get-StackOutput $runtimeBootstrapStack $RuntimeRegion 'BucketName'
$billingBucket = Get-StackOutput $billingBootstrapStack $BillingRegion 'BucketName'

Invoke-Aws cloudformation deploy `
    --stack-name $attachmentStack `
    --template-file (Join-Path $infraRoot 'attachments.template.yaml') `
    --region $RuntimeRegion `
    --capabilities CAPABILITY_IAM `
    --parameter-overrides Environment=production `
    --tags Project=FrequenIA Environment=pilot CostControl=usd-5 `
    --no-fail-on-empty-changeset

$attachmentBucket = Get-StackOutput $attachmentStack $RuntimeRegion 'AttachmentBucketName'
$attachmentQueueUrl = Get-StackOutput $attachmentStack $RuntimeRegion 'AttachmentScanQueueUrl'
$attachmentPublisherPolicyArn = Get-StackOutput $attachmentStack $RuntimeRegion 'AttachmentPublisherPolicyArn'
$attachmentWorkerPolicyArn = Get-StackOutput $attachmentStack $RuntimeRegion 'AttachmentWorkerPolicyArn'
$runtimeEnvironmentPath = Join-Path $generatedRoot 'runtime.env'
Write-RuntimeEnvironment `
    -SourcePath (Resolve-Path $RuntimeEnvFile).Path `
    -DestinationPath $runtimeEnvironmentPath `
    -AttachmentBucket $attachmentBucket `
    -DuckDnsName $DuckDnsSubdomain `
    -Region $RuntimeRegion `
    -AttachmentQueueUrl $attachmentQueueUrl

Invoke-Aws ssm put-parameter --region $RuntimeRegion --name '/frequenia/pilot/duckdns-token' `
    --type SecureString --value "file://$((Resolve-Path $DuckDnsTokenFile).Path)" --overwrite
Invoke-Aws ssm put-parameter --region $RuntimeRegion --name '/frequenia/pilot/runtime-env' `
    --type SecureString --value "file://$runtimeEnvironmentPath" --overwrite

$containerArchive = Get-Item -LiteralPath (Resolve-Path $ContainerArchivePath).Path
$localArchiveSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $containerArchive.FullName).Hash.ToLowerInvariant()
$containerArchiveKey = "runtime/frequenia-arm64-$localArchiveSha256.tar.gz"
$remoteArchiveLength = & $awsExe s3api head-object `
    --bucket $runtimeBucket `
    --key $containerArchiveKey `
    --region $RuntimeRegion `
    --query Metadata.sha256 `
    --output text 2>$null
$remoteArchiveFound = $LASTEXITCODE -eq 0
if ($remoteArchiveFound -and ([string]$remoteArchiveLength).Trim() -eq $localArchiveSha256) {
    Write-Output 'Imagem ARM64 imutavel ja enviada com o mesmo SHA-256; reutilizando o objeto privado no S3.'
} else {
    Invoke-Aws s3 cp $containerArchive.FullName `
        "s3://$runtimeBucket/$containerArchiveKey" `
        --region $RuntimeRegion `
        --sse AES256 `
        --metadata "sha256=$localArchiveSha256" `
        --only-show-errors
}

$runtimePackaged = Join-Path $generatedRoot 'runtime.packaged.yaml'
Invoke-Aws cloudformation package `
    --template-file (Join-Path $infraRoot 'runtime.template.yaml') `
    --s3-bucket $runtimeBucket `
    --s3-prefix lambda-temp/runtime `
    --output-template-file $runtimePackaged `
    --region $RuntimeRegion
Invoke-Aws cloudformation validate-template --template-body "file://$runtimePackaged" --region $RuntimeRegion
Invoke-Aws cloudformation deploy `
    --stack-name $runtimeStack `
    --template-file $runtimePackaged `
    --region $RuntimeRegion `
    --capabilities CAPABILITY_IAM `
    --parameter-overrides `
        ArtifactBucketName=$runtimeBucket `
        AttachmentBucketName=$attachmentBucket `
        AttachmentScanQueueUrl=$attachmentQueueUrl `
        AttachmentPublisherPolicyArn=$attachmentPublisherPolicyArn `
        AttachmentWorkerPolicyArn=$attachmentWorkerPolicyArn `
        ContainerArchiveKey=$containerArchiveKey `
        DynamicDnsSubdomain=$DuckDnsSubdomain `
        InstanceType=$InstanceType `
        NotificationEmail=$NotificationEmail `
    --tags Project=FrequenIA Environment=pilot CostControl=usd-5 `
    --no-fail-on-empty-changeset

$instanceId = Get-StackOutput $runtimeStack $RuntimeRegion 'InstanceId'
$tableName = Get-StackOutput $runtimeStack $RuntimeRegion 'RuntimeTableName'
$tableArn = Get-StackOutput $runtimeStack $RuntimeRegion 'RuntimeTableArn'
$runtimeAlertTopicArn = Get-StackOutput $runtimeStack $RuntimeRegion 'RuntimeAlertTopicArn'
$operatorRoleName = Get-StackOutput $runtimeStack $RuntimeRegion 'OperatorRoleName'
$operatorRoleArn = Get-StackOutput $runtimeStack $RuntimeRegion 'OperatorRoleArn'
$denyPolicyArn = Get-StackOutput $runtimeStack $RuntimeRegion 'CostLockDenyPolicyArn'

$billingPackaged = Join-Path $generatedRoot 'billing.packaged.yaml'
Invoke-Aws cloudformation package `
    --template-file (Join-Path $infraRoot 'billing.template.yaml') `
    --s3-bucket $billingBucket `
    --s3-prefix lambda-temp/billing `
    --output-template-file $billingPackaged `
    --region $BillingRegion
Invoke-Aws cloudformation validate-template --template-body "file://$billingPackaged" --region $BillingRegion
Invoke-Aws cloudformation deploy `
    --stack-name $billingStack `
    --template-file $billingPackaged `
    --region $BillingRegion `
    --capabilities CAPABILITY_IAM `
    --parameter-overrides `
        NotificationEmail=$NotificationEmail `
        MonthlyBudgetUsd=$MonthlyBudgetUsd `
        TargetRegion=$RuntimeRegion `
        InstanceId=$instanceId `
        RuntimeTableName=$tableName `
        RuntimeTableArn=$tableArn `
        RuntimeAlertTopicArn=$runtimeAlertTopicArn `
        OperatorRoleName=$operatorRoleName `
        OperatorRoleArn=$operatorRoleArn `
        CostLockDenyPolicyArn=$denyPolicyArn `
    --tags Project=FrequenIA Environment=pilot CostControl=usd-5 `
    --no-fail-on-empty-changeset

$applicationUrl = Get-StackOutput $runtimeStack $RuntimeRegion 'ApplicationUrl'
$apkBaseUrl = Get-StackOutput $runtimeBootstrapStack $RuntimeRegion 'ApkBaseUrl'
Write-Output "Aplicacao: $applicationUrl"
Write-Output "APK: $($apkBaseUrl)frequenia-latest.apk"
Write-Output 'Confirme as tres assinaturas de e-mail SNS recebidas.'
