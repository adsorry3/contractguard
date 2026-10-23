package com.contractguard.service.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

/**
 * 创建合同请求体。
 */
@Data
public class ContractCreateRequest {

    /** 文件名（必填） */
    @NotBlank(message = "文件名不能为空")
    private String filename;

    /** 文件路径 */
    private String filePath;

    /** 文件类型 */
    private String fileType;

    /** 页数 */
    private Integer pageCount;

    /** 字符数 */
    private Integer charCount;
}
