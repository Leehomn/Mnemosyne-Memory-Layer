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
              subject="about_user", kind=None):
    """
    创建一条记忆条目（返回一个字典）。

    参数：
        text       : 记忆内容（一句话）
        source     : 来源（user_said / her_inference / observed / third_party）
        confidence : 置信度（0 ~ 1）
        layer      : 类型（episode / impression / relationship），默认 episode
        hits       : 被想起次数，默认 0
        base_weight: 初始权重，默认 1.0
        half_life  : 半衰期（天）。不传则按 layer 自动取
        created_at : 创建时间戳（秒），默认当前时间
        subject    : 关于谁（about_user / about_self / about_us），默认 about_user
        kind       : 印象的子类型（trait / state），仅 layer=impression 时有意义

    返回：
        一个字典，代表一条记忆
    """
    if created_at is None:
        created_at = time.time()

    # 没传 half_life → 自动取
    if half_life is None:
        if layer == "impression" and kind in IMPRESSION_HALF_LIVES:
            # 印象：按 kind 细分半衰期（trait 近乎永久，state 两个月）
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