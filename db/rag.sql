CREATE DATABASE IF NOT EXISTS rag_rbac DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE rag_rbac;

DROP TABLE IF EXISTS user_rbac;
CREATE TABLE user_rbac (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
    user_id VARCHAR(50) NOT NULL COMMENT '用户唯一账号ID',
    username VARCHAR(50) DEFAULT '' COMMENT '用户名',
    dept_name VARCHAR(50) NOT NULL COMMENT '所属部门名称',
    dept_code VARCHAR(50) NOT NULL COMMENT '部门编码',
    role_level TINYINT NOT NULL DEFAULT 0 COMMENT '角色等级：0普通员工 1骨干 2部门负责人 3高管',
    privilege_tag VARCHAR(200) DEFAULT '' COMMENT '扩展权限标签',
    status TINYINT DEFAULT 1 COMMENT '账号状态：1正常 0禁用',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    UNIQUE KEY uk_userid (user_id),
    KEY idx_dept (dept_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='RBAC用户权限主表';

DROP TABLE IF EXISTS doc_permission;
CREATE TABLE doc_permission (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
    doc_id VARCHAR(50) NOT NULL COMMENT '文档全局唯一ID',
    vec_group_id VARCHAR(50) NOT NULL COMMENT '向量库分组ID(部门隔离)',
    dept_owner VARCHAR(50) NOT NULL COMMENT '文档归属部门',
    secret_level TINYINT NOT NULL DEFAULT 1 COMMENT '密级：0全员公开 1部门普通 2骨干可见 3负责人绝密',
    white_list_users VARCHAR(1000) DEFAULT '' COMMENT '白名单user_id，逗号分隔',
    black_list_users VARCHAR(1000) DEFAULT '' COMMENT '黑名单user_id，逗号分隔',
    is_allow_summary TINYINT DEFAULT 1 COMMENT '是否允许AI摘要 1是0否',
    is_allow_export TINYINT DEFAULT 1 COMMENT '是否允许导出原文 1是0否',
    uploader_id VARCHAR(50) NOT NULL COMMENT '上传人user_id',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '入库时间',
    UNIQUE KEY uk_docid (doc_id),
    KEY idx_dept_owner (dept_owner),
    KEY idx_secret_level (secret_level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档&向量切片权限绑定表';

DROP TABLE IF EXISTS rbac_rule;
CREATE TABLE rbac_rule (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
    role_level TINYINT NOT NULL COMMENT '角色等级',
    allow_secret_level TINYINT NOT NULL COMMENT '允许访问最大密级',
    allow_dept_list VARCHAR(200) DEFAULT '' COMMENT '可跨部门访问列表',
    is_cross_dept_query TINYINT DEFAULT 0 COMMENT '是否允许跨部门查询 0否1是',
    UNIQUE KEY uk_role_level (role_level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='角色权限映射规则配置表';

-- 销售部 普通员工
INSERT INTO user_rbac (user_id,username,dept_name,dept_code,role_level)
VALUES
('sale_001','销售-小王','销售部','DEPT_SALE',0),
-- 销售部 部门负责人
('sale_mgr','销售-经理','销售部','DEPT_SALE',2),
-- 研发部普通员工
('dev_001','研发-小李','研发部','DEPT_DEV',0),
-- 全局高管
('admin_001','企业高管','总经办','DEPT_ADMIN',3);

-- 1 紧急禁用某用户权限（安全事故应急）
-- UPDATE user_rbac 
-- SET status = 0 
-- WHERE user_id = 'xxx';

-- 2 批量降级文档密级（泄密风险应急）
-- 将部门绝密文档临时降级为部门内部
-- UPDATE doc_permission
-- SET secret_level = 1
-- WHERE dept_owner = '销售部' AND secret_level = 3;

-- 3 批量新增文档白名单（临时授权）
-- UPDATE doc_permission
-- SET white_list_users = CONCAT(white_list_users,',admin_001')
-- WHERE doc_id IN ('xxx','xxx');

--  4 清空某部门全部文档权限配置（重做知识库）
-- DELETE FROM doc_permission WHERE dept_owner = '财务部';

-- 5 恢复默认权限规则（权限乱套时重置）
-- TRUNCATE TABLE rbac_rule;
-- TINSERT INTO rbac_rule (role_level,allow_secret_level,allow_dept_list,is_cross_dept_query)
-- TVALUES
-- T(0,1,'',0),
-- T(1,2,'',0),
-- T(2,3,'',0),
-- T(3,3,'公共',1);

-- 6 查询越权风险文档排查（日常审计）
-- 查询所有高密级文档
-- SELECT doc_id,dept_owner,secret_level,white_list_users,create_time
-- FROM doc_permission
-- WHERE secret_level >= 2
-- ORDER BY create_time DESC;

-- 查询跨部门权限账号
-- SELECT * FROM user_rbac ur
-- JOIN rbac_rule rr ON ur.role_level = rr.role_level
-- WHERE rr.is_cross_dept_query = 1;
commit;
