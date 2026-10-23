package com.contractguard.service.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.contractguard.service.entity.RiskItem;
import com.contractguard.service.vo.RiskSummaryVO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

/**
 * 风险项表 Mapper。
 */
@Mapper
public interface RiskItemMapper extends BaseMapper<RiskItem> {

    /**
     * 按风险等级统计每个合同的风险数量，联表 contract 带出文件名，按数量倒序。
     * 对应自定义 XML：resources/mapper/RiskItemMapper.xml。
     */
    List<RiskSummaryVO> selectRiskSummary();
}
