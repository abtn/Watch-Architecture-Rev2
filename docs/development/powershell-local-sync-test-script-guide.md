# PowerShell Local Sync and Test Script Guide

This guide governs programmer-side sync, migration, and test scripts generated for this repository. Every script is expected to be pasted into a terminal and run without editing. Optimize for paste fidelity, safe failure, and an unambiguous result.

## Mandatory script structure

Every non-trivial script has these five parts, in this order:

1. **Header** — state what it does, that the shell is PowerShell, and its preconditions.
2. **Preflight** — read current state, compare it with explicit expectations, and throw on mismatch.
3. **Action** — perform the requested sync, migration, or test operation.
4. **Verify** — assert that the final state matches the expected branch, commit, migration, and worktree state.
5. **Success line** — finish with a clear PASSED message.

A script is not complete without all five parts. Even a short command should not bypass a necessary safety preflight.

## Deliver scripts as files

For scripts longer than approximately ten lines, generate a .ps1 file using a single-quoted here-string. Do not send a long bare multiline paste.

Use this scaffold:

~~~powershell
$path = "$env:TEMP\<descriptive-name>.ps1"
@'
# Description, shell, and preconditions.
$ErrorActionPreference = 'Stop'
Set-Location '<expected-repository-root>'

# --- Preflight ---
<read-only checks; throw on any mismatch>

# --- Action ---
<sync, migration, or test commands>

# --- Verify ---
<assert exact final state>

Write-Host 'PASSED: <specific result>'
'@ | Set-Content -LiteralPath $path -Encoding UTF8

# Parse before executing.
$tokens = $null
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile(
    $path,
    [ref]$tokens,
    [ref]$errors
) | Out-Null
if ($errors.Count -gt 0) {
    $errors | Format-List
    throw 'PowerShell syntax errors found.'
}

& $path
~~~

The here-string opener and terminator must both begin in column zero. Do not put trailing text on either marker. Use a single-quoted here-string so embedded PowerShell variables, SQL, and JSON are not expanded while writing the file.

## Execute compound statements atomically

PowerShell control-flow blocks must be delivered and executed as complete syntactic units. Never split a compound statement across separate terminal submissions.

In particular:

- Keep `if { ... } else { ... }`, `if { ... } elseif { ... } else { ... }`, `try { ... } catch { ... } finally { ... }`, loops, and function definitions together in one complete script.
- Never tell the user to paste or run an `else`, `elseif`, `catch`, or `finally` block after the preceding `if` or `try` block has already been submitted and executed. PowerShell parses those as part of the same statement; once the first block has executed at the prompt, a later `else` or `finally` is a new command and fails.
- Do not split a compound statement at a prompt boundary, even if the continuation prompt (`>>`) is no longer visible. The full block must be in the same paste/submission.
- For cleanup and error handling, prefer a complete `.ps1` file created from a single-quoted here-string, parser-checked, and then invoked with `& $path`. Do not ask the user to execute the script body section-by-section.
- For a genuinely short interactive command, avoid compound control flow when possible. Use one complete expression or provide the entire `if/else` block in one code block for one paste.
- After writing a script file, parse the entire file with `[System.Management.Automation.Language.Parser]::ParseFile(...)` before executing it. Parser success is necessary but does not replace executing the file as a whole.

Correct — one complete submission:

~~~powershell
if ($LASTEXITCODE -eq 0) {
    Write-Host 'Operation succeeded.'
}
else {
    Write-Host 'Operation did not succeed.'
}
~~~

Incorrect — do not submit the `else` later:

~~~powershell
if ($LASTEXITCODE -eq 0) {
    Write-Host 'Operation succeeded.'
}
# A later, separate terminal submission beginning with else is invalid.
~~~

For scripts using cleanup, keep the complete `try/catch/finally` structure in the same `.ps1` file. A successful main body followed by a separately pasted `finally` does not provide cleanup.

## Seven safety rules

1. **Stop on errors.** Put $ErrorActionPreference = 'Stop' near the top. This does not reliably turn every native executable's non-zero exit into a terminating PowerShell error. Check $LASTEXITCODE immediately after every consequential native command, including Git, Docker, uv, pytest, Ruff, and Alembic.

   ~~~powershell
   uv run pytest -q
   if ($LASTEXITCODE -ne 0) { throw "pytest failed with exit code $LASTEXITCODE." }
   ~~~

2. **Preflight before mutation.** For repository sync scripts, verify the repository root, current branch, exact current HEAD, and clean worktree before switching branches or changing files. Fetching is read-only; branch switching, dependency installation, migrations, and test execution should happen only after their relevant preconditions pass.

3. **Never repair a dirty worktree automatically.** If git status --porcelain returns content, stop. Do not auto-stash, reset, restore, discard, or overwrite user changes.

4. **Verify exact commits, not branch names.** Compare the fetched remote ref with an expected literal SHA. A branch name alone does not establish that the intended code is present.

5. **Restore process environment.** Save any environment variables the script changes, especially DATABASE_URL, TEST_DATABASE_URL, and PGPASSWORD; restore them in a finally block even when a command fails.

6. **Use disposable databases.** Never point tests or migration checks at the persistent watch database. Create a uniquely named disposable PostgreSQL container with a dynamically assigned loopback port. Clean up only the exact container created by the script. Never use broad cleanup such as docker system prune, wildcard container deletion, or docker compose down -v.

7. **Avoid continuation backticks.** Prefer argument arrays or splatting. A trailing PowerShell backtick is easy to lose in a copied terminal block and can silently change command parsing.


## Keep local and remote Git references distinct

A local verification branch is not necessarily a branch on GitHub. Never derive a remote ref from the current local branch name unless the task explicitly establishes that they are identical.

Use separate variables with names that encode their roles:

~~~powershell
$expectedLocalBranch = 'feature-name-local-verify'
$remotePrBranch = 'feature-name'
$baseBranch = 'target-base'
$expectedPrHeadSha = '<full expected PR head SHA>'
$expectedBaseSha = '<full expected base SHA>'

$prRefspec = ('+refs/heads/{0}:refs/remotes/origin/{0}' -f $remotePrBranch)
$baseRefspec = ('+refs/heads/{0}:refs/remotes/origin/{0}' -f $baseBranch)
git fetch origin $prRefspec $baseRefspec
if ($LASTEXITCODE -ne 0) { throw 'Fetching PR and base branches failed.' }

$actualPrHead = (git rev-parse "refs/remotes/origin/$remotePrBranch")
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve the fetched PR branch.' }
if ($actualPrHead -ne $expectedPrHeadSha) {
    throw "PR head mismatch. Expected $expectedPrHeadSha; found $actualPrHead."
}

$actualBase = (git rev-parse "refs/remotes/origin/$baseBranch")
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve the fetched base branch.' }
if ($actualBase -ne $expectedBaseSha) {
    throw "Base mismatch. Expected $expectedBaseSha; found $actualBase."
}
~~~

The local preflight must compare the current branch with the variable $expectedLocalBranch. Fetch and remote-SHA checks must use $remotePrBranch and $baseBranch, never $expectedLocalBranch. Keep the full expected commit SHAs as independent assertions. For detached-base diagnostics, create a temporary detached worktree at the exact base SHA; do not switch the user's active worktree merely to run the comparison.

## PowerShell interpolation at punctuation boundaries

In an expandable string, a colon immediately after a variable name can be parsed as part of a scoped-variable reference. This is a parser error:

~~~powershell
throw "$Label: operation failed."
~~~

Use a subexpression or the format operator instead:

~~~powershell
throw "$($Label): operation failed."
throw ('{0}: operation failed.' -f $Label)
~~~

Apply the same rule whenever punctuation immediately follows an interpolated variable. Parse the generated .ps1 file with [System.Management.Automation.Language.Parser]::ParseFile() and stop on any parser error before executing it. A successful parse proves syntax only; retain all runtime preflight and postcondition checks.

## Docker: publish and verify a dynamic loopback port

For disposable PostgreSQL, use Docker's omitted-host-port syntax bound explicitly to IPv4 loopback:

~~~powershell
$dockerArgs = @(
    'run', '-d',
    '--name', $containerName,
    '--label', "watch.verification-id=$verificationId",
    '--env', "POSTGRES_DB=$databaseName",
    '--env', 'POSTGRES_USER=watch_test',
    '--env', 'POSTGRES_PASSWORD=watch_test_only',
    '-p', '127.0.0.1::5432',
    'pgvector/pgvector:pg16'
)
$containerId = & docker @dockerArgs
if ($LASTEXITCODE -ne 0) { throw 'Disposable PostgreSQL container creation failed.' }

$publishedPort = (& docker port $containerName '5432/tcp')
if ($LASTEXITCODE -ne 0) { throw 'Docker did not report a published PostgreSQL port.' }
if ($publishedPort -notmatch '^127\.0\.0\.1:(\d+)$') {
    throw "Unexpected PostgreSQL port mapping: $publishedPort"
}
$hostPort = [int]$Matches[1]
if ($hostPort -lt 1 -or $hostPort -gt 65535 -or $hostPort -eq 5432) {
    throw "Docker returned an invalid or non-dynamic host port: $hostPort"
}
~~~

Do not use 127.0.0.0:0:5432: Docker may create a running container without publishing a usable port. Do not assume that a successful docker run means port publication succeeded. Always inspect docker port, validate the exact loopback address and numeric port, and only then construct database URLs. Keep the container name unique and record that exact name/ID for cleanup. If port verification fails, enter the normal finally cleanup path and remove only the container created by this script.

## Windows path comparison — mandatory

Do not compare a path returned by Git or PowerShell directly to a hard-coded Windows path as raw strings. Git commonly emits forward slashes (for example, C:/work/repo), while a configured Windows path commonly uses backslashes (C:\work\repo). They can identify the same directory while a raw string comparison reports a false mismatch.

For repository-root checks, resolve both paths, normalize separators, and compare case-insensitively:

~~~powershell
$expectedRoot = 'C:\path\to\Watch-Architecture-Rev2'
$actualRoot = (git rev-parse --show-toplevel)
if ($LASTEXITCODE -ne 0) { throw 'Cannot identify the Git repository root.' }

$actualRoot = [System.IO.Path]::GetFullPath($actualRoot).TrimEnd('\', '/').Replace('/', '\')
$expectedRoot = [System.IO.Path]::GetFullPath($expectedRoot).TrimEnd('\', '/').Replace('/', '\')

if (-not [string]::Equals(
    $actualRoot,
    $expectedRoot,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "Wrong repository root. Expected '$expectedRoot'; found '$actualRoot'."
}
~~~

Use the same normalization whenever comparing resolved filesystem paths on Windows. Do not solve this by weakening or removing the repository-root check.

## GitHub HTTPS origin comparison — mandatory

Do not require a literal trailing `.git` in an HTTPS GitHub remote URL. Both `https://github.com/owner/repository` and `https://github.com/owner/repository.git` are valid forms; a trailing slash may also be present. Compare the parsed URI's scheme, host, and normalized repository path rather than comparing the raw strings.

For this repository, use an explicit expected repository identity:

~~~powershell
$originUrl = (git remote get-url origin)
if ($LASTEXITCODE -ne 0) { throw 'Cannot read the origin remote URL.' }

$originUri = $null
if (-not [System.Uri]::TryCreate($originUrl.Trim(), [System.UriKind]::Absolute, [ref]$originUri)) {
    throw "Origin is not a valid absolute URL: $originUrl"
}

$originPath = $originUri.AbsolutePath.TrimEnd('/')
if ($originPath.EndsWith('.git', [System.StringComparison]::OrdinalIgnoreCase)) {
    $originPath = $originPath.Substring(0, $originPath.Length - 4)
}

if (
    $originUri.Scheme -ne 'https' -or
    $originUri.Host -ne 'github.com' -or
    -not [string]::Equals(
        $originPath,
        '/abtn/Watch-Architecture-Rev2',
        [System.StringComparison]::OrdinalIgnoreCase
    )
) {
    throw "Unexpected origin URL: $originUrl"
}
~~~

Do not accept an arbitrary host or repository merely because its URL ends with the expected repository name. If SSH remotes are intentionally supported, handle that as a separate explicit accepted format rather than weakening this HTTPS check.

## Git fetch refspecs — safe construction

Do not escape the colon in a double-quoted refspec with a PowerShell backtick. Build the refspec with the format operator:

~~~powershell
$refspec = 'refs/heads/{0}:refs/remotes/origin/{0}' -f $targetBranch
git fetch origin $refspec
if ($LASTEXITCODE -ne 0) { throw 'Fetch failed.' }
~~~

## Alembic revision output — mandatory

Do not assume `alembic current` or `alembic heads` always prints a verbose `Rev: <revision>` line. Depending on the Alembic command/output mode, a valid revision can be printed as a plain line, for example:

~~~text
0019_rw1_world_memory (head)
~~~

A parser that accepts only `Rev:` will reject this valid output. Capture stdout and stderr, check the native exit code immediately, then parse both the verbose and normal forms. Ignore informational headings/log lines, and require the exact number of revision identifiers expected by the check.

For a database expected to have exactly one current revision:

~~~powershell
$currentOutput = & uv run alembic current 2>&1
$currentExitCode = $LASTEXITCODE
if ($currentExitCode -ne 0) {
    throw "Alembic current failed: $($currentOutput -join [Environment]::NewLine)"
}

$currentLines = @(
    $currentOutput |
        ForEach-Object { $_.ToString().Trim() } |
        Where-Object { $_ }
)

$currentRevisions = @(
    foreach ($line in $currentLines) {
        if ($line -match '^Rev:\s*(\S+)') {
            $Matches[1]
        }
        elseif ($line -match '^(\S+)\s+\([^)]*\)$') {
            $Matches[1]
        }
    }
)

if ($currentRevisions.Count -ne 1) {
    throw "Expected exactly one current Alembic revision. Found $($currentRevisions.Count). Output: $($currentOutput -join [Environment]::NewLine)"
}

$currentRevision = $currentRevisions[0]
if ($currentRevision -ne $expectedHeadRevision) {
    throw "Alembic current revision mismatch. Expected '$expectedHeadRevision'; found '$currentRevision'."
}
~~~

If the expected database state is a single head, separately parse `alembic heads` and assert exactly one head. Do not silently take the first result, accept multiple revisions, or treat an unparsed output as success. Keep the expected revision as an explicit value established for the task. If a supported Alembic version emits another format, inspect its actual output and extend the parser deliberately rather than weakening the assertion.

## Additional failure modes to inspect

- A local-only verification branch name reused accidentally as a remote PR branch; keep local, PR-head, and base branch variables separate.
- Expandable strings with punctuation immediately after a variable, such as "$Label: ..."; use "$($Label): ..." or the format operator.
- Docker -p mappings that bind the wrong loopback address or specify host port zero incorrectly; use 127.0.0.1::5432 and verify docker port before using the database.
- Assuming docker run success proves that the requested port was published.
- Raw string comparison between Git's forward-slash repository path and a Windows backslash path.
- Backtick-escaped colons in Git fetch refspecs.
- Literal origin URL comparisons that reject the optional `.git` suffix or trailing slash.
- Origin checks that compare only a URL suffix instead of validating scheme, host, and repository path.
- Doubled braces such as {{ or }}, often introduced by templating.
- Bash-style backslash line continuations; they are not PowerShell continuations.
- Literal \n where actual newline characters or a here-string are required.
- Missing $LASTEXITCODE checks after native commands.
- Double-quoted here-strings where variable expansion was not intended.
- Indented here-string terminators.
- Cleanup that can match containers or volumes not created by the current script.
- A success message that can run after a failed native command.

## Pre-send checklist

Before presenting a generated script, verify each item:

- [ ] Local verification branch, remote PR branch, and base branch are represented by separate variables and independently verified against expected SHAs.
- [ ] Expandable strings do not place punctuation such as a colon immediately after an unbraced variable name.
- [ ] Docker PostgreSQL uses 127.0.0.1::5432; the published port is queried and validated before a database URL is built.
- [ ] The introduction identifies PowerShell as the shell.
- [ ] A script longer than approximately ten lines is delivered through the file-in-here-string scaffold.
- [ ] $ErrorActionPreference = 'Stop' is present.
- [ ] Preflight checks read and validate the expected repository, branch, HEAD, and worktree state where relevant.
- [ ] Every consequential native command is followed immediately by a $LASTEXITCODE check.
- [ ] No doubled braces, Bash continuations, or accidental literal newline escapes remain.
- [ ] Here-string markers begin in column zero.
- [ ] Every compound control-flow statement is complete and remains in one script file or one terminal submission; no `else`, `catch`, or `finally` is provided as a later standalone paste.
- [ ] The complete script is parser-checked and invoked as a whole, not executed section-by-section.
- [ ] No destructive Git command is used unless explicitly requested and authorized.
- [ ] Database-backed checks use a disposable database and narrowly scoped cleanup.
- [ ] Repository-root comparisons normalize slash direction and use a case-insensitive Windows comparison.
- [ ] Git fetch refspecs use safe string construction without backtick escaping.
- [ ] GitHub HTTPS origin validation parses the URL and validates scheme, host, and normalized repository path, accepting optional `.git` and trailing slash.
- [ ] Every compound control-flow statement is complete and remains in one script file or one terminal submission; no `else`, `catch`, or `finally` is provided as a later standalone paste.
- [ ] The complete script is parser-checked and invoked as a whole, not executed section-by-section.
- [ ] The final line is an unambiguous PASSED success message.

If an item fails, correct the script or split the workflow into smaller checkpoints.

## Worked example: safe branch sync

The following is an example only. Replace the illustrative repository path, branch names, and SHA with values established for the specific task before generating a user-facing script.

~~~powershell
$path = "$env:TEMP\sync-target-branch.ps1"
@'
# Sync one local branch to one verified remote commit.
# Shell: PowerShell.
# Preconditions: expected repository, expected current branch, clean worktree.
$ErrorActionPreference = 'Stop'
Set-Location 'C:\path\to\Watch-Architecture-Rev2'

$expectedRoot = 'C:\path\to\Watch-Architecture-Rev2'
$expectedCurrent = 'source-branch'
$expectedCurrentSha = 'fedcba9876543210fedcba9876543210fedcba98'
$targetBranch = 'target-branch'
$expectedSha = '0123456789abcdef0123456789abcdef01234567'

# --- Preflight ---
$actualRoot = (git rev-parse --show-toplevel)
if ($LASTEXITCODE -ne 0) { throw 'Cannot identify the Git repository root.' }
$actualRoot = [System.IO.Path]::GetFullPath($actualRoot).TrimEnd('\', '/').Replace('/', '\')
$expectedRoot = [System.IO.Path]::GetFullPath($expectedRoot).TrimEnd('\', '/').Replace('/', '\')
if (-not [string]::Equals($actualRoot, $expectedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Wrong repository root. Expected '$expectedRoot'; found '$actualRoot'."
}

$currentBranch = (git branch --show-current)
if ($LASTEXITCODE -ne 0) { throw 'Cannot identify the current branch.' }
if ($currentBranch -ne $expectedCurrent) {
    throw "Wrong current branch. Expected $expectedCurrent; found $currentBranch."
}

$currentSha = (git rev-parse HEAD)
if ($LASTEXITCODE -ne 0) { throw 'Cannot identify the current HEAD.' }
if ($currentSha -ne $expectedCurrentSha) { throw "Unexpected current HEAD: $currentSha" }

$status = (git status --porcelain)
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect the worktree.' }
if ($status) { throw 'Worktree is dirty. Aborting without changes.' }

# --- Fetch and verify target ---
$refspec = 'refs/heads/{0}:refs/remotes/origin/{0}' -f $targetBranch
git fetch origin $refspec
if ($LASTEXITCODE -ne 0) { throw 'Fetch failed.' }

$remoteSha = (git rev-parse "refs/remotes/origin/$targetBranch")
if ($LASTEXITCODE -ne 0) { throw 'Cannot read the fetched remote SHA.' }
if ($remoteSha -ne $expectedSha) { throw "Remote SHA mismatch: $remoteSha" }

# --- Switch ---
git show-ref --verify --quiet "refs/heads/$targetBranch"
$showRefExit = $LASTEXITCODE
if ($showRefExit -eq 0) {
    git switch $targetBranch
} elseif ($showRefExit -eq 1) {
    git switch --track -c $targetBranch "origin/$targetBranch"
} else {
    throw "git show-ref failed with exit code $showRefExit."
}
if ($LASTEXITCODE -ne 0) { throw 'Branch switch failed.' }

# --- Verify ---
$finalBranch = (git branch --show-current)
if ($LASTEXITCODE -ne 0) { throw 'Cannot verify the final branch.' }
if ($finalBranch -ne $targetBranch) { throw "Final branch mismatch: $finalBranch" }

$finalSha = (git rev-parse HEAD)
if ($LASTEXITCODE -ne 0) { throw 'Cannot verify final HEAD.' }
if ($finalSha -ne $expectedSha) { throw "Final HEAD mismatch: $finalSha" }

Write-Host "PASSED: on $targetBranch at $expectedSha"
'@ | Set-Content -LiteralPath $path -Encoding UTF8

$tokens = $null
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile(
    $path,
    [ref]$tokens,
    [ref]$errors
) | Out-Null
if ($errors.Count -gt 0) {
    $errors | Format-List
    throw 'PowerShell syntax errors found.'
}

& $path
~~~

## Governing principle

A script is a deliverable, not a suggestion. It should be safe to paste, fail closed when assumptions are wrong, preserve the user's state, and report success only after its assertions pass.
