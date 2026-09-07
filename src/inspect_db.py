import os
import chromadb

DB_DIR = "db/chroma_db"

def inspect_chroma():
    if not os.path.exists(DB_DIR):
        print(f"Directory {DB_DIR} does not exist!")
        return

    # Connect to persistent storage
    client = chromadb.PersistentClient(path=DB_DIR)
    
    # List all collections in the database
    collections = client.list_collections()
    print(f"Collections found: {[c.name for c in collections]}\n")

    if not collections:
        print("No collections found. Run src/ingest.py first.")
        return

    collection = client.get_collection(name="tech_jobs")
    total_count = collection.count()
    print(f"Total documents in 'tech_jobs': {total_count}\n")

    # Peek at the top 3 items
    sample = collection.peek(limit=3)
    
    print("--- SAMPLE ITEMS IN DATABASE ---")
    for idx, (doc_id, doc, meta) in enumerate(zip(sample["ids"], sample["documents"], sample["metadatas"])):
        print(f"\n[ID]: {doc_id}")
        print(f"[METADATA]: {meta}")
        print(f"[DOCUMENT TEXT]:\n{doc[:200]}...") # Print first 200 chars

if __name__ == "__main__":
    inspect_chroma()