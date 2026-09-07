# import os
# import chromadb
# from groq import Groq
# from sentence_transformers import SentenceTransformer
# from flashrank import Ranker, RerankRequest
# from dotenv import load_dotenv

# # Explicitly load .env file from project root
# load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

# # Initialize DB & Models
# DB_DIR = "db/chroma_db"
# client = chromadb.PersistentClient(path=DB_DIR)
# collection = client.get_collection(name="tech_jobs")

# embedding_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
# ranker = Ranker(model_name="ms-marco-TinyBERT-L-2-v2")

# # Set up Groq Client
# groq_key = os.getenv("GROQ_API_KEY")
# groq_client = Groq(api_key=groq_key) if groq_key else None

# def rewrite_query(user_query: str) -> str:
#     """Query Rewriting: Expands user query into technical search terms."""
#     if not groq_client:
#         return user_query

#     prompt = f"Rewrite this job search query to include relevant technical keywords and skills for a search engine: '{user_query}'. Return only the rewritten string."
#     try:
#         response = groq_client.chat.completions.create(
#             messages=[{"role": "user", "content": prompt}],
#             model="openai/gpt-oss-20b",  # Active model from your Groq key
#             temperature=0.2,
#         )
#         return response.choices[0].message.content.strip()
#     except Exception as e:
#         print(f"[Query Expansion Warning]: API call failed ({e}). Using raw query.")
#         return user_query

# def retrieve_and_rerank(user_query: str, top_k: int = 3):
#     # Step 1: Query Expansion
#     expanded_query = rewrite_query(user_query)
    
#     # Step 2: Vector Search
#     query_vector = embedding_model.encode([expanded_query]).tolist()
#     results = collection.query(query_embeddings=query_vector, n_results=10)
    
#     docs = results["documents"][0]
#     metadatas = results["metadatas"][0]
    
#     # Step 3: Re-ranking with FlashRank
#     passages = [
#         {"id": idx, "text": doc, "meta": meta} 
#         for idx, (doc, meta) in enumerate(zip(docs, metadatas))
#     ]
    
#     rerank_request = RerankRequest(query=user_query, passages=passages)
#     reranked_results = ranker.rerank(rerank_request)
    
#     # Return top_k reranked items
#     final_hits = reranked_results[:top_k]
#     return expanded_query, final_hits

# if __name__ == "__main__":
#     test_query = "Remote Python Data Engineer jobs with AWS"
#     expanded, hits = retrieve_and_rerank(test_query)
#     print(f"\nOriginal Query: {test_query}")
#     print(f"Expanded Query: {expanded}\n")
#     print("--- TOP RERANKED RESULTS ---")
#     for hit in hits:
#         print(f"Score: {hit['score']:.4f} | Title: {hit['meta']['title']} | Location: {hit['meta']['location']}")




import os
import time
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


def get_groq_client():
    """Safely retrieves the Groq API key from OS environment or Streamlit Secrets."""
    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key:
        try:
            import streamlit as st
            groq_key = st.secrets.get("GROQ_API_KEY")
        except Exception:
            pass

    if not groq_key:
        return None
    return Groq(api_key=groq_key)


def rewrite_query(user_query: str) -> str:
    """Query Rewriting: Expands user query into technical search terms with retry backoff."""
    groq_client = get_groq_client()
    if not groq_client:
        print("[Query Expansion Warning]: GROQ_API_KEY is not configured. Using raw query.")
        return user_query

    prompt = f"Rewrite this job search query to include relevant technical keywords and skills for a search engine: '{user_query}'. Return only the rewritten string."
    
    # List of models to try in case of 404/deprecation errors
    models = ["openai/gpt-oss-20b", "llama-3.3-70b-versatile"]
    
    for model in models:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = groq_client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model=model,
                    temperature=0.2,
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                err_msg = str(e)
                # Handle 429 Rate Limits with exponential backoff (1s, 3s, 7s)
                if "429" in err_msg or "rate_limit_exceeded" in err_msg:
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt + 1)
                        continue
                # Handle 404 Model Not Found by trying the next fallback model
                elif "404" in err_msg or "model_not_found" in err_msg:
                    print(f"[Query Expansion Warning]: Model '{model}' not found. Trying fallback model.")
                    break
                
                print(f"[Query Expansion Warning]: API call failed ({e}). Using raw query.")
                return user_query

    return user_query


def retrieve_and_rerank(user_query: str, top_k: int = 3):
    # Step 1: Query Expansion
    expanded_query = rewrite_query(user_query)
    
    # Step 2: Vector Search
    query_vector = embedding_model.encode([expanded_query]).tolist()
    results = collection.query(query_embeddings=query_vector, n_results=10)
    
    # Safely extract documents and metadatas
    docs = results["documents"][0] if results.get("documents") and len(results["documents"]) > 0 else []
    metadatas = results["metadatas"][0] if results.get("metadatas") and len(results["metadatas"]) > 0 else []
    
    if not docs:
        return expanded_query, []

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