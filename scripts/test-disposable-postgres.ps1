[CmdletBinding()]
param([string]$Image = "pgvector/pgvector:pg16", [switch]$SkipStaticChecks)
$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param([string]$Command, [string[]]$Arguments)
    Write-Host ""
    Write-Host ("> " + $Command + " " + ($Arguments -join " ")) -ForegroundColor Cyan
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw ("Command failed with exit code " + $LASTEXITCODE + ": " + $Command) }
}

if (-not (Test-Path (Join-Path (Get-Location).Path "alembic.ini"))) { throw "Run from repository root: alembic.ini not found." }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker CLI is required." }
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw "uv is required." }

$oldDatabaseUrl = $env:DATABASE_URL
$oldTestDatabaseUrl = $env:TEST_DATABASE_URL
$containerName = "watch-r7a-test-" + [guid]::NewGuid().ToString("N").Substring(0, 10)
$database = "watch_r7a_disposable"
$user = "watch_test"
$password = "watch_test_only"
$containerCreated = $false

try {
    Invoke-Checked -Command "docker" -Arguments @("run", "-d", "--name", $containerName, "-e", "POSTGRES_DB=$database", "-e", "POSTGRES_USER=$user", "-e", "POSTGRES_PASSWORD=$password", "-p", "127.0.0.1::5432", $Image)
    $containerCreated = $true
    $portMapping = (& docker port $containerName "5432/tcp").Trim()
    if ($LASTEXITCODE -ne 0 -or -not $portMapping) { throw "Could not determine disposable PostgreSQL host port." }
    $hostPort = ($portMapping -split ":")[-1]
    $databaseUrl = "postgresql+psycopg://" + $user + ":" + $password + "@127.0.0.1:" + $hostPort + "/" + $database
    if ($databaseUrl -match "/watch(?:\?|$)") { throw "Refusing to use persistent database 'watch'." }
    $env:DATABASE_URL = $databaseUrl
    $env:TEST_DATABASE_URL = $databaseUrl
    Write-Host "Disposable container: $containerName"
    Write-Host "Both DATABASE_URL and TEST_DATABASE_URL target the same disposable database: $database"

    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        & docker exec $containerName pg_isready -U $user -d $database *> $null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 2
    }
    if (-not $ready) { throw "PostgreSQL did not become ready within 120 seconds." }

    Invoke-Checked -Command "uv" -Arguments @("run", "alembic", "upgrade", "head")
    Invoke-Checked -Command "uv" -Arguments @("run", "alembic", "heads")
    if (-not $SkipStaticChecks) {
        Invoke-Checked -Command "uv" -Arguments @("run", "ruff", "check", "core", "tests", "migrations")
        Invoke-Checked -Command "uv" -Arguments @("run", "mypy", "core")
    }
    Invoke-Checked -Command "uv" -Arguments @("run", "pytest", "-q")
    Write-Host "Disposable PostgreSQL test run completed successfully." -ForegroundColor Green
}
finally {
    $env:DATABASE_URL = $oldDatabaseUrl
    $env:TEST_DATABASE_URL = $oldTestDatabaseUrl
    if ($containerCreated) {
        Write-Host "Removing disposable container $containerName..."
        & docker rm -f $containerName
        if ($LASTEXITCODE -ne 0) { Write-Warning "Could not remove container $containerName. Remove it manually." }
    }
}
