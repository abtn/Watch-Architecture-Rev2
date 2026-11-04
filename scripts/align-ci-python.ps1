[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

function Invoke-UvChecked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Label,

        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    Write-Host ""
    Write-Host "=== $Label ===" -ForegroundColor Cyan
    & $script:uvExecutable @Arguments
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        throw "$Label failed with uv exit code $exitCode."
    }
}

function Resolve-RepositoryPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$Root
    )

    $candidate = $Path
    if (-not [System.IO.Path]::IsPathRooted($candidate)) {
        $candidate = Join-Path $Root $candidate
    }

    return [System.IO.Path]::GetFullPath($candidate).TrimEnd(
        [char[]]@(
            [System.IO.Path]::DirectorySeparatorChar,
            [System.IO.Path]::AltDirectorySeparatorChar
        )
    )
}

function Test-PythonRequestMatch {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Request,

        [Parameter(Mandatory = $true)]
        [string]$ActualVersion
    )

    $requestedParts = $Request.Split(".")
    $actualParts = $ActualVersion.Split(".")

    if ($actualParts.Count -lt $requestedParts.Count) {
        return $false
    }

    for ($index = 0; $index -lt $requestedParts.Count; $index++) {
        if ($requestedParts[$index] -ne $actualParts[$index]) {
            return $false
        }
    }

    return $true
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venvPath = [System.IO.Path]::GetFullPath((Join-Path $repoRoot ".venv"))
$venvComparisonPath = Resolve-RepositoryPath -Path $venvPath -Root $repoRoot
$workflowPath = Join-Path $repoRoot ".github/workflows/ci.yml"
$pyprojectPath = Join-Path $repoRoot "pyproject.toml"
$lockPath = Join-Path $repoRoot "uv.lock"

$previousVirtualEnv = $env:VIRTUAL_ENV
$previousProjectEnvironment = $env:UV_PROJECT_ENVIRONMENT
$previousUvPython = $env:UV_PYTHON
$previousCondaPrefix = $env:CONDA_PREFIX

$backupPath = $null
$backupCreated = $false
$completed = $false

try {
    # 1. Repository and tool preflight.
    foreach ($requiredPath in @($workflowPath, $pyprojectPath, $lockPath)) {
        if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
            throw "Required project file is missing: $requiredPath"
        }
    }

    $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
    if ($null -eq $uvCommand -or $uvCommand.CommandType -ne "Application") {
        throw "A standalone uv executable was not found on PATH. Install uv outside the project .venv and retry."
    }

    $script:uvExecutable = [System.IO.Path]::GetFullPath($uvCommand.Source)
    $uvExecutablePrefix = $venvComparisonPath + [System.IO.Path]::DirectorySeparatorChar
    if ($script:uvExecutable.StartsWith(
        $uvExecutablePrefix,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "uv is installed inside the project .venv that this script needs to rebuild. Install uv outside .venv and retry."
    }

    $uvVersionOutput = & $script:uvExecutable --version
    if ($LASTEXITCODE -ne 0) {
        throw "Could not read the installed uv version."
    }
    $uvVersion = ([string]($uvVersionOutput | Select-Object -Last 1)).Trim()
    Write-Host "Repository: $repoRoot"
    Write-Host "uv: $uvVersion"

    if (-not [string]::IsNullOrWhiteSpace($previousCondaPrefix)) {
        throw "A Conda environment is active. Deactivate Conda before rebuilding the project .venv."
    }

    if (-not [string]::IsNullOrWhiteSpace($previousVirtualEnv)) {
        $activeEnvironment = Resolve-RepositoryPath -Path $previousVirtualEnv -Root $repoRoot
        if (-not [string]::Equals(
            $activeEnvironment,
            $venvComparisonPath,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            throw "The active VIRTUAL_ENV is not this repository's .venv: $previousVirtualEnv"
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($previousProjectEnvironment)) {
        $configuredEnvironment = Resolve-RepositoryPath -Path $previousProjectEnvironment -Root $repoRoot
        if (-not [string]::Equals(
            $configuredEnvironment,
            $venvComparisonPath,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            throw "UV_PROJECT_ENVIRONMENT points outside this repository's .venv: $previousProjectEnvironment"
        }
    }

    # Read the requested version from the exact command used by CI.
    $workflowText = Get-Content -LiteralPath $workflowPath -Raw
    $pythonMatch = [System.Text.RegularExpressions.Regex]::Match(
        $workflowText,
        '(?m)^\s*run:\s*uv\s+python\s+install\s+(?<version>\d+\.\d+(?:\.\d+)?)\s*$'
    )

    if (-not $pythonMatch.Success) {
        throw "Could not identify a one-line 'uv python install VERSION' command in .github/workflows/ci.yml. Update this script if the CI step changes."
    }

    $pythonRequest = $pythonMatch.Groups["version"].Value
    Write-Host "CI Python request: $pythonRequest"

    # 2. Install the same managed-Python request as CI.
    Invoke-UvChecked -Label "Install CI-requested Python" -Arguments @(
        "python", "install", $pythonRequest
    )

    # 3. Preserve the existing environment before rebuilding.
    if (Test-Path -LiteralPath $venvPath) {
        if (-not (Test-Path -LiteralPath $venvPath -PathType Container)) {
            throw "The expected .venv path exists but is not a directory: $venvPath"
        }

        $backupSuffix = Get-Date -Format "yyyyMMdd-HHmmss"
        $backupPath = Join-Path $repoRoot (".venv.backup-" + $backupSuffix)

        if (Test-Path -LiteralPath $backupPath) {
            $backupPath = Join-Path $repoRoot (
                ".venv.backup-" + $backupSuffix + "-" + [guid]::NewGuid().ToString("N").Substring(0, 8)
            )
        }

        Write-Host "Preserving the existing environment at: $backupPath" -ForegroundColor Yellow
        Move-Item -LiteralPath $venvPath -Destination $backupPath -ErrorAction Stop
        $backupCreated = $true
    }
    else {
        Write-Host "No existing .venv was found; a new one will be created."
    }

    # The old .venv has been moved aside. Remove active-environment hints
    # temporarily so python find cannot select the old interpreter.
    Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
    Remove-Item Env:UV_PYTHON -ErrorAction SilentlyContinue

    $basePythonOutput = & $script:uvExecutable python find $pythonRequest --managed-python
    $findExitCode = $LASTEXITCODE

    if ($findExitCode -ne 0) {
        throw "uv could not find its managed Python installation for $pythonRequest."
    }

    $basePython = ([string]($basePythonOutput | Select-Object -Last 1)).Trim()

    if ([string]::IsNullOrWhiteSpace($basePython) -or
        -not (Test-Path -LiteralPath $basePython -PathType Leaf)) {
        throw "uv python find did not return a valid interpreter path: $basePython"
    }

    $baseVersionOutput = & $basePython -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not inspect the selected managed Python interpreter."
    }

    $baseVersion = ([string]($baseVersionOutput | Select-Object -Last 1)).Trim()

    if (-not (Test-PythonRequestMatch -Request $pythonRequest -ActualVersion $baseVersion)) {
        throw "uv selected Python $baseVersion, which does not satisfy the CI request $pythonRequest."
    }

    Write-Host "Selected managed interpreter: $basePython"
    Write-Host "Selected Python version:      $baseVersion"

    # 4. Recreate .venv with the selected managed interpreter.
    Invoke-UvChecked -Label "Create a fresh project virtual environment" -Arguments @(
        "venv", $venvPath, "--python", $basePython
    )

    # Explicitly direct project commands to this repository's .venv.
    $env:UV_PROJECT_ENVIRONMENT = $venvPath
    $env:VIRTUAL_ENV = $venvPath

    Invoke-UvChecked -Label "Synchronize locked project dependencies" -Arguments @(
        "sync", "--locked"
    )

    Invoke-UvChecked -Label "Check installed dependency consistency" -Arguments @(
        "pip", "check"
    )

    # 5. Verify the interpreter selected by uv run.
    $verificationOutput = & uv run python -c "import sys; print('.'.join(map(str, sys.version_info[:3]))); print(sys.executable)"
    if ($LASTEXITCODE -ne 0 -or $verificationOutput.Count -lt 2) {
        throw "Could not verify the recreated project environment with uv run."
    }

    $actualVersion = ([string]$verificationOutput[0]).Trim()
    $actualExecutable = [System.IO.Path]::GetFullPath(
        ([string]$verificationOutput[1]).Trim()
    )

    if (-not (Test-PythonRequestMatch -Request $pythonRequest -ActualVersion $actualVersion)) {
        throw "The recreated environment uses Python $actualVersion, not the CI request $pythonRequest."
    }

    $venvPrefix = $venvComparisonPath + [System.IO.Path]::DirectorySeparatorChar
    if (-not $actualExecutable.StartsWith(
        $venvPrefix,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "uv run selected an interpreter outside the project .venv: $actualExecutable"
    }

    Write-Host ""
    Write-Host "Verified project interpreter:" -ForegroundColor Green
    Write-Host "Python:      $actualVersion"
    Write-Host "Executable:  $actualExecutable"

    if ($backupCreated) {
        Write-Host ""
        Write-Host "Previous environment retained for rollback:" -ForegroundColor Yellow
        Write-Host $backupPath
    }

    $completed = $true
    Write-Host ""
    Write-Host "Python environment alignment completed successfully." -ForegroundColor Green
    Write-Host "No project dependencies or lockfile entries were changed."
}
finally {
    # If creation or synchronization failed, preserve the partial new
    # environment for inspection and restore the previous .venv.
    if (-not $completed -and $backupCreated -and
        (Test-Path -LiteralPath $backupPath)) {
        try {
            if (Test-Path -LiteralPath $venvPath) {
                $failedSuffix = Get-Date -Format "yyyyMMdd-HHmmss"
                $failedPath = Join-Path $repoRoot (".venv.failed-" + $failedSuffix)
                if (Test-Path -LiteralPath $failedPath) {
                    $failedPath = Join-Path $repoRoot (
                        ".venv.failed-" + $failedSuffix + "-" + [guid]::NewGuid().ToString("N").Substring(0, 8)
                    )
                }

                Move-Item -LiteralPath $venvPath -Destination $failedPath -ErrorAction Stop
                Write-Warning "Partial environment preserved for inspection at: $failedPath"
            }

            Move-Item -LiteralPath $backupPath -Destination $venvPath -ErrorAction Stop
            Write-Warning "The previous .venv has been restored."
        }
        catch {
            Write-Warning "Automatic rollback was incomplete. Previous environment backup remains at: $backupPath"
            Write-Warning $_
        }
    }

    if ($null -eq $previousVirtualEnv) {
        Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
    }
    else {
        $env:VIRTUAL_ENV = $previousVirtualEnv
    }

    if ($null -eq $previousProjectEnvironment) {
        Remove-Item Env:UV_PROJECT_ENVIRONMENT -ErrorAction SilentlyContinue
    }
    else {
        $env:UV_PROJECT_ENVIRONMENT = $previousProjectEnvironment
    }

    if ($null -eq $previousUvPython) {
        Remove-Item Env:UV_PYTHON -ErrorAction SilentlyContinue
    }
    else {
        $env:UV_PYTHON = $previousUvPython
    }
}
