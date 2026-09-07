import os
import json
import chromadb
from sentence_transformers import SentenceTransformer

# Initialize ChromaDB persistent client
DB_DIR = "db/chroma_db"
os.makedirs(DB_DIR, exist_ok=True)

chroma_client = chromadb.PersistentClient(path=DB_DIR)

# Load lightweight embedding model
embedding_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

def load_data():
    with open("data/raw_jobs.json", "r", encoding="utf-8") as f:
        return json.load(f)

def run_ingestion():
    print("Starting ingestion pipeline into ChromaDB...")
    collection = chroma_client.get_or_create_collection(name="tech_jobs")
    
    jobs = load_data()
    documents = []
    metadatas = []
    ids = []

    for idx, job in enumerate(jobs):
        # Create rich context document for vector embedding
        doc_text = f"Title: {job['title']}\nCompany: {job['company']}\nLocation: {job['location']}\nSchedule: {job['schedule_type']}\nSkills: {job['skills']}\nDescription: {job['description']}"
        
        documents.append(doc_text)
        metadatas.append({
            "title": str(job["title"]),
            "company": str(job["company"]),
            "location": str(job["location"]),
            "skills": str(job["skills"])
        })
        ids.append(f"job_{idx}")

    print(f"Generating embeddings for {len(documents)} job listings...")
    embeddings = embedding_model.encode(documents).tolist()

    # Store in ChromaDB
    collection.add(
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
        ids=ids
    )

    print(f"Ingestion complete! Successfully indexed {collection.count()} jobs into ChromaDB.")

if __name__ == "__main__":
    run_ingestion()