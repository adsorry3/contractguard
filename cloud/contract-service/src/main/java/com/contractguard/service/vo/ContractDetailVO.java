package com.contractguard.service.vo;

import com.contractguard.service.entity.Clause;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 合同详情 VO（含条款列表）。
 *
 * 作为缓存 value 会被 GenericJackson2JsonRedisSerializer 序列化/反序列化，
 * 必须保留无参构造器，否则缓存命中时无法从 JSON 还原对象（失败会被降级吞掉，缓存永远不命中）。
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class ContractDetailVO {

    private Long id;

    private String filename;

    private String filePath;

    private String fileType;

    private Integer pageCount;

    private Integer charCount;

    private String status;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;

    /** 条款列表 */
    private List<Clause> clauses;
}
