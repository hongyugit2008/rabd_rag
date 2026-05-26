CREATE DATABASE  IF NOT EXISTS `rag_rbac` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci */;
USE `rag_rbac`;
-- MySQL dump 10.13  Distrib 8.0.26, for Win64 (x86_64)
--
-- Host: 127.0.0.1    Database: rag_rbac
-- ------------------------------------------------------
-- Server version	5.7.42-log

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `doc_permission`
--

DROP TABLE IF EXISTS `doc_permission`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `doc_permission` (
  `id` int(11) NOT NULL AUTO_INCREMENT COMMENT '自增主键',
  `doc_id` varchar(50) NOT NULL COMMENT '文档全局唯一ID',
  `vec_group_id` varchar(50) NOT NULL COMMENT '向量库分组ID(部门隔离)',
  `dept_owner` varchar(50) NOT NULL COMMENT '文档归属部门',
  `secret_level` tinyint(4) NOT NULL DEFAULT '1' COMMENT '密级：0全员公开 1部门普通 2骨干可见 3负责人绝密',
  `white_list_users` varchar(1000) DEFAULT '' COMMENT '白名单user_id，逗号分隔',
  `black_list_users` varchar(1000) DEFAULT '' COMMENT '黑名单user_id，逗号分隔',
  `is_allow_summary` tinyint(4) DEFAULT '1' COMMENT '是否允许AI摘要 1是0否',
  `is_allow_export` tinyint(4) DEFAULT '1' COMMENT '是否允许导出原文 1是0否',
  `uploader_id` varchar(50) NOT NULL COMMENT '上传人user_id',
  `file_sha256` varchar(64) DEFAULT NULL,
  `text_sha256` varchar(64) DEFAULT NULL,
  `original_filename` varchar(255) NOT NULL DEFAULT '',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '入库时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_docid` (`doc_id`),
  UNIQUE KEY `ux_doc_permission_file_sha256` (`file_sha256`),
  UNIQUE KEY `ux_doc_permission_text_sha256` (`text_sha256`),
  KEY `idx_dept_owner` (`dept_owner`),
  KEY `idx_secret_level` (`secret_level`)
) ENGINE=InnoDB AUTO_INCREMENT=25 DEFAULT CHARSET=utf8mb4 COMMENT='文档&向量切片权限绑定表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `doc_permission`
--

LOCK TABLES `doc_permission` WRITE;
/*!40000 ALTER TABLE `doc_permission` DISABLE KEYS */;
INSERT INTO `doc_permission` VALUES (24,'45c80808-5d22-4fa0-9d72-dbc88de62cd5','dept_销售部','销售部',1,'','',1,1,'sale_staff_01','1d94cf8383a68108497b846bc2dfd95e83004ebe34cdc2d88d043926e95f52a9','6e3b1d8a1ba2140290c012105ad61ffd2efb12807d60181bdaa8aa087cc710ea','09.AISWare iLink_专网智连产品_V2.0_白皮书V2.0.docx','2026-05-26 21:06:06');
/*!40000 ALTER TABLE `doc_permission` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `rbac_rule`
--

DROP TABLE IF EXISTS `rbac_rule`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `rbac_rule` (
  `id` int(11) NOT NULL AUTO_INCREMENT COMMENT '自增主键',
  `role_level` tinyint(4) NOT NULL COMMENT '角色等级',
  `allow_secret_level` tinyint(4) NOT NULL COMMENT '允许访问最大密级',
  `allow_dept_list` varchar(200) DEFAULT '' COMMENT '可跨部门访问列表',
  `is_cross_dept_query` tinyint(4) DEFAULT '0' COMMENT '是否允许跨部门查询 0否1是',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_role_level` (`role_level`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COMMENT='角色权限映射规则配置表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `rbac_rule`
--

LOCK TABLES `rbac_rule` WRITE;
/*!40000 ALTER TABLE `rbac_rule` DISABLE KEYS */;
INSERT INTO `rbac_rule` VALUES (1,0,1,'',0),(2,1,2,'',0),(3,2,3,'',0),(4,3,3,'销售部,研发部,财务部,行政人事部',1);
/*!40000 ALTER TABLE `rbac_rule` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `user_rbac`
--

DROP TABLE IF EXISTS `user_rbac`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `user_rbac` (
  `id` int(11) NOT NULL AUTO_INCREMENT COMMENT '自增主键',
  `user_id` varchar(50) NOT NULL COMMENT '用户唯一账号ID',
  `username` varchar(50) DEFAULT '' COMMENT '用户名',
  `dept_name` varchar(50) NOT NULL COMMENT '所属部门名称',
  `dept_code` varchar(50) NOT NULL COMMENT '部门编码',
  `role_level` tinyint(4) NOT NULL DEFAULT '0' COMMENT '角色等级：0普通员工 1骨干 2部门负责人 3高管',
  `privilege_tag` varchar(200) DEFAULT '' COMMENT '扩展权限标签',
  `status` tinyint(4) DEFAULT '1' COMMENT '账号状态：1正常 0禁用',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_userid` (`user_id`),
  KEY `idx_dept` (`dept_code`)
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COMMENT='RBAC用户权限主表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `user_rbac`
--

LOCK TABLES `user_rbac` WRITE;
/*!40000 ALTER TABLE `user_rbac` DISABLE KEYS */;
INSERT INTO `user_rbac` VALUES (1,'sale_staff_01','销售-普通员工A','销售部','DEPT_SALE',0,'',1,'2026-05-17 20:20:54'),(2,'sale_core_01','销售-骨干B','销售部','DEPT_SALE',1,'',1,'2026-05-17 20:20:54'),(3,'sale_mgr_01','销售-部门经理C','销售部','DEPT_SALE',2,'',1,'2026-05-17 20:20:54'),(4,'dev_staff_01','研发-普通员工D','研发部','DEPT_DEV',0,'',1,'2026-05-17 20:20:54'),(5,'dev_core_01','研发-骨干E','研发部','DEPT_DEV',1,'',1,'2026-05-17 20:20:54'),(6,'dev_mgr_01','研发-负责人F','研发部','DEPT_DEV',2,'',1,'2026-05-17 20:20:54'),(7,'finance_staff_01','财务-出纳G','财务部','DEPT_FIN',0,'',1,'2026-05-17 20:20:54'),(8,'finance_mgr_01','财务-主管H','财务部','DEPT_FIN',2,'',1,'2026-05-17 20:20:54'),(9,'hr_staff_01','人事-专员I','行政人事部','DEPT_HR',0,'',1,'2026-05-17 20:20:54'),(10,'admin_top_01','集团总经理J','总经办','DEPT_ADMIN',3,'',1,'2026-05-17 20:20:54');
/*!40000 ALTER TABLE `user_rbac` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-05-26 21:08:33
