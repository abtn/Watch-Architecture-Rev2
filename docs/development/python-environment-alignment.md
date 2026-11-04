# Align the local Python environment with CI

This guide explains the repository's Python-version contract and how to rebuild the local uv project environment when its interpreter is older than the Python selected by CI.

## Why alignment was needed

The repository currently has three related controls:

- The CI workflow, .github/workflows/ci.yml, runs **uv python install 3.12**.
- pyproject.toml requires Python 3.12 or newer and configures Mypy/Ruff for the Python 3.12 language target.
- uv.lock locks the dependency graph and supported package markers. It does not pin the Python interpreter patch release used to create .venv.

The 2026-11-03 CI log selected CPython 3.12.16 on its Linux runner. The local Windows run installed a uv-managed Python 3.12.12, but uv run python still reported Python 3.12.5. The existing .venv had not been rebuilt.

The important distinction is that **uv sync --locked synchronizes dependencies in the selected project environment**. It is not a request to recreate an existing environment with a newly installed interpreter. Installing another Python version therefore does not, by itself, replace the interpreter inside .venv.

## What this repository means by “match CI”

The current CI workflow requests the Python 3.12 minor line, not one exact patch release. The alignment script reads that request from the workflow and creates the local .venv with a uv-managed interpreter satisfying it.

The patch release may still differ between Windows and Linux. For example, the observed Windows interpreter was 3.12.12 while the observed Linux CI interpreter was 3.12.16. That is not a dependency-lock mismatch: the current CI configuration does not pin an exact patch version.

Exact patch parity would require a separate change to pin the same full Python version in CI and locally. This guide does not change the CI workflow, pyproject.toml, uv.lock, or add a .python-version pin.

## Run the alignment script

From a VS Code PowerShell terminal, run:

~~~powershell
.\scripts\align-ci-python.ps1
~~~

The script locates the repository from its own path, so it does not depend on the terminal's starting directory.

The script performs these steps:

1. Reads the Python request from the existing CI workflow.
2. Installs that request using uv's managed Python distribution.
3. Checks that any active VIRTUAL_ENV or UV_PROJECT_ENVIRONMENT points to this repository's .venv. It stops rather than modifying another environment.
4. Renames the existing .venv to a timestamped .venv.backup-* directory. It does not delete the previous environment.
5. Locates the uv-managed interpreter after the old environment has been moved aside.
6. Creates a new .venv using that explicit interpreter.
7. Runs uv sync --locked and uv pip check.
8. Verifies that uv run selects an interpreter inside the new .venv and that its version satisfies the CI request.
9. On failure, preserves a partial new environment as .venv.failed-* and attempts to restore the previous .venv.

The backup and failed-environment directories are ignored by Git. A successful run deliberately retains the old backup so it can be restored manually if needed.

### Preconditions and safety

- Run in Windows PowerShell with uv available on PATH.
- Close Python test processes, notebooks, and other processes that may hold files under .venv.
- Do not run while a Conda environment is active.
- If the terminal is using a virtual environment outside this repository, deactivate it before running the script.
- Ensure there is enough free disk space for the new environment and the retained backup.
- The script does not start PostgreSQL, run migrations, or execute tests. It only aligns and synchronizes the Python environment.

If Windows reports that files in .venv are in use, close the process holding them and rerun the script. Do not manually delete the backup to work around a failed rename.

## Verify after alignment

Run:

~~~powershell
uv run python --version
uv run python -c "import sys; print(sys.executable); print(sys.version)"
uv pip check
~~~

The executable should be under this repository's .venv directory, and the major/minor version should match the request in the CI workflow.

Then select the repository interpreter in VS Code:

1. Open the Command Palette.
2. Run **Python: Select Interpreter**.
3. Select the interpreter at .venv\Scripts\python.exe.
4. Open a new integrated terminal if VS Code still has an older activated environment.

For static project checks, use the same commands as CI:

~~~powershell
uv run ruff check core tests migrations
uv run mypy core
~~~

For a full CI-equivalent test run, also provide an explicit disposable PostgreSQL database through TEST_DATABASE_URL, apply migrations to that disposable database, and run uv run pytest -q. Follow the database safety requirements in docs/testing.md. Never point TEST_DATABASE_URL at the persistent database named watch.

## Rollback

After a successful run, the previous environment remains in the repository as .venv.backup-<timestamp>. To restore it:

1. Close Python processes and deactivate the repository environment.
2. Rename the current .venv to a distinct .venv.failed-* name.
3. Rename the selected .venv.backup-* directory back to .venv.
4. Reopen the terminal or reactivate .venv.

Do not copy individual packages from the backup into the new environment. Virtual environments are interpreter-bound; restore the complete directory if rollback is needed.

## Maintenance rule

The CI workflow is the source for the requested Python version. The script intentionally fails if the workflow changes away from the simple one-line uv python install VERSION form, so a future CI workflow change must update or review the script rather than silently using a stale version.

The dependency source of truth remains pyproject.toml plus uv.lock. Do not edit the lockfile merely to change the local interpreter.
