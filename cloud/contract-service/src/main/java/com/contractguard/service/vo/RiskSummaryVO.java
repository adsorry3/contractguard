package com.contractguard.service.vo;

import lombok.Data;

/**
 * 风险统计结果 VO（对应 RiskItemMapper.xml 中的联表统计 SQL）。
 */
@Data
public class RiskSummaryVO {

    /** 合同ID */
    private Long contractId;

    /** 文件名 */
    private String filename;

    /** 风险等级 */
    private String riskLevel;

    /** 该合同在该等级下的风险数量 */
    private Long riskCount;

    /** 该合同的风险总数量 */
    private Integer totalCount;
}
