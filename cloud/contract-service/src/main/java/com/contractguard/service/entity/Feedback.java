package com.contractguard.service.entity;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * 反馈表实体。
 */
@Data
@TableName("feedback")
public class Feedback {

    /** 主键 */
    @TableId(type = IdType.AUTO)
    private Long id;

    /** 风险项ID */
    private Long riskItemId;

    /** 操作：ACCEPT/REJECT */
    private String action;

    /** 评论 */
    private String comment;

    /** 创建时间（插入时自动填充） */
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;
}
