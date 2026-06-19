import hashlib
import logging
import os
import uuid
from pathlib import Path
from tempfile import NamedTemporaryFile
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import Docx2txtLoader, TextLoader
from langchain_huggingface import HuggingFaceEmbeddings
from sqlalchemy.orm import Session

from database import DocPermission, DocAcl
from config import (
    CHROMA_PERSIST_PATH,
    EMBEDDING_MODEL,
    OCR_MIN_CHINESE_RATIO,
    OCR_PREPROCESS_METHOD,
    OCR_LANGUAGE,
    OCR_ORIENTATION,
)
from ocr_utils import is_image_file, extract_text_from_image, assess_ocr_quality

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

logger.info(
    "initializing embeddings | model=%s | chroma_path=%s | base_dir=%s",
    EMBEDDING_MODEL,
    CHROMA_PERSIST_PATH,
    __file__,
)
try:
    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )
    logger.info("embeddings initialized successfully | model=%s", EMBEDDING_MODEL)
except Exception as e:
    logger.exception(
        "embeddings initialization failed | model=%s | reason=%s",
        EMBEDDING_MODEL,
        e,
    )
    raise

try:
    vector_db = Chroma(
        persist_directory=CHROMA_PERSIST_PATH,
        embedding_function=embeddings
    )
    logger.info("chroma vector db initialized | persist_directory=%s", CHROMA_PERSIST_PATH)
except Exception as e:
    logger.exception(
        "chroma initialization failed | persist_directory=%s | reason=%s",
        CHROMA_PERSIST_PATH,
        e,
    )
    raise


def _sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_of_text(text: str) -> str:
    normalized = "\n".join(line.strip() for line in text.splitlines()).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# 文档切片
def split_document(file_path: str):
    suffix = Path(file_path).suffix.lower()
    temp_path = None
    try:
        if suffix == '.docx':
            loader = Docx2txtLoader(file_path)
        elif suffix == '.txt':
            loader = TextLoader(file_path, encoding='utf-8')
        elif is_image_file(file_path):
            text = extract_text_from_image(
                file_path,
                lang=OCR_LANGUAGE,
                orientation=OCR_ORIENTATION,
                preprocess_method=OCR_PREPROCESS_METHOD,
            )
            if not text.strip():
                raise ValueError('图片 OCR 未识别到有效文本')

            # OCR 质量评估
            quality = assess_ocr_quality(text)
            logger.info(
                "ocr quality for %s | chinese_ratio=%.2f garbage_ratio=%.2f quality=%s",
                os.path.basename(file_path),
                quality["chinese_ratio"],
                quality["garbage_ratio"],
                quality["quality"],
            )

            if quality["quality"] == "unusable":
                raise ValueError(
                    f'图片 OCR 质量不可用（中文字符占比仅 {quality["chinese_ratio"]:.1%}），'
                    f'请使用更清晰的图片或手动录入文本。'
                    f'当前 OCR 最低要求: {OCR_MIN_CHINESE_RATIO:.0%}'
                )
            if quality["quality"] == "poor":
                logger.warning(
                    "ocr quality is poor for %s | chinese_ratio=%.2f | 入库后检索效果可能不理想",
                    os.path.basename(file_path),
                    quality["chinese_ratio"],
                )

            tmp = NamedTemporaryFile('w', encoding='utf-8', suffix='.txt', delete=False)
            temp_path = tmp.name
            tmp.write(text)
            tmp.close()
            loader = TextLoader(temp_path, encoding='utf-8')
        else:
            raise ValueError(f"不支持的文件类型: {file_path}")

        text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
        try:
            docs = loader.load_and_split(text_splitter=text_splitter)
        except Exception as e:
            raise RuntimeError(f"文档解析失败: {file_path} | 原因: {e}") from e
        return docs
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


# 带权限打标的文档入库
def ingest_doc_with_rbac(
    db: Session,
    file_path: str,
    uploader_id: str,
    dept_owner: str,
    secret_level: int,
    original_filename: str = "",
    acl_items: list[dict] | None = None,
):
    with open(file_path, "rb") as f:
        file_bytes = f.read()
    file_sha256 = _sha256_of_bytes(file_bytes)

    existing_doc = db.query(DocPermission).filter(DocPermission.file_sha256 == file_sha256, DocPermission.is_deleted == 0).first()
    if existing_doc:
        raise ValueError(
            f"文件内容重复：已存在相同内容文档 doc_id={existing_doc.doc_id} | 原文件名={existing_doc.original_filename or original_filename}"
        )

    chunks = split_document(file_path)
    text_sha256 = _sha256_of_text("\n".join(chunk.page_content for chunk in chunks))
    existing_text = db.query(DocPermission).filter(DocPermission.text_sha256 == text_sha256, DocPermission.is_deleted == 0).first()
    if existing_text:
        raise ValueError(
            f"文档语义内容重复：已存在相同文本文档 doc_id={existing_text.doc_id} | 原文件名={existing_text.original_filename or original_filename}"
        )

    doc_id = str(uuid.uuid4())
    vec_group_id = f"dept_{dept_owner}"

    for chunk in chunks:
        chunk.metadata.update({
            "doc_id": doc_id,
            "vec_group_id": vec_group_id,
            "dept_owner": dept_owner,
            "secret_level": secret_level,
            "filename": original_filename,
        })
        # 将文件名注入分片文本，使文档标题/文件名可被向量检索命中
        chunk.page_content = f"[文档：{original_filename}]\n{chunk.page_content}"

    try:
        texts = [chunk.page_content for chunk in chunks]
        vector_db.add_texts(texts=texts, metadatas=[chunk.metadata for chunk in chunks])
    except Exception as e:
        raise RuntimeError(f"向量库写入失败: doc_id={doc_id} | file_path={file_path} | 原因: {e}") from e

    doc_perm = DocPermission(
        doc_id=doc_id,
        vec_group_id=vec_group_id,
        dept_owner=dept_owner,
        secret_level=secret_level,
        uploader_id=uploader_id,
        file_sha256=file_sha256,
        text_sha256=text_sha256,
        original_filename=original_filename,
    )
    try:
        db.add(doc_perm)
        db.flush()

        if acl_items:
            acl_rows = []
            for item in acl_items:
                subject_type = (item.get("subject_type") or "").strip()
                subject_value = (item.get("subject_value") or "").strip()
                acl_type = (item.get("acl_type") or "").strip()
                if not subject_type or not subject_value or acl_type not in {"allow", "deny"}:
                    continue
                acl_rows.append(DocAcl(
                    doc_permission_id=doc_perm.id,
                    subject_type=subject_type,
                    subject_value=subject_value,
                    acl_type=acl_type,
                ))
            if acl_rows:
                db.add_all(acl_rows)

        db.commit()
    except Exception as e:
        db.rollback()
        raise RuntimeError(f"数据库提交失败: doc_id={doc_id} | 原因: {e}") from e

    return {"code":200, "msg":"入库成功", "doc_id":doc_id}
