import os

from neo4j import GraphDatabase


NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DB = os.getenv("NEO4J_DB", "retaildb")


driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def run(query: str, params: dict | None = None):
    with driver.session(database=NEO4J_DB) as session:
        return session.run(query, params or {})


def seed():
    # Create uniqueness constraints (idempotent)
    constraints = [
        "CREATE CONSTRAINT IF NOT EXISTS FOR (s:Supplier) REQUIRE s.name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Product) REQUIRE p.name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (pr:Promotion) REQUIRE pr.name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (st:Store) REQUIRE st.name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (r:Region) REQUIRE r.name IS UNIQUE",
    ]
    for c in constraints:
        run(c)

    # Seed the sample graph used by graph_rag_demo.py
    query = """
    MERGE (s:Supplier {name: $supplier})
    MERGE (p:Product {name: $product})
    MERGE (promo:Promotion {name: $promotion})
    MERGE (store:Store {name: $store})
    MERGE (reg:Region {name: $region})

    MERGE (s)-[:PROVIDES]->(p)
    MERGE (p)-[:IN_PROMOTION]->(promo)
    MERGE (promo)-[:ACTIVE_IN]->(store)
    MERGE (store)-[:LOCATED_IN]->(reg)
    """
    params = {
        "supplier": "Isha Supplies",
        "product": "Organic Almond Milk",
        "promotion": "Winter Wellness Sale",
        "store": "Downtown Store",
        "region": "West",
    }
    run(query, params)
    print("✅ Seeded sample retail graph into Neo4j")


if __name__ == "__main__":
    seed()
