[CmdletBinding()]
param(
    [string]$StackName = "catalogo-prod",
    [string]$Region = "sa-east-1",
    [string]$StageName = "prod",
    [string]$AwsProfile = $env:AWS_PROFILE,
    [string]$CatalogSessionSecret = $env:CATALOG_SESSION_SECRET,
    [string]$RepresentativeJwtSecret = $env:CATALOG_REPRESENTATIVE_JWT_SECRET,
    [string]$AdminLoginEmail = $env:CATALOG_ADMIN_LOGIN_EMAIL,
    [string]$AdminLoginPassword = $env:CATALOG_ADMIN_LOGIN_PASSWORD,
    [string]$RepresentativeUsersJson = $env:CATALOG_REPRESENTATIVE_USERS_JSON,
    [string]$GoogleDriveFolderId = $env:CATALOG_GOOGLE_DRIVE_FOLDER_ID,
    [string]$GoogleDriveApiKey = $env:CATALOG_GOOGLE_DRIVE_API_KEY,
    [string]$CorsAllowOrigins = "https://catalog.invalid",
    [string]$MediaPrefix = "produtos/",
    [string]$MediaSource = "",
    [switch]$UseContainer,
    [switch]$PreflightOnly,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$frontendRoot = Join-Path $projectRoot "frontend"

if (-not [string]::IsNullOrWhiteSpace($AwsProfile)) {
    $env:AWS_PROFILE = $AwsProfile
}
$env:AWS_DEFAULT_REGION = $Region
$env:SAM_CLI_TELEMETRY = "0"

function Assert-Command {
    param([Parameter(Mandatory = $true)][string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Comando obrigatorio nao encontrado: $Name"
    }
}

function Assert-Secret {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [AllowEmptyString()][string]$Value
    )
    if ([string]::IsNullOrWhiteSpace($Value) -or $Value.Length -lt 32) {
        throw "$Name deve ter pelo menos 32 caracteres. Defina a variavel de ambiente correspondente."
    }
}

function Get-StackOutput {
    param([Parameter(Mandatory = $true)][string]$OutputKey)
    $query = "Stacks[0].Outputs[?OutputKey=='$OutputKey'].OutputValue"
    $value = & aws cloudformation describe-stacks `
        --stack-name $StackName `
        --region $Region `
        --query $query `
        --output text
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($value) -or $value -eq "None") {
        throw "Nao foi possivel obter o output $OutputKey da stack $StackName."
    }
    return $value.Trim()
}

Assert-Command "aws"
Assert-Command "sam"
$npmCommand = if ($IsWindows -or $env:OS -eq "Windows_NT") { "npm.cmd" } else { "npm" }
Assert-Command $npmCommand
Assert-Secret "CATALOG_SESSION_SECRET" $CatalogSessionSecret
Assert-Secret "CATALOG_REPRESENTATIVE_JWT_SECRET" $RepresentativeJwtSecret

if ([string]::IsNullOrWhiteSpace($AdminLoginEmail) -or [string]::IsNullOrWhiteSpace($AdminLoginPassword)) {
    throw "Defina CATALOG_ADMIN_LOGIN_EMAIL e CATALOG_ADMIN_LOGIN_PASSWORD para o deploy de producao."
}

if (-not [string]::IsNullOrWhiteSpace($RepresentativeUsersJson)) {
    try {
        $representatives = $RepresentativeUsersJson | ConvertFrom-Json
        if ($null -eq $representatives) {
            throw "JSON vazio"
        }
    }
    catch {
        throw "CATALOG_REPRESENTATIVE_USERS_JSON nao contem JSON valido: $($_.Exception.Message)"
    }
}

if ($UseContainer) {
    Assert-Command "docker"
    & docker info --format '{{.ServerVersion}}' | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker nao esta em execucao. Inicie o Docker Desktop antes do build em container."
    }
}

& aws sts get-caller-identity --region $Region --output json | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "As credenciais AWS nao estao configuradas ou nao sao validas."
}

& sam validate --lint --template-file (Join-Path $projectRoot "template.yaml") --region $Region
if ($LASTEXITCODE -ne 0) {
    throw "O template SAM nao passou na validacao."
}

if ($PreflightOnly) {
    Write-Host "Preflight AWS concluido sem criar recursos."
    return
}

Push-Location $projectRoot
try {
    if (-not $SkipTests) {
        & python -m pytest
        if ($LASTEXITCODE -ne 0) {
            throw "Os testes do backend falharam."
        }
    }

    Push-Location $frontendRoot
    try {
        & $npmCommand ci
        if ($LASTEXITCODE -ne 0) {
            throw "npm ci falhou."
        }
        $env:VITE_API_BASES = "/"
        & $npmCommand run build
        if ($LASTEXITCODE -ne 0) {
            throw "O build do frontend falhou."
        }
    }
    finally {
        Pop-Location
    }

    $samBuildArgs = @("build")
    if ($UseContainer) {
        $samBuildArgs += "--use-container"
    }
    & sam @samBuildArgs
    if ($LASTEXITCODE -ne 0) {
        throw "sam build falhou."
    }

    $parameterOverrides = @(
        "StageName=$StageName",
        "CorsAllowOrigins=$CorsAllowOrigins",
        "CatalogSessionSecret=$CatalogSessionSecret",
        "RepresentativeJwtSecret=$RepresentativeJwtSecret",
        "AdminLoginEmail=$AdminLoginEmail",
        "AdminLoginPassword=$AdminLoginPassword",
        "RepresentativeUsersJson=$RepresentativeUsersJson",
        "GoogleDriveFolderId=$GoogleDriveFolderId",
        "GoogleDriveApiKey=$GoogleDriveApiKey",
        "MediaPrefix=$MediaPrefix"
    )

    & sam deploy `
        --stack-name $StackName `
        --region $Region `
        --resolve-s3 `
        --capabilities CAPABILITY_IAM `
        --no-confirm-changeset `
        --no-fail-on-empty-changeset `
        --parameter-overrides @parameterOverrides
    if ($LASTEXITCODE -ne 0) {
        throw "sam deploy falhou."
    }

    $frontendBucket = Get-StackOutput "FrontendBucketName"
    $mediaBucket = Get-StackOutput "MediaBucketName"
    $distributionId = Get-StackOutput "CloudFrontDistributionId"
    $applicationUrl = Get-StackOutput "ApplicationUrl"

    & aws s3 sync (Join-Path $frontendRoot "dist") "s3://$frontendBucket" `
        --delete `
        --region $Region
    if ($LASTEXITCODE -ne 0) {
        throw "O upload do frontend falhou."
    }

    if (-not [string]::IsNullOrWhiteSpace($MediaSource)) {
        $resolvedMediaSource = (Resolve-Path $MediaSource).Path
        & aws s3 sync $resolvedMediaSource "s3://$mediaBucket/$MediaPrefix" --region $Region
        if ($LASTEXITCODE -ne 0) {
            throw "O upload das imagens falhou."
        }
    }

    & aws cloudfront create-invalidation `
        --distribution-id $distributionId `
        --paths "/*" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "A invalidacao do CloudFront falhou."
    }

    Write-Host ""
    Write-Host "Deploy concluido: $applicationUrl"
    Write-Host "Frontend bucket: $frontendBucket"
    Write-Host "Media bucket: $mediaBucket"
}
finally {
    Pop-Location
}
