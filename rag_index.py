from chromadb import PersistentClient
import ollama
from retail_data import documents

client = PersistentClient(path="./chroma")
collection = client.get_or_create_collection(name="retail_rag")

for i, doc in enumerate(documents):
    embedding = ollama.embeddings(model="nomic-embed-text", prompt=doc)["embedding"]
    collection.add(ids=[str(i)], documents=[doc], embeddings=[embedding])

print("✅ retail_rag collection created at ./chroma")
