# import os
# import time
# import sqlite3
# import streamlit as st
# from dotenv import load_dotenv

# # Load Environment Variables
# load_dotenv()

# # Setup Local Monitoring Database (SQLite)
# FEEDBACK_DB = "db/feedback.db"
# os.makedirs("db", exist_ok=True)

# def init_feedback_db():
#     conn = sqlite3.connect(FEEDBACK_DB)
#     cursor = conn.cursor()
#     cursor.execute("""
#         CREATE TABLE IF NOT EXISTS query_logs (
#             id INTEGER PRIMARY KEY AUTOINCREMENT,
#             timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
#             query TEXT,
#             expanded_query TEXT,
#             response TEXT,
#             latency_sec REAL,
#             feedback INTEGER DEFAULT 0
#         )
#     """)
#     conn.commit()
#     conn.close()

# init_feedback_db()

# def log_interaction(query, expanded_query, response, latency):
#     conn = sqlite3.connect(FEEDBACK_DB)
#     cursor = conn.cursor()
#     cursor.execute("""
#         INSERT INTO query_logs (query, expanded_query, response, latency_sec)
#         VALUES (?, ?, ?, ?)
#     """, (query, expanded_query, response, latency))
#     log_id = cursor.lastrowid
#     conn.commit()
#     conn.close()
#     return log_id

# def log_feedback(log_id, feedback_value):
#     conn = sqlite3.connect(FEEDBACK_DB)
#     cursor = conn.cursor()
#     cursor.execute("UPDATE query_logs SET feedback = ? WHERE id = ?", (feedback_value, log_id))
#     conn.commit()
#     conn.close()

# # Page Config FIRST
# st.set_page_config(page_title="Tech Career RAG Assistant", page_icon="💼", layout="wide")

# # Cached Lazy Loaders
# @st.cache_resource(show_spinner="Loading ML Models and Vector Store...")
# def load_resources():
#     import chromadb
#     from groq import Groq
#     from sentence_transformers import SentenceTransformer
#     from flashrank import Ranker
    
#     client = chromadb.PersistentClient(path="db/chroma_db")
#     collection = client.get_collection(name="tech_jobs")
#     embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
#     ranker = Ranker(model_name="ms-marco-TinyBERT-L-2-v2")
#     groq_key = os.getenv("GROQ_API_KEY")
#     groq_client = Groq(api_key=groq_key) if groq_key else None
#     return collection, embedder, ranker, groq_client

# def rewrite_query(groq_client, user_query: str) -> str:
#     if not groq_client:
#         return user_query
#     prompt = f"Rewrite this job search query to include relevant technical keywords: '{user_query}'. Return only the rewritten string."
#     try:
#         res = groq_client.chat.completions.create(
#             messages=[{"role": "user", "content": prompt}],
#             model="openai/gpt-oss-20b",
#             temperature=0.2,
#         )
#         return res.choices[0].message.content.strip()
#     except Exception:
#         return user_query

# def generate_rag_response(collection, embedder, ranker, groq_client, user_query: str):
#     from flashrank import RerankRequest
#     start_time = time.time()
#     expanded_query = rewrite_query(groq_client, user_query)
    
#     query_vector = embedder.encode([expanded_query]).tolist()
#     results = collection.query(query_embeddings=query_vector, n_results=5)
    
#     docs = results["documents"][0]
#     metadatas = results["metadatas"][0]
    
#     passages = [{"id": idx, "text": doc, "meta": meta} for idx, (doc, meta) in enumerate(zip(docs, metadatas))]
#     rerank_req = RerankRequest(query=user_query, passages=passages)
#     reranked = ranker.rerank(rerank_req)[:3]
    
#     context_str = "\n\n".join([f"Job Title: {item['meta']['title']}\nLocation: {item['meta']['location']}\nDetails: {item['text']}" for item in reranked])
    
#     system_prompt = "You are an expert Tech Career & Job Search Assistant. Answer the candidate's query strictly based on the provided job listings."
#     user_prompt = f"Context:\n{context_str}\n\nCandidate Query: {user_query}"
    
#     try:
#         completion = groq_client.chat.completions.create(
#             messages=[
#                 {"role": "system", "content": system_prompt},
#                 {"role": "user", "content": user_prompt}
#             ],
#             model="openai/gpt-oss-20b",
#             temperature=0.3
#         )
#         answer = completion.choices[0].message.content
#     except Exception as e:
#         answer = f"Error generating response: {e}"
        
#     latency = round(time.time() - start_time, 2)
#     log_id = log_interaction(user_query, expanded_query, answer, latency)
    
#     return expanded_query, answer, reranked, latency, log_id

# # UI Layout
# st.title("💼 Tech Job Market Strategy RAG")
# st.caption("Powered by ChromaDB, FlashRank, Groq, and Streamlit")

# # Sidebar
# st.sidebar.header("📊 Application Metrics")
# conn = sqlite3.connect(FEEDBACK_DB)
# cursor = conn.cursor()
# cursor.execute("SELECT COUNT(*), AVG(latency_sec), SUM(CASE WHEN feedback = 1 THEN 1 ELSE 0 END), SUM(CASE WHEN feedback = -1 THEN 1 ELSE 0 END) FROM query_logs")
# stats = cursor.fetchone()
# conn.close()

# st.sidebar.metric("Total Queries Handled", stats[0] or 0)
# st.sidebar.metric("Avg Latency", f"{stats[1]:.2f}s" if stats[1] else "0.00s")
# st.sidebar.metric("Positive Feedback (+1)", stats[2] or 0)
# st.sidebar.metric("Negative Feedback (-1)", stats[3] or 0)

# # Load heavy resources
# collection, embedder, ranker, groq_client = load_resources()

# query_input = st.text_input("Ask a question about open tech roles, skills, or locations:", placeholder="e.g. Find remote Backend roles requiring Go or Docker")

# if st.button("Search Jobs", type="primary") and query_input:
#     with st.spinner("Retrieving, reranking, and synthesizing best job matches..."):
#         expanded_q, answer, top_hits, latency, log_id = generate_rag_response(
#             collection, embedder, ranker, groq_client, query_input
#         )
        
#         st.session_state["last_log_id"] = log_id
        
#         st.success(f"Response generated in {latency}s")
#         st.info(f"**Query Expansion:** {expanded_q}")
        
#         st.markdown("### Answer")
#         st.write(answer)
        
#         st.markdown("### Retrived & Reranked Matches")
#         for hit in top_hits:
#             with st.expander(f"Score: {hit['score']:.4f} | {hit['meta']['title']} ({hit['meta']['location']})"):
#                 st.write(hit['text'])

#         st.markdown("---")
#         col1, col2, _ = st.columns([1, 1, 8])
#         with col1:
#             if st.button("👍 Helpful"):
#                 log_feedback(log_id, 1)
#                 st.toast("Feedback recorded!")
#                 st.rerun()
#         with col2:
#             if st.button("👎 Unhelpful"):
#                 log_feedback(log_id, -1)
#                 st.toast("Feedback recorded!")
#                 st.rerun()




import os
import time
import sqlite3
import streamlit as st
from dotenv import load_dotenv

# Load Environment Variables for local dev
load_dotenv()

# Setup Local Monitoring Database (SQLite)
FEEDBACK_DB = "db/feedback.db"
os.makedirs("db", exist_ok=True)

def init_feedback_db():
    conn = sqlite3.connect(FEEDBACK_DB)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS query_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            query TEXT,
            expanded_query TEXT,
            response TEXT,
            latency_sec REAL,
            feedback INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

init_feedback_db()

def log_interaction(query, expanded_query, response, latency):
    conn = sqlite3.connect(FEEDBACK_DB)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO query_logs (query, expanded_query, response, latency_sec)
        VALUES (?, ?, ?, ?)
    """, (query, expanded_query, response, latency))
    log_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return log_id

def log_feedback(log_id, feedback_value):
    conn = sqlite3.connect(FEEDBACK_DB)
    cursor = conn.cursor()
    cursor.execute("UPDATE query_logs SET feedback = ? WHERE id = ?", (feedback_value, log_id))
    conn.commit()
    conn.close()

def get_groq_client():
    """Safely fetches Groq API key from Streamlit Secrets or OS Environment."""
    groq_key = None
    try:
        groq_key = st.secrets.get("GROQ_API_KEY")
    except Exception:
        pass

    if not groq_key:
        groq_key = os.getenv("GROQ_API_KEY")

    if not groq_key:
        return None

    from groq import Groq
    return Groq(api_key=groq_key)

# Page Config FIRST
st.set_page_config(page_title="Tech Career RAG Assistant", page_icon="💼", layout="wide")

# Cached Lazy Loaders
@st.cache_resource(show_spinner="Loading ML Models and Vector Store...")
def load_resources():
    import chromadb
    from sentence_transformers import SentenceTransformer
    from flashrank import Ranker
    
    client = chromadb.PersistentClient(path="db/chroma_db")
    collection = client.get_collection(name="tech_jobs")
    embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    ranker = Ranker(model_name="ms-marco-TinyBERT-L-2-v2")
    
    return collection, embedder, ranker

def rewrite_query(groq_client, user_query: str) -> str:
    if not groq_client:
        return user_query

    prompt = f"Rewrite this job search query to include relevant technical keywords: '{user_query}'. Return only the rewritten string."
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            res = groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="openai/gpt-oss-20b",
                temperature=0.2,
            )
            return res.choices[0].message.content.strip()
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate_limit_exceeded" in err_str:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt + 1)
                    continue
            return user_query

def generate_rag_response(collection, embedder, ranker, groq_client, user_query: str):
    from flashrank import RerankRequest
    start_time = time.time()
    
    # 🛑 GUARD: Ensure groq_client exists before attempting .chat
    if not groq_client:
        answer = "⚠️ **Configuration Error**: `GROQ_API_KEY` was not detected. Please verify your secrets in Streamlit Cloud Settings."
        latency = round(time.time() - start_time, 2)
        log_id = log_interaction(user_query, user_query, answer, latency)
        return user_query, answer, [], latency, log_id

    expanded_query = rewrite_query(groq_client, user_query)
    
    query_vector = embedder.encode([expanded_query]).tolist()
    results = collection.query(query_embeddings=query_vector, n_results=5)
    
    docs = results["documents"][0] if results.get("documents") else []
    metadatas = results["metadatas"][0] if results.get("metadatas") else []
    
    passages = [{"id": idx, "text": doc, "meta": meta} for idx, (doc, meta) in enumerate(zip(docs, metadatas))]
    rerank_req = RerankRequest(query=user_query, passages=passages)
    reranked = ranker.rerank(rerank_req)[:3]
    
    context_str = "\n\n".join([f"Job Title: {item['meta']['title']}\nLocation: {item['meta']['location']}\nDetails: {item['text']}" for item in reranked])
    
    system_prompt = "You are an expert Tech Career & Job Search Assistant. Answer the candidate's query strictly based on the provided job listings."
    user_prompt = f"Context:\n{context_str}\n\nCandidate Query: {user_query}"
    
    max_retries = 3
    answer = ""
    for attempt in range(max_retries):
        try:
            completion = groq_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                model="openai/gpt-oss-20b",
                temperature=0.3
            )
            answer = completion.choices[0].message.content
            break
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate_limit_exceeded" in err_str:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt + 1)
                    continue
                answer = "⚠️ **Rate Limit Reached**: The system is experiencing high traffic. Please wait a few seconds and try again."
            else:
                answer = f"Error generating response: {e}"
        
    latency = round(time.time() - start_time, 2)
    log_id = log_interaction(user_query, expanded_query, answer, latency)
    
    return expanded_query, answer, reranked, latency, log_id

# UI Layout
st.title("💼 Tech Job Market Strategy RAG")
st.caption("Powered by ChromaDB, FlashRank, Groq, and Streamlit")

# Sidebar Metrics
st.sidebar.header("📊 Application Metrics")
conn = sqlite3.connect(FEEDBACK_DB)
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*), AVG(latency_sec), SUM(CASE WHEN feedback = 1 THEN 1 ELSE 0 END), SUM(CASE WHEN feedback = -1 THEN 1 ELSE 0 END) FROM query_logs")
stats = cursor.fetchone()
conn.close()

st.sidebar.metric("Total Queries Handled", stats[0] or 0)
st.sidebar.metric("Avg Latency", f"{stats[1]:.2f}s" if stats[1] else "0.00s")
st.sidebar.metric("Positive Feedback (+1)", stats[2] or 0)
st.sidebar.metric("Negative Feedback (-1)", stats[3] or 0)

# Load heavy resources & dynamically acquire Groq client
collection, embedder, ranker = load_resources()
groq_client = get_groq_client()

query_input = st.text_input("Ask a question about open tech roles, skills, or locations:", placeholder="e.g. Find remote Backend roles requiring Go or Docker")

if st.button("Search Jobs", type="primary") and query_input:
    with st.spinner("Retrieving, reranking, and synthesizing best job matches..."):
        expanded_q, answer, top_hits, latency, log_id = generate_rag_response(
            collection, embedder, ranker, groq_client, query_input
        )
        
        st.session_state["last_log_id"] = log_id
        
        st.success(f"Response generated in {latency}s")
        st.info(f"**Query Expansion:** {expanded_q}")
        
        st.markdown("### Answer")
        st.write(answer)
        
        st.markdown("### Retrived & Reranked Matches")
        for hit in top_hits:
            with st.expander(f"Score: {hit['score']:.4f} | {hit['meta']['title']} ({hit['meta']['location']})"):
                st.write(hit['text'])

        st.markdown("---")
        col1, col2, _ = st.columns([1, 1, 8])
        with col1:
            if st.button("👍 Helpful"):
                log_feedback(log_id, 1)
                st.toast("Feedback recorded!")
                st.rerun()
        with col2:
            if st.button("👎 Unhelpful"):
                log_feedback(log_id, -1)
                st.toast("Feedback recorded!")
                st.rerun()