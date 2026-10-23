package com.contractguard.service.entity;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * 合同表实体。
 */
@Data
@TableName("contract")
public class Contract {

    /** 主键 */
    @TableId(type = IdType.AUTO)
    private Long id;

    /** 文件名 */
    private String filename;

    /** 文件路径 */
    private String filePath;

    /** 文件类型 */
    private String fileType;

    /** 页数 */
    private Integer pageCount;

    /** 字符数 */
    private Integer charCount;

    /** 状态：UPLOADED/PARSED/REVIEWING/DONE/FAILED */
    private String status;

    /** 创建时间（插入时自动填充） */
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;

    /** 更新时间（插入/更新时自动填充） */
    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedAt;
}
