#!/usr/bin/env python3
"""Run the 50-question Argus retrieval and answer-quality benchmark.

The benchmark reports RAGAS quality scores alongside latency, cost, retrieval,
and throughput metrics. It expects the local services to be running and reads
database and authentication credentials from the environment.
"""
from __future__ import annotations

import asyncio
import json
import os
import statistics
import time
import uuid
from datetime import datetime, timezone

import httpx
import psycopg2
import psycopg2.extras

BASE_URL   = os.getenv("ARGUS_URL",  "http://localhost:8080")
RAG_URL    = os.getenv("RAG_URL",   "http://localhost:8081")
OLLAMA_URL = os.getenv("OLLAMA_URL","http://localhost:11434")
DB_DSN     = os.environ["DB_DSN"]
EVAL_MODEL = os.getenv("EVAL_MODEL","command-r:35b")
TENANT_ID  = "00000000-0000-0000-0000-000000000001"
GIT_SHA    = os.getenv("GIT_SHA", "local")

try:
    from datasets import Dataset
    from ragas import evaluate as ragas_evaluate
    from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.run_config import RunConfig as RagasRunConfig
    from langchain_community.chat_models import ChatOllama
    from langchain_community.embeddings import OllamaEmbeddings
    RAGAS_OK = True
except ImportError as _e:
    RAGAS_OK = False
    print(f"[WARN] RAGAS not available ({_e}). pip install ragas==0.1.21 datasets langchain-community")

DOCUMENTS = [
    {
        "text": (
            "The Q3 cloud infrastructure budget is capped at $50,000. "
            "Any overrun must be approved by the CTO within 48 hours of detection. "
            "AWS spend accounts for 60% of total cloud cost per approved allocation. "
            "Unauthorized spending above the cap triggers an immediate review and "
            "potential project suspension. Budget resets on the first day of each quarter. "
            "Emergency provisions can be invoked by the VP of Engineering for critical outages."
        ),
        "source": "cloud-budget-policy.txt",
    },
    {
        "text": (
            "Q3 actual cloud spending reached $47,200, leaving a $2,800 buffer. "
            "AWS was $28,000 (59.3% of total), GCP was $12,000 (25.4%), "
            "and Azure was $7,200 (15.3%). All figures are within the approved $50,000 cap. "
            "Month breakdown: July $14,100, August $16,800, September $16,300. "
            "Forecast for Q4 is $52,000 pending CTO approval for the $2,000 overrun."
        ),
        "source": "q3-spend-report.txt",
    },
    {
        "text": (
            "The vendor SLA requires 99.9% uptime, equivalent to 8.76 hours downtime per year. "
            "Current vendor status is operational. Last incident was 45 days ago lasting 12 minutes. "
            "Year-to-date downtime is 23 minutes, leaving 505 minutes of SLA headroom. "
            "Penalty clause: 10% service credit per hour of breach beyond the annual threshold. "
            "Escalation contact: sla-breach@vendor.com, response within 15 minutes guaranteed."
        ),
        "source": "vendor-sla.txt",
    },
    {
        "text": (
            "Cloud cost governance policy mandates quarterly review of all provider invoices. "
            "Finance must reconcile AWS, GCP, and Azure invoices within 10 business days of quarter close. "
            "Discrepancies over $500 must be escalated to the VP of Engineering within 48 hours. "
            "All cloud resources must be tagged with: team, project, environment, and cost-center. "
            "Untagged resources are automatically suspended after 7 days of detection. "
            "Annual cost review is conducted every January by the FinOps team."
        ),
        "source": "cost-governance-policy.txt",
    },
    {
        "text": (
            "Q3 capacity planning: AWS reserved instances cover 70% of compute demand "
            "at a 35% discount versus on-demand pricing, saving approximately $14,700 in Q3. "
            "The remaining 30% runs on spot instances with automated fallback to on-demand. "
            "Spot interruption rate was 2.3% in Q3, causing 4 automated failovers. "
            "Recommended Q4 action: increase reserved instance coverage to 80% "
            "to capture additional $4,200 in annual savings."
        ),
        "source": "capacity-planning-q3.txt",
    },
    {
        "text": (
            "Security compliance report Q3: all cloud resources passed SOC2 Type II audit. "
            "14 medium-severity findings were remediated within SLA of 30 days. "
            "2 high-severity findings related to S3 bucket permissions were resolved in 72 hours. "
            "Zero critical findings. Next audit scheduled for Q1 next year. "
            "Penetration test completed by external firm; no critical vulnerabilities found. "
            "MFA is enforced on 98.7% of cloud accounts; 3 service accounts pending enforcement."
        ),
        "source": "security-compliance-q3.txt",
    },
    {
        "text": (
            "Engineering headcount report Q3: total engineering staff is 47. "
            "Cloud infrastructure team: 6 engineers, 1 manager. "
            "Backend engineering: 18 engineers, 3 managers. "
            "Frontend engineering: 12 engineers, 2 managers. "
            "Data engineering: 5 engineers, 1 manager. "
            "Q4 approved headcount additions: 3 backend engineers, 1 data engineer. "
            "Current open roles: 2 senior backend, 1 DevOps, 1 ML engineer. "
            "Average tenure: 2.4 years. Attrition rate Q3: 4.2%."
        ),
        "source": "engineering-headcount-q3.txt",
    },
    {
        "text": (
            "Q2 financial summary: total cloud spend was $41,800 against a $45,000 budget. "
            "AWS: $24,500, GCP: $11,200, Azure: $6,100. "
            "Q2 vs Q1 comparison: Q1 total was $38,200, representing 9.4% growth Q1 to Q2. "
            "Q2 reserved instance savings: $11,200. On-demand overage: $3,400. "
            "Q2 largest cost driver: ML training workloads on GCP ($6,800 of $11,200 GCP total). "
            "Finance flagged $1,200 in untagged resources; remediated by DevOps within 5 days."
        ),
        "source": "q2-financial-summary.txt",
    },
]

# Categories: FACTUAL (direct lookup), NUMERICAL (math/calc), POLICY (inference),
#             MULTI_SOURCE (cross-doc), COMPARATIVE (trend/comparison)
EVAL_DATASET = [
    # Factual
    {
        "question": "What is the Q3 cloud infrastructure budget cap?",
        "ground_truth": "The Q3 cloud infrastructure budget is capped at $50,000.",
        "category": "FACTUAL",
    },
    {
        "question": "Who must approve any cloud budget overrun?",
        "ground_truth": "Any cloud budget overrun must be approved by the CTO within 48 hours of detection.",
        "category": "FACTUAL",
    },
    {
        "question": "What is the vendor SLA uptime requirement?",
        "ground_truth": "The vendor SLA requires 99.9% uptime.",
        "category": "FACTUAL",
    },
    {
        "question": "How long was the last vendor incident?",
        "ground_truth": "The last vendor incident lasted 12 minutes.",
        "category": "FACTUAL",
    },
    {
        "question": "How many days ago did the last vendor incident occur?",
        "ground_truth": "The last vendor incident occurred 45 days ago.",
        "category": "FACTUAL",
    },
    {
        "question": "What is the current vendor operational status?",
        "ground_truth": "The current vendor status is operational.",
        "category": "FACTUAL",
    },
    {
        "question": "How much did GCP spend in Q3?",
        "ground_truth": "GCP spent $12,000 in Q3.",
        "category": "FACTUAL",
    },
    {
        "question": "How much did Azure spend in Q3?",
        "ground_truth": "Azure spent $7,200 in Q3.",
        "category": "FACTUAL",
    },
    {
        "question": "How much did AWS spend in Q3?",
        "ground_truth": "AWS spent $28,000 in Q3.",
        "category": "FACTUAL",
    },
    {
        "question": "What percentage of compute demand do reserved instances cover in Q3?",
        "ground_truth": "Reserved instances cover 70% of compute demand in Q3.",
        "category": "FACTUAL",
    },
    {
        "question": "How many engineers are on the cloud infrastructure team?",
        "ground_truth": "The cloud infrastructure team has 6 engineers and 1 manager.",
        "category": "FACTUAL",
    },
    {
        "question": "What is the total engineering headcount?",
        "ground_truth": "Total engineering staff is 47.",
        "category": "FACTUAL",
    },
    {
        "question": "How many high-severity security findings were found in Q3?",
        "ground_truth": "2 high-severity findings related to S3 bucket permissions were found and resolved in 72 hours.",
        "category": "FACTUAL",
    },
    {
        "question": "What is the within how many days must finance reconcile cloud invoices?",
        "ground_truth": "Finance must reconcile AWS, GCP, and Azure invoices within 10 business days of quarter close.",
        "category": "FACTUAL",
    },
    {
        "question": "What was Q2 total cloud spending?",
        "ground_truth": "Q2 total cloud spend was $41,800 against a $45,000 budget.",
        "category": "FACTUAL",
    },

    # Numerical
    {
        "question": "How much Q3 budget remains after actual cloud spending?",
        "ground_truth": "After Q3 spending of $47,200, the remaining budget buffer is $2,800 out of the $50,000 cap.",
        "category": "NUMERICAL",
    },
    {
        "question": "How much annual downtime is allowed under the 99.9% uptime SLA?",
        "ground_truth": "The 99.9% uptime SLA allows 8.76 hours of downtime per year.",
        "category": "NUMERICAL",
    },
    {
        "question": "How much SLA downtime headroom remains year-to-date?",
        "ground_truth": "With 23 minutes used year-to-date, there are 505 minutes of SLA headroom remaining.",
        "category": "NUMERICAL",
    },
    {
        "question": "How much did reserved instances save in Q3?",
        "ground_truth": "Reserved instances saved approximately $14,700 in Q3 through a 35% discount versus on-demand pricing.",
        "category": "NUMERICAL",
    },
    {
        "question": "What is the Q3 cloud spend growth compared to Q2?",
        "ground_truth": "Q3 spending was $47,200 versus Q2 at $41,800, representing a $5,400 increase (approximately 12.9% growth).",
        "category": "NUMERICAL",
    },
    {
        "question": "What percentage of Q3 cloud spend did AWS represent?",
        "ground_truth": "AWS represented 59.3% of Q3 total cloud spend ($28,000 of $47,200).",
        "category": "NUMERICAL",
    },
    {
        "question": "How much additional annual savings would increasing reserved instance coverage to 80% generate?",
        "ground_truth": "Increasing reserved instance coverage from 70% to 80% would capture approximately $4,200 in additional annual savings.",
        "category": "NUMERICAL",
    },
    {
        "question": "How many total security findings were remediated in Q3?",
        "ground_truth": "14 medium-severity and 2 high-severity findings were remediated in Q3, totaling 16 findings.",
        "category": "NUMERICAL",
    },
    {
        "question": "What is the Q4 cloud spend forecast and how much CTO approval is needed?",
        "ground_truth": "Q4 forecast is $52,000 with CTO approval needed for the $2,000 overrun above the $50,000 cap.",
        "category": "NUMERICAL",
    },
    {
        "question": "What was the cloud spend growth from Q1 to Q2?",
        "ground_truth": "Q1 total was $38,200 and Q2 was $41,800, representing 9.4% growth.",
        "category": "NUMERICAL",
    },

    # Policy and inference
    {
        "question": "What happens if cloud spending exceeds the approved cap?",
        "ground_truth": "Any overrun must be approved by the CTO within 48 hours. Unauthorized spending triggers an immediate review and potential project suspension.",
        "category": "POLICY",
    },
    {
        "question": "What happens to untagged cloud resources?",
        "ground_truth": "Untagged resources are automatically suspended after 7 days of detection.",
        "category": "POLICY",
    },
    {
        "question": "What tags are required on all cloud resources?",
        "ground_truth": "All cloud resources must be tagged with: team, project, environment, and cost-center.",
        "category": "POLICY",
    },
    {
        "question": "What is the escalation process for discrepancies over $500 in cloud invoices?",
        "ground_truth": "Discrepancies over $500 must be escalated to the VP of Engineering within 48 hours.",
        "category": "POLICY",
    },
    {
        "question": "What is the vendor penalty clause for SLA breaches?",
        "ground_truth": "The penalty clause is a 10% service credit per hour of breach beyond the annual downtime threshold.",
        "category": "POLICY",
    },
    {
        "question": "Who can invoke emergency provisions if spending exceeds the cap?",
        "ground_truth": "The VP of Engineering can invoke emergency provisions for critical outages.",
        "category": "POLICY",
    },
    {
        "question": "When does the cloud budget reset?",
        "ground_truth": "The cloud budget resets on the first day of each quarter.",
        "category": "POLICY",
    },
    {
        "question": "What is the SLA breach escalation contact and response guarantee?",
        "ground_truth": "The escalation contact is sla-breach@vendor.com with a guaranteed 15-minute response time.",
        "category": "POLICY",
    },
    {
        "question": "Is MFA fully enforced across all cloud accounts?",
        "ground_truth": "MFA is enforced on 98.7% of cloud accounts; 3 service accounts are still pending enforcement.",
        "category": "POLICY",
    },
    {
        "question": "When is the next security audit scheduled?",
        "ground_truth": "The next SOC2 audit is scheduled for Q1 next year.",
        "category": "POLICY",
    },

    # Multi-source
    {
        "question": "Is Q3 cloud spending within the approved budget and what is the remaining buffer?",
        "ground_truth": "Yes, Q3 spending of $47,200 is within the $50,000 budget, leaving a $2,800 buffer.",
        "category": "MULTI_SOURCE",
    },
    {
        "question": "How does Q3 AWS spend compare to the policy's expected 60% allocation?",
        "ground_truth": "Policy expects AWS to account for 60% of cloud cost. Q3 actual AWS spend was $28,000 of $47,200 total, which is 59.3% — closely aligned with the 60% policy target.",
        "category": "MULTI_SOURCE",
    },
    {
        "question": "What were the Q2 and Q3 cloud budgets and did spending stay within both?",
        "ground_truth": "Q2 budget was $45,000 with actual spend of $41,800 (within budget). Q3 budget is $50,000 with actual spend of $47,200 (within budget).",
        "category": "MULTI_SOURCE",
    },
    {
        "question": "How many engineers support the cloud infrastructure and what is the cost per engineer based on Q3 spend?",
        "ground_truth": "The cloud infrastructure team has 6 engineers. At Q3 spend of $47,200, the cost is approximately $7,867 per engineer.",
        "category": "MULTI_SOURCE",
    },
    {
        "question": "Did the vendor meet its SLA in Q3 given the last incident details?",
        "ground_truth": "Yes, the vendor met its SLA. Year-to-date downtime is 23 minutes against an allowable 8.76 hours (525 minutes) per year. The last incident was 12 minutes, 45 days ago.",
        "category": "MULTI_SOURCE",
    },
    {
        "question": "What security issues were found in Q3 and what is the remediation timeline policy?",
        "ground_truth": "14 medium-severity and 2 high-severity security findings were found. Medium findings must be remediated within 30 days; high-severity findings were resolved in 72 hours.",
        "category": "MULTI_SOURCE",
    },
    {
        "question": "Summarize Q3 cloud cost performance across all providers.",
        "ground_truth": "Q3 total spend was $47,200 of $50,000 budget. AWS: $28,000 (59.3%), GCP: $12,000 (25.4%), Azure: $7,200 (15.3%). All providers within budget. Month-over-month: July $14,100, August $16,800, September $16,300.",
        "category": "MULTI_SOURCE",
    },
    {
        "question": "What open engineering roles exist and what is the approved Q4 headcount plan?",
        "ground_truth": "Open roles: 2 senior backend, 1 DevOps, 1 ML engineer. Q4 approved additions: 3 backend engineers and 1 data engineer.",
        "category": "MULTI_SOURCE",
    },
    {
        "question": "How did Q2 and Q3 GCP spending compare and what drove Q2 GCP costs?",
        "ground_truth": "Q2 GCP spend was $11,200 and Q3 was $12,000, a $800 increase. Q2 GCP costs were primarily driven by ML training workloads at $6,800 of the $11,200 total.",
        "category": "MULTI_SOURCE",
    },
    {
        "question": "What is the total cloud spend across Q1, Q2, and Q3?",
        "ground_truth": "Q1 was $38,200, Q2 was $41,800, Q3 was $47,200. Total across all three quarters is $127,200.",
        "category": "MULTI_SOURCE",
    },

    # Comparative
    {
        "question": "Which cloud provider had the highest Q3 spend?",
        "ground_truth": "AWS had the highest Q3 spend at $28,000, representing 59.3% of total Q3 cloud spending.",
        "category": "COMPARATIVE",
    },
    {
        "question": "Which quarter had the highest cloud spend: Q1, Q2, or Q3?",
        "ground_truth": "Q3 had the highest cloud spend at $47,200, followed by Q2 at $41,800 and Q1 at $38,200.",
        "category": "COMPARATIVE",
    },
    {
        "question": "Compare Q2 and Q3 AWS spending.",
        "ground_truth": "Q2 AWS spend was $24,500 and Q3 AWS spend was $28,000, an increase of $3,500 (14.3% growth) quarter-over-quarter.",
        "category": "COMPARATIVE",
    },
    {
        "question": "Which engineering team is the largest by headcount?",
        "ground_truth": "Backend engineering is the largest team with 18 engineers and 3 managers.",
        "category": "COMPARATIVE",
    },
    {
        "question": "Compare the Q3 budget utilization rate to Q2.",
        "ground_truth": "Q3 utilized 94.4% of its $50,000 budget ($47,200 spent). Q2 utilized 92.9% of its $45,000 budget ($41,800 spent). Q3 had slightly higher utilization.",
        "category": "COMPARATIVE",
    },
]

def db_conn():
    return psycopg2.connect(DB_DSN)


def cleanup_db():
    print("\n[CLEANUP] Clearing DB (document_chunks, query_runs, eval_results) ...")
    with db_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM document_chunks;")
        cur.execute("DELETE FROM query_runs;")
        cur.execute("DELETE FROM eval_results;")
        conn.commit()
    print("[CLEANUP] Done.")


async def get_token() -> str:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            f"{BASE_URL}/api/v1/auth/token",
            json={"username": "tenant-alpha", "password": os.environ["DEV_AUTH_PASSWORD"]},
        )
        r.raise_for_status()
        return r.json()["access_token"]


async def ingest_documents(token: str) -> None:
    print(f"\n[INGEST] Loading {len(DOCUMENTS)} documents ...")
    async with httpx.AsyncClient(timeout=120) as client:
        for doc in DOCUMENTS:
            r = await client.post(
                f"{BASE_URL}/api/v1/ingest/documents",
                headers={"Authorization": f"Bearer {token}"},
                json=doc,
            )
            r.raise_for_status()
            chunks = r.json().get("chunks_inserted", 0)
            print(f"  {doc['source']} — {chunks} chunk(s)")


async def search_contexts(question: str, top_k: int = 5) -> tuple[list[str], float]:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{RAG_URL}/tools/search_documents",
            json={"query": question, "tenant_id": TENANT_ID, "top_k": top_k},
        )
        r.raise_for_status()
        results = r.json()["results"]
    texts = [res["text"] for res in results]
    top_score = results[0]["score"] if results else 0.0
    return texts, top_score


async def query_gateway(question: str, token: str) -> tuple[str, float, float]:
    started = time.perf_counter()
    tokens: list[str] = []
    cost_usd = 0.0
    latency_ms = 0.0

    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST",
            f"{BASE_URL}/api/v1/query",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"query": question},
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[6:])
                if event["type"] == "token":
                    tokens.append(event["data"])
                elif event["type"] == "done":
                    cost_usd = event["data"].get("cost_usd", 0.0)
                    latency_ms = event["data"].get("latency_ms", 0.0)

    answer = "".join(tokens).strip()
    return answer, latency_ms, cost_usd


def llm_judge(question: str, answer: str, context: str) -> dict[str, float]:
    prompt = f"""You are an evaluation judge. Score the AI answer strictly.

Question: {question}

Retrieved Context:
{context}

AI Answer:
{answer}

Rate on 0.0–1.0:
1. FAITHFULNESS: Are all claims in the answer supported by the context? (1.0=fully grounded, 0.0=hallucinated)
2. RELEVANCY: Does the answer directly address the question? (1.0=perfect, 0.0=off-topic)

JSON only: {{"faithfulness": <float>, "relevancy": <float>}}"""

    try:
        r = httpx.post(
            f"{OLLAMA_URL}/v1/chat/completions",
            json={"model": EVAL_MODEL, "temperature": 0,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=60,
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = "\n".join(content.splitlines()[1:-1])
        scores = json.loads(content)
        return {"faithfulness": float(scores.get("faithfulness", 0)),
                "relevancy":    float(scores.get("relevancy", 0))}
    except Exception as e:
        print(f"    [WARN] judge failed: {e}")
        return {"faithfulness": 0.0, "relevancy": 0.0}


def percentile(data: list[float], p: int) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    idx = max(0, int(len(s) * p / 100) - 1)
    return round(s[idx], 1)


def save_eval_results(metrics: list[dict]) -> None:
    with db_conn() as conn, conn.cursor() as cur:
        for m in metrics:
            cur.execute(
                "INSERT INTO eval_results (git_sha, metric, value, threshold, passed) "
                "VALUES (%s, %s, %s, %s, %s)",
                (GIT_SHA, m["metric"], m["value"], m.get("threshold"), m.get("passed")),
            )
        conn.commit()
    print(f"\n[DB] Saved {len(metrics)} metric(s) to eval_results.")


async def run_eval():
    total_start = time.perf_counter()

    cleanup_db()
    token = await get_token()
    await ingest_documents(token)

    n = len(EVAL_DATASET)
    print(f"\n[EVAL] Running {n} queries across "
          f"{len(set(q['category'] for q in EVAL_DATASET))} categories ...\n")

    results = []

    for i, item in enumerate(EVAL_DATASET):
        q           = item["question"]
        gt          = item["ground_truth"]
        cat         = item["category"]
        label       = f"Q{i+1:02d}"

        print(f"{label} [{cat}] {q}")

        contexts, top_ret = await search_contexts(q)
        answer, lat_ms, cost = await query_gateway(q, token)
        ctx_str = "\n".join(contexts[:3])
        judge = llm_judge(q, answer, ctx_str)

        results.append({
            "label": label, "question": q, "ground_truth": gt,
            "category": cat, "answer": answer, "contexts": contexts,
            "latency_ms": lat_ms, "cost_usd": cost,
            "top_retrieval_score": top_ret,
            "faithfulness": judge["faithfulness"],
            "relevancy":    judge["relevancy"],
            "answer_len":   len(answer),
        })

        print(f"  → {answer[:100]}{'...' if len(answer) > 100 else ''}")
        print(f"  lat={lat_ms:.0f}ms  cost=${cost:.6f}  ret={top_ret:.2f}  "
              f"faith={judge['faithfulness']:.2f}  rel={judge['relevancy']:.2f}\n")

    ragas_scores: dict[str, float] = {}
    if RAGAS_OK:
        print("[RAGAS] Running RAGAS evaluation ...")
        try:
            # The 35B local model is evaluated serially to avoid GPU contention.
            run_cfg = RagasRunConfig(timeout=180, max_workers=1, max_retries=2)
            llm_w = LangchainLLMWrapper(
                ChatOllama(model=EVAL_MODEL, base_url=OLLAMA_URL,
                           temperature=0, timeout=180))
            emb_w = LangchainEmbeddingsWrapper(
                OllamaEmbeddings(model=EVAL_MODEL, base_url=OLLAMA_URL))
            ds = Dataset.from_dict({
                "question":     [r["question"]     for r in results],
                "answer":       [r["answer"]       for r in results],
                "contexts":     [r["contexts"]     for r in results],
                "ground_truth": [r["ground_truth"] for r in results],
            })
            rr = ragas_evaluate(ds,
                metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
                llm=llm_w, embeddings=emb_w,
                raise_exceptions=False, run_config=run_cfg)
            ragas_scores = {k: round(float(v), 4) for k, v in rr.items()
                            if isinstance(v, (int, float)) and not __import__("math").isnan(v)}
        except Exception as e:
            print(f"  [WARN] RAGAS failed: {e}")

    categories = sorted(set(r["category"] for r in results))
    cat_stats: dict[str, dict] = {}
    for cat in categories:
        cat_r = [r for r in results if r["category"] == cat]
        cat_stats[cat] = {
            "count":       len(cat_r),
            "avg_faith":   round(statistics.mean(r["faithfulness"] for r in cat_r), 3),
            "avg_rel":     round(statistics.mean(r["relevancy"]    for r in cat_r), 3),
            "avg_latency": round(statistics.mean(r["latency_ms"]   for r in cat_r), 0),
            "avg_ret":     round(statistics.mean(r["top_retrieval_score"] for r in cat_r), 3),
        }

    latencies  = [r["latency_ms"]          for r in results]
    costs      = [r["cost_usd"]            for r in results]
    faiths     = [r["faithfulness"]        for r in results]
    rels       = [r["relevancy"]           for r in results]
    rets       = [r["top_retrieval_score"] for r in results]
    ans_lens   = [r["answer_len"]          for r in results]

    total_wall_s = time.perf_counter() - total_start
    throughput   = n / (total_wall_s / 60)

    custom = {
        "total_questions":          n,
        "p50_latency_ms":           percentile(latencies, 50),
        "p95_latency_ms":           percentile(latencies, 95),
        "p99_latency_ms":           percentile(latencies, 99),
        "cold_start_ms":            round(latencies[0], 1),
        "warm_avg_latency_ms":      round(statistics.mean(latencies[1:]), 1),
        "min_latency_ms":           round(min(latencies), 1),
        "max_latency_ms":           round(max(latencies), 1),
        "avg_faithfulness":         round(statistics.mean(faiths), 4),
        "avg_relevancy":            round(statistics.mean(rels), 4),
        "pct_perfect_faith":        round(sum(1 for f in faiths if f == 1.0) / n * 100, 1),
        "pct_perfect_rel":          round(sum(1 for r in rels   if r == 1.0) / n * 100, 1),
        "avg_retrieval_precision":  round(statistics.mean(rets), 3),
        "max_retrieval_precision":  round(max(rets), 3),
        "min_retrieval_precision":  round(min(rets), 3),
        "avg_cost_usd":             round(statistics.mean(costs), 6),
        "total_cost_usd":           round(sum(costs), 6),
        "avg_answer_len_chars":     round(statistics.mean(ans_lens), 0),
        "throughput_queries_min":   round(throughput, 2),
    }

    W = 62
    print("\n" + "=" * W)
    print("  ARGUS EVALUATION REPORT")
    print(f"  {n} questions  |  {len(DOCUMENTS)} documents  |  model: {EVAL_MODEL}")
    print("=" * W)

    print("\n  LATENCY")
    print(f"    Cold start (Q1)      : {custom['cold_start_ms']:.0f} ms")
    print(f"    Warm avg (Q2–Q{n})   : {custom['warm_avg_latency_ms']:.0f} ms")
    print(f"    Min / Max            : {custom['min_latency_ms']:.0f} ms / {custom['max_latency_ms']:.0f} ms")
    print(f"    P50                  : {custom['p50_latency_ms']:.0f} ms")
    print(f"    P95                  : {custom['p95_latency_ms']:.0f} ms")
    print(f"    P99                  : {custom['p99_latency_ms']:.0f} ms")

    print("\n  RETRIEVAL QUALITY (cross-encoder reranker scores, higher = better)")
    print(f"    Avg top score        : {custom['avg_retrieval_precision']:.3f}")
    print(f"    Max top score        : {custom['max_retrieval_precision']:.3f}")
    print(f"    Min top score        : {custom['min_retrieval_precision']:.3f}")

    print("\n  ANSWER QUALITY — LLM-as-judge (0.0–1.0)")
    print(f"    Avg faithfulness     : {custom['avg_faithfulness']:.3f} "
          f"({custom['pct_perfect_faith']:.0f}% scored 1.0)")
    print(f"    Avg relevancy        : {custom['avg_relevancy']:.3f} "
          f"({custom['pct_perfect_rel']:.0f}% scored 1.0)")

    print("\n  PER-CATEGORY BREAKDOWN")
    print(f"    {'Category':<14} {'N':>3}  {'Faith':>6}  {'Rel':>6}  {'Ret':>6}  {'Lat(ms)':>8}")
    print(f"    {'-'*52}")
    for cat, s in cat_stats.items():
        print(f"    {cat:<14} {s['count']:>3}  {s['avg_faith']:>6.3f}  "
              f"{s['avg_rel']:>6.3f}  {s['avg_ret']:>6.3f}  {s['avg_latency']:>8.0f}")

    if ragas_scores:
        print("\n  RAGAS SCORES (0.0–1.0)")
        for k, v in ragas_scores.items():
            print(f"    {k:<28} : {v:.4f}")

    print("\n  COST & THROUGHPUT")
    print(f"    Avg cost/query       : ${custom['avg_cost_usd']:.6f}")
    print(f"    Total ({n} queries)  : ${custom['total_cost_usd']:.5f}")
    print(f"    Throughput           : {custom['throughput_queries_min']:.1f} queries/min")

    print("\n" + "=" * W)

    thresholds = {
        "p95_latency_ms":          10000,
        "avg_faithfulness":        0.70,
        "avg_relevancy":           0.70,
        "avg_retrieval_precision": 3.0,
    }
    db_metrics = []
    for k, v in {**custom, **ragas_scores}.items():
        thr = thresholds.get(k)
        passed = None
        if thr is not None:
            passed = (v <= thr) if "latency" in k else (v >= thr)
        db_metrics.append({"metric": k, "value": float(v),
                           "threshold": thr, "passed": passed})
    save_eval_results(db_metrics)

    print("\n  RESUME-READY NUMBERS")
    print(f"    Evaluated on {n} questions across {len(categories)} categories "
          f"({len(DOCUMENTS)} source documents)")
    print(f"    Warm P50 latency             : {custom['p50_latency_ms']:.0f} ms end-to-end")
    print(f"    P95 latency                  : {custom['p95_latency_ms']:.0f} ms")
    print(f"    Faithfulness (LLM-judge)     : {custom['avg_faithfulness']*100:.0f}%")
    print(f"    Relevancy (LLM-judge)        : {custom['avg_relevancy']*100:.0f}%")
    print(f"    Perfect-faith answers        : {custom['pct_perfect_faith']:.0f}% of {n}")
    if ragas_scores:
        for k, v in ragas_scores.items():
            print(f"    RAGAS {k:<22} : {v:.2f}")
    print(f"    Retrieval precision (avg)    : {custom['avg_retrieval_precision']:.2f} (cross-encoder)")
    print(f"    Cost per query               : ${custom['avg_cost_usd']:.5f}")
    print(f"    Total eval cost ({n}q)       : ${custom['total_cost_usd']:.4f}")
    print()


if __name__ == "__main__":
    asyncio.run(run_eval())
