package com.contractguard.service.client;

import com.contractguard.service.dto.AiReviewRequest;
import com.contractguard.service.dto.AiReviewResponse;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

/**
 * Python AI 服务的 Feign 客户端。
 *
 * name=ai-service 走注册中心发现；url 默认空，若配置了 ai.service.url 则直连（演示兜底）。
 */
@FeignClient(name = "ai-service", url = "${ai.service.url:}")
public interface AiServiceClient {

    @PostMapping("/api/ai/review")
    AiReviewResponse review(@RequestBody AiReviewRequest request);
}
