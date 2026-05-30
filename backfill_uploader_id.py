import argparse
import csv
import json
import os
import re
from collections import defaultdict

from database import SessionLocal, DocPermission, UserRbac

LOG_PATH_CANDIDATES = [
    os.path.abspath('./app.log'),
    os.path.abspath('./server.log'),
    os.path.abspath('./uvicorn.log'),
]
UPLOAD_LOG_PATTERN = re.compile(r'upload start \| user_id=(?P<user_id>[^|]+) \| .*original_filename=(?P<filename>.+)$')


def load_upload_map_from_logs() -> dict[str, str]:
    filename_to_user: dict[str, str] = {}
    for path in LOG_PATH_CANDIDATES:
        if not os.path.exists(path):
            continue
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                m = UPLOAD_LOG_PATTERN.search(line.strip())
                if not m:
                    continue
                user_id = m.group('user_id').strip()
                filename = os.path.basename(m.group('filename').strip())
                if filename:
                    filename_to_user[filename] = user_id
    return filename_to_user


def load_upload_map_from_csv(csv_path: str) -> dict[str, str]:
    filename_to_user: dict[str, str] = {}
    with open(csv_path, 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            filename = os.path.basename((row.get('original_filename') or row.get('filename') or '').strip())
            user_id = (row.get('uploader_id') or row.get('user_id') or '').strip()
            if filename and user_id:
                filename_to_user[filename] = user_id
    return filename_to_user


def build_inference_map() -> dict[str, str]:
    mapping = load_upload_map_from_logs()
    return mapping


def resolve_uploader(doc: DocPermission, filename_to_user: dict[str, str], default_uploader: str | None) -> str | None:
    if doc.uploader_id:
        return doc.uploader_id
    candidates = []
    if doc.original_filename:
        candidates.append(os.path.basename(doc.original_filename))
    if doc.original_filename and '_' in doc.original_filename:
        candidates.append(doc.original_filename.split('_', 1)[-1])
    for key in candidates:
        if key in filename_to_user:
            return filename_to_user[key]
    return default_uploader


def main() -> None:
    parser = argparse.ArgumentParser(description='回填历史文档的 uploader_id')
    parser.add_argument('--csv', dest='csv_path', help='可选：CSV 映射文件，列名支持 original_filename/filename 和 uploader_id/user_id')
    parser.add_argument('--default-uploader', help='可选：找不到匹配时使用的兜底账号')
    parser.add_argument('--dry-run', action='store_true', help='只预览，不提交数据库')
    parser.add_argument('--only-empty', action='store_true', default=True, help='仅回填 uploader_id 为空的记录（默认开启）')
    args = parser.parse_args()

    filename_to_user = build_inference_map()
    if args.csv_path:
        filename_to_user.update(load_upload_map_from_csv(args.csv_path))

    db = SessionLocal()
    try:
        docs = db.query(DocPermission).order_by(DocPermission.create_time.asc()).all()
        total = len(docs)
        updated = 0
        skipped = 0
        missing_users = defaultdict(int)

        for doc in docs:
            if args.only_empty and doc.uploader_id:
                skipped += 1
                continue
            uploader_id = resolve_uploader(doc, filename_to_user, args.default_uploader)
            if not uploader_id:
                missing_users[doc.original_filename or doc.doc_id] += 1
                continue
            user = db.query(UserRbac).filter(UserRbac.user_id == uploader_id).first()
            if not user:
                missing_users[uploader_id] += 1
                continue
            doc.uploader_id = uploader_id
            updated += 1
            print(f'回填: doc_id={doc.doc_id} | uploader_id={uploader_id} | original_filename={doc.original_filename}')

        print(f'总记录数: {total} | 已处理: {updated} | 跳过: {skipped} | 未匹配: {sum(missing_users.values())}')
        if missing_users:
            print('未匹配项:')
            for key, cnt in sorted(missing_users.items(), key=lambda x: (-x[1], x[0]))[:50]:
                print(f'  - {key}: {cnt}')

        if args.dry_run:
            db.rollback()
            print('dry-run 模式，未提交。')
        else:
            db.commit()
            print('回填完成，已提交数据库。')
    finally:
        db.close()


if __name__ == '__main__':
    main()
