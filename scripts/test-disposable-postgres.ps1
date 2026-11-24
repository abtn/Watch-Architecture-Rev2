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

# Preserve both the value and whether each process variable existed. An unset
# variable and a variable set to an empty string are different states.
$trackedVariables = @("DATABASE_URL", "TEST_DATABASE_URL", "PGPASSWORD")
$processEnvironment = [System.Environment]::GetEnvironmentVariables("Process")
$originalEnvironment = @{}
foreach ($name in $trackedVariables) {
    $wasSet = $processEnvironment.Contains($name)
    $originalEnvironment[$name] = [pscustomobject]@{
        WasSet = $wasSet
        Value = if ($wasSet) { [string]$processEnvironment[$name] } else { $null }
    }
}

$containerName = "watch-local-test-" + [guid]::NewGuid().ToString("N").Substring(0, 10)
$database = "watch_local_disposable"
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
    if ($databaseUrl -match "/watch(?:[/?]|$)") { throw "Refusing to use persistent database 'watch'." }
    $env:DATABASE_URL = $databaseUrl
    $env:TEST_DATABASE_URL = $databaseUrl
    Write-Host "Disposable container: $containerName"
    Write-Host "Both database URLs target the isolated database: $database"

    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        & docker exec $containerName pg_isready -U $user -d $database *> $null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 2
    }
    if (-not $ready) { throw "PostgreSQL did not become ready within 120 seconds." }

    Invoke-Checked -Command "uv" -Arguments @("run", "alembic", "upgrade", "head")
    $headOutput = & uv run alembic heads
    if ($LASTEXITCODE -ne 0) { throw "Could not read Alembic heads." }
    $headLines = @($headOutput | Where-Object { $_.Trim() })
    if ($headLines.Count -ne 1) { throw "Expected exactly one Alembic head; found $($headLines.Count)." }
    $head = ($headLines[0].Trim() -split "\s+")[0]
    $currentOutput = & uv run alembic current
    if ($LASTEXITCODE -ne 0) { throw "Could not read the current Alembic revision." }
    $currentLines = @($currentOutput | Where-Object { $_.Trim() })
    if ($currentLines.Count -ne 1) { throw "Expected exactly one current Alembic revision; found $($currentLines.Count)." }
    $current = ($currentLines[0].Trim() -split "\s+")[0]
    if ($current -ne $head) { throw "Database revision '$current' does not match sole head '$head'." }

    if (-not $SkipStaticChecks) {
        Invoke-Checked -Command "uv" -Arguments @("run", "ruff", "check", "core", "tests", "migrations")
        Invoke-Checked -Command "uv" -Arguments @("run", "mypy", "core")
    }
    Invoke-Checked -Command "uv" -Arguments @("run", "pytest", "-q")
    Write-Host "Disposable PostgreSQL verification completed successfully." -ForegroundColor Green
}
finally {
    try {
        foreach ($name in $trackedVariables) {
            $saved = $originalEnvironment[$name]
            $environmentPath = "Env:\$name"
            if ($saved.WasSet) {
                Set-Item -LiteralPath $environmentPath -Value $saved.Value -ErrorAction Stop
            }
            else {
                $currentlySet = [System.Environment]::GetEnvironmentVariables("Process").Contains($name)
                if ($currentlySet) {
                    Remove-Item -LiteralPath $environmentPath -ErrorAction Stop
                }
            }
        }

        $restoredEnvironment = [System.Environment]::GetEnvironmentVariables("Process")
        foreach ($name in $trackedVariables) {
            $saved = $originalEnvironment[$name]
            $isSet = $restoredEnvironment.Contains($name)
            if ($isSet -ne $saved.WasSet) { throw "Environment-presence restoration failed for $name." }
            if ($isSet -and [string]$restoredEnvironment[$name] -cne $saved.Value) {
                throw "Environment-value restoration failed for $name."
            }
        }
        Write-Host "DATABASE_URL, TEST_DATABASE_URL, and PGPASSWORD restored exactly."
    }
    finally {
        if ($containerCreated) {
            Write-Host "Removing disposable container $containerName..."
            & docker rm -f $containerName
            if ($LASTEXITCODE -ne 0) { Write-Warning "Could not remove container $containerName. Remove it manually." }
        }
    }
}
