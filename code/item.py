# item.py —— 记忆条目的数据结构与校验

import time

# 各层的默认半衰期（天）
HALF_LIVES = {
    "episode": 14,          # 事件：两周
    "impression": 90,       # 印象：三个月（默认，未分 kind 时）
    "relationship": 3650,   # 关系：约十年，几乎不衰减
}

# 印象内部的半衰期（按 kind 细分）
IMPRESSION_HALF_LIVES = {
    "trait": 3650,          # 稳定内核（他是谁）：近乎永久
    "state": 60,            # 动态表现（他最近怎样）：两个月减半
}


def make_item(text, source, confidence, layer="episode", hits=0,
              base_weight=1.0, half_life=None, created_at=None,
              subject="about_user", kind=None, occurrences=1):
    """
    创建一条记忆条目（返回一个字典）。

    参数：
        ...（原有参数不变）
        occurrences : 在对话里反复出现的次数（默认 1，即第一次出现）

    返回：
        一个字典，代表一条记忆
    """
    if created_at is None:
        created_at = time.time()

    if half_life is None:
        if layer == "impression" and kind in IMPRESSION_HALF_LIVES:
            half_life = IMPRESSION_HALF_LIVES[kind]
        else:
            half_life = HALF_LIVES.get(layer, 14)

    item = {
        "text": text,
        "source": source,
        "confidence": confidence,
        "layer": layer,
        "hits": hits,
        "base_weight": base_weight,
        "half_life": half_life,
        "created_at": created_at,
        "subject": subject,
        "kind": kind,
        "occurrences": occurrences,   # 新增
    }
    return item


def is_valid(item):
    """
    判断一条记忆条目是否合法。
    """
    # 1. text 不能为空
    if not item.get("text"):
        return False

    # 2. confidence 必须在 0 ~ 1 之间
    conf = item.get("confidence")
    if conf is None or not (0 <= conf <= 1):
        return False

    # 3. source 必须是四种之一
    if item.get("source") not in ("user_said", "her_inference", "observed", "third_party"):
        return False

    # 4. layer 必须是三种之一
    if item.get("layer") not in ("episode", "impression", "relationship"):
        return False

    # 5. subject 必须是三种之一
    if item.get("subject") not in ("about_user", "about_self", "about_us"):
        return False

    # 6. kind 若存在，必须是 trait 或 state
    if item.get("kind") is not None and item["kind"] not in ("trait", "state"):
        return False

    # 全通过，合法
    return True