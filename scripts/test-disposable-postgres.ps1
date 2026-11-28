[CmdletBinding()]
param(
    [string]$Image = "pgvector/pgvector:pg16",
    [switch]$SkipStaticChecks,
    [string[]]$PytestArgs = @()
)
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
$trackedVariables = @(
    "DATABASE_URL",
    "TEST_DATABASE_URL",
    "DATABASE_ADMIN_URL",
    "WATCH_MIGRATOR_PASSWORD",
    "WATCH_RUNTIME_PASSWORD",
    "PGPASSWORD"
)
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
$adminUser = "watch_test"
$adminPassword = "watch_test_only"
$migratorPassword = [guid]::NewGuid().ToString("N")
$runtimePassword = [guid]::NewGuid().ToString("N")
$containerCreated = $false

try {
    Invoke-Checked -Command "docker" -Arguments @("run", "-d", "--name", $containerName, "-e", "POSTGRES_DB=$database", "-e", "POSTGRES_USER=$adminUser", "-e", "POSTGRES_PASSWORD=$adminPassword", "-p", "127.0.0.1::5432", $Image)
    $containerCreated = $true
    $portMapping = (& docker port $containerName "5432/tcp").Trim()
    if ($LASTEXITCODE -ne 0 -or -not $portMapping) { throw "Could not determine disposable PostgreSQL host port." }
    $hostPort = ($portMapping -split ":")[-1]
    $adminDatabaseUrl = "postgresql+psycopg://" + $adminUser + ":" + $adminPassword + "@127.0.0.1:" + $hostPort + "/" + $database
    $migratorDatabaseUrl = "postgresql+psycopg://watch_migrator:" + $migratorPassword + "@127.0.0.1:" + $hostPort + "/" + $database
    if ($adminDatabaseUrl -match "/watch(?:[/?]|$)" -or $migratorDatabaseUrl -match "/watch(?:[/?]|$)") {
        throw "Refusing to use persistent database 'watch'."
    }

    $env:DATABASE_ADMIN_URL = $adminDatabaseUrl
    $env:TEST_DATABASE_URL = $adminDatabaseUrl
    $env:DATABASE_URL = $migratorDatabaseUrl
    $env:WATCH_MIGRATOR_PASSWORD = $migratorPassword
    $env:WATCH_RUNTIME_PASSWORD = $runtimePassword

    Write-Host "Disposable container: $containerName"
    Write-Host "DATABASE_ADMIN_URL and TEST_DATABASE_URL use the isolated bootstrap administrator."
    Write-Host "DATABASE_URL uses watch_migrator for Alembic CLI migrations."

    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        & docker exec $containerName pg_isready -U $adminUser -d $database *> $null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 2
    }
    if (-not $ready) { throw "PostgreSQL did not become ready within 120 seconds." }

    Invoke-Checked -Command "uv" -Arguments @("run", "python", "scripts/provision_database_roles.py")
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

    $pytestArguments = @("run", "pytest", "-q") + $PytestArgs
    if ($PytestArgs.Count -gt 0) {
        Write-Host ("Running targeted pytest selection: " + ($PytestArgs -join " "))
    }
    else {
        Write-Host "No pytest selectors supplied; running the full suite."
    }
    Invoke-Checked -Command "uv" -Arguments $pytestArguments
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
        Write-Host "All tracked database and role-bootstrap environment variables restored exactly."
    }
    finally {
        if ($containerCreated) {
            $volumeNames = @()
            $mountInspectionSucceeded = $false
            $mountOutput = & docker inspect --format '{{json .Mounts}}' $containerName
            if ($LASTEXITCODE -eq 0) {
                $mounts = @($mountOutput | ConvertFrom-Json)
                $volumeNames = @(
                    $mounts |
                        Where-Object { $_.Type -eq "volume" -and $_.Name } |
                        ForEach-Object { [string]$_.Name }
                )
                $mountInspectionSucceeded = $true
            }
            else {
                Write-Warning "Could not inspect disposable container mounts; removal will still be attempted, but volume cleanup cannot be fully verified."
            }

            Write-Host "Removing disposable container and its anonymous volumes..."
            & docker rm -fv $containerName
            if ($LASTEXITCODE -ne 0) { throw "Could not remove disposable container and attached anonymous volumes: $containerName" }

            $remainingContainers = & docker container ls -a --filter "name=^/$containerName$" --format "{{.ID}}"
            if ($LASTEXITCODE -ne 0) { throw "Could not verify disposable container removal." }
            if (@($remainingContainers | Where-Object { $_.Trim() }).Count -gt 0) {
                throw "Disposable container remains after cleanup: $containerName"
            }

            if (-not $mountInspectionSucceeded) {
                throw "Container was removed, but attached anonymous-volume cleanup could not be verified."
            }

            $remainingVolumes = & docker volume ls --format "{{.Name}}"
            if ($LASTEXITCODE -ne 0) { throw "Could not verify Docker volume cleanup." }
            foreach ($volumeName in $volumeNames) {
                if (@($remainingVolumes | Where-Object { $_.Trim() -eq $volumeName }).Count -gt 0) {
                    throw "Disposable PostgreSQL volume remains after cleanup: $volumeName"
                }
            }
            Write-Host "Verified disposable container and all attached anonymous volumes are removed."
        }
    }
}
