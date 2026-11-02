# recall.py —— 召回

from decay import decayed_weight, days_since, effective_half_life


def recall_by_hits(items, limit=8):
    """
    按「被想起次数 hits」从高到低，挑出前 limit 条。

    参数：
        items : 记忆列表
        limit : 最多返回几条

    返回：
        排序后的前 limit 条
    """
    sorted_items = sorted(items, key=lambda x: x.get("hits", 0), reverse=True)
    return sorted_items[:limit]


def recall(items, limit=8, now=None):
    """
    按「权重」从高到低，挑出最重要的前 limit 条。

    参数：
        items : 记忆列表
        limit : 最多返回几条
        now   : 当前时间（不传就用系统现在）

    返回：
        按权重排序后的前 limit 条
    """
    # 先过滤掉已失效（墓碑）的记忆
    items = [m for m in items if not m.get("deleted")]

    # 1. 给每条记忆算权重，存进 (权重, 记忆) 的列表
    scored = []
    for m in items:
        age = days_since(m.get("created_at", 0), now)
        # 间隔重复：先算「被复习后变长的半衰期」，再用于衰减
        hl = effective_half_life(m.get("half_life", 14), m.get("hits", 0))
        w = decayed_weight(
            m.get("base_weight", 1.0),
            hl,
            m.get("hits", 0),
            m.get("confidence", 0.5),
            age,
        )
        scored.append((w, m))

    # 2. 按权重从高到低排序
    scored.sort(key=lambda x: x[0], reverse=True)

    # 3. 只返回记忆本身，取前 limit 条
    return [m for w, m in scored][:limit]

def format_recall_block(items):
    """
    把召回的记忆，格式化成「事实区 / 猜测区」分离的文字块。

    规则：
    - 事实区：source=user_said 且置信度高，且【关于用户或我们之间】
    - 猜测区：her_inference（AI 自己推断的）
    - 关于 AI 自己的事（about_self）：不进事实区

    返回：
        一段格式化文字；没有记忆则返回空字符串
    """
    # 事实：用户说的，高置信，且不是「关于AI自己」的
    facts = [m for m in items
             if m["source"] in ("user_said", "observed")  # ← 加上 observed
             and m["confidence"] >= 0.8
             and m["subject"] != "about_self"]

    # 猜测：AI 自己推断的
    guesses = [m for m in items if m["source"] == "her_inference"]

    parts = []
    if facts:
        lines = "\n".join(f"- {m['text']}" for m in facts)
        parts.append(f"（关于他的事实（他说过的，可以当真）：\n{lines}")

    if guesses:
        lines = "\n".join(f"- {m['text']}" for m in guesses)
        parts.append(f"你的猜测（不是他说的，别当事实讲）：\n{lines}")

    if not parts:
        return ""

    return "\n\n".join(parts) + "\n\n用法：聊到相关再说，别主动复述。）"

def semantic_recall(llm, items, query):
    """
    用模型综合判断：items 里哪些和 query 相关（含时间远近、含反义/过时）。

    参数：
        llm   : 模型函数
        items : 记忆列表
        query : 当前对话（用户这句话）

    返回：
        相关的记忆列表（可能为空）
    """
    # 先过滤掉已失效（墓碑）的记忆
    items = [m for m in items if not m.get("deleted")]
    if not items:
        return []

    # 1. 把记忆编号 + 时间一起列出来
    lines = []
    for i, m in enumerate(items):
        # 算这条记忆大概「几天前」的，帮模型判断「近不近」
        import time as _time
        age_days = (_time.time() - m.get("created_at", 0)) / 86400
        if age_days < 0:
            age_days = 0
        age_text = "刚刚" if age_days < 1 else f"{int(age_days)}天前"
        lines.append(f"{i}. {m['text']}（{age_text}）")
    lines_str = "\n".join(lines)

    # 2. 拼提示词
    prompt = (
        "下面是一批记忆（编号从 0 开始，括号里是多久之前记的）。"
        "请判断哪些和「当前这句话」真正相关。\n\n"
        "记忆：\n" + lines_str + "\n\n"
        "当前这句话：「" + query + "」\n\n"
        "判断时注意：\n"
        "- 相关 = 语义上真正有关（不要只看字面重合）。\n"
        "- 尤其注意「反义/过时」：比如记忆是「他爱吃辣」，但现在说「他不吃辣了」，"
        "那么旧记忆「他爱吃辣」已过时，不要当作相关召回。\n"
        "- 时间近的优先于时间远的。\n\n"
        "只输出相关的编号（用逗号分隔，比如 0,2）。没有真正相关的就只输出一个词：无\n"
        "不要输出任何其他内容，不要解释。"
    )

    # 3. 调模型
    reply = llm(prompt).strip()

    # 4. 解析编号
    if reply == "无" or reply == "":
        return []

    ids = []
    for part in reply.split(","):
        part = part.strip()
        if part.isdigit():
            idx = int(part)
            if 0 <= idx < len(items):
                ids.append(idx)

    return [items[i] for i in ids]