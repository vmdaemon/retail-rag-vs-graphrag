import os

from neo4j import GraphDatabase
import requests
import matplotlib.pyplot as plt
import networkx as nx
from matplotlib.patches import FancyBboxPatch

# ---------- CONFIG ----------

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DB = os.getenv("NEO4J_DB", "retaildb")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

# ---------- NEO4J HELPERS ----------

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def run_cypher(query, params=None):
    with driver.session(database=NEO4J_DB) as session:
        return session.run(query, params or {}).data()


# ---------- DIAGNOSTICS ----------


def diagnose_data():
    """Check what data exists in the database"""

    print("=== DATABASE DIAGNOSTICS ===\n")

    # Check all node labels
    print("1. NODE LABELS:")
    labels = run_cypher("CALL db.labels()")
    for label in labels:
        print(f"   - {label['label']}")

    # Count all nodes
    print("\n2. NODE COUNTS:")
    counts = run_cypher("MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count")
    for c in counts:
        print(f"   - {c['label']}: {c['count']} nodes")

    # Check suppliers
    print("\n3. SUPPLIERS:")
    suppliers = run_cypher("MATCH (s:Supplier) RETURN s.name AS name")
    if suppliers:
        for s in suppliers:
            print(f"   - '{s['name']}'")
    else:
        print("   - NO SUPPLIERS FOUND")

    # Check relationship types
    print("\n4. RELATIONSHIP TYPES:")
    rel_types = run_cypher("CALL db.relationshipTypes()")
    for rt in rel_types:
        print(f"   - {rt['relationshipType']}")

    # Check full impact chain
    print("\n5. COMPLETE IMPACT CHAINS:")
    chains = run_cypher("""
        MATCH path = (s:Supplier)-[:PROVIDES]->(p:Product)-[:IN_PROMOTION]->(promo:Promotion)-[:ACTIVE_IN]->(store:Store)-[:LOCATED_IN]->(region:Region)
        RETURN s.name AS supplier, p.name AS product, promo.name AS promotion, 
               store.name AS store, region.name AS region
        LIMIT 3
    """)
    if chains:
        for c in chains:
            print(
                f"   - {c['supplier']} → {c['product']} → {c['promotion']} → {c['store']} → {c['region']}"
            )
    else:
        print("   - NO COMPLETE CHAINS FOUND (missing some relationships)")

    print("\n" + "=" * 50 + "\n")


# ---------- GRAPH FACT EXTRACTION (GraphRAG-style) ----------


def get_supplier_impact_facts(supplier_name: str):
    """Original single-supplier fact extraction"""
    query = """
    MATCH (s:Supplier {name: $name})-[:PROVIDES]->(p:Product)
    OPTIONAL MATCH (p)-[:IN_PROMOTION]->(promo:Promotion)
    OPTIONAL MATCH (promo)-[:ACTIVE_IN]->(store:Store)
    OPTIONAL MATCH (store)-[:LOCATED_IN]->(r:Region)
    RETURN s, p, promo, store, r
    """
    rows = run_cypher(query, {"name": supplier_name})

    facts = set()

    for row in rows:
        s = row.get("s")
        p = row.get("p")
        promo = row.get("promo")
        store = row.get("store")
        region = row.get("r")

        if s and p:
            facts.add(f"Supplier {s['name']} provides {p['name']}.")

        if p and promo:
            facts.add(f"{p['name']} is included in the {promo['name']} promotion.")

        if promo and store:
            facts.add(
                f"The {promo['name']} promotion is active in the {store['name']}."
            )

        if store and region:
            facts.add(f"The {store['name']} is located in the {region['name']} region.")

    return sorted(facts)


def get_extended_supplier_impact(supplier_name: str):
    """NEW: Multi-hop impact analysis (up to 3 hops)"""
    query = """
    MATCH path = (s:Supplier {name: $name})-[*1..3]-(connected)
    WHERE s <> connected
    WITH s, connected, path
    RETURN DISTINCT 
        s.name AS supplier,
        labels(connected)[0] AS connected_type,
        connected.name AS connected_name,
        length(path) AS hops
    ORDER BY hops, connected_type
    """
    rows = run_cypher(query, {"name": supplier_name})

    facts = {
        "products": set(),
        "promotions": set(),
        "stores": set(),
        "regions": set(),
        "summary": [],
    }

    for row in rows:
        conn_type = row["connected_type"]
        conn_name = row["connected_name"]
        hops = row["hops"]

        if conn_type == "Product":
            facts["products"].add(conn_name)
        elif conn_type == "Promotion":
            facts["promotions"].add(conn_name)
        elif conn_type == "Store":
            facts["stores"].add(conn_name)
        elif conn_type == "Region":
            facts["regions"].add(conn_name)

    # Create summary
    if facts["products"]:
        facts["summary"].append(
            f"Products affected: {', '.join(sorted(facts['products']))}"
        )
    if facts["promotions"]:
        facts["summary"].append(
            f"Promotions impacted: {', '.join(sorted(facts['promotions']))}"
        )
    if facts["stores"]:
        facts["summary"].append(
            f"Stores affected: {', '.join(sorted(facts['stores']))}"
        )
    if facts["regions"]:
        facts["summary"].append(
            f"Regions impacted: {', '.join(sorted(facts['regions']))}"
        )

    return facts


# ---------- OLLAMA LLM CALL ----------


def ask_llm(prompt: str):
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are a precise, concise reasoning assistant.",
            },
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }
    resp = requests.post(OLLAMA_URL, json=payload)
    resp.raise_for_status()
    data = resp.json()
    return data["message"]["content"]


def graphrag_answer(question: str, supplier_name: str):
    """Original GraphRAG answer"""
    facts = get_supplier_impact_facts(supplier_name)
    context = "\n".join(facts) if facts else "No facts found."

    prompt = f"""
You are given graph-derived facts from a retail knowledge graph.

Facts:
{context}

Question:
{question}

Answer the question ONLY using the facts above. If something is not supported by the facts, say so explicitly.
Provide a short, clear answer.
"""
    return ask_llm(prompt), facts


def enhanced_graphrag_answer(question: str, supplier_name: str):
    """NEW: Enhanced answer using multi-hop analysis"""
    basic_facts = get_supplier_impact_facts(supplier_name)
    extended_facts = get_extended_supplier_impact(supplier_name)

    context = "\n".join(basic_facts) if basic_facts else "No direct facts found."
    extended_context = (
        "\n".join(extended_facts["summary"])
        if extended_facts["summary"]
        else "No extended impact found."
    )

    prompt = f"""
You are given graph-derived facts from a retail knowledge graph about supply chain impacts.

Direct Facts:
{context}

Extended Impact Analysis:
{extended_context}

Question:
{question}

Provide a comprehensive answer that explains:
1. Immediate impacts (direct connections)
2. Downstream effects (indirect connections)
3. Overall business risk

Be specific and cite the facts provided.
"""
    return ask_llm(prompt), basic_facts, extended_facts


# ---------- VISUALIZATION ----------


def plot_products_per_supplier():
    """Original bar chart"""
    query = """
    MATCH (s:Supplier)-[:PROVIDES]->(p:Product)
    RETURN s.name AS supplier, count(p) AS products
    ORDER BY products DESC
    """
    rows = run_cypher(query)

    suppliers = [row["supplier"] for row in rows]
    counts = [row["products"] for row in rows]

    if not suppliers:
        print("No data to plot.")
        return

    plt.figure(figsize=(8, 5))
    plt.bar(suppliers, counts, color="teal")
    plt.title("Products per Supplier")
    plt.xlabel("Supplier")
    plt.ylabel("Number of Products")
    plt.tight_layout()
    plt.show()


def visualize_impact_network(supplier_name: str):
    """NEW: Network graph visualization of supplier impact"""
    query = """
    MATCH path = (s:Supplier {name: $name})-[*1..3]-(connected)
    RETURN path
    """
    results = run_cypher(query, {"name": supplier_name})

    if not results:
        print(f"No impact network found for {supplier_name}")
        return

    # Create NetworkX graph
    G = nx.Graph()

    # Color mapping for different node types
    color_map = {
        "Supplier": "#FF6B6B",
        "Product": "#4ECDC4",
        "Promotion": "#FFE66D",
        "Store": "#95E1D3",
        "Region": "#C7CEEA",
    }

    node_colors = {}
    node_labels = {}

    # Process paths
    for result in results:
        path = result["path"]
        nodes = path.nodes
        relationships = path.relationships

        # Add nodes
        for node in nodes:
            node_id = node.element_id
            node_label = list(node.labels)[0] if node.labels else "Unknown"
            node_name = node.get("name", "Unnamed")

            G.add_node(node_id)
            node_colors[node_id] = color_map.get(node_label, "#CCCCCC")
            node_labels[node_id] = f"{node_name}\n({node_label})"

        # Add edges
        for rel in relationships:
            G.add_edge(
                rel.start_node.element_id, rel.end_node.element_id, label=rel.type
            )

    # Create visualization
    plt.figure(figsize=(14, 10))

    # Use spring layout for better visualization
    pos = nx.spring_layout(G, k=2, iterations=50)

    # Draw nodes
    colors = [node_colors[node] for node in G.nodes()]
    nx.draw_networkx_nodes(G, pos, node_color=colors, node_size=3000, alpha=0.9)

    # Draw edges
    nx.draw_networkx_edges(G, pos, width=2, alpha=0.5, edge_color="gray")

    # Draw labels
    labels = {node: node_labels[node] for node in G.nodes()}
    nx.draw_networkx_labels(G, pos, labels, font_size=8, font_weight="bold")

    # Draw edge labels
    edge_labels = nx.get_edge_attributes(G, "label")
    nx.draw_networkx_edge_labels(G, pos, edge_labels, font_size=7)

    # Add legend
    legend_elements = [
        plt.Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor=color,
            markersize=10,
            label=label,
        )
        for label, color in color_map.items()
    ]
    plt.legend(handles=legend_elements, loc="upper left", fontsize=10)

    plt.title(
        f"Supply Chain Impact Network: {supplier_name}", fontsize=16, fontweight="bold"
    )
    plt.axis("off")
    plt.tight_layout()
    plt.show()


def create_impact_dashboard(supplier_name: str):
    """NEW: Multi-panel dashboard showing all analytics"""

    # Get data
    extended_facts = get_extended_supplier_impact(supplier_name)

    # Create figure with subplots
    fig = plt.figure(figsize=(16, 10))
    gs = fig.add_gridspec(3, 2, hspace=0.3, wspace=0.3)

    # 1. Products per Supplier (top left)
    ax1 = fig.add_subplot(gs[0, 0])
    query1 = """
    MATCH (s:Supplier)-[:PROVIDES]->(p:Product)
    RETURN s.name AS supplier, count(p) AS products
    ORDER BY products DESC
    """
    rows1 = run_cypher(query1)
    if rows1:
        suppliers = [row["supplier"] for row in rows1]
        counts = [row["products"] for row in rows1]
        ax1.bar(suppliers, counts, color="teal")
        ax1.set_title("Products per Supplier", fontweight="bold")
        ax1.set_xlabel("Supplier")
        ax1.set_ylabel("Number of Products")

    # 2. Impact Summary (top right)
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.axis("off")
    impact_text = f"Impact Analysis: {supplier_name}\n\n"
    impact_text += f"Products: {len(extended_facts['products'])}\n"
    impact_text += f"Promotions: {len(extended_facts['promotions'])}\n"
    impact_text += f"Stores: {len(extended_facts['stores'])}\n"
    impact_text += f"Regions: {len(extended_facts['regions'])}\n\n"
    impact_text += "Affected Items:\n"
    for item in extended_facts["summary"]:
        impact_text += f"• {item}\n"

    ax2.text(
        0.1,
        0.9,
        impact_text,
        transform=ax2.transAxes,
        fontsize=11,
        verticalalignment="top",
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
    )

    # 3. Impact by Category (middle left)
    ax3 = fig.add_subplot(gs[1, 0])
    categories = ["Products", "Promotions", "Stores", "Regions"]
    impact_counts = [
        len(extended_facts["products"]),
        len(extended_facts["promotions"]),
        len(extended_facts["stores"]),
        len(extended_facts["regions"]),
    ]
    colors_pie = ["#4ECDC4", "#FFE66D", "#95E1D3", "#C7CEEA"]
    ax3.pie(
        impact_counts,
        labels=categories,
        autopct="%1.0f%%",
        colors=colors_pie,
        startangle=90,
    )
    ax3.set_title("Impact Distribution by Category", fontweight="bold")

    # 4. Promotion Coverage (middle right)
    ax4 = fig.add_subplot(gs[1, 1])
    query4 = """
    MATCH (promo:Promotion)-[:ACTIVE_IN]->(store:Store)
    RETURN promo.name AS promotion, count(store) AS stores
    ORDER BY stores DESC
    """
    rows4 = run_cypher(query4)
    if rows4:
        promos = [row["promotion"] for row in rows4]
        store_counts = [row["stores"] for row in rows4]
        ax4.barh(promos, store_counts, color="#FFE66D")
        ax4.set_title("Promotion Store Coverage", fontweight="bold")
        ax4.set_xlabel("Number of Stores")
        ax4.set_ylabel("Promotion")

    # 5. Regional Distribution (bottom, spans both columns)
    ax5 = fig.add_subplot(gs[2, :])
    query5 = """
    MATCH (region:Region)<-[:LOCATED_IN]-(store:Store)<-[:ACTIVE_IN]-(promo:Promotion)<-[:IN_PROMOTION]-(p:Product)
    RETURN region.name AS region, count(DISTINCT p) AS products
    ORDER BY products DESC
    """
    rows5 = run_cypher(query5)
    if rows5:
        regions = [row["region"] for row in rows5]
        prod_counts = [row["products"] for row in rows5]
        ax5.bar(regions, prod_counts, color="#C7CEEA")
        ax5.set_title("Products by Region", fontweight="bold")
        ax5.set_xlabel("Region")
        ax5.set_ylabel("Number of Products")

    fig.suptitle(
        f"Supply Chain Analytics Dashboard - {supplier_name}",
        fontsize=18,
        fontweight="bold",
        y=0.98,
    )

    plt.show()


# ---------- DEMO SCENARIOS ----------


def demo_basic_query(supplier_name: str):
    """Demo 1: Basic single-supplier query"""
    print("\n" + "=" * 60)
    print("DEMO 1: BASIC SUPPLIER IMPACT QUERY")
    print("=" * 60)

    question = f"If {supplier_name} has a disruption, what is impacted?"
    print(f"\nQuestion: {question}\n")

    answer, facts = graphrag_answer(question, supplier_name)

    print("Graph-derived facts:")
    if facts:
        for f in facts:
            print(f" - {f}")
    else:
        print(" - (No facts found)")

    print(f"\nGraphRAG Answer:\n{answer}\n")


def demo_enhanced_query(supplier_name: str):
    """Demo 2: Enhanced multi-hop analysis"""
    print("\n" + "=" * 60)
    print("DEMO 2: ENHANCED MULTI-HOP IMPACT ANALYSIS")
    print("=" * 60)

    question = f"What is the complete downstream impact if {supplier_name} has issues?"
    print(f"\nQuestion: {question}\n")

    answer, basic_facts, extended_facts = enhanced_graphrag_answer(
        question, supplier_name
    )

    print("Direct Facts:")
    for f in basic_facts:
        print(f" - {f}")

    print("\nExtended Impact:")
    for s in extended_facts["summary"]:
        print(f" - {s}")

    print(f"\nEnhanced GraphRAG Answer:\n{answer}\n")


def demo_multiple_questions(supplier_name: str):
    """Demo 3: Multiple question types"""
    print("\n" + "=" * 60)
    print("DEMO 3: MULTIPLE QUESTION SCENARIOS")
    print("=" * 60)

    questions = [
        f"What promotions would be affected if {supplier_name} has issues?",
        f"Which regions depend on {supplier_name}?",
        f"What's the complete impact chain for {supplier_name}?",
    ]

    for i, question in enumerate(questions, 1):
        print(f"\n--- Question {i} ---")
        print(f"Q: {question}")
        answer, _, extended = enhanced_graphrag_answer(question, supplier_name)
        print(f"A: {answer[:300]}...")  # Truncate for readability


# ---------- MAIN DEMO ----------


def main():
    # Run diagnostics
    diagnose_data()

    supplier = "Isha Supplies"

    # Demo 1: Basic query
    demo_basic_query(supplier)

    # Demo 2: Enhanced query
    demo_enhanced_query(supplier)

    # Demo 3: Multiple questions
    demo_multiple_questions(supplier)

    # Visualization 1: Original bar chart
    print("\n" + "=" * 60)
    print("VISUALIZATION 1: Products per Supplier")
    print("=" * 60)
    plot_products_per_supplier()

    # Visualization 2: Impact network
    print("\n" + "=" * 60)
    print("VISUALIZATION 2: Impact Network Graph")
    print("=" * 60)
    visualize_impact_network(supplier)

    # Visualization 3: Analytics dashboard
    print("\n" + "=" * 60)
    print("VISUALIZATION 3: Analytics Dashboard")
    print("=" * 60)
    create_impact_dashboard(supplier)

    print("\n" + "=" * 60)
    print("DEMO COMPLETE!")
    print("=" * 60)


if __name__ == "__main__":
    main()
