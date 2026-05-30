ALTER TABLE doc_permission
    ADD COLUMN file_sha256 VARCHAR(64) NOT NULL AFTER uploader_id,
    ADD COLUMN text_sha256 VARCHAR(64) NOT NULL AFTER file_sha256,
    ADD COLUMN original_filename VARCHAR(255) NOT NULL DEFAULT '' AFTER text_sha256;

CREATE UNIQUE INDEX ux_doc_permission_file_sha256 ON doc_permission (file_sha256);
CREATE INDEX ix_doc_permission_text_sha256 ON doc_permission (text_sha256);

-- 说明：
-- 1. file_sha256 用于文件级去重，避免同一二进制文件重复上传
-- 2. text_sha256 用于文本级去重，避免不同文件名但正文相同的文档重复入库
-- 3. original_filename 用于保留原始文件名，方便审计和排查
