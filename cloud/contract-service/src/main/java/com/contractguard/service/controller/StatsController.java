package com.contractguard.service.controller;

import com.contractguard.service.common.Result;
import com.contractguard.service.service.StatsService;
import com.contractguard.service.vo.RiskSummaryVO;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 统计接口。
 */
@RestController
@RequestMapping("/api/stats")
public class StatsController {

    private final StatsService statsService;

    public StatsController(StatsService statsService) {
        this.statsService = statsService;
    }

    /** 风险汇总（自定义 XML 联表统计） */
    @GetMapping("/risk-summary")
    public Result<List<RiskSummaryVO>> riskSummary() {
        return Result.ok(statsService.riskSummary());
    }
}
