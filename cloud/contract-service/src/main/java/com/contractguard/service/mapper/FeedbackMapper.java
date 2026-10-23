package com.contractguard.service.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.contractguard.service.entity.Feedback;
import org.apache.ibatis.annotations.Mapper;

/**
 * 反馈表 Mapper。
 */
@Mapper
public interface FeedbackMapper extends BaseMapper<Feedback> {
}
