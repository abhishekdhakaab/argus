# Argus

Argus is a multi-tenant retrieval system that answers one question across documents, structured analytics, and a simulated legacy API. A LangGraph agent chooses the relevant sources, runs retrieval in parallel, and streams a grounded answer through a FastAPI gateway.

## What is technically interesting

- Hybrid document search combines pgvector similarity, BM25, reciprocal-rank fusion, and a cross-encoder reranker.
- LangGraph fans queries out to only the selected retrieval services and merges their state before synthesis.
- Tenant IDs are enforced across authentication, rate limits, document retrieval, analytics, and usage reporting.
- The gateway emits Server-Sent Events for agent progress and answer delivery, then stores latency, token, cost, and tool-use metadata.
- The stack includes an operational Next.js UI, OpenTelemetry instrumentation, Docker packaging, Alembic migrations, and Terraform for Google Cloud Run.

## Architecture

```text
Next.js client
      |
      | JWT + SSE
      v
FastAPI gateway -----> Ollama / OpenAI-compatible LLM
      |
      v
LangGraph planner
      |
      +----------+----------------+----------------+
      |          |                |                |
      v          v                v                |
RAG service   SQL service   Legacy API service    |
      |          |                |                |
      +---- PostgreSQL       Redis cache <---------+
           + pgvector
```

The planner selects document search, SQL analytics, the external API, or a combination. Retrieval nodes run concurrently; synthesis receives the merged context and produces the final response.

## Stack

Python 3.11, FastAPI, LangGraph, PostgreSQL/pgvector, Redis, sentence-transformers, BM25, Ollama, Next.js 14, TypeScript, Docker Compose, OpenTelemetry, and Terraform.

## Run locally with Docker

Prerequisites: Docker with Compose, Node.js 18+, OpenSSL, and an OpenAI-compatible chat endpoint. The checked-in defaults target Ollama running on the host.

1. Create local configuration and replace every `replace-with-...` value:

   ```bash
   cp .env.example .env
   ```

2. Generate a local JWT signing pair. These files are ignored by Git:

   ```bash
   openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out gateway/private.pem
   openssl pkey -in gateway/private.pem -pubout -out gateway/public.pem
   ```

3. Start Ollama and make the configured model available:

   ```bash
   ollama pull command-r:35b
   ```

4. Build and start the API stack:

   ```bash
   docker compose -f docker-compose.prod.yml up --build
   ```

   Alembic creates the schema and two demo tenants on gateway startup. The API is available at `http://localhost:8080`; interactive docs are at `http://localhost:8080/docs`.

5. Start the frontend in another terminal:

   ```bash
   cd frontend
   npm ci
   FASTAPI_URL=http://127.0.0.1:8080 npm run dev
   ```

   Open `http://localhost:3000` and sign in as `tenant-alpha` with the `DEV_AUTH_PASSWORD` value from `.env`.

For a Linux host with Conda, PostgreSQL, Redis, and Ollama installed directly, `bash run_local.sh` bootstraps the Python environment and services. It also runs the end-to-end smoke test.

## Configuration

`.env.example` documents the required database, demo-authentication, JWT, and model settings. `OPENAI_API_KEY=ollama` is a non-secret compatibility value used only to enable calls to the configured local OpenAI-compatible endpoint; use a real key only when pointing the endpoint at a hosted provider.

The service-specific dependency files support small Docker images. The root `requirements.txt` installs the complete Python application, while `eval/requirements.txt` adds the optional evaluation packages. Frontend dependencies are locked in `frontend/package-lock.json`.

## Verification and evaluation

With the stack running:

```bash
bash smoke_test.sh
```

To rerun the full benchmark:

```bash
python -m pip install -r eval/requirements.txt
set -a; source .env; set +a
python eval/eval.py
```

The retained final run evaluated 50 questions across five categories and eight documents:

| Metric | Result |
| --- | ---: |
| Completed queries | 50 / 50 |
| RAGAS context precision | 0.9483 |
| RAGAS context recall | 0.9767 |
| Warm P50 / P95 latency | 1.797 s / 2.702 s |
| Average retrieval latency | 27.2 ms |
| Raw query throughput | 21.0 queries/min |
| Average cost per query | $0.000063 |
| RAGAS faithfulness / answer relevancy | 0.4935 / 0.5133 |

The lower answer-quality aggregates came from an evaluation mismatch: SQL values intentionally differed from the document fixtures, while RAGAS judged against document-only ground truth. Policy questions, which did not cross those conflicting sources, scored 1.0 for both faithfulness and relevancy. The [full evaluation report](results/evaluation.md) includes per-question output and the diagnosis.

## Repository map

| Path | Purpose |
| --- | --- |
| `agent/` | Planner, retrieval nodes, synthesis, and LangGraph assembly |
| `gateway/` | Authentication, rate limiting, SSE query API, usage metrics, and migrations |
| `mcp_servers/` | Document RAG, SQL analytics, and simulated external API services |
| `frontend/` | Next.js login, query, ingestion, and usage views |
| `eval/` | 50-question quality and performance benchmark |
| `terraform/` | Cloud Run, Cloud SQL, Redis, secrets, and monitoring resources |
| `results/` | Curated final evaluation report |

The external API service is intentionally simulated so the project can demonstrate retries, circuit breaking, and cached fallback behavior without depending on a private system.
