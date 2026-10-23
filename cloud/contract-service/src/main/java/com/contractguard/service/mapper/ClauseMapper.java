package com.contractguard.service.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.contractguard.service.entity.Clause;
import org.apache.ibatis.annotations.Mapper;

/**
 * 合同条款表 Mapper。
 */
@Mapper
public interface ClauseMapper extends BaseMapper<Clause> {
}
