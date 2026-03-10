from chromadb import PersistentClient
import ollama

client = PersistentClient(path="./chroma")
print("Available collections:", [c.name for c in client.list_collections()])

collection = client.get_collection("retail_rag")

question = "If Isha Supplies has a disruption, what is impacted?"

query_embedding = ollama.embeddings(model="nomic-embed-text", prompt=question)["embedding"]

results = collection.query(query_embeddings=[query_embedding], n_results=3)

print("\n📄 Retrieved Context:")
for doc in results["documents"][0]:
    print("-", doc)

prompt = f"""
Answer the question using the context below.

Context:
{chr(10).join(results["documents"][0])}

Question:
{question}
"""

response = ollama.generate(model="llama3", prompt=prompt)

print("\n🤖 RAG Answer:\n")
print(response["response"])
