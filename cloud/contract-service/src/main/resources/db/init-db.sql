-- ============================================================================
-- 合同卫士 ContractGuard 初始化建表脚本
-- 库：contractguard   字符集：utf8mb4
-- 执行方式：mysql -uroot -p < init-db.sql
-- ============================================================================

CREATE DATABASE IF NOT EXISTS contractguard DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
USE contractguard;

-- ----------------------------------------------------------------------------
-- 1. 用户表
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `user` (
    `id`            BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
    `username`      VARCHAR(64)  NOT NULL COMMENT '用户名',
    `password_hash` VARCHAR(128) NOT NULL COMMENT '密码哈希',
    `role`          VARCHAR(32)  NOT NULL DEFAULT 'LAWYER' COMMENT '角色',
    `created_at`    DATETIME     NOT NULL COMMENT '创建时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_username` (`username`)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '用户表';

-- ----------------------------------------------------------------------------
-- 2. 合同表
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `contract` (
    `id`         BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
    `filename`   VARCHAR(255) NOT NULL COMMENT '文件名',
    `file_path`  VARCHAR(512) DEFAULT NULL COMMENT '文件路径',
    `file_type`  VARCHAR(16)  DEFAULT NULL COMMENT '文件类型',
    `page_count` INT          NOT NULL DEFAULT 0 COMMENT '页数',
    `char_count` INT          NOT NULL DEFAULT 0 COMMENT '字符数',
    `status`     VARCHAR(32)  NOT NULL DEFAULT 'UPLOADED' COMMENT '状态：UPLOADED/PARSED/REVIEWING/DONE/FAILED',
    `created_at` DATETIME     NOT NULL COMMENT '创建时间',
    `updated_at` DATETIME     NOT NULL COMMENT '更新时间',
    PRIMARY KEY (`id`)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '合同表';

-- ----------------------------------------------------------------------------
-- 3. 合同条款表
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `clause` (
    `id`          BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
    `contract_id` BIGINT       NOT NULL COMMENT '合同ID',
    `clause_no`   VARCHAR(32)  DEFAULT NULL COMMENT '条款编号',
    `title`       VARCHAR(255) DEFAULT NULL COMMENT '标题',
    `content`     TEXT         COMMENT '内容',
    `level`       INT          NOT NULL DEFAULT 1 COMMENT '层级',
    `parent_no`   VARCHAR(32)  DEFAULT NULL COMMENT '父级编号',
    `page_no`     INT          NOT NULL DEFAULT 0 COMMENT '页码',
    `char_start`  INT          NOT NULL DEFAULT 0 COMMENT '起始字符位置',
    `char_end`    INT          NOT NULL DEFAULT 0 COMMENT '结束字符位置',
    PRIMARY KEY (`id`),
    KEY `idx_contract_clause` (`contract_id`, `clause_no`)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '合同条款表';

-- ----------------------------------------------------------------------------
-- 4. 风险项表
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `risk_item` (
    `id`          BIGINT        NOT NULL AUTO_INCREMENT COMMENT '主键',
    `contract_id` BIGINT        NOT NULL COMMENT '合同ID',
    `clause_id`   BIGINT        DEFAULT NULL COMMENT '条款ID',
    `risk_type`   VARCHAR(64)   NOT NULL COMMENT '风险类型',
    `risk_level`  VARCHAR(16)   NOT NULL COMMENT '风险等级：HIGH/MEDIUM/LOW',
    `reason`      TEXT          COMMENT '风险原因',
    `suggestion`  TEXT          COMMENT '修改建议',
    `confidence`  DECIMAL(4, 3) DEFAULT 0 COMMENT '置信度',
    `status`      VARCHAR(16)   NOT NULL DEFAULT 'PENDING' COMMENT '状态：PENDING/ACCEPTED/REJECTED',
    `created_at`  DATETIME      NOT NULL COMMENT '创建时间',
    PRIMARY KEY (`id`),
    KEY `idx_contract_level` (`contract_id`, `risk_level`)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '风险项表';

-- ----------------------------------------------------------------------------
-- 5. 审查任务表
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `review_task` (
    `id`          BIGINT      NOT NULL AUTO_INCREMENT COMMENT '主键',
    `contract_id` BIGINT      NOT NULL COMMENT '合同ID',
    `status`      VARCHAR(32) NOT NULL DEFAULT 'PENDING' COMMENT '状态',
    `progress`    INT         NOT NULL DEFAULT 0 COMMENT '进度（0-100）',
    `stage`       VARCHAR(64) DEFAULT NULL COMMENT '阶段',
    `error_text`  TEXT        COMMENT '错误信息',
    `started_at`  DATETIME    DEFAULT NULL COMMENT '开始时间',
    `finished_at` DATETIME    DEFAULT NULL COMMENT '结束时间',
    `created_at`  DATETIME    NOT NULL COMMENT '创建时间',
    PRIMARY KEY (`id`)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '审查任务表';

-- ----------------------------------------------------------------------------
-- 6. 反馈表
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `feedback` (
    `id`           BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
    `risk_item_id` BIGINT       NOT NULL COMMENT '风险项ID',
    `action`       VARCHAR(16)  NOT NULL COMMENT '操作：ACCEPT/REJECT',
    `comment`      VARCHAR(512) DEFAULT NULL COMMENT '评论',
    `created_at`   DATETIME     NOT NULL COMMENT '创建时间',
    PRIMARY KEY (`id`)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '反馈表';
