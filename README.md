# 合同卫士 ContractGuard

企业合同智能审查平台。上传合同 → 自动切分条款 → 抽取关键字段 → 识别 10 类风险 → 给出修改建议 → 人工复核 → 输出报告，并支持针对单份合同的多轮问答。

> 当前进度：**阶段 0（项目骨架与数据层）**

## 快速开始

```bash
# 1. 创建并激活环境（已完成可跳过）
conda create -n hetong python=3.11 -y
conda activate hetong

# 2. 安装依赖
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 3. 准备配置文件
copy .env.example .env

# 4. 自检
python check_env.py

# 5. 启动
uvicorn app.main:app --reload --port 8000
```

打开 http://127.0.0.1:8000/health ，看到 `"status": "ok"` 和 7 张表就说明成功了。

## 目录结构

```
hetong/
├── app/
│   ├── main.py          # FastAPI 入口
│   ├── config.py        # 配置（读 .env）
│   ├── db.py            # 数据库连接
│   ├── models.py        # 7 张表
│   ├── api/             # 接口（阶段 1 起填充）
│   ├── services/        # 业务逻辑（阶段 1 起填充）
│   ├── graph/           # LangGraph 状态机（阶段 2 起填充）
│   └── prompts/         # prompt 模板（阶段 2 起填充）
├── static/              # 前端单页（阶段 4）
├── eval/                # 评测（阶段 7）
├── uploads/             # 上传文件
├── requirements.txt
├── .env.example
└── check_env.py
```

## 数据模型

| 表 | 作用 |
|---|---|
| `contract` | 合同主表 |
| `clause` | 切分后的条款（检索单元） |
| `risk_item` | 识别出的风险项 |
| `review_task` | 异步审查任务与进度 |
| `feedback` | 人工复核记录 |
| `law_doc` | 法规库 |
| `eval_result` | 评测结果 |

## 路线图

- [x] 阶段 0：骨架与数据层
- [ ] 阶段 1：上传、解析、条款切分
- [ ] 阶段 2：字段抽取与风险识别
- [ ] 阶段 3：异步任务与进度推送
- [ ] 阶段 4：前端单页
- [ ] 阶段 5：RAG 检索与问答
- [ ] 阶段 6：MCP 工具封装
- [ ] 阶段 7：评测台

## 关于基础设施

阶段 0 用 SQLite，零安装。后续如需体现 MySQL / Redis / pgvector：

```bash
# 换 MySQL
python -m pip install pymysql cryptography
# 然后改 .env 里的 DATABASE_URL

# 换 PostgreSQL
python -m pip install psycopg2-binary pgvector
```

代码层只需要改 `.env`，表结构不用动。
