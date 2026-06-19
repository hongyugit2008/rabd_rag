#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Check OCR quality of 三字经 chunks and test retrieval accuracy."""

import sys, io
sys.path.insert(0, r"E:\code\LangChainRAG")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from doc_ingest import vector_db, embeddings

# 1. Show raw OCR text of 三字经 chunks
print("=" * 60)
print("1. SANZIJING RAW OCR TEXT IN CHROMA")
data = vector_db._collection.get()
sanzijing_chunks = []
for meta, doc in zip(data['metadatas'], data['documents']):
    if 'e243424e' in meta.get('doc_id', ''):
        sanzijing_chunks.append((meta, doc))
        print(f"\n--- Chunk (secret_level={meta.get('secret_level')}) ---")
        print(doc[:500])

# 2. Test embedding similarity: how well does query "三字经" match sanzijing chunks?
print("\n" + "=" * 60)
print("2. EMBEDDING SIMILARITY ANALYSIS")

query = "三字经"
query_embed = embeddings.embed_query(query)
chunk_embeddings = embeddings.embed_documents([doc for _, doc in sanzijing_chunks])

from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

for i, (meta, doc) in enumerate(sanzijing_chunks):
    sim = cosine_similarity([query_embed], [chunk_embeddings[i]])[0][0]
    print(f"   Chunk {i}: cosine_sim={sim:.4f} | preview={doc[:80]}")

# 3. Check what an actual semantic search returns for "三字经"
print("\n" + "=" * 60)
print("3. CHROMA SEARCH FOR '三字经' (global, no filter)")
results = vector_db.similarity_search_with_relevance_scores("三字经", k=17)
for i, (doc, score) in enumerate(results):
    doc_id = doc.metadata.get('doc_id', '')[:8]
    dept = doc.metadata.get('dept_owner', '')
    sl = doc.metadata.get('secret_level', '')
    preview = (doc.page_content or "")[:100].replace('\n', ' ')
    print(f"   rank={i+1} score={score:.4f} doc={doc_id} dept={dept} sl={sl}")
    print(f"         text: {preview}")

# 4. Check if OCR quality itself is the core problem
print("\n" + "=" * 60)
print("4. OCR QUALITY ASSESSMENT")
for meta, doc in sanzijing_chunks:
    # Count meaningful Chinese chars vs garbage
    clean_chinese = sum(1 for c in doc if '一' <= c <= '鿿')
    total = len(doc)
    ratio = clean_chinese / max(total, 1)
    print(f"   chunk: chinese_chars={clean_chinese}/{total} ratio={ratio:.2%}")
    print(f"          sample: {doc[:200]}")
    print()

# 5. Test RBAC filter logic trace for admin user
print("=" * 60)
print("5. SIMULATE FULL 'admin' RETRIEVAL FLOW")
from database import get_db, UserRbac
from rag_service import _get_acl_candidate_doc_ids
from config import ROLE_SECRET_RULE

db = next(get_db())
admin = db.query(UserRbac).filter(UserRbac.user_id == 'admin').first()
dept_name = admin.dept_name or ""
role_level = int(admin.role_level or 0)
allow_max_secret = ROLE_SECRET_RULE.get(role_level, 0)

print(f"   admin: dept_name={repr(dept_name)}, role_level={role_level}, allow_max_secret={allow_max_secret}")

# Step A: ACL pre-filter
allowed_doc_ids = _get_acl_candidate_doc_ids(db, admin.user_id, dept_name, role_level)
print(f"   Step A - ACL allowed doc_ids: {allowed_doc_ids}")

# Step B: Simulate Chroma search with dept filter
from rag_service import vector_db as vdb
try:
    dept_filtered = vdb.similarity_search("三字经", k=20, filter={"dept_owner": dept_name})
    print(f"   Step B - dept filtered search (dept='{dept_name}'): {len(dept_filtered)} hits")
except Exception as e:
    print(f"   Step B - dept filtered search failed: {e}")
    dept_filtered = []

# Step C: Fallback global search
try:
    global_hits = vdb.similarity_search("三字经", k=20)
    print(f"   Step C - global search: {len(global_hits)} hits")
except Exception as e:
    print(f"   Step C - global search failed: {e}")
    global_hits = []

# Step D: Apply filters
print(f"\n   Step D - Filtering results:")
candidates = dept_filtered if dept_filtered else global_hits
for i, item in enumerate(candidates):
    doc_id = item.metadata.get("doc_id")
    doc_dept = item.metadata.get("dept_owner", "")
    secret_level = int(item.metadata.get("secret_level", 0) or 0)
    preview = (item.page_content or "")[:80].replace("\n", " ")

    # Filter 1: doc_id in allowed list?
    in_allowed = doc_id in allowed_doc_ids
    # Filter 2: department check
    dept_ok = not (doc_dept != dept_name and secret_level != 0)
    # Filter 3: secret level check
    secret_ok = secret_level <= allow_max_secret

    status = "PASS" if (in_allowed and dept_ok and secret_ok) else "FAIL"
    reasons = []
    if not in_allowed: reasons.append("not_in_acl")
    if not dept_ok: reasons.append(f"dept_mismatch(doc={doc_dept}, user={dept_name})")
    if not secret_ok: reasons.append(f"secret_too_high({secret_level}>{allow_max_secret})")

    print(f"   [{i}] {status} | {', '.join(reasons)} | dept={doc_dept} sl={secret_level}")
    print(f"       preview: {preview}")

db.close()
print("\nDone.")
