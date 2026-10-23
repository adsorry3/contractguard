package com.contractguard.service.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.contractguard.service.client.AiServiceClient;
import com.contractguard.service.common.BusinessException;
import com.contractguard.service.dto.AiReviewRequest;
import com.contractguard.service.dto.AiReviewResponse;
import com.contractguard.service.dto.ClausePayload;
import com.contractguard.service.dto.ContractCreateRequest;
import com.contractguard.service.dto.RiskPayload;
import com.contractguard.service.entity.Clause;
import com.contractguard.service.entity.Contract;
import com.contractguard.service.entity.RiskItem;
import com.contractguard.service.entity.ReviewTask;
import com.contractguard.service.mapper.ClauseMapper;
import com.contractguard.service.mapper.ContractMapper;
import com.contractguard.service.mapper.RiskItemMapper;
import com.contractguard.service.mapper.ReviewTaskMapper;
import com.contractguard.service.vo.ContractDetailVO;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.BeanUtils;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 合同业务服务：合同生命周期与审查任务编排。
 */
@Slf4j
@Service
public class ContractService {

    /** 允许提交审查的状态 */
    private static final List<String> REVIEWABLE_STATUS = List.of("UPLOADED", "PARSED");

    private final ContractMapper contractMapper;
    private final ClauseMapper clauseMapper;
    private final RiskItemMapper riskItemMapper;
    private final ReviewTaskMapper reviewTaskMapper;
    private final AiServiceClient aiServiceClient;

    public ContractService(ContractMapper contractMapper,
                           ClauseMapper clauseMapper,
                           RiskItemMapper riskItemMapper,
                           ReviewTaskMapper reviewTaskMapper,
                           AiServiceClient aiServiceClient) {
        this.contractMapper = contractMapper;
        this.clauseMapper = clauseMapper;
        this.riskItemMapper = riskItemMapper;
        this.reviewTaskMapper = reviewTaskMapper;
        this.aiServiceClient = aiServiceClient;
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

    /**
     * 详情（含条款列表）。
     * 读多写少加缓存；注意：必须由外部（Controller）调用才走 AOP 代理生效，
     * 类内部自调用 this.detail(...) 会绕过代理、缓存注解无效。
     */
    @Cacheable(cacheNames = "contract:detail", key = "#id")
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
     * 提交审查：校验 → 查条款 → 建任务 → 调 AI → 落风险 → 完成任务。
     * 任一环节失败整体回滚。
     *
     * 取舍：AI 调用放在事务内，回滚语义清晰；但会长时间占用数据库连接，
     * 生产环境应改为「先调 AI，再开短事务写库」。
     */
    @Transactional(rollbackFor = Exception.class)
    @CacheEvict(cacheNames = "contract:detail", key = "#id")
    public void submitReview(Long id) {
        Contract contract = contractMapper.selectById(id);
        if (contract == null) {
            throw new BusinessException(404, "合同不存在");
        }
        if (!REVIEWABLE_STATUS.contains(contract.getStatus())) {
            throw new BusinessException(400, "当前状态不允许提交审查：" + contract.getStatus());
        }

        // 查询该合同所有条款，并建立 clause_no -> clause_id 映射
        List<Clause> clauses = clauseMapper.selectList(
                new LambdaQueryWrapper<Clause>()
                        .eq(Clause::getContractId, id)
                        .orderByAsc(Clause::getClauseNo));
        if (clauses.isEmpty()) {
            throw new BusinessException(400, "该合同没有条款，无法审查");
        }

        List<ClausePayload> payloads = new ArrayList<>();
        Map<String, Long> clauseNoToId = new HashMap<>();
        for (Clause clause : clauses) {
            ClausePayload p = new ClausePayload();
            p.setClauseNo(clause.getClauseNo());
            p.setTitle(clause.getTitle());
            p.setContent(clause.getContent());
            payloads.add(p);
            clauseNoToId.put(clause.getClauseNo(), clause.getId());
        }

        // 建审查任务（记录开始）
        ReviewTask task = new ReviewTask();
        task.setContractId(id);
        task.setStatus("RUNNING");
        task.setProgress(0);
        task.setStage("AI_REVIEW");
        task.setStartedAt(LocalDateTime.now());
        reviewTaskMapper.insert(task);

        // 调 Python AI 审查；失败则抛业务异常，事务整体回滚
        AiReviewRequest request = new AiReviewRequest();
        request.setClauses(payloads);
        AiReviewResponse response;
        try {
            response = aiServiceClient.review(request);
        } catch (Exception e) {
            log.error("调用 AI 服务失败，contractId={}", id, e);
            throw new BusinessException("AI 服务不可用，请稍后重试");
        }

        // 幂等：先删除该合同旧的风险记录，再写入新结果
        riskItemMapper.delete(new LambdaQueryWrapper<RiskItem>().eq(RiskItem::getContractId, id));

        List<RiskPayload> risks = response.getRisks() == null ? List.of() : response.getRisks();
        for (RiskPayload rp : risks) {
            Long clauseId = clauseNoToId.get(rp.getClauseNo());
            if (clauseId == null) {
                // 映射不到条款的风险项直接丢弃，不写入 NULL/0 的脏数据
                log.warn("风险项映射不到条款，已丢弃：contractId={}, clauseNo={}",
                        id, rp.getClauseNo());
                continue;
            }
            RiskItem item = new RiskItem();
            item.setContractId(id);
            item.setClauseId(clauseId);
            item.setRiskType(rp.getRiskType());
            String level = rp.getRiskLevel();
            item.setRiskLevel(level == null ? "MEDIUM" : level.toUpperCase());
            item.setReason(rp.getReason());
            item.setSuggestion(rp.getSuggestion());
            item.setConfidence(rp.getConfidence());
            item.setStatus("PENDING");
            riskItemMapper.insert(item);
        }

        // 完成任务 + 更新合同状态为 DONE
        task.setStatus("DONE");
        task.setProgress(100);
        task.setStage("DONE");
        task.setFinishedAt(LocalDateTime.now());
        reviewTaskMapper.updateById(task);

        contract.setStatus("DONE");
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
