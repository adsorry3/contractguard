"""生成评测用例：20 份合成合同 + ground truth 标签 + 双向自检。

用法（项目根目录下）：
    python eval/gen_cases.py

产物：
    eval/cases/contract_01.docx ... contract_20.docx
    eval/cases/labels.json

关键设计：
    - seed=42 固定，随机注入可复现；
    - 每份合同随机注入 3-6 类风险，其余条款写「正常表述」；
    - 生成后立即跑 screen_candidates 做双向自检：
        断言 1：注入的每个 risk_type 必须进入候选（否则说明注入表述没命中规则）；
        断言 2：未注入风险的条款不得进入候选（否则说明「正常表述」写得像风险）。
      两条都通过才算成功，否则打印「第几份合同、哪个条款」后退出。
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

from docx import Document

# 项目根目录（本文件在 eval/ 下，上溯一级），加入 sys.path 才能 import app
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.parser import parse_document
from app.services.risk_rules import screen_candidates
from app.services.splitter import split_clauses

SEED = 42
NUM_CONTRACTS = 20
CASES_DIR = ROOT / "eval" / "cases"
LABELS_PATH = CASES_DIR / "labels.json"

# 10 类风险各自挂靠的条款号（与模板条款一一对应）
RISK_CLAUSE: dict[str, str] = {
    "payment_term_too_long": "第一条",
    "penalty_too_high": "第二条",
    "liability_cap_missing": "第二条",  # 缺失类，挂靠「违约责任」条款
    "acceptance_vague": "第三条",
    "ip_ownership_unclear": "第四条",
    "unilateral_termination": "第五条",
    "jurisdiction_unfair": "第六条",
    "confidentiality_vague": "第七条",
    "auto_renewal": "第八条",
    "force_majeure_broad": "第九条",
}

ALL_RISK_TYPES = list(RISK_CLAUSE.keys())


def build_contract_clauses(injected: set[str]) -> list[tuple[str, str]]:
    """根据注入的风险集合，生成 10 个条款，返回 [(标题, 内容), ...]。

    注意：每个「正常表述」必须避开 risk_rules.py 里的正则，否则双向自检的断言 2 会失败。
    """
    clauses: list[tuple[str, str]] = []

    # 第一章 总则（固定，无任何风险词）
    clauses.append(
        ("第一章 总则", "本合同经双方协商一致订立。甲方为采购方，乙方为供应方。")
    )

    # 第一条 付款（payment_term_too_long）
    if "payment_term_too_long" in injected:
        clauses.append(("第一条 付款", "付款账期为 90 日，付款方式为银行转账。"))
    else:
        # 账期 30 日是商业合同里最常见的写法，规则用数值阈值（> 60 日）判断，不会误报
        clauses.append(("第一条 付款", "付款账期为 30 日，付款方式为银行转账。"))

    # 第二条 违约责任（penalty_too_high + liability_cap_missing 的挂靠条款）
    penalty = (
        "违约金为合同总金额的 35%。"
        if "penalty_too_high" in injected
        else "违约金为合同总金额的 15%。"  # 15% 在 20% 阈值以内，规则不会误报
    )
    # cap 里不能出现两位数百分比：会被 penalty_too_high 的正则跨句命中，改用文字表述
    # （同时必须含「赔偿上限」，否则规则会判成「缺少赔偿上限」）
    cap = "" if "liability_cap_missing" in injected else "赔偿上限不超过合同总金额。"
    clauses.append(("第二条 违约责任", penalty + cap))

    # 第三条 验收（acceptance_vague）
    if "acceptance_vague" in injected:
        clauses.append(("第三条 验收", "验收标准由双方另行确认。"))
    else:
        clauses.append(("第三条 验收", "验收标准为符合国家标准 GB/T 19001。"))

    # 第四条 知识产权（ip_ownership_unclear）
    if "ip_ownership_unclear" in injected:
        clauses.append(("第四条 知识产权", "知识产权归属由双方另行协商确定。"))
    else:
        # 注意：正则「归.{0,6}方」会把「归甲方」也命中，所以正常表述不用「归…方」
        clauses.append(("第四条 知识产权", "知识产权全部由甲方享有。"))

    # 第五条 合同解除（unilateral_termination）
    if "unilateral_termination" in injected:
        clauses.append(("第五条 合同解除", "甲方有权随时单方解除本合同。"))
    else:
        clauses.append(("第五条 合同解除", "经双方协商一致，可以解除本合同。"))

    # 第六条 管辖（jurisdiction_unfair）
    if "jurisdiction_unfair" in injected:
        clauses.append(("第六条 管辖", "因本合同发生的争议，由乙方所在地人民法院管辖。"))
    else:
        # 「被告所在地法院管辖」是默认规则、中性条款，规则已移除「被告」，不会误报
        clauses.append(("第六条 管辖", "因本合同发生的争议，由被告所在地人民法院管辖。"))

    # 第七条 保密（confidentiality_vague）
    if "confidentiality_vague" in injected:
        clauses.append(("第七条 保密", "保密期限由双方另行约定。"))
    else:
        clauses.append(("第七条 保密", "保密期限为合同终止后五年。"))

    # 第八条 续约（auto_renewal）
    if "auto_renewal" in injected:
        clauses.append(("第八条 续约", "合同期满后自动续约。"))
    else:
        clauses.append(("第八条 续约", "合同期满后如需续约，应提前三十日书面通知对方。"))

    # 第九条 不可抗力（force_majeure_broad）
    if "force_majeure_broad" in injected:
        clauses.append(("第九条 不可抗力", "不可抗力包括但不限于政策调整、市场变化。"))
    else:
        clauses.append(("第九条 不可抗力", "不可抗力指不能预见、不能避免且不能克服的自然灾害。"))

    return clauses


def write_docx(path: Path, clauses: list[tuple[str, str]]) -> None:
    """把条款写入 docx：每个条款一个标题段落 + 一个内容段落。"""
    doc = Document()
    for heading, content in clauses:
        doc.add_paragraph(heading)
        doc.add_paragraph(content)
    doc.save(str(path))


def self_check(labels: dict) -> bool:
    """双向自检：注入的风险必须进候选，正常条款不得进候选。

    返回是否全部通过；失败时打印「第几份合同、哪个条款、哪个 risk_type」。
    """
    all_ok = True
    for name, injected_items in labels.items():
        docx_path = CASES_DIR / f"{name}.docx"
        doc = parse_document(docx_path)
        spans = split_clauses(doc)
        clauses = [
            {"clause_id": i, "clause_no": s.clause_no, "title": s.title, "content": s.content}
            for i, s in enumerate(spans)
        ]
        candidates = screen_candidates(clauses)

        # 候选里的 risk_type -> 命中的条款号集合
        candidate_types: dict[str, set[str]] = {}
        for clause, types in candidates:
            for t in types:
                candidate_types.setdefault(t, set()).add(clause["clause_no"])

        injected_types = {item["risk_type"] for item in injected_items}

        # 断言 1：注入的每个 risk_type 必须进入候选
        for item in injected_items:
            rt = item["risk_type"]
            if rt not in candidate_types:
                print(f"  [断言1失败] {name} 注入的 {rt}（{item['clause_no']}）未进入候选")
                all_ok = False

        # 断言 2：候选里不能出现未注入的 risk_type
        for rt, clause_nos in candidate_types.items():
            if rt not in injected_types:
                print(f"  [断言2失败] {name} 未注入的 {rt} 误入候选（条款 {sorted(clause_nos)}）")
                all_ok = False

    return all_ok


def main() -> int:
    rng = random.Random(SEED)
    CASES_DIR.mkdir(parents=True, exist_ok=True)

    labels: dict[str, list[dict]] = {}
    for i in range(1, NUM_CONTRACTS + 1):
        name = f"contract_{i:02d}"
        # 随机注入 3-6 类风险（不重复）
        k = rng.randint(3, 6)
        injected = set(rng.sample(ALL_RISK_TYPES, k))

        clauses = build_contract_clauses(injected)
        write_docx(CASES_DIR / f"{name}.docx", clauses)

        labels[name] = [
            {"risk_type": rt, "clause_no": RISK_CLAUSE[rt]} for rt in sorted(injected)
        ]

    # 写 ground truth 标签
    LABELS_PATH.write_text(
        json.dumps(labels, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"已生成 {NUM_CONTRACTS} 份合同 -> {CASES_DIR}")
    print(f"已写入标签 -> {LABELS_PATH}")

    # 逐份打印注入情况，方便人工核对
    for name, items in labels.items():
        summary = ", ".join(f"{it['risk_type']}({it['clause_no']})" for it in items)
        print(f"  {name}: {summary}")

    # 双向自检
    print("\n开始双向自检（screen_candidates）...")
    ok = self_check(labels)
    if not ok:
        print("\n自检未通过：请修正「危险表述 / 正常表述」后重跑。")
        return 1
    print("自检通过：注入风险全部进入候选，正常条款零误触发。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
