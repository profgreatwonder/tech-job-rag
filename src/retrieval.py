import os
import chromadb
from groq import Groq
from sentence_transformers import SentenceTransformer
from flashrank import Ranker, RerankRequest
from dotenv import load_dotenv

# Explicitly load .env file from project root
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

# Initialize DB & Models
DB_DIR = "db/chroma_db"
client = chromadb.PersistentClient(path=DB_DIR)
collection = client.get_collection(name="tech_jobs")

embedding_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
ranker = Ranker(model_name="ms-marco-TinyBERT-L-2-v2")

# Set up Groq Client
groq_key = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=groq_key) if groq_key else None

def rewrite_query(user_query: str) -> str:
    """Query Rewriting: Expands user query into technical search terms."""
    if not groq_client:
        return user_query

    prompt = f"Rewrite this job search query to include relevant technical keywords and skills for a search engine: '{user_query}'. Return only the rewritten string."
    try:
        response = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="openai/gpt-oss-20b",  # Active model from your Groq key
            temperature=0.2,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[Query Expansion Warning]: API call failed ({e}). Using raw query.")
        return user_query

def retrieve_and_rerank(user_query: str, top_k: int = 3):
    # Step 1: Query Expansion
    expanded_query = rewrite_query(user_query)
    
    # Step 2: Vector Search
    query_vector = embedding_model.encode([expanded_query]).tolist()
    results = collection.query(query_embeddings=query_vector, n_results=10)
    
    docs = results["documents"][0]
    metadatas = results["metadatas"][0]
    
    # Step 3: Re-ranking with FlashRank
    passages = [
        {"id": idx, "text": doc, "meta": meta} 
        for idx, (doc, meta) in enumerate(zip(docs, metadatas))
    ]
    
    rerank_request = RerankRequest(query=user_query, passages=passages)
    reranked_results = ranker.rerank(rerank_request)
    
    # Return top_k reranked items
    final_hits = reranked_results[:top_k]
    return expanded_query, final_hits

if __name__ == "__main__":
    test_query = "Remote Python Data Engineer jobs with AWS"
    expanded, hits = retrieve_and_rerank(test_query)
    print(f"\nOriginal Query: {test_query}")
    print(f"Expanded Query: {expanded}\n")
    print("--- TOP RERANKED RESULTS ---")
    for hit in hits:
        print(f"Score: {hit['score']:.4f} | Title: {hit['meta']['title']} | Location: {hit['meta']['location']}")