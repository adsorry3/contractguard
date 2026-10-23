package com.contractguard.service.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

/**
 * 合同条款表实体（无时间字段，不需自动填充）。
 */
@Data
@TableName("clause")
public class Clause {

    /** 主键 */
    @TableId(type = IdType.AUTO)
    private Long id;

    /** 合同ID */
    private Long contractId;

    /** 条款编号 */
    private String clauseNo;

    /** 标题 */
    private String title;

    /** 内容 */
    private String content;

    /** 层级 */
    private Integer level;

    /** 父级编号 */
    private String parentNo;

    /** 页码 */
    private Integer pageNo;

    /** 起始字符位置 */
    private Integer charStart;

    /** 结束字符位置 */
    private Integer charEnd;
}
