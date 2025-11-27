"""
文档去重工具

基于内容相似度的多级去重策略
"""

import hashlib
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Set

from loguru import logger


def _normalize_text(text: str) -> str:
    """
    文本标准化：去除HTML/Markdown标签、标点、多余空格等（私有辅助函数）

    用于后续的哈希计算和相似度比对
    """
    if not text:
        return ""

    # 移除HTML标签
    text = re.sub(r"<[^>]+>", "", text)
    # 移除Markdown标题标记
    text = re.sub(r"^#+\s+", "", text, flags=re.MULTILINE)
    # 移除Markdown链接
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # 转小写
    text = text.lower()
    # 折叠多余空白符
    text = re.sub(r"\s+", " ", text)
    # 只保留中英文、数字
    text = re.sub(r"[^\w\u4e00-\u9fa5]+", "", text)

    return text.strip()


def _compute_strong_hash(text: str) -> str:
    """
    计算文本的强哈希值（SHA256）（私有辅助函数）

    用于检测完全相同的文档
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _compute_simhash(text: str, hashbits: int = 64) -> int:
    """
    计算SimHash（局部敏感哈希）（私有辅助函数）

    用于检测高度相似的文档
    算法：对文本分词后，使用每个词的hash进行加权求和
    """
    if not text:
        return 0

    # 简单分词（按空格）
    tokens = text.split()
    if not tokens:
        return 0

    # 初始化特征向量
    v = [0] * hashbits

    for token in tokens:
        # 计算token的hash
        h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)

        # 对每一位进行加权
        for i in range(hashbits):
            if h & (1 << i):
                v[i] += 1
            else:
                v[i] -= 1

    # 生成SimHash指纹
    fingerprint = 0
    for i in range(hashbits):
        if v[i] > 0:
            fingerprint |= 1 << i

    return fingerprint


def _hamming_distance(hash1: int, hash2: int) -> int:
    """
    计算两个SimHash的汉明距离（私有辅助函数）
    """
    x = hash1 ^ hash2
    distance = 0
    while x:
        distance += 1
        x &= x - 1  # 清除最低位的1
    return distance


def _compute_shingles(text: str, k: int = 5) -> Set[str]:
    """
    生成k-shingles（滑动窗口字符串集合）（私有辅助函数）

    用于Jaccard相似度计算
    """
    if len(text) < k:
        return {text}

    shingles = set()
    for i in range(len(text) - k + 1):
        shingles.add(text[i : i + k])

    return shingles


def _jaccard_similarity(set1: Set[str], set2: Set[str]) -> float:
    """
    计算Jaccard相似度（私有辅助函数）
    """
    if not set1 or not set2:
        return 0.0

    intersection = len(set1 & set2)
    union = len(set1 | set2)

    return intersection / union if union > 0 else 0.0


def _should_remove_duplicate(
    doc_a: Dict[str, Any], doc_b: Dict[str, Any]
) -> Optional[int]:
    """
    判断两个文档是否重复，返回应该移除的文档ID（私有辅助函数）

    返回值：
    - None: 不重复
    - document_id: 应该移除的文档ID（保留内容更长、时间更新的）

    Args:
        doc_a: 文档A的dict，包含 normalized, strong_hash, simhash, shingles, document_id, content
        doc_b: 文档B的dict
    """
    # 阶段1: 强哈希完全相同
    if doc_a["strong_hash"] == doc_b["strong_hash"]:
        logger.debug(
            f"文档 {doc_a['document_id']} 和 {doc_b['document_id']} 强哈希相同（完全重复）"
        )
        # 保留内容更长的
        if len(doc_a["content"]) < len(doc_b["content"]):
            return doc_a["document_id"]
        else:
            return doc_b["document_id"]

    # 阶段2: SimHash汉明距离很小（高度相似）
    hamming_dist = _hamming_distance(doc_a["simhash"], doc_b["simhash"])
    if hamming_dist <= 3:  # 阈值可调
        logger.debug(
            f"文档 {doc_a['document_id']} 和 {doc_b['document_id']} SimHash距离={hamming_dist}（高度相似）"
        )
        if len(doc_a["content"]) < len(doc_b["content"]):
            return doc_a["document_id"]
        else:
            return doc_b["document_id"]

    # 阶段3: Jaccard相似度很高
    jac_sim = _jaccard_similarity(doc_a["shingles"], doc_b["shingles"])
    if jac_sim > 0.75:  # 阈值可调
        logger.debug(
            f"文档 {doc_a['document_id']} 和 {doc_b['document_id']} Jaccard={jac_sim:.3f}（内容重叠高）"
        )
        if len(doc_a["content"]) < len(doc_b["content"]):
            return doc_a["document_id"]
        else:
            return doc_b["document_id"]

    # 阶段4: 只对Jaccard在0.5-0.75之间的做精细difflib比对（避免O(n²)开销）
    if 0.5 < jac_sim <= 0.75:
        # difflib比对（较慢，只对候选执行）
        ratio = SequenceMatcher(None, doc_a["normalized"], doc_b["normalized"]).ratio()
        if ratio > 0.80:  # 阈值可调
            logger.debug(
                f"文档 {doc_a['document_id']} 和 {doc_b['document_id']} difflib={ratio:.3f}（精细比对重复）"
            )
            if len(doc_a["content"]) < len(doc_b["content"]):
                return doc_a["document_id"]
            else:
                return doc_b["document_id"]

    return None


def deduplicate_documents(documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    文档去重工具（基于内容相似度）

    使用多级去重策略：
    1. 强哈希（SHA256）- 检测完全相同
    2. SimHash - 检测高度相似
    3. Jaccard相似度 - 检测内容重叠
    4. difflib精细比对 - 最终确认

    Args:
        documents: 文档列表，每个文档必须包含 id, title, content 字段

    Returns:
        去重后的文档列表
    """
    if not documents or len(documents) <= 1:
        return documents

    logger.info(f"🗑️ 开始文档去重，原始文档数: {len(documents)}")

    # 预处理：计算所有文档的特征
    processed_docs = []
    for doc in documents:
        content = doc.get("content", "")
        if not content:
            # 没有内容的文档保留
            processed_docs.append(
                {
                    "document_id": doc.get("id") or doc.get("document_id"),
                    "original": doc,
                    "content": "",
                    "normalized": "",
                    "strong_hash": "",
                    "simhash": 0,
                    "shingles": set(),
                }
            )
            continue

        normalized = _normalize_text(content)
        processed_docs.append(
            {
                "document_id": doc.get("id") or doc.get("document_id"),
                "original": doc,
                "content": content,
                "normalized": normalized,
                "strong_hash": _compute_strong_hash(normalized),
                "simhash": _compute_simhash(normalized),
                "shingles": _compute_shingles(normalized),
            }
        )

    # 去重逻辑：两两比对
    to_remove = set()
    for i in range(len(processed_docs)):
        if processed_docs[i]["document_id"] in to_remove:
            continue

        for j in range(i + 1, len(processed_docs)):
            if processed_docs[j]["document_id"] in to_remove:
                continue

            # 判断是否重复
            dup_id = _should_remove_duplicate(processed_docs[i], processed_docs[j])
            if dup_id is not None:
                to_remove.add(dup_id)

    # 过滤掉重复文档
    result = [
        doc["original"] for doc in processed_docs if doc["document_id"] not in to_remove
    ]

    logger.info(
        f"✅ 文档去重完成: {len(documents)} -> {len(result)} 篇 (移除 {len(to_remove)} 篇重复)"
    )

    return result
