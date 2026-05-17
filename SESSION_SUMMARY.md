# LeadForge AI System — Session Summary

## Overview

This session covered a broad set of improvements across the LeadForge AI System:
frontend UI cleanup, backend pipeline wiring, NLP search, email enrichment,
message tracking, and test safety. All changes were incremental and scoped.

---

## 1. Frontend Cleanup

### Removed Debug Job Override (`Leads.jsx`)
- Deleted hardcoded `debugJobId` constant
- Deleted `handleLoadDebugJob` function
- Deleted the orange-dashed debug `<section>` UI block
- No other logic was changed

---

## 2. Backend Pipeline Fixes

### `lead_pipeline_service.py`
- Added `job_id` to return dict: `{ "job_id": ..., "discovered": ..., "processed": ..., "stored": ... }`
- Added optional `job_id` parameter to `run_pipeline()` so callers can supply a pre-created id
- Removed temporary debug print statements

### `lead_discovery_service.py`
- Fixed silent API failure: added `status = data.get("status")` check — returns `[]` and logs error if status is not `"OK"`
- Added debug prints: `[GOOGLE RAW RESPONSE]` and `[PARSED LEADS]`
- Added domain extraction after lead building loop using `urllib.parse.urlparse`
- Reverted `full_name` back to `result.get("name", "")` after a brief incorrect change

### `lead_processing_service.py` — `normalize_leads`
- Added `first_name` + `last_name` combining logic
- Priority chain: `first_name + last_name` → `full_name` → `company` (fallback for Google business leads)
- Prevents Google leads from being dropped by `deduplicate_leads` (which skips empty `full_name`)

---

## 3. Natural Language Search

### `lead_discovery_service.py`
Added three query-parsing helpers (each an iteration):
- `normalize_query` — strips filler words
- `extract_intent` — keyword matching with fallback
- `parse_query` — combined with `q.split()[0]` fallback
- `parse_natural_query` — final version with broader filler list and multi-word keywords (`"software company"`, `"marketing agency"`)

`fetch_leads_from_api` now uses `intent = parse_natural_query(query)` before building params.

### `leads.py` — New `/search-nlp` Route
- Added `POST /search-nlp` endpoint (path corrected from `/leads/search-nlp`)
- Parses `request.keywords` via `parse_natural_query`
- Substitutes parsed query into a `model_copy` of the request (preserves `location`, `company`, `limit`)
- Uses same `_run_google_pipeline` background task and JOBS/RESULTS wiring as `/leads/search`
- Added `raw_query = request.keywords or getattr(request, "query", "") or ""` for field flexibility

### `Leads.jsx` — NLP Detection + Routing
- Added `isNaturalLanguage` detection (`>= 2 words` threshold using `/\s+/` split)
- Routes to `/search-nlp` for multi-word queries, `/leads/search` for single-word
- Updated `handleNlSearch` to call `/search-nlp` instead of `/leads/nl-search`
- Replaced both `/leads/search-nlp` occurrences with `/search-nlp` after route path fix
- Added `[SEARCH TYPE]`, `[SEARCH TRIGGERED]`, `[NLP INPUT]`, `[SEARCH RESPONSE]` console logs

---

## 4. Pipeline Background Task Wiring (`leads.py`)

### `_run_google_pipeline` function
- Added `[BG TASK] STARTED`, `[BG TASK] COMPLETED`, `[BG TASK ERROR]` print statements
- Added `raise` in except block so FastAPI sees background task failures
- After pipeline completes: syncs `RESULTS[job_id]` from DB, reloads `JOBS[job_id]` from DB
- Added explicit `model_copy` to stamp `status="complete"`, `results_count=len(RESULTS[job_id])`, `updated_at`

### `lead_pipeline_service.py` — Debug Prints
- Added `[PIPELINE] raw_count=N` after `fetch_leads_from_api`
- Added `[PIPELINE] scored_count=N` after `score_leads`

---

## 5. Hunter.io Email Enrichment (`lead_enrichment_service.py`)

### `enrich_with_hunter`
- New function (not yet wired into pipeline)
- Reads `HUNTER_API_KEY` from environment
- Calls Hunter.io `/v2/domain-search` per lead domain (timeout=5s)
- Role-based email selection: prefers `owner`, `founder`, `ceo`, `marketing`, `manager`
- Falls back to first email if no role match
- Silently skips leads without a domain or on API error

---

## 6. Message Sending & Tracking

### `lead_message_service.py` (new file)
- `send_message_to_leads(leads, message)` — simulates sending, marks each lead:
  - `message_status: "sent"` if email present
  - `message_status: "no_email"` otherwise
- Shallow-copies each lead to avoid mutating originals

### Test Mode Safety
- `TEST_MODE = os.getenv("EMAIL_TEST_MODE", "true").lower() == "true"` (defaults ON)
- When active: saves originals to `original_email` / `original_phone`, redirects all sends to:
  - Email: `peacecrowne@gmail.com`
  - Phone: `+18322777883`

### Wired into Results Endpoint (`leads.py`)
- `GET /leads/jobs/{job_id}/results` now applies `send_message_to_leads` to paged results before returning
- Storage and pipeline are untouched — enrichment is response-only

---

## 7. UI Updates (`Leads.jsx`)

### Table Column Changes
- Split `Name` column from `First Name` / `Last Name` back to single `Name` column
- Added `Status` column showing `✅ Sent` / `⚠️ No Email` / `—`
- Final column order: **Name | Title | Company | Email | Location | Score | Variant | Status | Action**
- `colSpan` kept in sync through all changes (currently `10`)

---

## 8. Dashboard Drill-Down (`Dashboard.jsx`)

- Added `leads` state
- Fetches latest job results on load via `/leads/jobs/latest` → `/leads/jobs/{job_id}/results`
- Fetch failure is silently swallowed — dashboard remains functional with no leads
- Added "Recent Emails Sent" card (top 5 leads with `message_status === "sent"`)
- Card only renders when sent leads exist
- Existing metric cards and campaign summary untouched

---

## Files Changed

| File | Type |
|---|---|
| `frontend/src/pages/Leads.jsx` | Modified |
| `frontend/src/pages/Dashboard.jsx` | Modified |
| `backend/services/lead_pipeline_service.py` | Modified |
| `backend/services/lead_discovery_service.py` | Modified |
| `backend/services/lead_processing_service.py` | Modified |
| `backend/services/lead_enrichment_service.py` | Modified |
| `backend/services/lead_message_service.py` | **Created** |
| `backend/routes/leads.py` | Modified |

---

## Pending / Not Yet Done

- `enrich_with_hunter` is implemented but **not wired into the pipeline** — needs a call in `lead_pipeline_service.py` after `enrich_leads` and `HUNTER_API_KEY` in `.env`
- Debug print statements in `lead_discovery_service.py` (`[GOOGLE RAW RESPONSE]`, `[PARSED LEADS]`) and `lead_pipeline_service.py` (`[PIPELINE] raw_count`, `[PIPELINE] scored_count`) are still present — remove before production
- `/leads/nl-search` backend route (the old NL search) may still exist but is no longer called from the frontend
