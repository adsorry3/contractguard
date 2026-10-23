package com.contractguard.service.common;

import lombok.Getter;

/**
 * 业务异常：携带业务码，由 {@link GlobalExceptionHandler} 统一转换为 Result。
 */
@Getter
public class BusinessException extends RuntimeException {

    /** 业务码 */
    private final Integer code;

    public BusinessException(String message) {
        this(400, message);
    }

    public BusinessException(Integer code, String message) {
        super(message);
        this.code = code;
    }
}
