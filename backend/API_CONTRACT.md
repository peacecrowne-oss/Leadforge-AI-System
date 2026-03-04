# LeadForge AI — Backend API Contract

> **Status:** Lead Search MVP
> **Provider:** Simulated (deterministic mock leads; no live data source connected)
> **Persistence:** In-memory cache + SQLite (`backend/leadforge.db`)

---

## Base URL

```
http://127.0.0.1:8000
```

## CORS

Requests are accepted from:

| Origin | Usage |
|--------|-------|
| `http://localhost:5173` | Vite default port |
| `http://localhost:5174` | Vite fallback port (if 5173 is busy) |

All HTTP methods and headers are allowed. Credentials (`allow_credentials=True`) are enabled.

---

## Data Models

### `LeadSearchRequest`

Sent as the JSON body of `POST /leads/search`.

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `keywords` | `string \| null` | `null` | — | Free-text keyword seed |
| `title` | `string \| null` | `null` | — | Target job title |
| `location` | `string \| null` | `null` | — | Geographic filter |
| `company` | `string \| null` | `null` | — | Target company name |
| `limit` | `integer` | `25` | 1 – 200 | Max leads to return after dedupe |

### `Lead`

| Field | Type | Notes |
|-------|------|-------|
| `id` | `string` | UUID v4 |
| `full_name` | `string` | Required |
| `title` | `string \| null` | Job title |
| `company` | `string \| null` | — |
| `location` | `string \| null` | — |
| `email` | `string \| null` | — |
| `linkedin_url` | `string \| null` | — |
| `score` | `float \| null` | Relevance score (0.0 – 1.0) |

### `SearchJob`

| Field | Type | Notes |
|-------|------|-------|
| `job_id` | `string` | UUID v4 |
| `status` | `"queued" \| "running" \| "complete" \| "failed"` | — |
| `created_at` | `datetime` | ISO 8601, UTC |
| `updated_at` | `datetime` | ISO 8601, UTC |
| `request` | `LeadSearchRequest` | Original search parameters |
| `results_count` | `integer` | Count of deduped leads stored; 0 until complete |
| `error` | `string \| null` | Populated only on `"failed"` status |

---

## Endpoints

---

### `GET /`

Root endpoint. Confirms the backend process is reachable.

**Response `200 OK`**

```json
{"message": "LeadForge AI Backend Running"}
```

---

### `GET /health`

Health check. No authentication required.

**Response `200 OK`**

```json
{"status": "ok"}
```

---

### `POST /leads/search`

Submit a lead search job. The search runs asynchronously in a background task.

**Request body** — `application/json` — `LeadSearchRequest`

```json
{
  "keywords": "saas",
  "title": "Account Executive",
  "location": "Austin, TX",
  "company": "Stripe",
  "limit": 10
}
```

All fields are optional. Omitted fields receive their defaults.

**Response `202 Accepted`**

```json
{"job_id": "<uuid>"}
```

**Status codes**

| Code | Meaning |
|------|---------|
| `202` | Job accepted and queued |
| `422` | Validation error (e.g., `limit` outside 1–200) |

**Behavior**

1. A `SearchJob` with `status="queued"` is created and immediately persisted to SQLite.
2. A background task transitions the job through `queued → running → complete` (or `failed`).
3. The background task sleeps ~0.5 s to simulate provider latency, then generates 5–15 deterministic mock leads, deduplicates them, caps at `limit`, and writes results to SQLite.

---

### `GET /leads/jobs/{job_id}`

Poll the status and metadata of a search job.

**Path parameter**

| Name | Type | Description |
|------|------|-------------|
| `job_id` | `string` (UUID) | Returned by `POST /leads/search` |

**Response `200 OK`** — `SearchJob`

```json
{
  "job_id": "3fa85f64-...",
  "status": "complete",
  "created_at": "2026-02-22T14:00:00.000000+00:00",
  "updated_at": "2026-02-22T14:00:01.000000+00:00",
  "request": {
    "keywords": "saas",
    "title": "Account Executive",
    "location": "Austin, TX",
    "company": "Stripe",
    "limit": 10
  },
  "results_count": 9,
  "error": null
}
```

**Status codes**

| Code | Meaning |
|------|---------|
| `200` | Job found |
| `404` | Job not found, or owned by a different user |

**Behavior**

- Checks in-memory `JOBS` dict first; falls back to SQLite if missing (e.g., after a server restart). Caches the result in memory on load.
- Ownership enforced: a token for user B cannot read a job created by user A (returns 404, not 403, to avoid leaking existence).

---

### `GET /leads/jobs/{job_id}/results`

Retrieve the leads for a completed job with pagination and stable ordering.

**Path parameter**

| Name | Type | Description |
|------|------|-------------|
| `job_id` | `string` (UUID) | — |

**Query parameters**

| Name | Type | Default | Constraints | Description |
|------|------|---------|-------------|-------------|
| `offset` | `integer` | `0` | ≥ 0 | Number of leads to skip |
| `limit` | `integer` | `25` | 1 – 200 | Max leads to return per page |

**Sorting** (applied before pagination, always deterministic)

1. `score` descending (`null` treated as `0.0`)
2. `full_name` ascending (tie-breaker)

**Response `200 OK`**

```json
{
  "job_id": "3fa85f64-...",
  "results": [
    {
      "id": "<uuid>",
      "full_name": "Alex Rivera",
      "title": "Senior Account Executive",
      "company": "Stripe Inc.",
      "location": "Austin, TX",
      "email": "alex.rivera@example.com",
      "linkedin_url": "https://linkedin.com/in/alex.rivera",
      "score": 0.95
    }
  ],
  "count": 9,
  "offset": 0,
  "limit": 25
}
```

> `count` is always the **total** number of deduped leads for the job, not the number returned in this page.

**Status codes**

| Code | Meaning |
|------|---------|
| `200` | Results returned (may be empty if job is not yet complete) |
| `404` | Job not found, or owned by a different user |
| `422` | Invalid query parameter value |

**Behavior**

- The endpoint does **not** require `status="complete"` — it returns whatever leads are currently stored (may be `[]` while running).
- Falls back to SQLite for both job metadata and results if not in memory.

---

### `GET /leads/jobs/{job_id}/export.csv`

Download all leads for a completed job as a CSV file.

**Path parameter**

| Name | Type | Description |
|------|------|-------------|
| `job_id` | `string` (UUID) | — |

**No query parameters.** The export always includes all leads (no pagination).

**Response `200 OK`**

```
Content-Type: text/csv
Content-Disposition: attachment; filename="leads_<job_id>.csv"
```

CSV columns (in order):

```
id,full_name,title,company,location,email,linkedin_url,score
```

- Blank fields are empty strings (not `null`).
- `score` is numeric when present.
- Rows use the same sort order as `/results` (score desc, full_name asc).

**Status codes**

| Code | Meaning |
|------|---------|
| `200` | CSV returned |
| `404` | Job not found, or owned by a different user |
| `409` | Job exists, is owned by caller, but status is not `"complete"` |

---

## PowerShell Examples

### Create job → poll → fetch results

```powershell
# 1. Submit search
$job = Invoke-RestMethod -Uri "http://127.0.0.1:8000/leads/search" `
  -Method POST -ContentType "application/json" `
  -Body '{"keywords":"saas","title":"Account Executive","location":"Austin, TX","limit":10}'
$id = $job.job_id
Write-Host "Job ID: $id"

# 2. Poll until complete
do {
    Start-Sleep -Seconds 1
    $status = Invoke-RestMethod "http://127.0.0.1:8000/leads/jobs/$id"
    Write-Host "Status: $($status.status)"
} while ($status.status -notin @("complete","failed"))

# 3. Fetch results
$res = Invoke-RestMethod "http://127.0.0.1:8000/leads/jobs/$id/results"
Write-Host "Total leads: $($res.count)"
$res.results | Select-Object full_name, score | Format-Table
```

### Pagination example (page size 2)

```powershell
# Page 1 (offset=0, limit=2)
$p1 = Invoke-RestMethod "http://127.0.0.1:8000/leads/jobs/$id/results?offset=0&limit=2"
Write-Host "Page 1 — total: $($p1.count)"
$p1.results | Select-Object full_name, score

# Page 2 (offset=2, limit=2)
$p2 = Invoke-RestMethod "http://127.0.0.1:8000/leads/jobs/$id/results?offset=2&limit=2"
Write-Host "Page 2"
$p2.results | Select-Object full_name, score
```

### CSV export — print first 5 lines (no file write)

```powershell
$csv = Invoke-WebRequest "http://127.0.0.1:8000/leads/jobs/$id/export.csv"
$csv.Content -split "`n" | Select-Object -First 5
```

---

## Persistence & Caching Notes

| Layer | What is stored | Lifetime |
|-------|---------------|----------|
| In-memory (`JOBS` / `RESULTS` dicts) | All jobs and results created in the current process | Lost on server restart |
| SQLite (`backend/leadforge.db`) | All jobs at `queued` time; results + final status at `complete`/`failed` time | Survives restarts |

On every read endpoint, the server checks the in-memory cache first. On a cache miss (e.g., after restart), it loads from SQLite and re-caches in memory. Jobs restarted in a `queued` or `running` state will appear in the DB but their background task will **not** be re-queued automatically on restart — they remain visible with their last-written status.

> **Simulated provider:** `simulate_provider_search` sleeps 0.5 s then generates deterministic mock leads from the request fields. No live data source is connected. Lead count per job is 5–15 (derived from keyword length), capped by `request.limit`, then deduplicated by email → LinkedIn URL → name+company key.
