# Embedding API — R6-D

R6-D uses a provider-neutral adapter for the OpenAI-compatible `/v1/models` and
`/v1/embeddings` endpoints. The first local target is **BAAI/BGE-M3 served by
LM Studio**. Other local or hosted providers can be used if they implement that
API contract. PostgreSQL with pgvector remains Watch's retrieval store. CI uses
deterministic fake embeddings and never calls a real provider or downloads model
weights.

## Prepare LM Studio on Windows

1. In LM Studio, download a model explicitly intended for **text embeddings**.
   Your chat models do not automatically provide embeddings. BGE-M3 is the initial
   embedding model. The model ID verified in the operator's 2026-10-29 local run
   was `text-embedding-bge-m3`; your LM Studio server may expose a different ID.
2. Load the embedding model in LM Studio, then start its local server from the
   Developer/Server UI. Keep it bound to localhost; do not expose the API to the
   public internet.
3. In PowerShell, list the model IDs actually exposed by the running server:

    ```powershell
    $models = Invoke-RestMethod -Method Get -Uri "http://localhost:1234/v1/models"
    $models.data | Select-Object id, object, owned_by | Format-Table
    ```

4. Copy the exact `id` of the loaded embedding model. Use that exact value as
   `WATCH_EMBEDDING_MODEL`; don't guess the ID from the display name.

Check that the embedding API returns vectors:

    ```powershell
    $modelId = "<exact-model-id-from-v1-models>"
    $body = @{
        model = $modelId
        input = @("A local embedding smoke test.")
        encoding_format = "float"
    } | ConvertTo-Json -Depth 4

    $result = Invoke-RestMethod -Method Post -Uri "http://localhost:1234/v1/embeddings" -ContentType "application/json" -Body $body
    $result.data[0].embedding.Count
    ```

BGE-M3 is expected to return 1,024 dimensions. If the dimension count differs,
stop and set the expected dimensions to the model's verified output only after
confirming the selected model is the intended embedding model.

## Watch configuration

Set these variables in the same PowerShell session used to run Watch. The
operator's verified ID was `text-embedding-bge-m3`; first check `/v1/models` and
replace this value if your running LM Studio instance reports a different ID:

    ```powershell
    $env:WATCH_EMBEDDING_PROVIDER = "openai_compatible"
    $env:WATCH_EMBEDDING_BASE_URL = "http://localhost:1234/v1"
    $env:WATCH_EMBEDDING_MODEL = "text-embedding-bge-m3"
    $env:WATCH_EMBEDDING_DIMENSIONS = "1024"
    $env:WATCH_EMBEDDING_TIMEOUT_SECONDS = "180"
    $env:WATCH_EMBEDDING_READY_TIMEOUT_SECONDS = "180"
    $env:WATCH_EMBEDDING_BATCH_SIZE = "8"
    $env:WATCH_EMBEDDING_RETRY_ATTEMPTS = "2"
    ```

| Variable | Default | Purpose |
|---|---|---|
| `WATCH_EMBEDDING_PROVIDER` | `openai_compatible` | Adapter contract; supports compatible local or hosted APIs. |
| `WATCH_EMBEDDING_BASE_URL` | `http://localhost:1234/v1` | API base URL, without the `/models` or `/embeddings` suffix. |
| `WATCH_EMBEDDING_MODEL` | `bge-m3` | Exact model ID exposed by `GET /v1/models`. Set this to LM Studio's actual ID. |
| `WATCH_EMBEDDING_DIMENSIONS` | `1024` | Required vector width; every response is checked. |
| `WATCH_EMBEDDING_TIMEOUT_SECONDS` | `180` | Timeout for each HTTP request, allowing for a slow local machine or cold model. |
| `WATCH_EMBEDDING_READY_TIMEOUT_SECONDS` | `180` | Maximum time to wait for the API and configured model to appear in `/v1/models`. |
| `WATCH_EMBEDDING_BATCH_SIZE` | `8` | Maximum texts per request. Start small on a local PC; raise only after measuring memory and latency. |
| `WATCH_EMBEDDING_RETRY_ATTEMPTS` | `2` | Total attempts for transient embedding-request failures. Permanent 4xx/configuration failures are not retried. |
| `WATCH_EMBEDDING_API_KEY` | empty | Optional bearer token for providers that require authentication. Do not commit or print it. |
| `WATCH_EMBEDDING_REVISION` | derived from API model metadata | Optional stable model/weights/quantization version pin. Set it explicitly when the API cannot expose an immutable weight revision; change it whenever the model file, quantization, or preprocessing changes. |
| `WATCH_EMBEDDING_CONFIGURATION` | `openai-embeddings-v1` | Versioned request contract. Change it if the embedding request semantics change. |

## Readiness, retries, and local hardware

Before embedding, Watch polls `GET /v1/models` with bounded exponential delays until
the exact configured model ID appears or the readiness timeout expires. This
accommodates a server starting or a model being loaded in LM Studio. If LM Studio's
just-in-time loading is enabled, the model may be listed before it is resident and
the first embedding request may trigger loading. That first request can be slow and
is bounded by the configured HTTP timeout. If just-in-time loading is disabled,
load the embedding model in LM Studio before running Watch. Embedding requests retry
only transient network, timeout, overload, rate-limit, and server errors, with a
short bounded backoff. Invalid requests, wrong model IDs returned by the API, and
invalid vectors fail explicitly rather than causing repeated expensive calls.

Watch does not issue LM Studio-specific load/unload commands or decide GPU
offload. LM Studio owns model loading and CPU/GPU placement; Watch observes the
standard API's readiness. The API does not provide a portable guarantee that
weights are pinned in VRAM or that a cold request will finish within a particular
time. Begin with a small batch, inspect LM Studio's load/processing settings, and
measure on the actual PC. If the model is not visible through `/v1/models`, load
it and start the server in LM Studio, then rerun the command. A readiness timeout
is configurable for slower startups.

The standard OpenAI-compatible model-list response does not guarantee an immutable
weight digest. Watch fingerprints the returned model metadata by default; for a
persistent index, set `WATCH_EMBEDDING_REVISION` to an explicit version identifier
when replacing the model or quantization, and rerun indexing to rebuild the
projection. The endpoint identity, provider, model ID, revision, dimensions, and
request configuration participate in the vector-space key. Vectors from different
keys are never mixed in a query.

No model weights, local caches, snapshots, credentials, or API keys belong in the
repository. Hosted APIs can have costs and data-handling implications; the intended
initial setup is local LM Studio.

## Run the Watch end-to-end smoke test

Use only a positively identified development or disposable PostgreSQL database.
The test removes its temporary rows, but `uv run alembic upgrade head` can change the
schema and is not safe to run against a persistent database just because the smoke
script cleans up afterward. The URL below is an example for a dedicated disposable
database named `watch_embedding_smoke`; create/verify that database first, or replace
the URL with the connection string for your own disposable instance. Do not assume a
database named `watch` is disposable. From the project root, in PowerShell:

    ```powershell
    $env:DATABASE_URL = "postgresql+psycopg://watch:watch@127.0.0.1:5432/watch_embedding_smoke"
    $env:TEST_DATABASE_URL = $env:DATABASE_URL
    uv run alembic upgrade head
    uv run python -m core.embedding_smoke
    ```

The smoke command needs the configured API and exact model ID to be visible.
It creates a uniquely identified temporary Team, source policy, and Signal, then
checks indexing, idempotency, and authorized hybrid retrieval. It removes the test
database rows in a finally block and uses a temporary SnapshotStore. If cleanup
fails, the command prints a warning so the database can be inspected before reuse.


### Local run evidence — 2026-10-29

The operator's local Watch smoke command reported PASS with model ID `text-embedding-bge-m3`, 1,024 dimensions, projection indexing, repeat-indexing idempotency, and authorized hybrid retrieval. The API reported metadata fingerprint `metadata-sha256:e8ffcf172118d67251eccbf45916e407b7e0537deef08f70bbd62e86518e9c69`; `WATCH_EMBEDDING_REVISION` was not explicitly set, so this is a metadata-derived fingerprint rather than an operator-managed immutable weight pin.

The command transcript used a database URL ending in `/watch`. That output does not establish that the target was disposable. Until it is confirmed disposable or the smoke is rerun using a verified disposable database, regard the API/index/retrieval result as positive functional evidence, not as formal closure of the R6-D gate.
