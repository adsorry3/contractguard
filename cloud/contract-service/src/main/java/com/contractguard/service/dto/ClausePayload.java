package com.contractguard.service.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

/**
 * AI 审查入参的条款载荷（对应 Python 侧的 clause_no / title / content）。
 */
@Data
public class ClausePayload {

    @JsonProperty("clause_no")
    private String clauseNo;

    private String title;

    private String content;
}
