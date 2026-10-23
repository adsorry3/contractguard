# 合同卫士 ContractGuard

**企业合同智能审查平台**：上传一份合同，几秒内得到「风险清单 + 原文定位 + 可直接采用的修改建议 + 风险等级」，法务只需做采纳/驳回决策。

![审查报告](docs/screenshot-report.png)

> 左侧合同原文按风险等级高亮，右侧风险清单给出原因、修改建议与置信度，支持逐条采纳/驳回；底部可对合同直接提问，答案带原文引用。

---

## 核心指标

20 份可复现评测集上的实测结果（详见 [eval/report.md](eval/report.md)）：

| 指标 | 结果 |
| --- | --- |
| 风险召回率 | **100%**（86/86） |
| 误报率 | **0.0%**（0/86） |
| 字段抽取准确率 | **100%**（60/60） |
| 端到端耗时 | 中位 **3.3s**，P95 **3.9s** |
| 判定稳定性 | **Jaccard 1.000**（3 份 × 3 次，风险类型集合完全一致） |
| 单份成本 | **约 ¥0.009**（估算值） |

> ⚠️ 评测集为合成合同（条款结构固定、表述规整），指标偏乐观，真实合同预期显著更低。方法与局限见下文。

**Java 侧实测**：合同详情缓存命中 **342ms → 12ms（27.8×）**；跨服务审查调用（Feign → Python → MySQL）单次 **2.3s**；事务回滚、缓存失效、Redis 降级均经故障注入验证。

---

## 功能

- **上传与解析**：支持 PDF / DOCX，自动抽取文本、按条款切分，记录每条字符偏移与页码，供前端精确高亮定位
- **10 类风险识别**：违约金过高、账期过长、单方解除、管辖不利、缺赔偿上限、保密模糊、知识产权不明、验收模糊、自动续约、不可抗力过宽
- **异步审查 + 进度推送**：提交后立即返回 task_id，后台执行，前端轮询或订阅 SSE
- **报告页**：原文高亮、风险卡片、采纳/驳回，反馈落库并自动失效缓存
- **合同问答（RAG）**：混合检索（向量 + BM25 + RRF 融合）+ 两层拒答门控，答案强制标注出处，答不出时明确说「合同未约定」
- **MCP Server**：把条款检索等能力封装为标准 MCP 工具，可在 Claude Desktop 等客户端直接调用

---

## 架构

系统拆成**两个服务**：Java 管业务与事务，Python 管 AI 能力，通过 Eureka 注册中心互相发现。

```text
浏览器（Vue3 单页，CDN，无构建）
   │
   ▼
contract-service（Java 21 / Spring Boot，8081）
   ├─ MySQL：合同 / 条款 / 风险 / 任务 / 反馈 6 张表
   ├─ Redis：合同详情缓存（@Cacheable + @CacheEvict，TTL 5 分钟）
   └─ OpenFeign ──────────┐
                          │  服务发现（Eureka Server，8761）
   ai-service（Python / FastAPI，8000）◄──┘
   ├─ BackgroundTasks ─► LangGraph 状态机
   │                       ├─ extract_fields：LLM 抽 9 个关键字段
   │                       └─ detect_risks：规则粗筛 → LLM 并发精判
   │                                         └─ 缺失型风险：规则直判
   ├─ 问答：bge-m3 向量 + BM25 → RRF 融合 → DeepSeek 生成（答案带引用）
   ├─ Redis：任务进度 / 分布式锁 / 报告缓存
   └─ MCP Server（stdio）◄── Claude Desktop 等外部客户端
```

**为什么拆成两个服务**：AI 调用慢（8~15 秒）且结果不确定，不该和数据库事务绑在一个进程里。
Java 负责事务边界、状态机、权限；Python 负责文档解析与 LLM 编排。**数据归 Java，能力归 Python**——
Python 的 `/api/ai/review` 是无状态接口，只接收条款、返回 JSON，不落库。

**分层**：API 层只做 HTTP 与校验 → 服务层承载能力（解析 / 切分 / 检索 / LLM）→ 编排层用 LangGraph 串流程 → 数据层。

**关键约束**：LangGraph 节点是纯计算，不碰数据库。节点内有线程池并发，而 SQLAlchemy Session 不是线程安全的；持久化统一放在 API / 任务层。

---

## 技术栈

| 层 | 选型 |
| --- | --- |
| **Java 侧** | Spring Boot 3.3.5 / Spring Cloud 2023.0.3 / MyBatis-Plus 3.5.7 / MySQL 8 / Redis |
| **Python 侧** | FastAPI + uvicorn / LangGraph + LangChain / DeepSeek / BAAI-bge-m3 |
| 服务治理 | Eureka（注册发现）+ OpenFeign（声明式调用）+ Spring Cloud LoadBalancer |
| 编排 | LangGraph（规则粗筛 → LLM 并发精判） |
| 模型 | DeepSeek（生成）、bge-m3（向量，1024 维） |
| 缓存 | Redis：Java 侧缓存合同详情，Python 侧存任务进度 / 分布式锁 / 报告缓存 |
| 前端 | Vue3（CDN 单文件，无构建步骤） |
| 工具协议 | MCP（mcp 2.x，MCPServer） |

---

## 快速开始

```bash
# 1. 创建环境
conda create -n hetong python=3.11 -y
conda activate hetong

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置
cp .env.example .env
# 填写 DEEPSEEK_API_KEY 与 SILICONFLOW_API_KEY

# 4. 启动
python run.py
```

- 界面：http://127.0.0.1:8000/
- API 文档：http://127.0.0.1:8000/docs

### Java 微服务侧（可选）

不启动也能用 Python 侧的完整功能；启动后可验证跨服务调用。

```bash
# 1. 初始化数据库（需要 MySQL）
mysql -u root -p < cloud/contract-service/src/main/resources/db/init-db.sql

# 2. 配置数据源（复制模板并填账号密码，该文件已被 gitignore）
cp cloud/contract-service/src/main/resources/application-local.yml.example \
   cloud/contract-service/src/main/resources/application-local.yml

# 3. 构建
cd cloud && mvn clean package -DskipTests

# 4. 依次启动：注册中心 → 业务服务
java -jar eureka-server/target/eureka-server-1.0.0.jar        # 8761
java -jar contract-service/target/contract-service-1.0.0.jar  # 8081
```

- 注册中心控制台：http://localhost:8761
- 业务接口：http://localhost:8081/api/contracts

**Redis 是可选依赖**：未启动时两侧都会自动降级（Python 落数据库、Java 缓存回源），不影响主流程。

**MCP 方式**（可选）：

```bash
python scripts/test_mcp.py     # 命令行自测 4 个工具
```

在 Claude Desktop 配置中追加：

```json
"contractguard": {
  "command": "<你的 python 路径>",
  "args": ["D:\\hetong\\mcp_server.py"]
}
```

---

## API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/contracts` | 上传合同，同步完成解析与切分 |
| GET | `/api/contracts` | 合同列表（分页） |
| GET | `/api/contracts/{id}` | 合同详情（含条款） |
| GET | `/api/contracts/{id}/clauses` | 条款列表 |
| POST | `/api/contracts/{id}/review` | 提交异步审查，返回 task_id |
| POST | `/api/contracts/{id}/analyze` | 同步审查（评测脚本使用） |
| GET | `/api/contracts/{id}/report` | 审查报告（带缓存） |
| POST | `/api/risks/{id}/feedback` | 采纳 / 驳回 |
| POST | `/api/contracts/{id}/index` | 建向量索引 |
| POST | `/api/contracts/{id}/chat` | 基于合同问答 |
| GET | `/api/tasks/{id}` | 任务状态 |
| GET | `/api/tasks/{id}/stream` | 任务进度（SSE） |
| GET | `/health` | 健康检查 |
| GET | `/` | 前端页面 |

### Java 业务服务（8081）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/contracts` | 创建合同（`@Valid` 校验） |
| GET | `/api/contracts` | 分页 + 状态筛选 + 关键字搜索（MyBatis-Plus） |
| GET | `/api/contracts/{id}` | 详情（含条款，**Redis 缓存**） |
| POST | `/api/contracts/{id}/review` | 提交审查：查条款 → Feign 调 AI → 落风险（**事务**） |
| GET | `/api/contracts/{id}/risks` | 风险列表（可按等级筛选） |
| GET | `/api/stats/risk-summary` | 按等级统计（**自定义 XML 联表 SQL**） |

### 跨服务接口（Python 侧，无状态）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/ai/review` | 入参条款列表，返回 `{fields, risks}`，不落库 |

---

## 项目结构

```
app/                      Python 服务（ai-service）
├── main.py              FastAPI 入口
├── config.py            配置（.env）
├── db.py                数据库连接
├── models.py            业务表
├── schemas.py           请求 / 响应模型
├── api/                 contracts / tasks / ai（无状态 AI 接口）
├── services/            parser / splitter / llm / risk_rules /
│                        embedding / retriever / qa / review_service /
│                        task_runner / task_store / redis_client /
│                        ai_review / eureka_client
└── graph/               state / nodes / build（LangGraph）

cloud/                    Java 服务（contract-service）
├── pom.xml              父 pom（多模块）
├── eureka-server/       注册中心，8761
└── contract-service/    业务服务，8081
    ├── src/main/java/com/contractguard/service/
    │   ├── controller/   ContractController / StatsController
    │   ├── service/      ContractService / StatsService
    │   ├── mapper/       MyBatis-Plus Mapper
    │   ├── entity/       6 张表实体
    │   ├── client/       AiServiceClient（OpenFeign）
    │   ├── config/       MybatisPlusConfig / RedisConfig / CacheErrorHandler
    │   └── common/       Result / BusinessException / GlobalExceptionHandler
    └── src/main/resources/
        ├── db/init-db.sql
        └── mapper/RiskItemMapper.xml（联表统计）

mcp_server.py            MCP Server（4 个只读工具）
scripts/test_mcp.py      MCP 自测
eval/                    gen_cases.py / run_eval.py / report.md
docs/                    截图
```

---

## 设计取舍

**1. 规则粗筛 + LLM 精判，而不是全量丢给模型**
18 条条款全量判定又慢又贵，而「违约金」「账期」这类风险的关键词是确定的。规则零成本筛出候选（约一半），模型只精判候选。规则同时可解释、可由业务方维护。

**2. 数值类风险必须做数值判断，不能只看位数**
早期用 `\d{2,}日` 判断账期过长，把「30 日」也判成风险；用 `\d{2,}%` 把「15%」判成过高。改为提取数值后与阈值比较（账期 > 60 日、违约金 > 20%），并支持「百分之三十」这类中文写法。

**3. 缺失型风险改由规则直判**
「全文是否约定赔偿上限」是全文级判断，而 LLM 精判只看单条条款。评测中这类风险 7/7 全部漏报，定位为架构缺陷后改为规则直判（规则扫的就是全文），召回率从 91.9% 提升到 100%。

**4. 拒答用两层门控**
第一层用向量余弦阈值（< 0.45 直接拒答，不调用 LLM）；第二层由模型判断给定条款能否回答。实测发现阈值只能挡住「完全无关」的问题（0.36），挡不住「相关但合同未约定」的问题（0.68，甚至高于某些可回答的问题），因此两层缺一不可。

**5. Redis 全链路可降级**
任务进度、分布式锁、报告缓存都走 Redis，但每个调用都有降级路径：Redis 不可用时落数据库、无锁执行、跳过缓存。实测 Redis 关闭后接口仍全部可用，且单次请求在 300ms 内失败而非等待系统超时。

**6. 只缓存读多写少的合同详情**
列表接口不缓存（条件组合多、命中率低）。失效靠两条机制：提交审查时 `@CacheEvict` 立即清，加 TTL 5 分钟兜底。Redis 不可用时由 `CacheErrorHandler` 吞掉异常、自动回源数据库，接口不报错。

**7. 事务里调远程服务的取舍**
`submitReview` 一个事务包含 8~15 秒的 Feign 调用。好处是回滚语义清晰（AI 失败则任务和状态一起撤销），代价是长时间占用数据库连接——连接池 10 个，10 个并发请求就会占满。当前规模可接受，生产环境应改为「先调 AI，再开短事务写库」。

---

## 评测方法与局限

**方法**：不找真实合同人工标注（成本高且易错），而是**先造题再答题**——用固定模板生成 20 份合同，每份随机注入 3~6 个已知风险，注入时即生成 ground truth。生成后做**双向自检**：注入的风险必须进入规则候选，未注入的条款不得进入候选，否则报错退出（这一步实际抓出过 6 份合同的误触发）。

复现：

```bash
python eval/gen_cases.py    # 生成 20 份合同 + labels（seed=42）
python eval/run_eval.py     # 跑评测，输出 eval/report.md
```

**局限**（重要）：

1. **合成数据偏乐观**：条款结构固定、表述规整，真实合同更长、更不规范
2. **风险类型固定 10 类**：真实合同的风险形态更复杂
3. **成本为 tiktoken 估算值**：非实际账单
4. **管辖规则只覆盖「对方所在地」视角**：约定「甲方所在地」对乙方不利的情况暂未覆盖
5. **任务在进程内执行**：服务重启会中断运行中的任务（启动时清理僵尸任务）；生产环境应换成独立 worker + 消息队列
6. **新实例上线有 35 秒可见延迟**：Spring Cloud LoadBalancer 默认缓存实例列表 35 秒，Python 侧刚注册后立即调用会报「AI 服务不可用」，等下一次刷新即可
7. **服务间无鉴权**：内网 demo 环境未做服务间认证，生产需要加 mTLS 或 token

---

## 已知限制

- SQLite 单机，无并发写优化；向量检索为暴力余弦，适合单份合同（数十条条款）规模
- 扫描件（图片型 PDF）无法抽取文本，接口明确返回 422 提示需要 OCR
- 前端为单页演示版，未做移动端适配与多用户隔离

---

## 后续计划

- [ ] 缺失型风险扩展到「缺少保密期限」「缺少争议解决条款」等
- [ ] 长文档分段检索（先定位章节，再检索条款）
- [ ] 评测集引入真实合同（脱敏）校准指标
- [ ] 独立 worker + 消息队列，支持多任务并发
