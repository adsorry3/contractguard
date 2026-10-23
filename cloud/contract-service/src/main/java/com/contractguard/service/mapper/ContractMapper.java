package com.contractguard.service.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.contractguard.service.entity.Contract;
import org.apache.ibatis.annotations.Mapper;

/**
 * 合同表 Mapper。
 */
@Mapper
public interface ContractMapper extends BaseMapper<Contract> {
}
