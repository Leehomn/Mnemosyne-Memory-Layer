# index.py —— 对外统一入口（Cognition 类）

import time

from item import make_item, is_valid
from store import save_items, load_items
from recall import recall, format_recall_block, semantic_recall
from source import default_confidence

# 墓碑（软删除）在库里最多躺多少天，之后被真空清理（物理删除）。
# 软删除保证「刚过期的还能找回」，真空清理保证「死人不会越堆越多」。
TOMBSTONE_RETENTION_DAYS = 90


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

    def remember(self, text, source, confidence=None, **kwargs):
        # 不传置信度 → 按来源自动取（user_said 0.9 / observed 0.8 /
        # third_party 0.5 / her_inference 0.4）。猜的东西不能和「他说的」同分。
        if confidence is None:
            confidence = default_confidence(source)
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

        # 找相似的旧记忆（只有「关于同一个人」的才能合并：
        # 「我」的事和「他」的事，哪怕字面一样也不是一条）
        for old in items:
            # 墓碑（deleted）不是活记忆，不能拿来做去重合并：
            # 否则用户改口说回一条已被推翻的话，新话会被吞进死记录里，
            # 召回时又被过滤掉，等于白说。墓碑只能被「复活」机制单独处理。
            if old.get("deleted"):
                continue
            same_subject = (old.get("subject", "about_user")
                            == item.get("subject", "about_user"))
            if same_subject and (old.get("text") == item["text"] or
                                 jaccard(old.get("text", ""), item["text"]) >= 0.5):
                # —— 增强：出现次数 +1 ——
                # 「又说了几乎一样的话」是「出现次数」该管的事，不是「被想起」。
                # hits（被想起次数）由语义召回负责 +1，这里不能碰，否则「用户重说」
                # 和「AI 想起」两件事被混成一件，晋升与用进废退的计数就都错了。
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

        注意：本方法有「副作用」——被真正召回（想起来用）的记忆，hits +1 并落库。
        这是「用进废退」的触发点：记忆被想起来就该变强（半衰期拉长、权重提高），
        而不是靠用户重复说同一句话来触发。
        """
        if self.llm is None:
            # 没传模型，退回普通召回
            return self.recall_block(limit=limit)

        items = load_items(self.path)
        related = semantic_recall(self.llm, items, query)
        # 再按权重排序取前 limit
        top = recall(related, limit=limit)

        # —— 用进废退：被真正召回的记忆，hits +1 落库 ——
        # 这里只给「被想起」的记忆 +1，和去重合并里的 occurrences 分开：
        # occurrences = 出现次数（用户说了几次），决定晋升；
        # hits       = 被想起次数（AI 主动用了它几次），决定用进废退/半衰期。
        if top:
            for m in top:
                m["hits"] = m.get("hits", 0) + 1
            save_items(items, self.path)

        return format_recall_block(top)

    def maintain(self):
        """
        维护：淘汰 + 真空清理墓碑。

        1. 衰减到阈值以下的记忆 → 软删除（标墓碑，不物理删）。
           这样「过期」也不是永久抹掉，符合「宁可漏记，不可乱记」——万一
           用户又想起它，还能靠复活机制找回。
        2. 已经躺了超过 TOMBSTONE_RETENTION_DAYS 的墓碑 → 物理删除。
           防止死人越堆越多，稀释语义召回、白花 token。

        返回：
            本次软删除（标墓碑）的条数
        """
        from decay import decayed_weight, days_since, should_forget, effective_half_life

        now = time.time()
        items = load_items(self.path)
        kept = []
        tombstoned = 0

        for m in items:
            # 已经是墓碑的，不参与衰减，只判断要不要真空清理
            if m.get("deleted"):
                deleted_at = m.get("deleted_at")
                if deleted_at is not None and \
                        (now - deleted_at) / 86400 > TOMBSTONE_RETENTION_DAYS:
                    continue  # 躺太久，物理删除
                kept.append(m)
                continue

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
                # 软删除：标墓碑，不物理删
                m["deleted"] = True
                m["deleted_reason"] = "衰减过期"
                m["deleted_at"] = now
                tombstoned += 1
            kept.append(m)

        save_items(kept, self.path)
        return tombstoned

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
                m["deleted_at"] = time.time()
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

        # 1. 筛选出「还没被消化过」的 episode（事件）
        episodes = [m for m in items
                    if m.get("layer") == "episode" and not m.get("digested")]

        if not episodes:
            return 0

        # 2. 需要 llm 才能归纳
        if self.llm is None:
            return 0

        # 3. 调 reconstruct 里的 consolidate，用 self.remember 写入
        added = _consolidate(self.llm, episodes, self.remember, kind="state")

        # 4. 记账：这批事件已消化，下次不再重复归纳。
        #    否则同一批事件每晚会「重复出现」一次，把一条印象顶成永久的 trait。
        items = load_items(self.path)
        done = {(m.get("text"), m.get("created_at")) for m in episodes}
        for m in items:
            if (m.get("text"), m.get("created_at")) in done:
                m["digested"] = True
        save_items(items, self.path)

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
                    # 不能写 deleted_reason —— 那是墓碑字段，专记「为什么失效」。
                    # 一条仍然有效的记忆挂上「验证确认」，语义就脏了（也骗过按
                    # deleted_reason 判断状态的代码）。置信度变动记在独立字段。
                    m["confidence_reason"] = reason
                break
        save_items(items, self.path)
        return item

    def _all_items(self):
        """读库，返回所有记忆（内部用）。"""
        return load_items(self.path)
