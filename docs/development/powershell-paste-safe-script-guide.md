# Writing paste-safe PowerShell scripts for terminal use

This guide defines how an assistant or contributor must format Windows PowerShell scripts when the Operator is expected to copy a response and paste it directly into a terminal.

The goal is not merely to produce valid PowerShell. The goal is to produce a **complete, unambiguous, correctly delimited script whose formatting survives copying from chat or Markdown into PowerShell**.

This guide is a repository workflow convention. It does not authorize a script to change project state, use a database, delete resources, commit, push, or merge. Those actions still require the authority and safety checks in [\`AGENTS.md\`](../../AGENTS.md).

## 1. Choose the delivery form deliberately

Use one of these forms:

1. **Direct-paste script** — for a short, self-contained operation that is safe to run as one block.
2. **Save-then-run script** — for long scripts, multi-stage verification, repeated use, or scripts where exact content matters.
3. **Command sequence** — only when each command is intentionally run and inspected separately. Label the boundaries and expected result of each step.

Prefer save-then-run for long scripts. A long script pasted directly into an interactive shell is more exposed to accidental partial selection, terminal paste limits, bracketed-paste behavior, and chat-rendering damage.

Do not combine unrelated operations into one large script merely to reduce the number of copy/paste steps.

## 2. Direct-paste format

A direct-paste script must follow all of these rules:

- Put the **entire executable block in one fenced code block** marked \`powershell\`.
- Do not put explanatory prose, Markdown bullets, line numbers, terminal prompts, or output inside the code block.
- Do not include PowerShell prompts such as \`PS C:\\>\` or \`(watch) PS ...>\`.
- Do not use ellipses (\`...\`), placeholders, or comments such as “continue the same way” in an executable script.
- Do not split one logical script across multiple code fences.
- Keep one command or one logical statement per line.
- Use actual newline characters. Do not represent line breaks with the two literal characters \`\\n\`.
- Do not wrap lines visually by inserting manual breaks in the middle of a quoted string, path, URL, variable name, parameter, or operator.
- Do not add Markdown quote markers (\`>\`) or list prefixes (\`-\`, \`1.\`) to executable lines.
- Do not place prose after a command on the same line.
- Avoid requiring the Operator to remove or repair any characters before execution.

A suitable shape is:

\`\`\`powershell
$ErrorActionPreference = "Stop"

$projectRoot = (Get-Location).Path
Write-Host "Project root: $projectRoot"

git status --short --branch
if ($LASTEXITCODE -ne 0) {
    throw "git status failed."
}
\`\`\`

The opening and closing fences are presentation only. The Operator copies only the lines between them.

## 3. Braces, parentheses, and brackets

PowerShell uses delimiters with different meanings. Do not treat them as decorative formatting.

- \`{ ... }\` defines a script block, function, loop, conditional body, or other language block.
- \`( ... )\` groups an expression or invokes a command in an expression context.
- \`@(...)\` creates an array.
- \`@{...}\` creates a hashtable.
- \`$(...)\` performs a subexpression inside a string or expression.
- \`@'\` and \`'@\` delimit a literal here-string.
- \`@"\` and \`"@\` delimit an expandable here-string.

Rules:

1. Every opening delimiter must have exactly one matching closing delimiter of the same kind.
2. Nest delimiters in a readable order. Close the innermost block before the outer block.
3. Put the closing brace for a multi-line block on its own line, aligned with the statement that opened the block.
4. Do not omit a closing brace because the code “looks complete” in a chat preview.
5. Do not add an extra outer \`{ ... }\` around a script unless that script-block scope is intentional.
6. Do not replace PowerShell delimiters with JSON-style escaped forms such as \`\\{\` or \`\\}\`.
7. Never use typographic or full-width substitutes for ASCII delimiters: \`{ }\`, \`( )\`, and \`[ ]\` must be literal ASCII characters.

Correct:

\`\`\`powershell
if ($LASTEXITCODE -ne 0) {
    throw "The command failed."
}

foreach ($item in $items) {
    Write-Host $item
}
\`\`\`

Incorrect:

\`\`\`powershell
if ($LASTEXITCODE -ne 0) {{
    throw "The command failed."
}
\`\`\`

The incorrect example has an extra opening brace and cannot be parsed.

## 4. Quoting and variable expansion

Use quoting intentionally:

- Use single quotes for literal strings whenever interpolation is not required.
- Use double quotes only when PowerShell variable or subexpression expansion is intended.
- Escape an embedded single quote inside a single-quoted string by doubling it: \`'it''s literal'\`.
- Do not assume backslash escapes quotes in PowerShell. PowerShell's escape character is the backtick.
- Avoid backticks for line continuation. They are easy to lose when copying and must be the final character on the line.
- Do not accidentally interpolate variables in paths, SQL, JSON, regular expressions, or here-strings.

Examples:

\`\`\`powershell
$literal = 'The value is $HOME; it will not expand.'
$expanded = "The home directory is $HOME."
\`\`\`

For JSON or other text containing many quotation marks, prefer a single-quoted here-string and pass the result to a serializer or file-writing command rather than hand-escaping several layers.

## 5. Here-strings and embedded files

Use a here-string when a script must write a multi-line file or preserve structured text.

Rules:

- The opening marker (\`@'\` or \`@"\`) must be the final characters on its line.
- The closing marker (\`'@\` or \`"@\`) must begin at the start of its own line; do not indent it.
- Do not append comments or other characters to either marker line.
- Use \`@'\` for literal content. Use \`@"\` only when variable expansion inside the content is intentional.
- Do not put Markdown fences inside the here-string unless those fences are intended to become part of the generated file.
- Do not confuse the here-string terminator with a normal quote.

Example — write a script file without expanding variables inside its content:

\`\`\`powershell
$scriptPath = Join-Path (Get-Location) "verify-project.ps1"

$scriptContent = @'
$ErrorActionPreference = "Stop"

git status --short --branch
if ($LASTEXITCODE -ne 0) {
    throw "Git status failed."
}
'@

Set-Content -LiteralPath $scriptPath -Value $scriptContent -Encoding utf8
Write-Host "Created: $scriptPath"
\`\`\`

The closing \`'@\` is deliberately flush-left. Indenting it can prevent PowerShell from recognizing the terminator in Windows PowerShell.

## 6. Line breaks and command continuation

Prefer syntax that does not require explicit continuation characters.

Safe continuation contexts include an open parenthesis, array, hashtable, or a pipeline continued after the pipe operator. However, keep command construction simple and visually obvious.

Prefer:

\`\`\`powershell
$containers = @(
    "watch-r7b-b2-step2-full-clean"
    "watch-r7b-b2-step2-smoke"
)

$containers | ForEach-Object {
    docker inspect $_
}
\`\`\`

Avoid backtick continuation:

\`\`\`powershell
# Fragile: a trailing space after the backtick breaks continuation.
docker run \`
    --name "example" \`
    --rm
\`\`\`

If a native command needs many arguments, consider an argument array or splatting where supported, or keep the invocation on one line. Do not use Bash continuation syntax (\`\\\`) in PowerShell.

Do not break a quoted value across physical lines unless a here-string is intended. A line break inside a normal quoted string is not a formatting substitute for concatenation.

## 7. Variables, paths, and native commands

- Quote filesystem paths with \`-LiteralPath\` where the cmdlet supports it.
- Use \`Join-Path\` instead of manually concatenating path separators.
- Use descriptive variable names; initialize variables before use.
- Quote paths and arguments that may contain spaces.
- Use \`--%\` only when its stop-parsing behavior is specifically required; it is not a general quoting fix.
- For native executables such as \`git\`, \`docker\`, and \`uv\`, check \`$LASTEXITCODE\` after commands whose failure must stop the script.
- \`$ErrorActionPreference = "Stop"\` is useful for PowerShell cmdlets, but it does not replace checking native-process exit codes.
- Do not hide failures with \`2>$null\`, \`Out-Null\`, broad \`try/catch\`, or ignored exit codes unless suppression is deliberate and explained.
- Do not invent paths, branch names, commit SHAs, database names, ports, or environment values. Derive them from verified state or mark them as explicit operator-supplied inputs.

A reusable native-command check:

\`\`\`powershell
git status --short --branch
if ($LASTEXITCODE -ne 0) {
    throw "git status failed with exit code $LASTEXITCODE."
}
\`\`\`

## 8. Safe script-file delivery

For scripts longer than a short terminal block, provide a complete file-writing block or a downloadable file whose exact path has been verified. Do not claim a file exists merely because a script contains a filename.

A file-writing block should:

1. Name the destination explicitly.
2. Use a literal here-string when the script body should not interpolate variables.
3. Write the entire script in one operation.
4. Validate the written file before execution.
5. Execute the exact path that was just written.
6. Preserve the user's existing files; do not silently overwrite an existing script.

Example with an overwrite guard:

\`\`\`powershell
$scriptPath = Join-Path (Get-Location) "verify-project.ps1"

if (Test-Path -LiteralPath $scriptPath) {
    throw "Refusing to overwrite existing file: $scriptPath"
}

$scriptContent = @'
$ErrorActionPreference = "Stop"

Write-Host "Verification script started."
'@

Set-Content -LiteralPath $scriptPath -Value $scriptContent -Encoding utf8

if (-not (Test-Path -LiteralPath $scriptPath)) {
    throw "Script file was not created."
}

Write-Host "Created script: $scriptPath"
\`\`\`

For an existing file, ask before replacing it or choose a new, explicit filename. Never use a broad wildcard to overwrite or clean script files.

## 9. Parse before execution

When a script is saved to disk, parse it before running it. Parsing catches syntax problems such as unmatched braces, incomplete strings, and malformed statements. It does not prove that commands are safe or that runtime operations will succeed.

\`\`\`powershell
$scriptPath = Join-Path (Get-Location) "verify-project.ps1"
$tokens = $null
$parseErrors = $null

[System.Management.Automation.Language.Parser]::ParseFile(
    $scriptPath,
    [ref]$tokens,
    [ref]$parseErrors
) | Out-Null

if ($parseErrors.Count -gt 0) {
    $parseErrors | Format-List
    throw "PowerShell parser found errors. The script was not executed."
}

Write-Host "PowerShell syntax check passed."
\`\`\`

For script text held in a variable, use \`Parser.ParseInput(...)\` with the same \`[ref]\` token and error variables. Do not use \`Invoke-Expression\` as a syntax checker.

After parsing, inspect the script's side effects and target values before execution. A syntactically valid script can still target the wrong branch, database, container, or directory.

## 10. Environment and cleanup discipline

A paste-safe script must also be operationally safe.

- Start with a preflight that prints the current directory, branch, HEAD, and worktree state when the operation depends on repository state.
- Stop if the observed state differs from the stated preconditions.
- Save environment variables before changing them and restore them in a \`finally\` block.
- Use a uniquely named disposable database/container and a dynamically assigned host port for database tests.
- Never target the persistent \`watch\` database for disposable verification.
- Never assume port 5432 is free or safe to use.
- Cleanup only resources created by the current script, identified by their exact names or IDs.
- Do not use destructive Git commands, force-push, volume deletion, or broad cleanup commands as convenience steps.
- Make cleanup behavior explicit. If cleanup fails, report it; do not hide the failure.
- Do not put irreversible operations in an automatic \`finally\` block merely to make the script appear self-cleaning.

These rules supplement the database and Git safety requirements in [\`AGENTS.md\`](../../AGENTS.md).

## 11. Common paste-corruption patterns

| Problem | Why it fails | Required correction |
|---|---|---|
| Missing or extra \`}\`, \`)\`, or \`]\` | PowerShell cannot parse the block/expression | Balance every delimiter; run the parser before execution |
| \`{{\` or \`}}\` copied from a template | Template escaping is not PowerShell syntax | Use literal single braces in PowerShell code |
| Terminal prompt included | Prompt text is interpreted as a command | Exclude all prompts and output from code blocks |
| Markdown fence copied | Backticks are not PowerShell syntax | Copy only the code between fences |
| Literal \`\\n\` used as a line break | PowerShell sees backslash and n characters | Use actual newlines |
| Bash \`\\\` continuation | Backslash is not PowerShell continuation | Restructure the command or use PowerShell syntax |
| Trailing backtick has whitespace after it | Continuation is broken | Avoid backticks; otherwise make it the final character |
| Here-string terminator indented | PowerShell may not recognize the terminator | Put the terminator at column one |
| Double-quoted path unexpectedly expands | A \`$\` expression is interpolated | Use single quotes or escape intentionally |
| Script is split across separate code blocks | Missing context or delimiters may make each block invalid | Deliver one complete block |
| Ellipses or “repeat for each item” | The result is not executable | Include every required statement |
| Command failure is ignored | Later commands may run against invalid state | Check \`$LASTEXITCODE\` and stop on failure |

## 12. Required response format for terminal scripts

When providing a script to the Operator, use this structure:

1. **Purpose** — one sentence describing what the script does.
2. **Preconditions** — branch/HEAD, directory, database, permissions, or other required state.
3. **Execution block** — one complete \`powershell\` code fence, without prompts or omitted sections.
4. **Expected result** — the key success lines or state changes the Operator should see.
5. **Failure behavior** — where the script stops and what output to provide for diagnosis.
6. **Safety note** — identify any persistent state, external service, or destructive action touched. State explicitly when none is touched.

Do not bury a critical warning after the code block. If the script is unsafe to run until a precondition is verified, put that condition before the block and make the script enforce it where practical.

## 13. Final author checklist

Before sending a terminal script, verify every item:

- [ ] The shell is identified correctly (PowerShell, not Bash or Command Prompt).
- [ ] The script is complete and appears in one code block.
- [ ] No prompt prefixes, output, Markdown markers, ellipses, or unfilled placeholders are inside the block.
- [ ] Every \`{ }\`, \`( )\`, and \`[ ]\` pair is balanced and correctly nested.
- [ ] Every quote and here-string has a valid closing delimiter.
- [ ] Here-string terminators begin at column one.
- [ ] Each physical line is intentional; no accidental wrapped or missing lines.
- [ ] No fragile backtick continuation is used unnecessarily.
- [ ] Paths and strings are quoted appropriately; variable expansion is intentional.
- [ ] Native command exit codes are checked where required.
- [ ] Preconditions and target resources are explicit and verified.
- [ ] Environment changes are restored and cleanup is narrowly scoped.
- [ ] The script's side effects are explained before execution.
- [ ] The expected output and failure-report instructions are included.

If any item cannot be verified, revise the script or label the unresolved condition clearly. Never present an unverified fragment as a ready-to-paste script.
