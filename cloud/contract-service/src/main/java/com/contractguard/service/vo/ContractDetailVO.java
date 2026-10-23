package com.contractguard.service.vo;

import com.contractguard.service.entity.Clause;
import lombok.Data;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 合同详情 VO（含条款列表）。
 */
@Data
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
