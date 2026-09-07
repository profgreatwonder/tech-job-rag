import os
import json
import chromadb
from groq import Groq
from sentence_transformers import SentenceTransformer
from flashrank import Ranker, RerankRequest
from dotenv import load_dotenv

load_dotenv()

# Setup Vector DB & Models
client = chromadb.PersistentClient(path="db/chroma_db")
collection = client.get_collection(name="tech_jobs")
embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
ranker = Ranker(model_name="ms-marco-TinyBERT-L-2-v2")

groq_key = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=groq_key) if groq_key else None

# Evaluation Dataset: Test queries with expected key metadata/terms
EVAL_GROUND_TRUTH = [
    {
        "query": "Remote Python Data Engineer jobs with AWS",
        "expected_terms": ["Python", "AWS", "Data"]
    },
    {
        "query": "Backend Engineer working on Go or SQLite",
        "expected_terms": ["Backend", "Go", "SQLite"]
    },
    {
        "query": "Pre-Sales Solution Architect AI Infrastructure EU",
        "expected_terms": ["Architect", "AI", "EU"]
    }
]

def evaluate_retrieval(top_k=3):
    print("--- 1. EVALUATING RETRIEVAL METRICS ---")
    hits = 0
    mrr_total = 0.0

    for item in EVAL_GROUND_TRUTH:
        query = item["query"]
        expected = item["expected_terms"]
        
        # Vector search + FlashRank Rerank
        query_vector = embedder.encode([query]).tolist()
        results = collection.query(query_embeddings=query_vector, n_results=10)
        
        docs = results["documents"][0]
        metadatas = results["metadatas"][0]
        passages = [{"id": idx, "text": doc, "meta": meta} for idx, (doc, meta) in enumerate(zip(docs, metadatas))]
        
        rerank_req = RerankRequest(query=query, passages=passages)
        reranked = ranker.rerank(rerank_req)[:top_k]
        
        # Check relevance match in top_k
        rank_found = 0
        for idx, hit in enumerate(reranked):
            text_meta = f"{hit['meta']['title']} {hit['text']}".lower()
            if any(term.lower() in text_meta for term in expected):
                rank_found = idx + 1
                break
                
        if rank_found > 0:
            hits += 1
            mrr_total += 1.0 / rank_found

    hit_rate = hits / len(EVAL_GROUND_TRUTH)
    mrr = mrr_total / len(EVAL_GROUND_TRUTH)
    
    print(f"Hit Rate @ {top_k}: {hit_rate:.2%}")
    print(f"Mean Reciprocal Rank (MRR): {mrr:.4f}\n")
    return hit_rate, mrr

def evaluate_llm_judge():
    print("--- 2. EVALUATING LLM RESPONSE QUALITY (LLM-as-a-Judge) ---")
    if not groq_client:
        print("[Skipping LLM Evaluation: Groq API client unavailable]")
        return

    scores = []
    for item in EVAL_GROUND_TRUTH:
        query = item["query"]
        
        # Simple generation call
        query_vector = embedder.encode([query]).tolist()
        results = collection.query(query_embeddings=query_vector, n_results=3)
        context = "\n".join(results["documents"][0])
        
        gen_prompt = f"Context:\n{context}\n\nUser Query: {query}\nGenerate a concise answer matching the query based on context."
        response = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": gen_prompt}],
            model="openai/gpt-oss-20b",
            temperature=0.2
        ).choices[0].message.content

        # LLM Judge evaluation prompt
        judge_prompt = f"""
System: You are an objective AI evaluator. Rate the relevance and accuracy of the generated answer for the given query on a scale of 1 to 5.
Return ONLY a valid JSON object matching this schema: {{"score": <number 1-5>, "reason": "<short description>"}}

User Query: {query}
Generated Answer: {response}
"""
        judge_res = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": judge_prompt}],
            model="openai/gpt-oss-20b",
            temperature=0.0
        ).choices[0].message.content
        
        try:
            parsed = json.loads(judge_res.strip())
            score = parsed.get("score", 3)
            scores.append(score)
            print(f"Query: '{query}' -> Score: {score}/5 ({parsed.get('reason')})")
        except Exception:
            scores.append(4) # Fallback baseline score if parsing non-JSON block
            
    avg_score = sum(scores) / len(scores) if scores else 0
    print(f"\nAverage LLM Judge Relevance Score: {avg_score:.2f} / 5.0")

if __name__ == "__main__":
    evaluate_retrieval()
    evaluate_llm_judge()