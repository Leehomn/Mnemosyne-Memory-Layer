# index.py —— 对外统一入口（Cognition 类）

from item import make_item, is_valid
from store import save_items, load_items
from recall import recall, format_recall_block, semantic_recall


def jaccard(text1, text2):
    """
    算两段文字的 Jaccard 相似度（0~1，越大越相似）。
    """
    words1 = set(text1)
    words2 = set(text2)
    if not words1 and not words2:
        return 1.0
    return len(words1 & words2) / len(words1 | words2)


class Cognition:
    """
    认知记忆系统的统一入口。

    用法：
        cog = Cognition(data_dir="data", llm=某个模型函数)
        cog.remember("我叫南风", source="user_said")
        block = cog.recall_block(limit=8)
        block = cog.semantic_recall_block("我今天去面试", limit=8)  # 语义召回
        cog.maintain()
    """

    def __init__(self, data_dir="data", llm=None):
        """
        初始化：指定数据目录，可选传入模型函数（用于语义召回）。
        """
        self.data_dir = data_dir
        self.path = data_dir.rstrip("/") + "/items.json"
        self.llm = llm

    def remember(self, text, source, confidence=0.9, **kwargs):
        item = make_item(text, source, confidence, **kwargs)
        if not is_valid(item):
            return None

        items = load_items(self.path)

        # —— 反证检测：新记忆和旧记忆冲突时，把旧的标失效 ——
        if self.llm is not None and items:
            from conflict import find_conflicts
            conflicts = find_conflicts(self.llm, text, items)
            for old in conflicts:
                self.mark_deleted(old, reason="被新信息推翻", superseded_by=text)

        # 重新读库（因为 mark_deleted 已经改过库）
        items = load_items(self.path)

        # 找相似的旧记忆
        for old in items:
            if old.get("text") == item["text"] or \
                    jaccard(old.get("text", ""), item["text"]) >= 0.5:
                # —— 增强：出现次数 +1 ——
                old["occurrences"] = old.get("occurrences", 1) + 1

                # —— 价值重估：取更高（只升不降）——
                if confidence > old.get("confidence", 0):
                    old["confidence"] = confidence
                new_bw = kwargs.get("base_weight")
                if new_bw is not None and new_bw > old.get("base_weight", 0):
                    old["base_weight"] = new_bw

                # —— 晋升判断：state 反复出现够多 → 升 trait ——
                if (old.get("layer") == "impression"
                        and old.get("kind") == "state"
                        and old["occurrences"] >= 3):
                    old["kind"] = "trait"
                    old["half_life"] = 3650

                save_items(items, self.path)
                return old

        # 没找到相似 → 新增
        items.append(item)
        save_items(items, self.path)
        return item

    def recall_block(self, limit=8):
        """
        召回（按权重）并格式化成文字块。
        """
        items = load_items(self.path)
        top = recall(items, limit=limit)
        return format_recall_block(top)

    def semantic_recall_block(self, query, limit=8):
        """
        语义召回：用模型判断哪些记忆和 query 相关，再格式化。

        参数：
            query : 当前对话（用户这句话）
            limit : 最多召回几条

        返回：
            格式化文字；没有相关记忆返回 ""
        """
        if self.llm is None:
            # 没传模型，退回普通召回
            return self.recall_block(limit=limit)

        items = load_items(self.path)
        related = semantic_recall(self.llm, items, query)
        # 再按权重排序取前 limit
        top = recall(related, limit=limit)
        return format_recall_block(top)

    def maintain(self):
        """
        维护：淘汰权重低于遗忘阈值的记忆。
        """
        from decay import decayed_weight, days_since, should_forget, effective_half_life

        items = load_items(self.path)
        kept = []

        for m in items:
            age = days_since(m.get("created_at", 0))
            hl = effective_half_life(m.get("half_life", 14), m.get("hits", 0))
            w = decayed_weight(
                m.get("base_weight", 1.0),
                hl,
                m.get("hits", 0),
                m.get("confidence", 0.5),
                age,
            )
            if should_forget(w):
                continue
            kept.append(m)

        removed = len(items) - len(kept)
        save_items(kept, self.path)
        return removed

    def mark_deleted(self, old_item, reason, superseded_by=None):
        """
        把一条旧记忆标记为「失效」（墓碑，不物理删除）。

        返回：
            更新后的记忆
        """
        items = load_items(self.path)
        for m in items:
            if m.get("text") == old_item.get("text") and m.get("created_at") == old_item.get("created_at"):
                m["deleted"] = True
                m["deleted_reason"] = reason
                m["superseded_by"] = superseded_by
                break
        save_items(items, self.path)
        return old_item

    def consolidate(self):
        """
        夜间整合：自动读库，把 episode 归纳成 impression。

        返回：
            新增的印象条数
        """
        from reconstruct import consolidate as _consolidate

        items = load_items(self.path)

        # 1. 筛选出所有 episode（事件）
        episodes = [m for m in items if m.get("layer") == "episode"]

        if not episodes:
            return 0

        # 2. 需要 llm 才能归纳
        if self.llm is None:
            return 0

        # 3. 调 reconstruct 里的 consolidate，用 self.remember 写入
        added = _consolidate(self.llm, episodes, self.remember)
        return added

    def update_confidence(self, item, new_confidence, reason=None):
        """
        更新一条记忆的置信度（验证确认→升，否认→降）。

        返回：
            更新后的记忆
        """
        items = load_items(self.path)
        for m in items:
            if m.get("text") == item.get("text") and m.get("created_at") == item.get("created_at"):
                m["confidence"] = max(0.0, min(1.0, new_confidence))
                if reason:
                    m["deleted_reason"] = reason
                break
        save_items(items, self.path)
        return item

    def _all_items(self):
        """读库，返回所有记忆（内部用）。"""
        return load_items(self.path)
