# Demo: Retail RAG vs GraphRAG (Step-by-step)

This repository demonstrates two ways to answer questions about retail supply-chain impact:

1. **Vector RAG** (ChromaDB): retrieve relevant text from embedded documents.
2. **GraphRAG** (Neo4j): retrieve structured, multi-hop facts from a graph and ask the LLM to answer using those facts.

The dataset is intentionally small and synthetic (see `retail_data.py`).

---

## What you will run

**Graph side**
- `seed_graph.py` — seeds Neo4j with a sample chain:
  `Supplier (Isha Supplies) → Product (Organic Almond Milk) → Promotion (Winter Wellness Sale) → Store (Downtown Store) → Region (West)`

**Vector side**
- `rag_index.py` — embeds documents from `retail_data.py` using Ollama (`nomic-embed-text`) and stores them in Chroma (`./chroma`).

**End-to-end demo**
- `graph_rag_demo.py` — runs Neo4j diagnostics, extracts facts via Cypher, calls Ollama chat, and shows plots.

---

## Prerequisites

- Python 3.11+ (3.12 works)
- Neo4j running locally (Bolt enabled)
- Ollama running locally

Install Python deps (minimal set):

```bash
python -m venv .venv
source .venv/bin/activate

pip install -U pip
pip install neo4j chromadb ollama requests matplotlib networkx pandas seaborn numpy
```

Pull required Ollama models:

```bash
ollama pull llama3
ollama pull nomic-embed-text
```

---

## Step 1 — Start services

### Neo4j
Make sure Neo4j is running and accessible at:

- `bolt://localhost:7687`

### Ollama

```bash
ollama serve
```

---

## Step 2 — Set configuration (env vars)

All scripts read config from environment variables.

```bash
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="<your-neo4j-password>"
export NEO4J_DB="retaildb"

export OLLAMA_URL="http://localhost:11434/api/chat"
export OLLAMA_MODEL="llama3"
```

Notes:
- If your Neo4j instance uses the default DB, set `NEO4J_DB=neo4j`.

---

## Step 3 — Seed the graph (GraphRAG knowledge source)

```bash
python seed_graph.py
```

### Expected output

```text
✅ Seeded sample retail graph into Neo4j
```

### What this creates

Nodes:
- `(:Supplier {name: "Isha Supplies"})`
- `(:Product {name: "Organic Almond Milk"})`
- `(:Promotion {name: "Winter Wellness Sale"})`
- `(:Store {name: "Downtown Store"})`
- `(:Region {name: "West"})`

Relationships:
- `(Supplier)-[:PROVIDES]->(Product)`
- `(Product)-[:IN_PROMOTION]->(Promotion)`
- `(Promotion)-[:ACTIVE_IN]->(Store)`
- `(Store)-[:LOCATED_IN]->(Region)`

---

## Step 4 — Build the vector index (RAG knowledge source)

```bash
python rag_index.py
```

### Sample input

`rag_index.py` reads the `documents` list in `retail_data.py`.

### Expected output

```text
✅ retail_rag collection created at ./chroma
```

### What this produces

- A local Chroma persistence directory at `./chroma`
- A collection named `retail_rag`

---

## Step 5 — Run the end-to-end demo (diagnostics + GraphRAG answers)

```bash
python graph_rag_demo.py
```

This script:
- prints Neo4j diagnostics
- extracts grounding facts from the graph for a supplier
- calls Ollama chat (HTTP) to generate an answer grounded in facts
- shows plots/visualizations (matplotlib + networkx)

### 5.1 Expected diagnostics output

The exact counts may differ if you already had data, but you should see these labels and relationship types.

```text
=== DATABASE DIAGNOSTICS ===

1. NODE LABELS:
   - Supplier
   - Product
   - Promotion
   - Store
   - Region

2. NODE COUNTS:
   - Supplier: 1 nodes
   - Product: 1 nodes
   - Promotion: 1 nodes
   - Store: 1 nodes
   - Region: 1 nodes

3. SUPPLIERS:
   - 'Isha Supplies'

4. RELATIONSHIP TYPES:
   - PROVIDES
   - IN_PROMOTION
   - ACTIVE_IN
   - LOCATED_IN

5. COMPLETE IMPACT CHAINS:
   - Isha Supplies → Organic Almond Milk → Winter Wellness Sale → Downtown Store → West

==================================================
```

### 5.2 Sample question (input)

The demo centers on a question like:

> **"If Isha Supplies has a disruption, what is impacted?"**

and uses the graph to pull multi-hop facts.

### 5.3 Expected extracted facts (Graph grounding)

```text
Supplier Isha Supplies provides Organic Almond Milk.
Organic Almond Milk is included in the Winter Wellness Sale promotion.
The Winter Wellness Sale promotion is active in the Downtown Store.
The Downtown Store is located in the West region.
```

### 5.4 Expected LLM answer (output)

The exact wording varies by model run, but it should reference the facts above:

```text
GraphRAG Answer:
If Isha Supplies is disrupted, Organic Almond Milk availability is impacted. Since that product is
part of the Winter Wellness Sale, the promotion may be affected at the Downtown Store, which serves
the West region. This could reduce promotional performance and cause out-of-stocks in that store/region.
```

### 5.5 Visual results

`graph_rag_demo.py` opens plots (matplotlib). If you run on a headless machine, configure a backend or run locally with GUI.

---

## Optional runs

### A) Minimal GraphRAG query

```bash
python graphrag_query.py
```

It prints:
- the raw Neo4j record returned
- a formatted bullet list of impacts
- an LLM answer from Ollama

### B) Generate a BI report text file

```bash
python dynamic_bi_report.py
```

Expected output artifact:
- `bi_report_YYYYMMDD_HHMMSS.txt`

The report contains:
- prompt
- generated Cypher query
- tabular results

---

## Troubleshooting

### Neo4j authentication errors

- Confirm `NEO4J_PASSWORD` is set.
- Confirm the DB exists: set `NEO4J_DB=neo4j` if you use the default.

### Ollama errors / model missing

```bash
ollama pull llama3
ollama pull nomic-embed-text
```

---

## If you want “real captured output”

Run steps 3–5 and paste the terminal output into this file under a new section like:

```md
## Captured output (my run)
<paste logs>
```
