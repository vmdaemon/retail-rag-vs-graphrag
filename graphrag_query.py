import os

from neo4j import GraphDatabase
import ollama

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DB = os.getenv("NEO4J_DB", "retaildb")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

question = "If Isha Supplies has a disruption, what is impacted?"

with driver.session(database=NEO4J_DB) as session:
    result = session.run("""
        MATCH (sup:Supplier {name:"Isha Supplies"})-[:SUPPLIES]->(p)
              -[:PART_OF]->(promo)
              -[:ACTIVE_IN]->(store)
              -[:LOCATED_IN]->(region)
        RETURN
          p.name AS product,
          promo.name AS promotion,
          store.name AS store,
          region.name AS region
    """).single()
facts = f"""
- Product impacted: {result["product"]}
- Promotion impacted: {result["promotion"]}
- Store impacted: {result["store"]}
- Region impacted: {result["region"]}
"""
print(result)
print(facts)

prompt = f"""
You are answering using graph-derived facts.

Facts:
{facts}

Question:
{question}

Answer with clear reasoning.
"""

response = ollama.generate(model="llama3", prompt=prompt)

print("\nGraphRAG Answer:\n")
print(response["response"])
