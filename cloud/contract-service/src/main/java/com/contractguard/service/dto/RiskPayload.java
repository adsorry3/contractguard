package com.contractguard.service.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.math.BigDecimal;

/**
 * Python 返回的风险项（用 clause_no 关联条款，由 Java 侧映射到 clause_id）。
 */
@Data
public class RiskPayload {

    @JsonProperty("clause_no")
    private String clauseNo;

    @JsonProperty("risk_type")
    private String riskType;

    @JsonProperty("risk_level")
    private String riskLevel;

    private String reason;

    private String suggestion;

    private BigDecimal confidence;
}
