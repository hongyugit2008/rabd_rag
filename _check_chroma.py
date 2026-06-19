#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Quick diagnostic script to check Chroma data and RAG retrieval."""

import sys
import io
sys.path.insert(0, r"E:\code\LangChainRAG")

# Force UTF-8 output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from doc_ingest import vector_db
from database import get_db, DocPermission, UserRbac, DocAcl
from config import ROLE_SECRET_RULE

def safe_repr(s):
    """Return ASCII-safe representation of a string."""
    if s is None:
        return "None"
    try:
        return s.encode('ascii', errors='replace').decode('ascii')
    except:
        return str(s)

# 1. Check Chroma directly
print("="*60)
print("1. ChromaDB direct search for sanzijing")
results = vector_db.similarity_search('三字经', k=10)
print(f"   Total hits: {len(results)}")
for i, r in enumerate(results):
    doc_id = r.metadata.get('doc_id', 'N/A')
    dept = r.metadata.get('dept_owner', 'N/A')
    sl = r.metadata.get('secret_level', 'N/A')
    vg = r.metadata.get('vec_group_id', 'N/A')
    print(f"   [{i}] doc_id={doc_id}")
    print(f"       dept_owner_bytes={dept.encode('utf-8', errors='replace') if dept else b'empty'}")
    print(f"       dept_owner_repr={repr(dept)}")
    print(f"       secret_level={sl}")
    print(f"       vec_group_id={vg}")

# 2. Check Chroma collection count
print()
print("="*60)
print("2. ChromaDB collection info")
try:
    count = vector_db._collection.count()
    print(f"   Total vectors in collection: {count}")

    sample = vector_db._collection.get(limit=5)
    if sample and sample['ids']:
        print(f"   Sample IDs: {sample['ids']}")
        for m in sample['metadatas']:
            print(f"   metadata: {m}")
except Exception as e:
    print(f"   Error: {e}")

# 3. Check with department filter (as admin with empty dept)
print()
print("="*60)
print("3. Chroma search with empty dept filter (simulating admin)")
results_dept = vector_db.similarity_search('三字经', k=10, filter={"dept_owner": ""})
print(f"   Hits with dept_owner='': {len(results_dept)}")

# 4. Check database records
print()
print("="*60)
print("4. DocPermission records from MySQL")
db = next(get_db())
docs = db.query(DocPermission).all()
for d in docs:
    print(f"   doc_id={d.doc_id}")
    dept_owner_bytes = d.dept_owner.encode('utf-8', errors='replace') if d.dept_owner else b'empty'
    print(f"     dept_owner={repr(d.dept_owner)} bytes={dept_owner_bytes}")
    print(f"     secret_level={d.secret_level}")
    fname_bytes = d.original_filename.encode('utf-8', errors='replace') if d.original_filename else b'empty'
    print(f"     filename={repr(d.original_filename)} bytes={fname_bytes}")
    print(f"     is_deleted={d.is_deleted}")

# 5. Check users
print()
print("="*60)
print("5. User accounts")
users = db.query(UserRbac).all()
for u in users:
    print(f"   user_id={u.user_id} | dept_name={repr(u.dept_name)} | role_level={u.role_level}")

# 6. Test department filter with actual dept name from DB
print()
print("="*60)
print("6. Test Chroma search with actual dept from DB")
for d in docs:
    dept = d.dept_owner
    if dept:
        results_d = vector_db.similarity_search('三字经', k=10, filter={"dept_owner": dept})
        print(f"   filter dept_owner={repr(dept)}: {len(results_d)} hits")
    else:
        print(f"   dept_owner is empty/None for doc_id={d.doc_id}")

# 7. Critical test: simulate rag_chat flow for specific users
print()
print("="*60)
print("7. Simulate _retrieve_chunks for each user")
from rag_service import _retrieve_chunks

for u in users:
    chunks = _retrieve_chunks('三字经', u.dept_name, u.role_level, db, u.user_id)
    print(f"   user={u.user_id} dept={repr(u.dept_name)} role={u.role_level} -> {len(chunks)} chunks")

db.close()
print()
print("="*60)
print("Done.")
