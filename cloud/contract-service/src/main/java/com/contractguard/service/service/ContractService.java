package com.contractguard.service.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.contractguard.service.common.BusinessException;
import com.contractguard.service.dto.ContractCreateRequest;
import com.contractguard.service.entity.Clause;
import com.contractguard.service.entity.Contract;
import com.contractguard.service.entity.RiskItem;
import com.contractguard.service.entity.ReviewTask;
import com.contractguard.service.mapper.ClauseMapper;
import com.contractguard.service.mapper.ContractMapper;
import com.contractguard.service.mapper.RiskItemMapper;
import com.contractguard.service.mapper.ReviewTaskMapper;
import com.contractguard.service.vo.ContractDetailVO;
import org.springframework.beans.BeanUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 合同业务服务：合同生命周期与审查任务编排。
 */
@Service
public class ContractService {

    /** 允许提交审查的状态 */
    private static final List<String> REVIEWABLE_STATUS = List.of("UPLOADED", "PARSED");

    private final ContractMapper contractMapper;
    private final ClauseMapper clauseMapper;
    private final RiskItemMapper riskItemMapper;
    private final ReviewTaskMapper reviewTaskMapper;

    public ContractService(ContractMapper contractMapper,
                           ClauseMapper clauseMapper,
                           RiskItemMapper riskItemMapper,
                           ReviewTaskMapper reviewTaskMapper) {
        this.contractMapper = contractMapper;
        this.clauseMapper = clauseMapper;
        this.riskItemMapper = riskItemMapper;
        this.reviewTaskMapper = reviewTaskMapper;
    }

    /** 创建合同 */
    public Contract create(ContractCreateRequest request) {
        Contract contract = new Contract();
        contract.setFilename(request.getFilename());
        contract.setFilePath(request.getFilePath());
        contract.setFileType(request.getFileType());
        contract.setPageCount(request.getPageCount() == null ? 0 : request.getPageCount());
        contract.setCharCount(request.getCharCount() == null ? 0 : request.getCharCount());
        contract.setStatus("UPLOADED");
        contractMapper.insert(contract);
        return contract;
    }

    /** 分页 + 条件查询（status 精确、keyword 模糊匹配 filename） */
    public Page<Contract> page(int page, int size, String status, String keyword) {
        LambdaQueryWrapper<Contract> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(status != null && !status.isBlank(), Contract::getStatus, status)
                .like(keyword != null && !keyword.isBlank(), Contract::getFilename, keyword)
                .orderByDesc(Contract::getCreatedAt);
        return contractMapper.selectPage(new Page<>(page, size), wrapper);
    }

    /** 详情（含条款列表） */
    public ContractDetailVO detail(Long id) {
        Contract contract = contractMapper.selectById(id);
        if (contract == null) {
            throw new BusinessException(404, "合同不存在");
        }
        ContractDetailVO vo = new ContractDetailVO();
        BeanUtils.copyProperties(contract, vo);

        List<Clause> clauses = clauseMapper.selectList(
                new LambdaQueryWrapper<Clause>()
                        .eq(Clause::getContractId, id)
                        .orderByAsc(Clause::getClauseNo));
        vo.setClauses(clauses);
        return vo;
    }

    /**
     * 提交审查：校验合同状态 → 新建 review_task → 合同状态改为 REVIEWING。
     * 任一环节失败整体回滚。
     */
    @Transactional(rollbackFor = Exception.class)
    public void submitReview(Long id) {
        Contract contract = contractMapper.selectById(id);
        if (contract == null) {
            throw new BusinessException(404, "合同不存在");
        }
        if (!REVIEWABLE_STATUS.contains(contract.getStatus())) {
            throw new BusinessException(400, "当前状态不允许提交审查：" + contract.getStatus());
        }

        ReviewTask task = new ReviewTask();
        task.setContractId(id);
        task.setStatus("PENDING");
        task.setProgress(0);
        task.setStage("INIT");
        task.setStartedAt(LocalDateTime.now());
        reviewTaskMapper.insert(task);

        contract.setStatus("REVIEWING");
        contract.setUpdatedAt(LocalDateTime.now());
        contractMapper.updateById(contract);
    }

    /** 风险列表（可按等级筛选） */
    public List<RiskItem> listRisks(Long id, String riskLevel) {
        LambdaQueryWrapper<RiskItem> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(RiskItem::getContractId, id)
                .eq(riskLevel != null && !riskLevel.isBlank(), RiskItem::getRiskLevel, riskLevel)
                .orderByDesc(RiskItem::getCreatedAt);
        return riskItemMapper.selectList(wrapper);
    }
}
