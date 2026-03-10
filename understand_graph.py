import os

from neo4j import GraphDatabase
import pandas as pd
import json
import os

# ---------- CONFIG ----------
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DB = os.getenv("NEO4J_DB", "retaildb")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def run_cypher(query, params=None):
    with driver.session(database=NEO4J_DB) as session:
        return session.run(query, params or {}).data()


# ---------- GRAPH SCHEMA EXPLORER ----------


def explore_graph_schema():
    """Complete understanding of your graph structure"""

    print("=" * 70)
    print(" GRAPH DATA STRUCTURE ANALYSIS")
    print("=" * 70)

    # 1. Node Types and Properties
    print("\n📊 NODE TYPES AND PROPERTIES:\n")

    node_labels = run_cypher("CALL db.labels()")

    for label_row in node_labels:
        label = label_row["label"]

        # Get sample node with all properties
        sample = run_cypher(f"""
            MATCH (n:{label})
            RETURN n LIMIT 1
        """)

        if sample:
            node = sample[0]["n"]
            properties = dict(node.items()) if hasattr(node, "items") else {}

            # Count nodes of this type
            count = run_cypher(f"MATCH (n:{label}) RETURN count(n) AS count")[0][
                "count"
            ]

            print(f"   🏷️  {label} ({count} nodes)")
            print(f"      Properties: {list(properties.keys())}")
            print(f"      Sample: {properties}")
            print()

    # 2. Relationship Types and Patterns
    print("\n🔗 RELATIONSHIP TYPES AND PATTERNS:\n")

    rel_types = run_cypher("CALL db.relationshipTypes()")

    for rel_row in rel_types:
        rel_type = rel_row["relationshipType"]

        # Get relationship pattern
        pattern = run_cypher(f"""
            MATCH (a)-[r:{rel_type}]->(b)
            RETURN labels(a)[0] AS from_label, labels(b)[0] AS to_label, count(*) AS count
            ORDER BY count DESC
            LIMIT 3
        """)

        if pattern:
            print(f"   ➡️  {rel_type}")
            for p in pattern:
                print(
                    f"      ({p['from_label']})-[:{rel_type}]->({p['to_label']}) × {p['count']}"
                )
            print()

    # 3. Graph Statistics
    print("\n📈 GRAPH STATISTICS:\n")

    total_nodes = run_cypher("MATCH (n) RETURN count(n) AS count")[0]["count"]
    total_rels = run_cypher("MATCH ()-[r]->() RETURN count(r) AS count")[0]["count"]

    print(f"   Total Nodes: {total_nodes}")
    print(f"   Total Relationships: {total_rels}")
    print(
        f"   Graph Density: {total_rels / max(total_nodes, 1):.2f} relationships per node"
    )

    # 4. Common Patterns
    print("\n🔍 COMMON GRAPH PATTERNS:\n")

    # Pattern 1: Full supply chain
    full_chains = run_cypher("""
        MATCH path = (s:Supplier)-[:PROVIDES]->(p:Product)-[:IN_PROMOTION]->(pr:Promotion)-[:ACTIVE_IN]->(st:Store)-[:LOCATED_IN]->(r:Region)
        RETURN count(path) AS count
    """)
    print(f"   Complete Supply Chains: {full_chains[0]['count']}")

    # Pattern 2: Products without promotions
    orphan_products = run_cypher("""
        MATCH (p:Product)
        WHERE NOT (p)-[:IN_PROMOTION]->()
        RETURN count(p) AS count
    """)
    print(f"   Products Not in Promotions: {orphan_products[0]['count']}")

    # Pattern 3: Most connected nodes (FIXED QUERY)
    print("\n   Most Connected Nodes:")
    most_connected = run_cypher("""
        MATCH (n)
        WHERE n.name IS NOT NULL
        RETURN labels(n)[0] AS type, n.name AS name, 
               count { (n)--() } AS connections
        ORDER BY connections DESC
        LIMIT 5
    """)
    for node in most_connected:
        print(
            f"      - {node['name']} ({node['type']}): {node['connections']} connections"
        )

    print("\n" + "=" * 70)


# ---------- DATA EXPORT FOR ANALYSIS ----------


def export_graph_to_dataframes():
    """Export graph data as Pandas DataFrames for analysis"""

    print("\n📤 EXPORTING GRAPH DATA TO DATAFRAMES...\n")

    dataframes = {}

    # Export Suppliers
    suppliers_df = pd.DataFrame(
        run_cypher("""
        MATCH (s:Supplier)
        RETURN s.name AS name, id(s) AS id
    """)
    )
    dataframes["suppliers"] = suppliers_df
    print(f"✓ Suppliers: {len(suppliers_df)} rows")

    # Export Products
    products_df = pd.DataFrame(
        run_cypher("""
        MATCH (p:Product)
        RETURN p.name AS name, id(p) AS id
    """)
    )
    dataframes["products"] = products_df
    print(f"✓ Products: {len(products_df)} rows")

    # Export Promotions
    promotions_df = pd.DataFrame(
        run_cypher("""
        MATCH (pr:Promotion)
        RETURN pr.name AS name, id(pr) AS id
    """)
    )
    dataframes["promotions"] = promotions_df
    print(f"✓ Promotions: {len(promotions_df)} rows")

    # Export Stores
    stores_df = pd.DataFrame(
        run_cypher("""
        MATCH (st:Store)
        RETURN st.name AS name, id(st) AS id
    """)
    )
    dataframes["stores"] = stores_df
    print(f"✓ Stores: {len(stores_df)} rows")

    # Export Regions
    regions_df = pd.DataFrame(
        run_cypher("""
        MATCH (r:Region)
        RETURN r.name AS name, id(r) AS id
    """)
    )
    dataframes["regions"] = regions_df
    print(f"✓ Regions: {len(regions_df)} rows")

    # Export Supplier-Product relationships
    supplier_products_df = pd.DataFrame(
        run_cypher("""
        MATCH (s:Supplier)-[:PROVIDES]->(p:Product)
        RETURN s.name AS supplier, p.name AS product
    """)
    )
    dataframes["supplier_products"] = supplier_products_df
    print(f"✓ Supplier-Products: {len(supplier_products_df)} rows")

    # Export Product-Promotion relationships
    product_promotions_df = pd.DataFrame(
        run_cypher("""
        MATCH (p:Product)-[:IN_PROMOTION]->(pr:Promotion)
        RETURN p.name AS product, pr.name AS promotion
    """)
    )
    dataframes["product_promotions"] = product_promotions_df
    print(f"✓ Product-Promotions: {len(product_promotions_df)} rows")

    # Export Promotion-Store relationships
    promotion_stores_df = pd.DataFrame(
        run_cypher("""
        MATCH (pr:Promotion)-[:ACTIVE_IN]->(st:Store)
        RETURN pr.name AS promotion, st.name AS store
    """)
    )
    dataframes["promotion_stores"] = promotion_stores_df
    print(f"✓ Promotion-Stores: {len(promotion_stores_df)} rows")

    # Export Store-Region relationships
    store_regions_df = pd.DataFrame(
        run_cypher("""
        MATCH (st:Store)-[:LOCATED_IN]->(r:Region)
        RETURN st.name AS store, r.name AS region
    """)
    )
    dataframes["store_regions"] = store_regions_df
    print(f"✓ Store-Regions: {len(store_regions_df)} rows")

    # Export complete supply chain view
    supply_chain_df = pd.DataFrame(
        run_cypher("""
        MATCH (s:Supplier)-[:PROVIDES]->(p:Product)
        OPTIONAL MATCH (p)-[:IN_PROMOTION]->(pr:Promotion)
        OPTIONAL MATCH (pr)-[:ACTIVE_IN]->(st:Store)
        OPTIONAL MATCH (st)-[:LOCATED_IN]->(r:Region)
        RETURN s.name AS supplier, p.name AS product, 
               pr.name AS promotion, st.name AS store, r.name AS region
    """)
    )
    dataframes["supply_chain"] = supply_chain_df
    print(f"✓ Supply Chain View: {len(supply_chain_df)} rows")

    print("\n" + "=" * 70)

    return dataframes


# ---------- GRAPH SUMMARY FOR LLM ----------


def generate_graph_summary_for_llm():
    """Generate a concise summary of the graph for LLM context"""

    summary = {
        "node_types": [],
        "relationship_types": [],
        "sample_data": {},
        "graph_patterns": [],
        "statistics": {},
    }

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
            RETURN labels(a)[0] AS from, labels(b)[0] AS to, count(*) AS count
            ORDER BY count DESC
            LIMIT 1
        """)

        if pattern and pattern[0].get("from") and pattern[0].get("to"):
            summary["relationship_types"].append(
                {
                    "type": rel_type,
                    "pattern": f"({pattern[0]['from']})-[:{rel_type}]->({pattern[0]['to']})",
                    "count": pattern[0]["count"],
                }
            )

    # Statistics
    total_nodes = run_cypher("MATCH (n) RETURN count(n) AS count")[0]["count"]
    total_rels = run_cypher("MATCH ()-[r]->() RETURN count(r) AS count")[0]["count"]

    summary["statistics"] = {
        "total_nodes": total_nodes,
        "total_relationships": total_rels,
        "density": total_rels / max(total_nodes, 1),
    }

    # Common patterns
    full_chains = run_cypher("""
        MATCH path = (s:Supplier)-[:PROVIDES]->(p:Product)-[:IN_PROMOTION]->(pr:Promotion)-[:ACTIVE_IN]->(st:Store)-[:LOCATED_IN]->(r:Region)
        RETURN count(path) AS count
    """)[0]["count"]

    summary["graph_patterns"].append(
        {
            "pattern": "Complete Supply Chain",
            "description": "Supplier → Product → Promotion → Store → Region",
            "count": full_chains,
        }
    )

    # Sample complete chains
    sample_chains = run_cypher("""
        MATCH (s:Supplier)-[:PROVIDES]->(p:Product)-[:IN_PROMOTION]->(pr:Promotion)-[:ACTIVE_IN]->(st:Store)-[:LOCATED_IN]->(r:Region)
        RETURN s.name AS supplier, p.name AS product, pr.name AS promotion, st.name AS store, r.name AS region
        LIMIT 3
    """)

    summary["sample_data"]["complete_chains"] = sample_chains

    return summary


def print_graph_summary():
    """Print human-readable graph summary"""

    summary = generate_graph_summary_for_llm()

    print("\n" + "=" * 70)
    print(" GRAPH SUMMARY FOR BI REPORTING")
    print("=" * 70)

    print("\n📊 NODE TYPES:")
    for node_type in summary["node_types"]:
        print(f"   • {node_type['type']}: {node_type['count']} nodes")
        if node_type["samples"]:
            print(f"     Examples: {', '.join(node_type['samples'])}")

    print("\n🔗 RELATIONSHIP TYPES:")
    for rel_type in summary["relationship_types"]:
        print(f"   • {rel_type['pattern']}: {rel_type['count']} connections")

    print("\n📈 STATISTICS:")
    print(f"   • Total Nodes: {summary['statistics']['total_nodes']}")
    print(f"   • Total Relationships: {summary['statistics']['total_relationships']}")
    print(f"   • Density: {summary['statistics']['density']:.2f}")

    print("\n🔍 GRAPH PATTERNS:")
    for pattern in summary["graph_patterns"]:
        print(f"   • {pattern['pattern']}: {pattern['description']}")
        print(f"     Count: {pattern['count']}")

    print("\n📋 SAMPLE COMPLETE SUPPLY CHAINS:")
    for chain in summary["sample_data"].get("complete_chains", []):
        print(
            f"   • {chain['supplier']} → {chain['product']} → {chain['promotion']} → {chain['store']} → {chain['region']}"
        )

    print("\n" + "=" * 70)

    return summary


# ---------- MAIN ----------

if __name__ == "__main__":
    # 1. Explore full schema
    explore_graph_schema()

    # 2. Export to DataFrames
    dataframes = export_graph_to_dataframes()

    # 3. Show sample data
    print("\n📋 SAMPLE DATA:\n")
    print("Suppliers:")
    print(dataframes["suppliers"])
    print("\nProducts:")
    print(dataframes["products"])
    print("\nSupply Chain View (first 10 rows):")
    print(dataframes["supply_chain"].head(10))

    # 4. Generate summary
    summary = print_graph_summary()

    # 5. Save summary as JSON for LLM use
    with open("graph_schema.json", "w") as f:
        json.dump(summary, f, indent=2)
    print("\n✓ Graph schema saved to 'graph_schema.json'")

    print(
        "\n✅ Graph analysis complete! You can now use 'dynamic_bi_reports.py' to generate reports."
    )
