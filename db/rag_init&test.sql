use rag_rbac;

TRUNCATE TABLE user_rbac;
TRUNCATE TABLE doc_permission;
TRUNCATE TABLE rbac_rule;

INSERT INTO rbac_rule (role_level,allow_secret_level,allow_dept_list,is_cross_dept_query)
VALUES
(0, 1, '', 0),
(1, 2, '', 0),
(2, 3, '', 0),
(3, 3, '销售部,研发部,财务部,行政人事部', 1);

-- 1. 销售部
INSERT INTO user_rbac (user_id, username, dept_name, dept_code, role_level, status) VALUES
('sale_staff_01', '销售-普通员工A', '销售部', 'DEPT_SALE', 0, 1),
('sale_core_01', '销售-骨干B',     '销售部', 'DEPT_SALE', 1, 1),
('sale_mgr_01',  '销售-部门经理C', '销售部', 'DEPT_SALE', 2, 1);

-- 2. 研发部
INSERT INTO user_rbac (user_id, username, dept_name, dept_code, role_level, status) VALUES
('dev_staff_01', '研发-普通员工D', '研发部', 'DEPT_DEV', 0, 1),
('dev_core_01',  '研发-骨干E',     '研发部', 'DEPT_DEV', 1, 1),
('dev_mgr_01',   '研发-负责人F',   '研发部', 'DEPT_DEV', 2, 1);

-- 3. 财务部
INSERT INTO user_rbac (user_id, username, dept_name, dept_code, role_level, status) VALUES
('finance_staff_01', '财务-出纳G',  '财务部', 'DEPT_FIN', 0, 1),
('finance_mgr_01',   '财务-主管H',  '财务部', 'DEPT_FIN', 2, 1);

-- 4. 行政人事部
INSERT INTO user_rbac (user_id, username, dept_name, dept_code, role_level, status) VALUES
('hr_staff_01', '人事-专员I', '行政人事部', 'DEPT_HR', 0, 1);

-- 5. 集团高管（跨部门权限）
INSERT INTO user_rbac (user_id, username, dept_name, dept_code, role_level, status) VALUES
('admin_top_01', '集团总经理J', '总经办', 'DEPT_ADMIN', 3, 1);


-- 1. 全局公开文档（密级0，全员可见）
INSERT INTO doc_permission
(doc_id, vec_group_id, dept_owner, secret_level, white_list_users, black_list_users, uploader_id)
VALUES
('doc_pub_001', 'dept_public', '公共', 0, '', '', 'hr_staff_01');

-- 2. 销售部 分级文档
INSERT INTO doc_permission
(doc_id, vec_group_id, dept_owner, secret_level, white_list_users, black_list_users, uploader_id)
VALUES
-- 销售部内部通用（密级1）
('doc_sale_001', 'dept_销售部', '销售部', 1, '', '', 'sale_core_01'),
-- 销售骨干专属（密级2）
('doc_sale_002', 'dept_销售部', '销售部', 2, '', '', 'sale_mgr_01'),
-- 销售底价绝密（密级3，仅部门负责人+高管）
('doc_sale_003', 'dept_销售部', '销售部', 3, '', '', 'sale_mgr_01'),
-- 极强涉密：仅指定白名单可见（销售经理+总经理）
('doc_sale_004', 'dept_销售部', '销售部', 3, 'sale_mgr_01,admin_top_01', '', 'sale_mgr_01');

-- 3. 研发部 分级文档
INSERT INTO doc_permission
(doc_id, vec_group_id, dept_owner, secret_level, white_list_users, black_list_users, uploader_id)
VALUES
('doc_dev_001', 'dept_研发部', '研发部', 1, '', '', 'dev_core_01'),
('doc_dev_002', 'dept_研发部', '研发部', 2, '', '', 'dev_mgr_01'),
('doc_dev_003', 'dept_研发部', '研发部', 3, '', '', 'dev_mgr_01'),
-- 黑名单示例：禁止研发普通员工访问
('doc_dev_004', 'dept_研发部', '研发部', 2, '', 'dev_staff_01', 'dev_mgr_01');

-- 4. 财务部 涉密文档
INSERT INTO doc_permission
(doc_id, vec_group_id, dept_owner, secret_level, white_list_users, black_list_users, uploader_id)
VALUES
('doc_fin_001', 'dept_财务部', '财务部', 1, '', '', 'finance_staff_01'),
('doc_fin_002', 'dept_财务部', '财务部', 3, '', '', 'finance_mgr_01');

ALTER TABLE doc_permission
MODIFY COLUMN file_sha256 VARCHAR(64) NULL,
MODIFY COLUMN text_sha256 VARCHAR(64) NULL;

UPDATE doc_permission
SET file_sha256 = NULL
WHERE file_sha256 = '';
UPDATE doc_permission
SET text_sha256 = NULL
WHERE text_sha256 = '';

commit;