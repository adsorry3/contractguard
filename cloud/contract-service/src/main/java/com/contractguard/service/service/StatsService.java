package com.contractguard.service.service;

import com.contractguard.service.mapper.RiskItemMapper;
import com.contractguard.service.vo.RiskSummaryVO;
import org.springframework.stereotype.Service;

import java.util.List;

/**
 * 统计服务。
 */
@Service
public class StatsService {

    private final RiskItemMapper riskItemMapper;

    public StatsService(RiskItemMapper riskItemMapper) {
        this.riskItemMapper = riskItemMapper;
    }

    /** 风险汇总统计（对应自定义 XML SQL） */
    public List<RiskSummaryVO> riskSummary() {
        return riskItemMapper.selectRiskSummary();
    }
}
