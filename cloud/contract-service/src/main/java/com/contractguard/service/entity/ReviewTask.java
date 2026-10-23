package com.contractguard.service.entity;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * 审查任务表实体。
 */
@Data
@TableName("review_task")
public class ReviewTask {

    /** 主键 */
    @TableId(type = IdType.AUTO)
    private Long id;

    /** 合同ID */
    private Long contractId;

    /** 状态 */
    private String status;

    /** 进度（0-100） */
    private Integer progress;

    /** 阶段 */
    private String stage;

    /** 错误信息 */
    private String errorText;

    /** 开始时间 */
    private LocalDateTime startedAt;

    /** 结束时间 */
    private LocalDateTime finishedAt;

    /** 创建时间（插入时自动填充） */
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;
}
