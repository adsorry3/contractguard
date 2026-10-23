package com.contractguard.service.dto;

import lombok.Data;

import java.util.List;
import java.util.Map;

/**
 * Python AI 审查的响应体：fields + risks。
 */
@Data
public class AiReviewResponse {

    private Map<String, Object> fields;

    private List<RiskPayload> risks;
}
