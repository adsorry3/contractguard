package com.contractguard.service;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.client.discovery.EnableDiscoveryClient;
import org.springframework.cloud.openfeign.EnableFeignClients;

/**
 * 合同业务服务：启动后注册到 eureka（8761），对外暴露 8081。
 * 后续通过 Feign 调用 Python 侧的 ai-service 做审查与问答。
 */
@SpringBootApplication
@EnableDiscoveryClient
@EnableFeignClients
public class ContractServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(ContractServiceApplication.class, args);
    }
}
