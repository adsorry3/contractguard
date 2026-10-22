"""评测执行器：跑 20 份合成合同审查，比对 labels.json 的 ground truth，输出 report.md。

用法（项目根目录下）：
    python eval/run_eval.py

独立性：用独立的 eval_tmp.db，不污染开发库 contractguard.db。
环境变量必须在 import app.* 之前设置（engine 在 import app.db 时创建）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ★ 必须最先：设置独立数据库 + 把项目根加入 sys.path，之后才 import app.*
ROOT = Path(__file__).resolve().parent.parent
os.environ["DATABASE_URL"] = "sqlite:///./eval_tmp.db"
sys.path.insert(0, str(ROOT))

import json
import logging
import re
import statistics
import time
from datetime import datetime

import tiktoken
from sqlalchemy import select

from app.db import Base, SessionLocal, engine
from app.graph.build import get_graph
from app.models import Clause, Contract
from app.services import review_service
from app.services.parser import parse_document
from app.services.splitter import split_clauses

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("eval")

CASES_DIR = ROOT / "eval" / "cases"
LABELS_PATH = CASES_DIR / "labels.json"
REPORT_PATH = ROOT / "eval" / "report.md"

# 稳定性测试固定抽这 3 份（风险数 3 / 4 / 6，有梯度）
STABILITY_CONTRACTS = ("contract_01", "contract_02", "contract_03")

# 3 个关键字段（FieldExtraction 里的字段名）
FIELD_KEYS = ("penalty_rate", "payment_term", "jurisdiction")

# 成本估算常量（DeepSeek 参考价，元/百万 token，估算值，非实际账单）
INPUT_PRICE = 2.0
OUTPUT_PRICE = 8.0
_OUTPUT_TOKENS_FIELDS = 150  # 字段抽取输出 token 经验值
_OUTPUT_TOKENS_RISK = 200    # 每条风险判定输出 token 经验值

# tiktoken 编码器（cl100k_base，与 DeepSeek 分词近似，仅用于估算）
_ENC = tiktoken.get_encoding("cl100k_base")


# ================================================================ 工具函数


def _reset_db() -> None:
    """清空评测库：drop_all + create_all。

    不删文件：Windows 上引擎已打开的 SQLite 文件删不掉（PermissionError）。
    """
    import app.models  # noqa: F401  确保所有模型注册到 Base.metadata

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    logger.info("评测库已重置：%s", engine.url)


def _extract_golden_fields(name: str, spans) -> dict:
    """从条款文本推导 3 个字段的黄金值，推导后立即断言（防止静默失败）。"""
    penalty = payment = jurisdiction = None
    for span in spans:
        content = span.content or ""
        if penalty is None:
            m = re.search(r"违约金为合同总金额的\s*(\d+(?:\.\d+)?)\s*%", content)
            if m:
                penalty = f"{m.group(1)}%"
        if payment is None:
            m = re.search(r"付款账期为\s*(\d+)\s*日", content)
            if m:
                payment = f"{m.group(1)} 日"
        if jurisdiction is None:
            m = re.search(r"由(乙方所在地|被告所在地)人民法院管辖", content)
            if m:
                jurisdiction = m.group(1)

    # 推导失败直接报出是哪份合同、推导出了什么，然后退出（不能静默用错值）
    assert penalty in {"15%", "35%"}, f"{name} 违约金黄金值推导异常：{penalty!r}"
    assert payment in {"30 日", "90 日"}, f"{name} 账期黄金值推导异常：{payment!r}"
    assert jurisdiction in {"乙方所在地", "被告所在地"}, f"{name} 管辖黄金值推导异常：{jurisdiction!r}"

    return {"penalty_rate": penalty, "payment_term": payment, "jurisdiction": jurisdiction}


def _normalize(s) -> str:
    """归一化字段值：全角转半角、去所有空白、去货币/数字分隔符。"""
    if not s:
        return ""
    s = str(s).strip()
    s = s.replace("％", "%").replace("，", ",").replace("　", " ")
    s = re.sub(r"\s+", "", s)
    s = s.replace("人民币", "").replace("元", "").replace(",", "")
    return s


def _field_match(golden: str, actual) -> bool:
    """互相包含判断。None / 空直接判错（不做 in 判断，避免 TypeError）。"""
    g = _normalize(golden)
    a = _normalize(actual)
    if not g or not a:
        return False
    return g in a or a in g


def _jaccard(a: set, b: set) -> float:
    """两个集合的 Jaccard 相似度；都为空时算 1.0。"""
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def _percentile(data: list[float], p: float) -> float:
    """第 p 百分位（p 取 0~1），空列表返回 0。"""
    if not data:
        return 0.0
    ordered = sorted(data)
    idx = min(len(ordered) - 1, int(len(ordered) * p))
    return ordered[idx]


def _estimate_cost(input_tokens: int, output_tokens: int) -> float:
    """按 token 估算成本（元）。输入 token 用 tiktoken 估，输出 token 用经验值。"""
    return (
        input_tokens / 1_000_000 * INPUT_PRICE
        + output_tokens / 1_000_000 * OUTPUT_PRICE
    )


def _run_once(i: int, name: str, run: int) -> dict | None:
    """跑一份合同一次审查。

    返回 dict（含 risks / fields / golden / id_to_no / elapsed_seconds / cost 等），
    失败（如 429 重试后仍失败）返回 None。
    """
    docx_path = CASES_DIR / f"{name}.docx"
    doc = parse_document(docx_path)
    spans = split_clauses(doc)

    # 黄金值推导 + 断言（在跑 LLM 之前先校验，省一次调用）
    golden = _extract_golden_fields(name, spans)

    start = time.perf_counter()

    # 落库 + 组 state（state 是纯 dict，session 关闭后仍可用）
    with SessionLocal() as db:
        contract = Contract(
            filename=f"{name}.docx",
            file_path=str(docx_path),
            file_type="docx",
            page_count=doc.page_count,
            char_count=len(doc.text),
            status="parsed",
        )
        db.add(contract)
        db.flush()
        db.add_all(
            [
                Clause(
                    contract_id=contract.id,
                    clause_no=s.clause_no,
                    title=s.title,
                    content=s.content,
                    level=s.level,
                    parent_no=s.parent_no,
                    page_no=s.page_no,
                    char_start=s.char_start,
                    char_end=s.char_end,
                )
                for s in spans
            ]
        )
        db.commit()
        contract_id = contract.id
        clauses = db.scalars(
            select(Clause).where(Clause.contract_id == contract_id).order_by(Clause.id)
        ).all()
        state = review_service.build_state(contract_id, clauses)
        # 数据库自增 id -> clause_no，用于把 risk 的 clause_id 映射回条款号
        id_to_no = {c.id: c.clause_no for c in clauses}

    # thread_id 每次不同，避免复用 checkpoint
    config = {"configurable": {"thread_id": f"eval-{i}-{name}-{run}"}}

    # 429 限流：失败 sleep 2 秒重试一次，仍失败返回 None（调用方跳过）
    result = None
    for attempt in range(2):
        try:
            result = get_graph().invoke(state, config=config)
            break
        except Exception as exc:  # noqa: BLE001
            if attempt == 0:
                logger.warning("%s run=%d 审查失败，2 秒后重试：%s", name, run, exc)
                time.sleep(2)
            else:
                logger.exception("%s run=%d 重试仍失败，跳过", name, run)
                return None

    elapsed_seconds = time.perf_counter() - start
    risks = result.get("risks") or []
    fields = result.get("fields") or {}

    # token 估算：输入 = 全文 + 各条款；输出 = 字段抽取 + 每条风险判定
    input_text = doc.text + "\n" + "\n".join(s.content or "" for s in spans)
    input_tokens = len(_ENC.encode(input_text))
    output_tokens = _OUTPUT_TOKENS_FIELDS + len(risks) * _OUTPUT_TOKENS_RISK

    return {
        "risks": risks,
        "fields": fields,
        "golden": golden,
        "id_to_no": id_to_no,
        "elapsed_seconds": elapsed_seconds,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost": _estimate_cost(input_tokens, output_tokens),
    }


# ================================================================ 主流程


def main() -> int:
    labels = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
    _reset_db()

    # ---- 主流程：20 份各跑一次（run=0）----
    results: dict[str, dict] = {}
    skipped: list[str] = []
    for i, name in enumerate(labels.keys(), start=1):
        logger.info("开始审查 %s (%d/20)", name, i)
        r = _run_once(i, name, run=0)
        if r is None:
            skipped.append(name)
            continue
        results[name] = r

    # ---- 统计 6 个指标 ----
    total_injected = 0
    total_hit = 0
    total_predicted = 0
    total_fp = 0
    field_correct = 0
    field_total = 0
    elapsed_list: list[float] = []
    total_cost = 0.0
    total_input_tokens = 0
    total_output_tokens = 0

    detail_rows: list[tuple] = []       # (name, 注入数, 命中, 误报, 耗时秒)
    misses: list[tuple] = []            # (name, risk_type, clause_no, 实际判出类型)
    false_positives: list[tuple] = []   # (name, clause_no, 被判类型)

    for name, items in labels.items():
        r = results.get(name)
        if r is None:
            continue

        risks = r["risks"]
        id_to_no = r["id_to_no"]
        fields = r["fields"]
        golden = r["golden"]

        label_types = {it["risk_type"] for it in items}
        label_pairs = {(it["risk_type"], it["clause_no"]) for it in items}

        predicted_types = [x["risk_type"] for x in risks]
        predicted_pairs = [(x["risk_type"], id_to_no.get(x["clause_id"], "?")) for x in risks]

        hit = sum(1 for p in predicted_pairs if p in label_pairs)
        fp = sum(1 for t in predicted_types if t not in label_types)

        total_injected += len(items)
        total_hit += hit
        total_predicted += len(risks)
        total_fp += fp
        elapsed_list.append(r["elapsed_seconds"])
        total_cost += r["cost"]
        total_input_tokens += r["input_tokens"]
        total_output_tokens += r["output_tokens"]

        # 字段准确率（3 字段各判一次）
        for key in FIELD_KEYS:
            field_total += 1
            if _field_match(golden[key], fields.get(key)):
                field_correct += 1

        detail_rows.append((name, len(items), hit, fp, r["elapsed_seconds"]))

        # 漏报样本
        for it in items:
            if (it["risk_type"], it["clause_no"]) not in predicted_pairs:
                misses.append((name, it["risk_type"], it["clause_no"], sorted(set(predicted_types))))
        # 误报样本
        for x in risks:
            if x["risk_type"] not in label_types:
                false_positives.append((name, id_to_no.get(x["clause_id"], "?"), x["risk_type"]))

    # ---- 稳定性：contract_01/02/03 各跑 3 次（run=0 复用主流程结果）----
    stability_jaccards: list[float] = []
    stability_detail: dict[str, list[set]] = {}
    for name in STABILITY_CONTRACTS:
        r0 = results.get(name)
        if r0 is None:
            continue
        idx = list(labels.keys()).index(name) + 1
        sets = [set(x["risk_type"] for x in r0["risks"])]
        for run in (1, 2):
            r = _run_once(idx, name, run)
            sets.append(set(x["risk_type"] for x in r["risks"]) if r else set())
        stability_detail[name] = sets
        # 两两 Jaccard
        for a, b in ((0, 1), (0, 2), (1, 2)):
            stability_jaccards.append(_jaccard(sets[a], sets[b]))

    stability_mean = statistics.mean(stability_jaccards) if stability_jaccards else 0.0
    recall = total_hit / total_injected if total_injected else 0.0
    fpr = total_fp / total_predicted if total_predicted else 0.0
    field_acc = field_correct / field_total if field_total else 0.0
    median_sec = statistics.median(elapsed_list) if elapsed_list else 0.0
    p95_sec = _percentile(elapsed_list, 0.95)

    # ---- 写报告 ----
    _write_report(
        labels=labels,
        recall=recall, fpr=fpr, field_acc=field_acc,
        median_sec=median_sec, p95_sec=p95_sec,
        total_cost=total_cost, total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        detail_rows=detail_rows, misses=misses, false_positives=false_positives,
        stability_mean=stability_mean, stability_detail=stability_detail,
        skipped=skipped,
    )

    # ---- 汇总打印 ----
    print("\n" + "=" * 70)
    print(
        f"召回 {total_hit}/{total_injected} ({recall:.1%}) | "
        f"误报 {total_fp}/{total_predicted} ({fpr:.1%}) | "
        f"字段 {field_correct}/{field_total} | "
        f"中位耗时 {median_sec:.1f}s | "
        f"P95 {p95_sec:.1f}s | "
        f"稳定性 {stability_mean:.3f}"
    )
    print(
        f"估算成本 {total_cost:.4f} 元（输入 {total_input_tokens} tok + "
        f"输出 {total_output_tokens} tok，估算值）"
    )
    if skipped:
        print(f"跳过（失败）合同：{skipped}")
    print(f"报告已写入：{REPORT_PATH}")
    print("=" * 70)
    return 0


def _write_report(
    labels, recall, fpr, field_acc, median_sec, p95_sec,
    total_cost, total_input_tokens, total_output_tokens,
    detail_rows, misses, false_positives, stability_mean, stability_detail, skipped,
) -> None:
    """生成 eval/report.md。"""
    lines: list[str] = []
    lines.append("# 评测报告")
    lines.append("")
    lines.append(f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("- 数据来源：eval/cases 下 20 份合成合同（seed=42），labels 为注入时的 ground truth")
    lines.append(f"- 合同数：{len(labels)}，跳过（失败）：{len(skipped)}")

    lines.append("")
    lines.append("## 总览")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("| --- | --- |")
    lines.append(f"| 风险召回率 | {recall:.1%} |")
    lines.append(f"| 误报率 | {fpr:.1%} |")
    lines.append(f"| 字段抽取准确率（3 字段） | {field_acc:.1%} |")
    lines.append(f"| 端到端耗时中位数 | {median_sec:.1f}s |")
    lines.append(f"| 端到端耗时 P95 | {p95_sec:.1f}s |")
    lines.append(f"| 单份平均成本（估算值） | ¥{total_cost / max(len(detail_rows), 1):.4f} |")
    lines.append(f"| 总成本（估算值） | ¥{total_cost:.4f}（输入 {total_input_tokens} tok + 输出 {total_output_tokens} tok） |")
    lines.append(f"| 稳定性（Jaccard 均值） | {stability_mean:.3f} |")

    lines.append("")
    lines.append("## 逐份明细")
    lines.append("")
    lines.append("| 合同号 | 注入数 | 命中 | 误报 | 耗时(s) |")
    lines.append("| --- | --- | --- | --- | --- |")
    for name, injected, hit, fp, sec in detail_rows:
        lines.append(f"| {name} | {injected} | {hit} | {fp} | {sec:.1f} |")

    lines.append("")
    lines.append("## 漏报样本（前 5 条）")
    lines.append("")
    if misses:
        lines.append("| 合同号 | 应为 | 条款 | 实际判出类型 |")
        lines.append("| --- | --- | --- | --- |")
        for name, rt, no, pred in misses[:5]:
            lines.append(f"| {name} | {rt} | {no} | {', '.join(pred) or '（无）'} |")
    else:
        lines.append("无漏报。")

    lines.append("")
    lines.append("## 误报样本（前 5 条）")
    lines.append("")
    if false_positives:
        lines.append("| 合同号 | 条款 | 被判类型 |")
        lines.append("| --- | --- | --- |")
        for name, no, rt in false_positives[:5]:
            lines.append(f"| {name} | {no} | {rt} |")
    else:
        lines.append("无误报。")

    lines.append("")
    lines.append("## 稳定性")
    lines.append("")
    lines.append(f"三份合同（contract_01/02/03）各跑 3 次，risk_type 集合两两 Jaccard 均值：**{stability_mean:.3f}**")
    lines.append("")
    for name, sets in stability_detail.items():
        runs = " | ".join("、".join(sorted(s)) if s else "（空）" for s in sets)
        lines.append(f"- {name}：{runs}")

    lines.append("")
    lines.append("## 已知限制")
    lines.append("")
    lines.append("1. 合成数据：条款结构固定、表述规整，风险形态比真实合同简单，指标偏乐观。")
    lines.append("2. 风险类型只有 10 类，真实合同的风险形态更复杂，本评测未覆盖。")
    lines.append("3. 成本为 tiktoken 估算值（输入 token 用 cl100k_base 近似，输出 token 用经验值），非实际账单。")

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
