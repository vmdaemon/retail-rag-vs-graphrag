import os

from neo4j import GraphDatabase
import requests
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import json
from datetime import datetime
import os

# ---------- CONFIG ----------
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DB = os.getenv("NEO4J_DB", "retaildb")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def run_cypher(query, params=None):
    with driver.session(database=NEO4J_DB) as session:
        return session.run(query, params or {}).data()


# ---------- GRAPH SCHEMA LOADER ----------


def load_graph_schema():
    """Load graph schema for LLM context"""

    if os.path.exists("graph_schema.json"):
        with open("graph_schema.json", "r") as f:
            schema = json.load(f)
    else:
        # Generate schema if not exists
        schema = generate_schema()

    # Ensure sample_queries exists
    if "sample_queries" not in schema:
        schema["sample_queries"] = [
            {
                "description": "Count products per supplier",
                "cypher": "MATCH (s:Supplier)-[:PROVIDES]->(p:Product) RETURN s.name AS supplier, count(p) AS products ORDER BY products DESC",
            },
            {
                "description": "List all promotions and their stores",
                "cypher": "MATCH (pr:Promotion)-[:ACTIVE_IN]->(st:Store) RETURN pr.name AS promotion, st.name AS store",
            },
            {
                "description": "Complete supply chain view",
                "cypher": "MATCH (s:Supplier)-[:PROVIDES]->(p:Product)-[:IN_PROMOTION]->(pr:Promotion)-[:ACTIVE_IN]->(st:Store)-[:LOCATED_IN]->(r:Region) RETURN s.name AS supplier, p.name AS product, pr.name AS promotion, st.name AS store, r.name AS region",
            },
            {
                "description": "Products by region",
                "cypher": "MATCH (p:Product)-[:IN_PROMOTION]->(pr:Promotion)-[:ACTIVE_IN]->(st:Store)-[:LOCATED_IN]->(r:Region) RETURN r.name AS region, count(DISTINCT p) AS products ORDER BY products DESC",
            },
            {
                "description": "Stores with most promotions",
                "cypher": "MATCH (pr:Promotion)-[:ACTIVE_IN]->(st:Store) RETURN st.name AS store, count(pr) AS promotions ORDER BY promotions DESC",
            },
        ]

    return schema


def generate_schema():
    """Generate schema from database"""

    summary = {"node_types": [], "relationship_types": [], "sample_queries": []}

    # Node types
    labels = run_cypher("CALL db.labels()")
    for label_row in labels:
        label = label_row["label"]
        count = run_cypher(f"MATCH (n:{label}) RETURN count(n) AS count")[0]["count"]
        sample = run_cypher(
            f"MATCH (n:{label}) WHERE n.name IS NOT NULL RETURN n.name AS name LIMIT 3"
        )

        summary["node_types"].append(
            {
                "type": label,
                "count": count,
                "samples": [s["name"] for s in sample if s.get("name")],
            }
        )

    # Relationship types
    rel_types = run_cypher("CALL db.relationshipTypes()")
    for rel_row in rel_types:
        rel_type = rel_row["relationshipType"]
        pattern = run_cypher(f"""
            MATCH (a)-[r:{rel_type}]->(b)
            WHERE labels(a)[0] IS NOT NULL AND labels(b)[0] IS NOT NULL
            RETURN labels(a)[0] AS from, labels(b)[0] AS to
            LIMIT 1
        """)

        if pattern and pattern[0].get("from"):
            summary["relationship_types"].append(
                {
                    "type": rel_type,
                    "pattern": f"({pattern[0]['from']})-[:{rel_type}]->({pattern[0]['to']})",
                }
            )

    # Sample queries
    summary["sample_queries"] = [
        {
            "description": "Count products per supplier",
            "cypher": "MATCH (s:Supplier)-[:PROVIDES]->(p:Product) RETURN s.name AS supplier, count(p) AS products",
        },
        {
            "description": "List all promotions and their stores",
            "cypher": "MATCH (pr:Promotion)-[:ACTIVE_IN]->(st:Store) RETURN pr.name AS promotion, st.name AS store",
        },
        {
            "description": "Complete supply chain view",
            "cypher": "MATCH (s:Supplier)-[:PROVIDES]->(p:Product)-[:IN_PROMOTION]->(pr:Promotion)-[:ACTIVE_IN]->(st:Store)-[:LOCATED_IN]->(r:Region) RETURN s.name, p.name, pr.name, st.name, r.name",
        },
    ]

    return summary


# ---------- LLM QUERY GENERATOR ----------


def ask_llm(prompt: str):
    """Call Ollama LLM"""
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are a Neo4j Cypher query expert and data analyst.",
            },
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }
    resp = requests.post(OLLAMA_URL, json=payload)
    resp.raise_for_status()
    data = resp.json()
    return data["message"]["content"]


def generate_cypher_from_prompt(user_prompt: str, schema: dict):
    """Generate Cypher query from natural language prompt"""

    schema_context = f"""
You are a Neo4j Cypher query generator. Generate ONLY the Cypher query, nothing else.

GRAPH SCHEMA:

Node Types:
{json.dumps(schema["node_types"], indent=2)}

Relationship Types:
{json.dumps(schema["relationship_types"], indent=2)}

Sample Queries:
{json.dumps(schema.get("sample_queries", []), indent=2)}

RULES:
1. Return ONLY valid Cypher query
2. Use proper node labels and relationship types from schema
3. Return meaningful column aliases using AS
4. Use aggregations when appropriate (count, sum, avg)
5. Add ORDER BY and LIMIT when relevant
6. DO NOT include any explanation, markdown formatting, or code blocks
7. Return just the raw Cypher query

USER REQUEST:
{user_prompt}

CYPHER QUERY:
"""

    response = ask_llm(schema_context)

    # Clean the response to extract just the Cypher query
    cypher = response.strip()

    # Remove markdown code blocks if present
    if "```" in cypher:
        lines = cypher.split("```")
        for line in lines:
            if line.strip() and not line.strip().startswith("cypher"):
                cypher = line.strip()
                break

    # Remove "cypher" prefix if present
    if cypher.lower().startswith("cypher"):
        cypher = cypher[6:].strip()

    # Remove any remaining backticks
    cypher = cypher.replace("`", "")

    return cypher.strip()


def generate_visualization_code(user_prompt: str, data: list, cypher_query: str):
    """Generate Python visualization code from data"""

    if not data:
        return "print('No data to visualize')"

    viz_prompt = f"""
You are a Python data visualization expert using matplotlib and seaborn.

USER REQUEST:
{user_prompt}

CYPHER QUERY USED:
{cypher_query}

DATA STRUCTURE (first 3 rows):
{json.dumps(data[:3], indent=2, default=str)}

TOTAL ROWS: {len(data)}

Generate Python code that:
1. Converts the data to a pandas DataFrame
2. Creates an appropriate visualization (bar, line, pie, heatmap, etc.)
3. Adds proper titles, labels, and styling
4. Uses the provided 'data' variable (list of dicts)

Return ONLY the Python code, no explanation or markdown.

The code should start with:
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

df = pd.DataFrame(data)

Then create the visualization and end with plt.tight_layout().
"""

    response = ask_llm(viz_prompt)

    # Clean the response
    code = response.strip()
    if "```python" in code:
        code = code.split("```python")[1].split("```")[0]
    elif "```" in code:
        lines = code.split("```")
        for line in lines:
            if "import" in line or "df" in line:
                code = line
                break

    return code.strip()


# ---------- BI REPORT GENERATOR ----------


def generate_bi_report(user_prompt: str):
    """Main function to generate BI report from prompt"""

    print("\n" + "=" * 70)
    print(f" BI REPORT: {user_prompt}")
    print("=" * 70)

    # Load schema
    print("\n📊 Loading graph schema...")
    schema = load_graph_schema()

    # Generate Cypher query
    print("🤖 Generating Cypher query from prompt...")
    cypher_query = generate_cypher_from_prompt(user_prompt, schema)
    print(f"\n📝 Generated Query:\n{cypher_query}\n")

    # Execute query
    print("⚡ Executing query...")
    try:
        data = run_cypher(cypher_query)
        print(f"✓ Retrieved {len(data)} rows\n")

        if not data:
            print("⚠️ No data returned from query")
            return None

        # Display data as table
        print("📋 DATA PREVIEW:")
        df = pd.DataFrame(data)
        print(df.to_string(index=False))
        print()

        # Generate visualization
        print("🎨 Generating visualization...")
        viz_code = generate_visualization_code(user_prompt, data, cypher_query)
        print(f"\n📝 Visualization Code:\n{viz_code}\n")

        # Execute visualization
        print("📊 Creating visualization...")
        try:
            exec(viz_code, {"data": data, "pd": pd, "plt": plt, "sns": sns})
        except Exception as e:
            print(f"⚠️ Visualization error: {str(e)}")
            print("Creating default bar chart...")
            # Fallback visualization
            df = pd.DataFrame(data)
            if len(df.columns) >= 2:
                plt.figure(figsize=(10, 6))
                plt.bar(df.iloc[:, 0].astype(str), df.iloc[:, 1])
                plt.xlabel(df.columns[0])
                plt.ylabel(df.columns[1])
                plt.title(user_prompt)
                plt.xticks(rotation=45, ha="right")
                plt.tight_layout()

        # Save report
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = f"bi_report_{timestamp}.txt"

        with open(report_file, "w") as f:
            f.write(f"BI REPORT\n")
            f.write(f"Generated: {datetime.now()}\n")
            f.write(f"Prompt: {user_prompt}\n\n")
            f.write(f"Cypher Query:\n{cypher_query}\n\n")
            f.write(f"Results ({len(data)} rows):\n")
            f.write(df.to_string(index=False))

        print(f"\n✓ Report saved to: {report_file}")

        return {
            "query": cypher_query,
            "data": data,
            "dataframe": df,
            "visualization_code": viz_code,
        }

    except Exception as e:
        print(f"❌ Error executing query: {str(e)}")
        print(f"   Query: {cypher_query}")
        return None


# ---------- PREDEFINED REPORT TEMPLATES ----------


def run_predefined_reports():
    """Run a set of common BI reports"""

    reports = [
        "Show me the number of products each supplier provides",
        "Which promotions are active in which stores?",
        "Show product distribution across regions",
        "Which stores have the most promotions?",
    ]

    print("\n" + "=" * 70)
    print(" RUNNING PREDEFINED BI REPORTS")
    print("=" * 70)

    results = []
    for i, prompt in enumerate(reports, 1):
        print(f"\n\n{'=' * 70}")
        print(f" REPORT {i}/{len(reports)}")
        print(f"{'=' * 70}")
        result = generate_bi_report(prompt)
        if result:
            results.append({"prompt": prompt, "result": result})

        # Wait for user to close plot
        if result:
            plt.show()

    return results


# ---------- INTERACTIVE BI ASSISTANT ----------


def interactive_bi_assistant():
    """Interactive mode for ad-hoc BI queries"""

    print("\n" + "=" * 70)
    print(" INTERACTIVE BI ASSISTANT")
    print("=" * 70)
    print("\nAsk me to generate any BI report from your retail graph!")
    print("Type 'exit' to quit\n")

    while True:
        user_prompt = input("📊 Your question: ").strip()

        if user_prompt.lower() in ["exit", "quit", "q"]:
            print("\n👋 Goodbye!")
            break

        if not user_prompt:
            continue

        result = generate_bi_report(user_prompt)

        if result:
            plt.show()

            # Ask if user wants to refine
            refine = input("\n🔄 Refine this report? (yes/no): ").strip().lower()
            if refine == "yes":
                refinement = input("   How should I refine it? ").strip()
                refined_prompt = f"{user_prompt}. {refinement}"
                result = generate_bi_report(refined_prompt)
                if result:
                    plt.show()


# ---------- MAIN ----------

if __name__ == "__main__":
    print("\n🎯 DYNAMIC BI REPORT GENERATOR")
    print("=" * 70)
    print("\nChoose an option:")
    print("1. Run predefined reports")
    print("2. Interactive mode (ask your own questions)")
    print("3. Generate single report")

    choice = input("\nYour choice (1/2/3): ").strip()

    if choice == "1":
        run_predefined_reports()

    elif choice == "2":
        interactive_bi_assistant()

    elif choice == "3":
        prompt = input("\n📊 What report would you like? ").strip()
        result = generate_bi_report(prompt)
        if result:
            plt.show()

    else:
        print("Invalid choice")
