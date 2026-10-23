package com.contractguard.service.entity;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 风险项表实体。
 */
@Data
@TableName("risk_item")
public class RiskItem {

    /** 主键 */
    @TableId(type = IdType.AUTO)
    private Long id;

    /** 合同ID */
    private Long contractId;

    /** 条款ID */
    private Long clauseId;

    /** 风险类型 */
    private String riskType;

    /** 风险等级：HIGH/MEDIUM/LOW */
    private String riskLevel;

    /** 风险原因 */
    private String reason;

    /** 修改建议 */
    private String suggestion;

    /** 置信度 */
    private BigDecimal confidence;

    /** 状态：PENDING/ACCEPTED/REJECTED */
    private String status;

    /** 创建时间（插入时自动填充） */
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;
}
