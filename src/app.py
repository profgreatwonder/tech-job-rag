# import os
# import time
# import sqlite3
# import streamlit as st
# from dotenv import load_dotenv

# # Load local .env if present
# load_dotenv()

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

# def get_groq_client():
#     """Safely retrieves API key from Streamlit Secrets or local environment."""
#     groq_key = None
#     try:
#         groq_key = st.secrets.get("GROQ_API_KEY")
#     except Exception:
#         pass

#     if not groq_key:
#         groq_key = os.getenv("GROQ_API_KEY")

#     if not groq_key:
#         return None

#     from groq import Groq
#     return Groq(api_key=groq_key)

# st.set_page_config(page_title="Tech Career RAG Assistant", page_icon="💼", layout="wide")

# @st.cache_resource(show_spinner="Loading ML Models and Vector Store...")
# def load_resources():
#     import chromadb
#     from sentence_transformers import SentenceTransformer
#     from flashrank import Ranker
    
#     client = chromadb.PersistentClient(path="db/chroma_db")
#     collection = client.get_collection(name="tech_jobs")
#     embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
#     ranker = Ranker(model_name="ms-marco-TinyBERT-L-2-v2")
    
#     return collection, embedder, ranker

# def rewrite_query(groq_client, user_query: str) -> str:
#     if not groq_client or len(user_query.strip().split()) <= 1:
#         # Avoid running expansion LLM on single-word searches like "AWS" or "Python"
#         return user_query

#     prompt = (
#         f"You are a job search query enhancer. Expand the following user search query into technical skills, "
#         f"frameworks, and role titles for a vector database: '{user_query}'. "
#         f"Output ONLY the search terms, nothing else."
#     )
    
#     # Primary & fallback models with higher TPM limits on Groq
#     models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-20b"]
    
#     for model_name in models:
#         try:
#             res = groq_client.chat.completions.create(
#                 messages=[{"role": "user", "content": prompt}],
#                 model=model_name,
#                 temperature=0.2,
#             )
#             expanded = res.choices[0].message.content.strip()
#             # Guard against conversational output
#             if "would like" in expanded.lower() or "please provide" in expanded.lower():
#                 return user_query
#             return expanded
#         except Exception:
#             continue
            
#     return user_query

# def generate_rag_response(collection, embedder, ranker, groq_client, user_query: str):
#     from flashrank import RerankRequest
#     start_time = time.time()
    
#     if not groq_client:
#         answer = "⚠️ **API Key Missing**: `GROQ_API_KEY` was not found. Check your local `.env` file or Streamlit secrets."
#         latency = round(time.time() - start_time, 2)
#         log_id = log_interaction(user_query, user_query, answer, latency)
#         return user_query, answer, [], latency, log_id

#     expanded_query = rewrite_query(groq_client, user_query)
    
#     query_vector = embedder.encode([expanded_query]).tolist()
#     results = collection.query(query_embeddings=query_vector, n_results=5)
    
#     docs = results["documents"][0] if results.get("documents") else []
#     metadatas = results["metadatas"][0] if results.get("metadatas") else []
    
#     passages = [{"id": idx, "text": doc, "meta": meta} for idx, (doc, meta) in enumerate(zip(docs, metadatas))]
    
#     if passages:
#         rerank_req = RerankRequest(query=user_query, passages=passages)
#         reranked = ranker.rerank(rerank_req)[:3]
#     else:
#         reranked = []
    
#     # Context Truncation Guard: Keep context strictly under 2,500 characters (~600 tokens)
#     context_blocks = []
#     for item in reranked:
#         text_snippet = item['text'][:800] # Truncate long descriptions
#         context_blocks.append(f"Job Title: {item['meta']['title']}\nLocation: {item['meta']['location']}\nDetails: {text_snippet}")
    
#     context_str = "\n\n".join(context_blocks)
    
#     system_prompt = "You are an expert Tech Career Assistant. Answer concisely based strictly on the provided job context."
#     user_prompt = f"Context:\n{context_str}\n\nCandidate Query: {user_query}"
    
#     models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-20b"]
#     answer = ""
    
#     for model_name in models:
#         max_retries = 3
#         for attempt in range(max_retries):
#             try:
#                 completion = groq_client.chat.completions.create(
#                     messages=[
#                         {"role": "system", "content": system_prompt},
#                         {"role": "user", "content": user_prompt}
#                     ],
#                     model=model_name,
#                     temperature=0.3
#                 )
#                 answer = completion.choices[0].message.content
#                 break
#             except Exception as e:
#                 err_str = str(e)
#                 if "429" in err_str or "rate_limit_exceeded" in err_str or "413" in err_str:
#                     if attempt < max_retries - 1:
#                         time.sleep(2 ** attempt + 1)
#                         continue
#                 print(f"[Model Fallback]: Model '{model_name}' failed ({e}). Retrying...")
#                 break
#         if answer and not answer.startswith("Error"):
#             break

#     if not answer:
#         answer = "⚠️ **Rate Limit / API Error**: Request failed across available models. Please wait a minute and try again."

#     latency = round(time.time() - start_time, 2)
#     log_id = log_interaction(user_query, expanded_query, answer, latency)
    
#     return expanded_query, answer, reranked, latency, log_id

# # UI Layout
# st.title("💼 Tech Job Market Strategy RAG")
# st.caption("Powered by ChromaDB, FlashRank, Groq, and Streamlit")

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

# collection, embedder, ranker = load_resources()
# groq_client = get_groq_client()

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




# import os
# import time
# import sqlite3
# import streamlit as st
# from dotenv import load_dotenv

# # Load local .env if present
# load_dotenv()

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

# def get_groq_client():
#     """Safely retrieves API key from Streamlit Secrets or local environment."""
#     groq_key = None
#     try:
#         groq_key = st.secrets.get("GROQ_API_KEY")
#     except Exception:
#         pass

#     if not groq_key:
#         groq_key = os.getenv("GROQ_API_KEY")

#     if not groq_key:
#         return None

#     from groq import Groq
#     return Groq(api_key=groq_key)

# st.set_page_config(page_title="Tech Career RAG Assistant", page_icon="💼", layout="wide")

# @st.cache_resource(show_spinner="Loading ML Models and Vector Store...")
# def load_resources():
#     import chromadb
#     from sentence_transformers import SentenceTransformer
#     from flashrank import Ranker
    
#     client = chromadb.PersistentClient(path="db/chroma_db")
#     collection = client.get_collection(name="tech_jobs")
#     embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
#     ranker = Ranker(model_name="ms-marco-TinyBERT-L-2-v2")
    
#     return collection, embedder, ranker

# def rewrite_query(groq_client, user_query: str) -> str:
#     if not groq_client or len(user_query.strip().split()) <= 1:
#         # Bypass rewrite for single-word queries (e.g. "AWS", "Python")
#         return user_query

#     prompt = (
#         f"You are a job search query enhancer. Expand the following user search query into technical skills, "
#         f"frameworks, and role titles for a vector database: '{user_query}'. "
#         f"Output ONLY the relevant technical search terms, nothing else."
#     )
    
#     # Updated primary & fallback model list for Groq
#     models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-20b"]
    
#     for model_name in models:
#         try:
#             res = groq_client.chat.completions.create(
#                 messages=[{"role": "user", "content": prompt}],
#                 model=model_name,
#                 temperature=0.2,
#             )
#             expanded = res.choices[0].message.content.strip()
#             # Guard against conversational prompt leaks
#             if "would like" in expanded.lower() or "please provide" in expanded.lower():
#                 return user_query
#             return expanded
#         except Exception:
#             continue
            
#     return user_query

# def generate_rag_response(collection, embedder, ranker, groq_client, user_query: str):
#     from flashrank import RerankRequest
#     start_time = time.time()
    
#     if not groq_client:
#         answer = "⚠️ **API Key Missing**: `GROQ_API_KEY` was not found. Check your local `.env` file or Streamlit secrets."
#         latency = round(time.time() - start_time, 2)
#         log_id = log_interaction(user_query, user_query, answer, latency)
#         return user_query, answer, [], latency, log_id

#     expanded_query = rewrite_query(groq_client, user_query)
    
#     query_vector = embedder.encode([expanded_query]).tolist()
#     results = collection.query(query_embeddings=query_vector, n_results=5)
    
#     docs = results["documents"][0] if results.get("documents") else []
#     metadatas = results["metadatas"][0] if results.get("metadatas") else []
    
#     passages = [{"id": idx, "text": doc, "meta": meta} for idx, (doc, meta) in enumerate(zip(docs, metadatas))]
    
#     if passages:
#         rerank_req = RerankRequest(query=user_query, passages=passages)
#         reranked = ranker.rerank(rerank_req)[:3]
#     else:
#         reranked = []
    
#     # Context Truncation Guard: Keep context text snippet length bounded to prevent TPM rate limits
#     context_blocks = []
#     for item in reranked:
#         text_snippet = item['text'][:800]
#         context_blocks.append(f"Job Title: {item['meta']['title']}\nLocation: {item['meta']['location']}\nDetails: {text_snippet}")
    
#     context_str = "\n\n".join(context_blocks)
    
#     system_prompt = "You are an expert Tech Career Assistant. Answer concisely based strictly on the provided job context."
#     user_prompt = f"Context:\n{context_str}\n\nCandidate Query: {user_query}"
    
#     models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-20b"]
#     answer = ""
    
#     for model_name in models:
#         max_retries = 3
#         for attempt in range(max_retries):
#             try:
#                 completion = groq_client.chat.completions.create(
#                     messages=[
#                         {"role": "system", "content": system_prompt},
#                         {"role": "user", "content": user_prompt}
#                     ],
#                     model=model_name,
#                     temperature=0.3
#                 )
#                 answer = completion.choices[0].message.content
#                 break
#             except Exception as e:
#                 err_str = str(e)
#                 if "429" in err_str or "rate_limit_exceeded" in err_str or "413" in err_str:
#                     if attempt < max_retries - 1:
#                         time.sleep(2 ** attempt + 1)
#                         continue
#                 print(f"[Model Fallback]: Model '{model_name}' failed ({e}). Retrying...")
#                 break
#         if answer and not answer.startswith("Error"):
#             break

#     if not answer:
#         answer = "⚠️ **Rate Limit / API Error**: Request failed across available models. Please wait a minute and try again."

#     latency = round(time.time() - start_time, 2)
#     log_id = log_interaction(user_query, expanded_query, answer, latency)
    
#     return expanded_query, answer, reranked, latency, log_id

# # UI Layout
# st.title("💼 Tech Job Market Strategy RAG")
# st.caption("Powered by ChromaDB, FlashRank, Groq, and Streamlit")

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

# collection, embedder, ranker = load_resources()
# groq_client = get_groq_client()

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



# import os
# import time
# import sqlite3
# import streamlit as st
# from dotenv import load_dotenv

# # Load local .env if present
# load_dotenv()

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

# def get_groq_client():
#     """Safely retrieves API key from Streamlit Secrets or local environment."""
#     groq_key = None
#     try:
#         groq_key = st.secrets.get("GROQ_API_KEY")
#     except Exception:
#         pass

#     if not groq_key:
#         groq_key = os.getenv("GROQ_API_KEY")

#     if not groq_key:
#         return None

#     from groq import Groq
#     return Groq(api_key=groq_key)

# st.set_page_config(page_title="Tech Career RAG Assistant", page_icon="💼", layout="wide")

# @st.cache_resource(show_spinner="Loading ML Models and Vector Store...")
# def load_resources():
#     import chromadb
#     from sentence_transformers import SentenceTransformer
#     from flashrank import Ranker
    
#     client = chromadb.PersistentClient(path="db/chroma_db")
#     collection = client.get_collection(name="tech_jobs")
#     embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
#     ranker = Ranker(model_name="ms-marco-TinyBERT-L-2-v2")
    
#     return collection, embedder, ranker

# def rewrite_query(groq_client, user_query: str) -> str:
#     if not groq_client or len(user_query.strip().split()) <= 1:
#         # Bypass rewrite for single-word queries (e.g. "AWS", "Python")
#         return user_query

#     prompt = (
#         f"You are a job search query enhancer. Expand the following user search query into technical skills, "
#         f"frameworks, and role titles for a vector database: '{user_query}'. "
#         f"Output ONLY the relevant technical search terms, nothing else."
#     )
    
#     # Stable model fallback array to avoid 404 Model Not Found errors
#     models = ["llama3-70b-8192", "llama3-8b-8192", "openai/gpt-oss-20b", "llama-3.3-70b-versatile"]
    
#     for model_name in models:
#         try:
#             res = groq_client.chat.completions.create(
#                 messages=[{"role": "user", "content": prompt}],
#                 model=model_name,
#                 temperature=0.2,
#             )
#             expanded = res.choices[0].message.content.strip()
#             # Guard against conversational prompt leaks
#             if "would like" in expanded.lower() or "please provide" in expanded.lower():
#                 return user_query
#             return expanded
#         except Exception:
#             continue
            
#     return user_query

# def generate_rag_response(collection, embedder, ranker, groq_client, user_query: str):
#     from flashrank import RerankRequest
#     start_time = time.time()
    
#     if not groq_client:
#         answer = "⚠️ **API Key Missing**: `GROQ_API_KEY` was not found. Check your local `.env` file or Streamlit secrets."
#         latency = round(time.time() - start_time, 2)
#         log_id = log_interaction(user_query, user_query, answer, latency)
#         return user_query, answer, [], latency, log_id

#     expanded_query = rewrite_query(groq_client, user_query)
    
#     query_vector = embedder.encode([expanded_query]).tolist()
#     results = collection.query(query_embeddings=query_vector, n_results=5)
    
#     docs = results["documents"][0] if results.get("documents") else []
#     metadatas = results["metadatas"][0] if results.get("metadatas") else []
    
#     passages = [{"id": idx, "text": doc, "meta": meta} for idx, (doc, meta) in enumerate(zip(docs, metadatas))]
    
#     if passages:
#         rerank_req = RerankRequest(query=user_query, passages=passages)
#         reranked = ranker.rerank(rerank_req)[:3]
#     else:
#         reranked = []
    
#     # Context Truncation Guard: Keep context text snippet length bounded to prevent TPM rate limits
#     context_blocks = []
#     for item in reranked:
#         text_snippet = item['text'][:800]
#         context_blocks.append(f"Job Title: {item['meta']['title']}\nLocation: {item['meta']['location']}\nDetails: {text_snippet}")
    
#     context_str = "\n\n".join(context_blocks)
    
#     system_prompt = "You are an expert Tech Career Assistant. Answer concisely based strictly on the provided job context."
#     user_prompt = f"Context:\n{context_str}\n\nCandidate Query: {user_query}"
    
#     models = ["llama3-70b-8192", "llama3-8b-8192", "openai/gpt-oss-20b", "llama-3.3-70b-versatile"]
#     answer = ""
    
#     for model_name in models:
#         max_retries = 3
#         for attempt in range(max_retries):
#             try:
#                 completion = groq_client.chat.completions.create(
#                     messages=[
#                         {"role": "system", "content": system_prompt},
#                         {"role": "user", "content": user_prompt}
#                     ],
#                     model=model_name,
#                     temperature=0.3
#                 )
#                 answer = completion.choices[0].message.content
#                 break
#             except Exception as e:
#                 err_str = str(e)
#                 # Handle Rate Limit / Too Large errors with exponential backoff retry
#                 if "429" in err_str or "rate_limit_exceeded" in err_str or "413" in err_str:
#                     if attempt < max_retries - 1:
#                         time.sleep(2 ** attempt + 1)
#                         continue
#                 # For 404 Model Not Found errors, stop retrying this model and switch immediately
#                 print(f"[Model Fallback]: Model '{model_name}' failed ({e}). Retrying with next model...")
#                 break
#         if answer and not answer.startswith("Error"):
#             break

#     if not answer:
#         answer = "⚠️ **Rate Limit / API Error**: Request failed across available models. Please wait a minute and try again."

#     latency = round(time.time() - start_time, 2)
#     log_id = log_interaction(user_query, expanded_query, answer, latency)
    
#     return expanded_query, answer, reranked, latency, log_id

# # UI Layout
# st.title("💼 Tech Job Market Strategy RAG")
# st.caption("Powered by ChromaDB, FlashRank, Groq, and Streamlit")

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

# collection, embedder, ranker = load_resources()
# groq_client = get_groq_client()

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

# Load local .env if present
load_dotenv()

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
    """Safely retrieves API key from Streamlit Secrets or local environment."""
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

st.set_page_config(page_title="Tech Career RAG Assistant", page_icon="💼", layout="wide")

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

# def rewrite_query(groq_client, user_query: str) -> str:
#     if not groq_client or len(user_query.strip().split()) <= 1:
#         # Bypass rewrite for single-word queries (e.g. "AWS", "Python")
#         return user_query

#     prompt = (
#         f"You are a job search query enhancer. Expand the following user search query into technical skills, "
#         f"frameworks, and role titles for a vector database: '{user_query}'. "
#         f"Output ONLY the relevant technical search terms, nothing else."
#     )

def rewrite_query(groq_client, user_query: str) -> str:
    if not groq_client or len(user_query.strip().split()) <= 1:
        return user_query

    prompt = (
        f"You are a job search query enhancer. Output ONLY 3-6 core technical keywords "
        f"and primary job titles directly relevant to this search query: '{user_query}'. "
        f"Do NOT include generic terms, soft skills, or full sentences. Output lowercase keywords separated by commas."
    )
    
    # Active, non-decommissioned Groq model IDs
    models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-20b"]
    
    for model_name in models:
        try:
            res = groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=model_name,
                temperature=0.2,
            )
            expanded = res.choices[0].message.content.strip()
            # Guard against conversational prompt leaks
            if "would like" in expanded.lower() or "please provide" in expanded.lower():
                return user_query
            return expanded
        except Exception:
            continue
            
    return user_query

def generate_rag_response(collection, embedder, ranker, groq_client, user_query: str):
    from flashrank import RerankRequest
    start_time = time.time()
    
    if not groq_client:
        answer = "⚠️ **API Key Missing**: `GROQ_API_KEY` was not found. Check your local `.env` file or Streamlit secrets."
        latency = round(time.time() - start_time, 2)
        log_id = log_interaction(user_query, user_query, answer, latency)
        return user_query, answer, [], latency, log_id

    expanded_query = rewrite_query(groq_client, user_query)
    
    query_vector = embedder.encode([expanded_query]).tolist()
    results = collection.query(query_embeddings=query_vector, n_results=10)
    
    docs = results["documents"][0] if results.get("documents") else []
    metadatas = results["metadatas"][0] if results.get("metadatas") else []
    
    passages = [{"id": idx, "text": doc, "meta": meta} for idx, (doc, meta) in enumerate(zip(docs, metadatas))]
    
    if passages:
        rerank_req = RerankRequest(query=user_query, passages=passages)
        reranked = ranker.rerank(rerank_req)[:3]
    else:
        reranked = []
    
    # Context Truncation Guard: Keep context text snippet length bounded to prevent TPM rate limits
    context_blocks = []
    for item in reranked:
        text_snippet = item['text'][:800]
        context_blocks.append(f"Job Title: {item['meta']['title']}\nLocation: {item['meta']['location']}\nDetails: {text_snippet}")
    
    context_str = "\n\n".join(context_blocks)
    
    system_prompt = "You are an expert Tech Career Assistant. Answer concisely based strictly on the provided job context."
    user_prompt = f"Context:\n{context_str}\n\nCandidate Query: {user_query}"
    
    # Active, non-decommissioned Groq model IDs
    models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-20b"]
    answer = ""
    
    for model_name in models:
        max_retries = 2
        for attempt in range(max_retries):
            try:
                completion = groq_client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    model=model_name,
                    temperature=0.3
                )
                answer = completion.choices[0].message.content
                break
            except Exception as e:
                err_str = str(e)
                # Handle Rate Limit / Too Large errors with exponential backoff retry
                if "429" in err_str or "rate_limit_exceeded" in err_str or "413" in err_str:
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt + 1)
                        continue
                print(f"[Model Fallback]: Model '{model_name}' failed ({e}). Retrying next model...")
                break
        if answer and not answer.startswith("Error"):
            break

    if not answer:
        answer = "⚠️ **Rate Limit / API Error**: Request failed across available models. Please wait a minute and try again."

    latency = round(time.time() - start_time, 2)
    log_id = log_interaction(user_query, expanded_query, answer, latency)
    
    return expanded_query, answer, reranked, latency, log_id

# UI Layout
st.title("💼 Tech Job Market Strategy RAG")
st.caption("Powered by ChromaDB, FlashRank, Groq, and Streamlit")

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