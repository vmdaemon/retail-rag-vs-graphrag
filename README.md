# Retail: RAG vs GraphRAG (Neo4j + Chroma + Ollama)

Side-by-side demo of **vector RAG** (ChromaDB) vs **GraphRAG** (Neo4j) on a small, synthetic retail dataset.

- **RAG**: embed documents → store in Chroma → retrieve relevant docs → LLM answer
- **GraphRAG**: seed entities/relations → query facts via Cypher → LLM answer grounded in graph facts

## Repository contents

- `retail_data.py` — synthetic retail “documents” used for RAG indexing
- `rag_index.py` — builds the local Chroma collection (`./chroma`) using Ollama embeddings (`nomic-embed-text`)
- `rag_query.py` — runs a basic RAG query against Chroma

- `seed_graph.py` — seeds Neo4j with a small retail graph (Supplier → Product → Promotion → Store → Region)
- `graphrag_query.py` — minimal GraphRAG query (Cypher facts + LLM)
- `graph_rag_demo.py` — end-to-end demo + diagnostics + visualizations
- `understand_graph.py` — graph diagnostics / exploration utilities
- `dynamic_bi_report.py` — generates a timestamped BI report file (`bi_report_*.txt`)

## Prerequisites

- Python 3.11+ (3.12 works)
- **Neo4j** running locally (Bolt enabled)
- **Ollama** running locally
  - chat model default: `llama3`
  - embedding model used by default: `nomic-embed-text`

## Configuration

All Neo4j/Ollama configuration is via environment variables:

```bash
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="<your-password>"
export NEO4J_DB="retaildb"

export OLLAMA_URL="http://localhost:11434/api/chat"
export OLLAMA_MODEL="llama3"
```

Notes:
- If your Neo4j uses the default database, set `NEO4J_DB=neo4j`.
- `OLLAMA_URL`/`OLLAMA_MODEL` are used by scripts that call Ollama via HTTP.
- `rag_index.py` uses the `ollama` python client for embeddings.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate

pip install -U pip
pip install neo4j chromadb ollama requests matplotlib networkx pandas seaborn numpy

ollama pull llama3
ollama pull nomic-embed-text
```

## Run

```bash
# Seed Neo4j graph
python seed_graph.py

# Build Chroma vector index
python rag_index.py

# Run end-to-end demo
python graph_rag_demo.py
```

## Demo walkthrough

See [`DEMO.md`](./DEMO.md) for the step-by-step runbook with sample inputs and expected outputs.

## Troubleshooting

### Neo4j auth failures

- Ensure `NEO4J_PASSWORD` is set.
- Ensure `NEO4J_DB` exists (or change it to `neo4j`).

### Ollama errors

- Ensure Ollama is running: `ollama serve`
- Pull required models:
  - `ollama pull llama3`
  - `ollama pull nomic-embed-text`

## License

MIT (see `LICENSE`).
