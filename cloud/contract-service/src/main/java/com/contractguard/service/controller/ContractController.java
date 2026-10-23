package com.contractguard.service.controller;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.contractguard.service.common.Result;
import com.contractguard.service.dto.ContractCreateRequest;
import com.contractguard.service.entity.Contract;
import com.contractguard.service.entity.RiskItem;
import com.contractguard.service.service.ContractService;
import com.contractguard.service.vo.ContractDetailVO;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 合同接口。
 */
@RestController
@RequestMapping("/api/contracts")
public class ContractController {

    private final ContractService contractService;

    public ContractController(ContractService contractService) {
        this.contractService = contractService;
    }

    /** 创建合同 */
    @PostMapping
    public Result<Contract> create(@Valid @RequestBody ContractCreateRequest request) {
        return Result.ok(contractService.create(request));
    }

    /** 分页 + 条件查询 */
    @GetMapping
    public Result<Page<Contract>> page(@RequestParam(name = "page", defaultValue = "1") int page,
                                       @RequestParam(name = "size", defaultValue = "10") int size,
                                       @RequestParam(name = "status", required = false) String status,
                                       @RequestParam(name = "keyword", required = false) String keyword) {
        return Result.ok(contractService.page(page, size, status, keyword));
    }

    /** 详情（含条款） */
    @GetMapping("/{id}")
    public Result<ContractDetailVO> detail(@PathVariable Long id) {
        return Result.ok(contractService.detail(id));
    }

    /** 提交审查 */
    @PostMapping("/{id}/review")
    public Result<Void> review(@PathVariable Long id) {
        contractService.submitReview(id);
        return Result.ok();
    }

    /** 风险列表（可按等级筛选） */
    @GetMapping("/{id}/risks")
    public Result<List<RiskItem>> risks(@PathVariable Long id,
                                        @RequestParam(name = "riskLevel", required = false) String riskLevel) {
        return Result.ok(contractService.listRisks(id, riskLevel));
    }
}
