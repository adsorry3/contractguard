package com.contractguard.service.dto;

import lombok.Data;

import java.util.List;

/**
 * 调用 Python AI 审查的请求体。
 */
@Data
public class AiReviewRequest {

    private List<ClausePayload> clauses;
}
