# Local Embeddings — R6-D

R6-D uses **BGE-M3 served locally by Ollama** as the first embedding implementation. PostgreSQL with pgvector remains Watch's retrieval store. The model is not required for CI: automated tests inject a deterministic fake embedding provider.

## Install and verify on Windows

Install Ollama for Windows from its official installer, then run this in PowerShell:

    ollama pull bge-m3
    ollama list

The download is stored in Ollama's local model cache; it is not stored in the Watch repository. Keep the Ollama server on the local machine and do not expose its API to the public internet.

Send a local smoke-test request:

    $body = @{
        model = "bge-m3"
        input = @("A local embedding smoke test.")
        truncate = $false
    } | ConvertTo-Json -Depth 4

    $result = Invoke-RestMethod -Method Post -Uri "http://localhost:11434/api/embed" -ContentType "application/json" -Body $body
    $result.embeddings[0].Count  # Expected: 1024
    ollama ps

The final command shows which model is loaded and whether Ollama reports CPU or GPU processing. The NVIDIA GTX 1650 Super may help inference, but performance depends on available VRAM, model residency, and the installed driver/runtime. CPU execution remains a valid fallback; measure latency on the actual machine rather than assuming GPU offload.

## Watch configuration

The provider factory reads these optional environment variables:

| Variable | Default | Meaning |
|---|---|---|
| WATCH_EMBEDDING_PROVIDER | ollama | Provider adapter. Only ollama is implemented in this slice. |
| WATCH_EMBEDDING_BASE_URL | http://localhost:11434 | Ollama API base URL; can be changed for a deliberate local Docker/network layout. |
| WATCH_EMBEDDING_MODEL | bge-m3 | Installed Ollama model name. |
| WATCH_EMBEDDING_DIMENSIONS | 1024 | Expected vector width; responses with a different width are rejected. |
| WATCH_EMBEDDING_TIMEOUT_SECONDS | 60 | Timeout per local HTTP request. |
| WATCH_EMBEDDING_BATCH_SIZE | 32 | Maximum inputs sent in one embedding request. |
| WATCH_EMBEDDING_CONFIGURATION | ollama-embed-v1 | Versioned adapter/request configuration. Changing it creates a different embedding-space key. |

When the Watch Python process runs directly on Windows, the default localhost URL is appropriate. If Watch itself is later run inside a container, localhost refers to that container; configure a reachable Ollama endpoint deliberately, and do not publish the model API outside a trusted interface.

## Model/version safety and cost

The adapter resolves the installed model's digest through Ollama's local /api/tags endpoint. Each vector-space key includes the provider, model name, exact installed digest, dimensions, and configuration version. Index rows are only eligible for queries made in that same vector space. After pulling a model update, re-run the indexer to rebuild the projection; stale vectors are not mixed with the new model.

Inference requests are local and have no per-token API charge. They still use local CPU/GPU time, RAM/VRAM, storage, and electricity. Never commit model weights, Ollama cache files, private source snapshots, credentials, or tokens.

No Ollama service or model downloads are used in CI. Deterministic fake embeddings verify index/retrieval behavior; a separate local smoke test verifies the actual Ollama installation.

## Run an end-to-end Watch smoke test

After the model-only HTTP smoke test passes, run the Watch-side smoke test against a **development or disposable PostgreSQL database that has already been migrated to head**. Do not point this at a production database. From the project root, in PowerShell:

    uv run alembic upgrade head
    $env:TEST_DATABASE_URL = "postgresql+psycopg://watch:watch@127.0.0.1:5432/watch"
    uv run python -m core.embedding_smoke

The smoke command requires a reachable Ollama server with BGE-M3 installed. It creates a uniquely identified temporary Team, source policy, and Signal, then checks that indexing works, a second indexing pass is idempotent, and an authorized hybrid query retrieves the source. It removes the test database rows in a finally block and uses a temporary SnapshotStore. If cleanup itself fails, the script prints a warning so the database can be inspected before reuse.
