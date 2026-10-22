"""条款切分：把合同全文切成可检索、可定位的条款块。

切分策略（按优先级，命中即停）：
1. 中文编号「第X章」「第X条」  —— 合同最标准的写法
2. Markdown 标题「##」或数字编号「1.」「1.2」
3. 中文列表「（一）（二）」
4. 都没有：按固定长度切（带重叠），保证不会切出空结果
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from collections.abc import Iterator

from app.services.parser import ParsedDocument

MAX_TITLE_LEN = 120
FALLBACK_SIZE = 500
FALLBACK_OVERLAP = 50

# 第X章 / 第X条：捕获「编号」和「后面的标题或正文开头」
_CN_CHAPTER = re.compile(r"^(第[一二三四五六七八九十百千零〇0-9]+章)[\s:：、.·]*(.*)$")
_CN_ARTICLE = re.compile(r"^(第[一二三四五六七八九十百千零〇0-9]+条)[\s:：、.·]*(.*)$")
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_NUM_HEADING = re.compile(r"^(\d+(?:\.\d+){0,3})[.、]\s*(.*)$")
_CN_LIST = re.compile(r"^[（(]([一二三四五六七八九十]+)[）)][\s:：、.]*(.*)$")


@dataclass
class ClauseSpan:
    """一个切分出来的条款块。"""

    clause_no: str
    title: str
    content: str
    level: int
    parent_no: str
    char_start: int
    char_end: int
    page_no: int


def split_clauses(doc: ParsedDocument) -> list[ClauseSpan]:
    """把解析结果切成条款列表。"""
    headings = _detect_headings(doc.text)
    if not headings:
        return _fallback_chunks(doc)
    return _build_spans(doc, headings)


# ---------------------------------------------------------------- 内部实现


def _iter_lines(text: str) -> Iterator[tuple[int, str]]:
    """逐行产出（该行起始偏移, 行内容）。"""
    offset = 0
    for line in text.split("\n"):
        yield offset, line
        offset += len(line) + 1


def _detect_headings(text: str) -> list[tuple[int, str, str, int]]:
    """依次尝试三种规则，返回 (起始偏移, 编号, 标题, 层级)。

    至少命中 2 个才认为这个文件真的用了这套编号，
    避免正文里偶然出现一句「第一条」就把整篇切乱。
    """
    for detector in (_detect_cn_headings, _detect_md_or_num, _detect_cn_list):
        found = detector(text)
        if len(found) >= 2:
            return found
    return []


def _detect_cn_headings(text: str) -> list[tuple[int, str, str, int]]:
    out: list[tuple[int, str, str, int]] = []
    for start, line in _iter_lines(text):
        stripped = line.strip()
        if not stripped:
            continue
        match = _CN_CHAPTER.match(stripped)
        if match:
            out.append((start, match.group(1), match.group(2).strip(), 1))
            continue
        match = _CN_ARTICLE.match(stripped)
        if match:
            out.append((start, match.group(1), match.group(2).strip(), 2))
    return out


def _detect_md_or_num(text: str) -> list[tuple[int, str, str, int]]:
    out: list[tuple[int, str, str, int]] = []
    for start, line in _iter_lines(text):
        stripped = line.strip()
        if not stripped:
            continue
        match = _MD_HEADING.match(stripped)
        if match:
            out.append((start, "", match.group(2).strip(), len(match.group(1))))
            continue
        match = _NUM_HEADING.match(stripped)
        if match:
            number = match.group(1)
            out.append((start, number, match.group(2).strip(), number.count(".") + 1))
    return out


def _detect_cn_list(text: str) -> list[tuple[int, str, str, int]]:
    out: list[tuple[int, str, str, int]] = []
    for start, line in _iter_lines(text):
        stripped = line.strip()
        if not stripped:
            continue
        match = _CN_LIST.match(stripped)
        if match:
            out.append((start, f"（{match.group(1)}）", match.group(2).strip(), 2))
    return out


def _build_spans(
    doc: ParsedDocument, headings: list[tuple[int, str, str, int]]
) -> list[ClauseSpan]:
    """把标题位置变成「从本标题到下一个标题」的条款块。"""
    spans: list[ClauseSpan] = []
    text = doc.text

    # 第一个标题之前的内容作为「前言」
    first_start = headings[0][0]
    if first_start > 0:
        intro = text[:first_start].strip()
        if intro:
            spans.append(
                ClauseSpan(
                    clause_no="前言",
                    title="前言",
                    content=intro,
                    level=1,
                    parent_no="",
                    char_start=0,
                    char_end=first_start,
                    page_no=doc.page_no_at(0),
                )
            )

    current_chapter = ""
    for index, (start, number, title, level) in enumerate(headings):
        end = headings[index + 1][0] if index + 1 < len(headings) else len(text)
        block = text[start:end].strip()
        if not block:
            continue

        if level == 1:
            current_chapter = number

        spans.append(
            ClauseSpan(
                clause_no=number,
                title=(title or number)[:MAX_TITLE_LEN],
                content=block,
                level=level,
                parent_no=current_chapter if level > 1 else "",
                char_start=start,
                char_end=end,
                page_no=doc.page_no_at(start),
            )
        )

    return spans


def _fallback_chunks(doc: ParsedDocument) -> list[ClauseSpan]:
    """没有识别到任何结构时，按固定长度切块（带重叠）。"""
    text = doc.text
    spans: list[ClauseSpan] = []
    start = 0
    index = 1

    while start < len(text):
        end = min(start + FALLBACK_SIZE, len(text))
        chunk = text[start:end].strip()
        if chunk:
            spans.append(
                ClauseSpan(
                    clause_no=f"段落{index}",
                    title="",
                    content=chunk,
                    level=1,
                    parent_no="",
                    char_start=start,
                    char_end=end,
                    page_no=doc.page_no_at(start),
                )
            )
            index += 1
        if end >= len(text):
            break
        start = end - FALLBACK_OVERLAP

    return spans
