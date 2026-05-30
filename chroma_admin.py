import argparse
import ast
import os
from collections import Counter, defaultdict
from typing import Any

import chromadb
from dotenv import load_dotenv

from database import DocPermission, UserRbac, SessionLocal, get_db

load_dotenv()

CHROMA_PERSIST_PATH = os.getenv('CHROMA_PERSIST_PATH', './chroma_db')


def get_client() -> chromadb.PersistentClient:
    return chromadb.PersistentClient(path=CHROMA_PERSIST_PATH)


def safe_count(collection) -> int:
    try:
        return collection.count()
    except Exception:
        return 0


def flatten_metadata(item: Any) -> dict:
    if isinstance(item, dict):
        return item
    return {}


def build_uploader_map() -> dict[str, dict[str, str]]:
    uploader_map: dict[str, dict[str, str]] = {}
    db = SessionLocal()
    try:
        docs = db.query(DocPermission).all()
        uploader_ids = {doc.uploader_id for doc in docs if doc.uploader_id}
        users = db.query(UserRbac).filter(UserRbac.user_id.in_(uploader_ids)).all() if uploader_ids else []
        user_map = {user.user_id: user for user in users}
        for doc in docs:
            user = user_map.get(doc.uploader_id or '')
            uploader_map[doc.doc_id] = {
                'uploader_id': doc.uploader_id or '',
                'uploader_username': user.username if user else '',
            }
    finally:
        db.close()
    return uploader_map


def print_stats() -> None:
    client = get_client()
    collections = client.list_collections()
    if not collections:
        print(f'Chroma 路径: {CHROMA_PERSIST_PATH}')
        print('未发现任何 collection。')
        return

    print(f'Chroma 路径: {CHROMA_PERSIST_PATH}')
    print(f'Collection 数量: {len(collections)}')
    for col in collections:
        collection = client.get_collection(col.name)
        count = safe_count(collection)
        print(f'\n[{col.name}]')
        print(f'  文档/切片数: {count}')

        # 先拉取全部 ids 与 metadata，便于统计所有 doc_id，而不是只看默认分页的前几条
        try:
            all_data = collection.get(include=['metadatas', 'documents'])
        except Exception as exc:
            print(f'  拉取全量数据失败: {exc}')
            continue

        metadatas = all_data.get('metadatas') or []
        docs = all_data.get('documents') or []
        ids = all_data.get('ids') or []

        dept_counter = Counter()
        secret_counter = Counter()
        doc_counter = Counter()
        doc_to_preview = {}
        uploader_map = build_uploader_map()
        for idx, meta in enumerate(metadatas):
            meta = flatten_metadata(meta)
            dept = str(meta.get('dept_owner', 'unknown'))
            secret = str(meta.get('secret_level', 'unknown'))
            doc_id = str(meta.get('doc_id', 'unknown'))
            dept_counter[dept] += 1
            secret_counter[secret] += 1
            doc_counter[doc_id] += 1
            if doc_id not in doc_to_preview and idx < len(docs):
                doc_to_preview[doc_id] = (docs[idx] or '').replace('\n', ' ')[:120]

        print(f'  涉及 doc_id 数: {len(doc_counter)}')
        if ids:
            print(f'  首批 ids: {", ".join(ids[:5])}')
        if dept_counter:
            print(f'  部门分布: {dict(dept_counter)}')
        if secret_counter:
            print(f'  密级分布: {dict(secret_counter)}')
        print('  doc_id -> 切片数:')
        for doc_id, chunk_count in doc_counter.most_common():
            preview = doc_to_preview.get(doc_id, '')
            uploader = uploader_map.get(doc_id, {})
            uploader_text = uploader.get('uploader_username') or uploader.get('uploader_id') or '未知'
            if uploader.get('uploader_username'):
                uploader_text = f"{uploader.get('uploader_id') or '-'}（{uploader.get('uploader_username')}）"
            print(f'    - {doc_id}: {chunk_count} 个切片 | 上传者: {uploader_text} | {preview}')


def delete_by_ids(collection_name: str, ids: list[str]) -> int:
    client = get_client()
    collection = client.get_collection(collection_name)
    before = safe_count(collection)
    collection.delete(ids=ids)
    after = safe_count(collection)
    return before - after


def delete_by_where(collection_name: str, where: dict) -> int:
    client = get_client()
    collection = client.get_collection(collection_name)
    before = safe_count(collection)
    collection.delete(where=where)
    after = safe_count(collection)
    return before - after


def get_stats_payload() -> dict:
    client = get_client()
    collections = client.list_collections()
    payload = {
        'chroma_path': CHROMA_PERSIST_PATH,
        'collection_count': len(collections),
        'collections': [],
    }

    for col in collections:
        collection = client.get_collection(col.name)
        count = safe_count(collection)
        try:
            all_data = collection.get(include=['metadatas', 'documents'])
        except Exception as exc:
            payload['collections'].append({
                'name': col.name,
                'count': count,
                'error': str(exc),
            })
            continue

        metadatas = all_data.get('metadatas') or []
        docs = all_data.get('documents') or []
        ids = all_data.get('ids') or []

        dept_counter = Counter()
        secret_counter = Counter()
        doc_counter = Counter()
        doc_to_preview = {}
        doc_to_secret = {}
        for idx, meta in enumerate(metadatas):
            meta = flatten_metadata(meta)
            dept = str(meta.get('dept_owner', 'unknown'))
            secret = str(meta.get('secret_level', 'unknown'))
            doc_id = str(meta.get('doc_id', 'unknown'))
            dept_counter[dept] += 1
            secret_counter[secret] += 1
            doc_counter[doc_id] += 1
            doc_to_secret[doc_id] = int(meta.get('secret_level', 0) or 0)
            if doc_id not in doc_to_preview and idx < len(docs):
                doc_to_preview[doc_id] = (docs[idx] or '').replace('\n', ' ')[:120]

        uploader_map = build_uploader_map()
        doc_uploader_map = {doc_id: uploader_map.get(doc_id, {}) for doc_id in doc_counter}

        payload['collections'].append({
            'name': col.name,
            'count': count,
            'doc_count': len(doc_counter),
            'dept_distribution': dict(dept_counter),
            'secret_distribution': dict(secret_counter),
            'doc_chunks': dict(doc_counter),
            'doc_secrets': doc_to_secret,
            'doc_uploaders': doc_uploader_map,
            'sample_ids': ids[:5],
            'doc_previews': doc_to_preview,
        })
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description='Chroma 数据统计与删除工具')
    sub = parser.add_subparsers(dest='command', required=True)

    sub.add_parser('stats', help='统计 Chroma 数据')

    p_del_ids = sub.add_parser('delete-ids', help='按向量 id 删除')
    p_del_ids.add_argument('--collection', required=True, help='collection 名称')
    p_del_ids.add_argument('--ids', required=True, nargs='+', help='要删除的向量 ids')

    p_del_doc = sub.add_parser('delete-doc', help='按 doc_id 删除整篇文档的所有切片')
    p_del_doc.add_argument('--collection', required=True, help='collection 名称')
    p_del_doc.add_argument('--doc-id', required=True, help='文档 doc_id')

    p_del_where = sub.add_parser('delete-where', help='按 metadata 条件删除')
    p_del_where.add_argument('--collection', required=True, help='collection 名称')
    p_del_where.add_argument('--where', required=True, help='Python 字典格式条件，例如 "{\'dept_owner\': \'销售部\'}"')

    args = parser.parse_args()

    if args.command == 'stats':
        print_stats()
        return

    if args.command == 'delete-ids':
        removed = delete_by_ids(args.collection, args.ids)
        print(f'已删除 {removed} 条向量记录。')
        return

    if args.command == 'delete-doc':
        removed = delete_by_where(args.collection, {'doc_id': args.doc_id})
        print(f'已删除 doc_id={args.doc_id} 的 {removed} 条向量记录。')
        return

    if args.command == 'delete-where':
        try:
            where = eval(args.where, {'__builtins__': {}}, {})
        except Exception as exc:
            raise SystemExit(f'where 参数解析失败: {exc}')
        if not isinstance(where, dict):
            raise SystemExit('where 必须是 dict')
        removed = delete_by_where(args.collection, where)
        print(f'已删除 {removed} 条匹配记录。')
        return


if __name__ == '__main__':
    main()
