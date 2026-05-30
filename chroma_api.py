from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Any

from auth_middleware import get_current_user
from database import get_db, DocPermission
from chroma_admin import get_stats_payload, delete_by_ids, delete_by_where, get_client
from chroma_service import get_access_scope, can_view_doc, list_visible_doc_ids
import datetime

router = APIRouter(prefix='/api/chroma', tags=['chroma-admin'])


class DeleteIdsPayload(BaseModel):
    collection: str = Field(..., description='Chroma collection 名称')
    ids: list[str] = Field(..., min_length=1, description='要删除的向量 id 列表')


class DeleteDocPayload(BaseModel):
    collection: str = Field(..., description='Chroma collection 名称')
    doc_id: str = Field(..., description='要删除的 doc_id')


class DeleteWherePayload(BaseModel):
    collection: str = Field(..., description='Chroma collection 名称')
    where: dict[str, Any] = Field(..., description='metadata 条件，例如 {"dept_owner": "销售部"}')


@router.get('/stats')
def chroma_stats(db: Session = Depends(get_db), user_id: str = Depends(get_current_user)):
    scope = get_access_scope(db, user_id)
    if not scope['ok']:
        raise HTTPException(status_code=404, detail=scope['msg'])
    payload = get_stats_payload(db=db)
    if scope['is_admin']:
        return {'code': 200, 'data': payload}
    visible_docs = set(list_visible_doc_ids(db, user_id))
    filtered = []
    for col in payload['collections']:
        doc_chunks = col.get('doc_chunks', {})
        doc_previews = col.get('doc_previews', {})
        doc_uploaders = col.get('doc_uploaders', {})
        doc_secrets = col.get('doc_secrets', {})
        doc_chunks = {doc_id: cnt for doc_id, cnt in doc_chunks.items() if doc_id in visible_docs}
        doc_previews = {doc_id: preview for doc_id, preview in doc_previews.items() if doc_id in visible_docs}
        doc_uploaders = {doc_id: uploader for doc_id, uploader in doc_uploaders.items() if doc_id in visible_docs}
        doc_secrets = {doc_id: secret for doc_id, secret in doc_secrets.items() if doc_id in visible_docs}
        filtered.append({**col, 'doc_count': len(doc_chunks), 'doc_chunks': doc_chunks, 'doc_previews': doc_previews, 'doc_uploaders': doc_uploaders, 'doc_secrets': doc_secrets})
    payload['collections'] = filtered
    return {'code': 200, 'data': payload}


@router.post('/delete-ids')
def chroma_delete_ids(payload: DeleteIdsPayload, db: Session = Depends(get_db), user_id: str = Depends(get_current_user)):
    scope = get_access_scope(db, user_id)
    if not scope['ok']:
        raise HTTPException(status_code=404, detail=scope['msg'])

    client = get_client()
    collection = client.get_collection(payload.collection)
    all_vecs = collection.get(ids=payload.ids, include=['metadatas'])
    vec_ids = all_vecs.get('ids') or []
    metadatas = all_vecs.get('metadatas') or []
    meta_map = {vector_id: (meta or {}) for vector_id, meta in zip(vec_ids, metadatas)}

    if scope['is_admin']:
        try:
            removed = delete_by_ids(payload.collection, payload.ids)
            audit = [{
                'vector_id': vector_id,
                'doc_id': meta_map.get(vector_id, {}).get('doc_id'),
                'status': 'deleted',
                'reason': 'admin',
            } for vector_id in payload.ids]
            skipped = [vector_id for vector_id in payload.ids if vector_id not in vec_ids]
            for vector_id in skipped:
                audit.append({
                    'vector_id': vector_id,
                    'doc_id': None,
                    'status': 'skipped',
                    'reason': 'not_found',
                })
            return {
                'code': 200,
                'msg': '删除成功',
                'removed': removed,
                'collection': payload.collection,
                'audit': audit,
                'skipped_ids': skipped,
                'deleted_ids': payload.ids,
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    visible_doc_ids = set(list_visible_doc_ids(db, user_id))
    if not visible_doc_ids:
        raise HTTPException(status_code=403, detail='无删除权限')

    allowed_ids = []
    skipped_audit = []
    for vector_id in payload.ids:
        doc_id = meta_map.get(vector_id, {}).get('doc_id')
        doc = db.query(DocPermission).filter(DocPermission.doc_id == doc_id).first() if doc_id else None
        if doc_id in visible_doc_ids and doc and int(doc.secret_level or 0) != 0:
            allowed_ids.append(vector_id)
        else:
            skipped_audit.append({
                'vector_id': vector_id,
                'doc_id': doc_id,
                'status': 'skipped',
                'reason': 'public_not_deletable' if doc and int(doc.secret_level or 0) == 0 else 'permission_denied',
            })

    if not allowed_ids:
        raise HTTPException(status_code=403, detail='无权限删除任何指定分片')

    try:
        removed = delete_by_ids(payload.collection, allowed_ids)
        audit = [{
            'vector_id': vector_id,
            'doc_id': meta_map.get(vector_id, {}).get('doc_id'),
            'status': 'deleted',
            'reason': 'allowed',
        } for vector_id in allowed_ids]
        audit.extend(skipped_audit)
        return {
            'code': 200,
            'msg': '删除成功',
            'removed': removed,
            'collection': payload.collection,
            'allowed_ids': allowed_ids,
            'skipped_ids': [item['vector_id'] for item in skipped_audit],
            'audit': audit,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post('/delete-doc')
def chroma_delete_doc(payload: DeleteDocPayload, db: Session = Depends(get_db), user_id: str = Depends(get_current_user)):
    scope = get_access_scope(db, user_id)
    if not scope['ok']:
        raise HTTPException(status_code=404, detail=scope['msg'])
    doc = db.query(DocPermission).filter(DocPermission.doc_id == payload.doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail='文档不存在')
    ok, reason = can_view_doc(db, user_id, doc)
    if not scope['is_admin'] and not ok:
        raise HTTPException(status_code=403, detail=f'无删除权限: {reason}')
    try:
        removed = delete_by_where(payload.collection, {'doc_id': payload.doc_id})
        doc.is_deleted = 1
        doc.deleted_by = user_id
        doc.deleted_at = datetime.datetime.now()
        doc.delete_reason = f'chroma_delete_doc:{payload.collection}'
        db.commit()
        return {'code': 200, 'msg': '删除成功', 'removed': removed, 'collection': payload.collection, 'doc_id': payload.doc_id}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))


@router.post('/restore-doc')
def chroma_restore_doc(payload: DeleteDocPayload, db: Session = Depends(get_db), user_id: str = Depends(get_current_user)):
    scope = get_access_scope(db, user_id)
    if not scope['ok']:
        raise HTTPException(status_code=404, detail=scope['msg'])
    if not scope['is_admin']:
        raise HTTPException(status_code=403, detail='非管理员不允许恢复文档')
    doc = db.query(DocPermission).filter(DocPermission.doc_id == payload.doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail='文档不存在')
    try:
        doc.is_deleted = 0
        doc.deleted_by = None
        doc.deleted_at = None
        doc.delete_reason = None
        db.commit()
        return {'code': 200, 'msg': '恢复成功', 'collection': payload.collection, 'doc_id': payload.doc_id}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))


@router.post('/delete-where')
def chroma_delete_where(payload: DeleteWherePayload, db: Session = Depends(get_db), user_id: str = Depends(get_current_user)):
    scope = get_access_scope(db, user_id)
    if not scope['ok']:
        raise HTTPException(status_code=404, detail=scope['msg'])
    if not scope['is_admin']:
        raise HTTPException(status_code=403, detail='非管理员不允许按任意条件删除')
    try:
        removed = delete_by_where(payload.collection, payload.where)
        return {'code': 200, 'msg': '删除成功', 'removed': removed, 'collection': payload.collection, 'where': payload.where}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
