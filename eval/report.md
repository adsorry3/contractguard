# 评测报告

- 生成时间：2026-10-22 20:22:15
- 数据来源：eval/cases 下 20 份合成合同（seed=42），labels 为注入时的 ground truth
- 合同数：20，跳过（失败）：0

## 总览

| 指标 | 数值 |
| --- | --- |
| 风险召回率 | 100.0% |
| 误报率 | 0.0% |
| 字段抽取准确率（3 字段） | 100.0% |
| 端到端耗时中位数 | 3.3s |
| 端到端耗时 P95 | 3.9s |
| 单份平均成本（估算值） | ¥0.0093 |
| 总成本（估算值） | ¥0.1855（输入 11938 tok + 输出 20200 tok） |
| 稳定性（Jaccard 均值） | 1.000 |

## 逐份明细

| 合同号 | 注入数 | 命中 | 误报 | 耗时(s) |
| --- | --- | --- | --- | --- |
| contract_01 | 3 | 3 | 0 | 3.2 |
| contract_02 | 4 | 4 | 0 | 3.2 |
| contract_03 | 6 | 6 | 0 | 3.9 |
| contract_04 | 3 | 3 | 0 | 2.7 |
| contract_05 | 4 | 4 | 0 | 3.2 |
| contract_06 | 4 | 4 | 0 | 3.5 |
| contract_07 | 4 | 4 | 0 | 3.5 |
| contract_08 | 3 | 3 | 0 | 3.2 |
| contract_09 | 3 | 3 | 0 | 2.5 |
| contract_10 | 6 | 6 | 0 | 3.8 |
| contract_11 | 5 | 5 | 0 | 3.8 |
| contract_12 | 4 | 4 | 0 | 3.1 |
| contract_13 | 3 | 3 | 0 | 2.3 |
| contract_14 | 5 | 5 | 0 | 3.9 |
| contract_15 | 5 | 5 | 0 | 3.5 |
| contract_16 | 6 | 6 | 0 | 3.8 |
| contract_17 | 4 | 4 | 0 | 2.3 |
| contract_18 | 3 | 3 | 0 | 2.6 |
| contract_19 | 6 | 6 | 0 | 3.5 |
| contract_20 | 5 | 5 | 0 | 3.5 |

## 漏报样本（前 5 条）

无漏报。

## 误报样本（前 5 条）

无误报。

## 稳定性

三份合同（contract_01/02/03）各跑 3 次，risk_type 集合两两 Jaccard 均值：**1.000**

- contract_01：acceptance_vague、ip_ownership_unclear、payment_term_too_long | acceptance_vague、ip_ownership_unclear、payment_term_too_long | acceptance_vague、ip_ownership_unclear、payment_term_too_long
- contract_02：auto_renewal、ip_ownership_unclear、liability_cap_missing、penalty_too_high | auto_renewal、ip_ownership_unclear、liability_cap_missing、penalty_too_high | auto_renewal、ip_ownership_unclear、liability_cap_missing、penalty_too_high
- contract_03：confidentiality_vague、force_majeure_broad、ip_ownership_unclear、jurisdiction_unfair、payment_term_too_long、penalty_too_high | confidentiality_vague、force_majeure_broad、ip_ownership_unclear、jurisdiction_unfair、payment_term_too_long、penalty_too_high | confidentiality_vague、force_majeure_broad、ip_ownership_unclear、jurisdiction_unfair、payment_term_too_long、penalty_too_high

## 已知限制

1. 合成数据：条款结构固定、表述规整，风险形态比真实合同简单，指标偏乐观。
2. 风险类型只有 10 类，真实合同的风险形态更复杂，本评测未覆盖。
3. 成本为 tiktoken 估算值（输入 token 用 cl100k_base 近似，输出 token 用经验值），非实际账单。
