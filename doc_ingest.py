import logging
import uuid
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import Docx2txtLoader, TextLoader
from langchain_huggingface import HuggingFaceEmbeddings
from sqlalchemy.orm import Session

from database import DocPermission
from config import CHROMA_PERSIST_PATH, EMBEDDING_MODEL

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

# 初始化向量库
# 说明：DeepSeek 仅用于生成式问答，不提供这里需要的向量嵌入接口。
# 检索阶段改为本地 HuggingFace 向量模型，避免调用远端 embeddings 接口导致 404。
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

# 文档切片
def split_document(file_path: str):
    # 判断文件扩展名
    if file_path.endswith('.docx'):
        loader = Docx2txtLoader(file_path)
    elif file_path.endswith('.txt'):
        loader = TextLoader(file_path, encoding='utf-8')
    else:
        raise ValueError(f"不支持的文件类型: {file_path}")

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    try:
        docs = loader.load_and_split(text_splitter=text_splitter)
    except Exception as e:
        raise RuntimeError(f"文档解析失败: {file_path} | 原因: {e}") from e
    return docs

# 带权限打标的文档入库
def ingest_doc_with_rbac(db: Session, file_path: str, uploader_id: str, dept_owner: str, secret_level: int):
    chunks = split_document(file_path)
    doc_id = str(uuid.uuid4())
    vec_group_id = f"dept_{dept_owner}"

    for chunk in chunks:
        chunk.metadata.update({
            "doc_id": doc_id,
            "vec_group_id": vec_group_id,
            "dept_owner": dept_owner,
            "secret_level": secret_level
        })

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
        uploader_id=uploader_id
    )
    try:
        db.add(doc_perm)
        db.commit()
    except Exception as e:
        db.rollback()
        raise RuntimeError(f"数据库提交失败: doc_id={doc_id} | 原因: {e}") from e

    return {"code":200, "msg":"入库成功", "doc_id":doc_id}
