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
              subject="about_user", kind=None, occurrences=1,
              event_time=None, topic=None,
              who=None, what=None, value=None, tier=None):
    """
    创建一条记忆条目（返回一个字典）。

    参数：
        ...（原有参数不变）
        occurrences : 在对话里反复出现的次数（默认 1，即第一次出现）
        event_time  : 可选。这条记忆描述的「事件发生的逻辑日期」字符串
                      （如 "2026-05-25"）。与 created_at 区分：
                      - created_at = 这条记忆「什么时候被记住」的（系统时间戳，用于衰减）
                      - event_time = 这条记忆「讲的是哪一天的事」的（逻辑日期，用于按日期检索/排序）
                      默认 None，老数据没有这个字段也完全兼容。
        topic       : 可选。这条记忆的「话题标签」字符串（如 "养狗"/"工作"）。
                      由模型在写入时顺带输出，用于将来「按话题缩小召回范围」。
                      现在只存不筛，先观察话题词质量；默认 None，老数据兼容。
        who         : 可选。这条记忆「涉及哪个具体的人」。约定：
                      - None = 用户本人（提炼时「他」= 对话对象，第三人称写法）
                      - 写名 = 第三方（如 "老曹"/"周宁"/"李楠"）
                      用于将来「按人物隔离」：who 不同的记忆永不判冲突、永不合并，
                      避免「周宁的护膝」和「老曹的生日」被当成同一事实（认错人）。
                      现在只存不筛，先观察模型抽取质量；默认 None，老数据兼容。
        what        : 可选。这条记忆的「事实维度」标签（如 "生日"/"住处"/"护膝放哪"）。
                      用于将来「同维度 + 同人 + 不同值 → 判冲突」，取代现在靠模型
                      猜文本语义的脆弱做法。现在只存不筛；默认 None，老数据兼容。
        value       : 可选。这条记忆的「具体值」（如 "6月9号"/"北京"/"柜子下面"）。
                      与 what 配对使用：同一 what 给出不同 value，才是「同一事实
                      的新版本」，其余都是不同事实。现在只存不筛；默认 None，兼容。
        tier        : 可选。这条记忆涉及的人的「关系等级」，四档：
                      0 = 用户本人，1 = 亲密的人，2 = 一般关系，3 = 遇到的陌生人。
                      由模型在写入时顺带判断（谁都不写 = 0 用户本人）。
                      将来用于「按关系等级物理分库」：不同档存不同文件，
                      关系亲疏还能影响记忆策略（亲密记得细、陌生一笔带过）。
                      现在只存不筛，先观察模型判断质量；默认 None，老数据兼容。

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
        "event_time": event_time,    # 事件发生的逻辑日期（可选，None=没记/不适用）
        "topic": topic,              # 话题标签（可选，None=没打标签，供将来按话题召回）
        "who": who,                  # 涉及哪个具体的人（None=用户本人，写名=第三方）
        "what": what,                # 事实维度标签（可选，None=没抽，供将来按维度判冲突）
        "value": value,              # 具体值（可选，None=没抽，与 what 配对用）
        "tier": tier,                # 关系等级 0用户/1亲密/2一般/3陌生（可选，None=未判）
        "subject": subject,
        "kind": kind,
        "occurrences": occurrences,   # 在对话里反复出现的次数
        "deleted": False,            # 是否已失效（墓碑）
        "deleted_reason": None,      # 为什么失效（如「被用户纠正」）
        "superseded_by": None,       # 被哪条新记忆推翻
        "deleted_at": None,          # 被标墓碑的时间（用于真空清理）
        "digested": False,           # 事件是否已被夜间整合「消化」过
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

    # 3. source 必须是五种之一
    if item.get("source") not in ("user_said", "her_inference", "observed", "third_party", "self_said"):
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