package com.contractguard.service.common;

import lombok.Data;

/**
 * 统一返回体：{code, message, data}，成功时 code = 0。
 *
 * @param <T> 数据类型
 */
@Data
public class Result<T> {

    /** 业务码：0 表示成功 */
    private Integer code;

    /** 提示信息 */
    private String message;

    /** 数据 */
    private T data;

    public Result() {
    }

    public Result(Integer code, String message, T data) {
        this.code = code;
        this.message = message;
        this.data = data;
    }

    /** 成功（无数据） */
    public static <T> Result<T> ok() {
        return new Result<>(0, "success", null);
    }

    /** 成功（带数据） */
    public static <T> Result<T> ok(T data) {
        return new Result<>(0, "success", data);
    }

    /** 失败 */
    public static <T> Result<T> fail(Integer code, String message) {
        return new Result<>(code, message, null);
    }
}
