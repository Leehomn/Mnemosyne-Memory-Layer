# recall.py —— 召回

import re
from datetime import datetime

from decay import decayed_weight, days_since, effective_half_life
from embed import rank_by_similarity, EMBED_TOP_K


def _expand_conflicts(selected, pool):
    """
    把「两说未定」的矛盾对成对召回：selected 里命中任一方，自动带上「仍存活」的
    另一方（从 pool 里按 (text, created_at) 找到）。

    pool 是「已过滤掉墓碑」的全部存活记忆；selected 是当前要返回的一小撮
    （可能因为 limit 或排序被砍掉了矛盾对的另一方）。矛盾对的另一方若已被删
    （不在 pool 里），说明矛盾已解决，不带。
    """
    by_key = {(m.get("text"), m.get("created_at")): m for m in pool}
    out = list(selected)
    seen = {(m.get("text"), m.get("created_at")) for m in out}
    for m in selected:
        for ref in m.get("conflicts_with", []):
            key = (ref.get("text"), ref.get("created_at"))
            if key in by_key and key not in seen:
                out.append(by_key[key])
                seen.add(key)
    return out


def _is_conflict_member(m, result_keys):
    """
    判断 m 是否是「两说未定」矛盾对的一员：它的 conflicts_with 里有另一方，
    且另一方也在这批召回结果里（成对出现才标注，另一方被删了就不标）。
    """
    for ref in m.get("conflicts_with", []):
        if (ref.get("text"), ref.get("created_at")) in result_keys:
            return True
    return False


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
    alive = [m for m in items if not m.get("deleted")]

    # 矛盾对成对召回：命中一方带另一方，让「两说未定」一起进结果。
    # 注意：recall 的 items 只是「待选池」，先扩矛盾对再排序取前 limit，
    # 否则矛盾对另一方可能因权重低被 limit 砍掉。
    items = _expand_conflicts(alive, alive)

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
    把召回的记忆，格式化成「事实区 / 猜测区 / 我说过的话区」分离的文字块。

    规则：
    - 事实区：置信度够高（>= 0.8，即被证实），且【关于用户或我们之间】，不看来源
    - 猜测区：her_inference 且置信度中等（0.6 ~ 0.8，被验证过一部分但还没到当真）
    - 我说过的话区：subject=about_self（AI 自己说过的承诺/建议/自述），单独分区，
      明确标注「这是你之前说的，不是他的事实」——既不能被当成用户事实，也不能丢。

    返回：
        一段格式化文字；没有记忆则返回空字符串
    """
    # 事实：用户说的，高置信，且不是「关于AI自己」的
    facts = [m for m in items
             if m["confidence"] >= 0.8  # 置信度够高 = 被证实（不管来源）
             and m["subject"] != "about_self"]

    # 第三方转述：source=third_party（别人说的/书面写的）。置信 0.5，进不了事实区
    # 也进不了猜测区（那是 her_inference 专属），单独一格，标「别当用户亲口的事实」。
    # 设计定稿 5.1：third_party 必须带说话人，禁止算到对话对象头上。
    third_party = [m for m in items if m.get("source") == "third_party"]

    # 我说过的话：关于 AI 自己的（about_self），单独一区。
    # 置信度不设门槛——AI 自己说过的话是确定的（self_said 出生即 0.9），不是猜。
    self_said = [m for m in items if m.get("subject") == "about_self"]

    # 猜测：AI 自己推断的，且置信度「中等」才进猜测区。
    # 0.6 ~ 0.8：被验证过一部分、但还没到「可以当真」的程度 → 进猜测区，标「别当事实」。
    # < 0.6：出生默认 0.4、从没验证过 → 连猜测区都不进（免得顺着没把握的猜测乱编）。
    # >= 0.8：已经和事实区重叠了，这里要排除——一条被证实的猜测不能既当事实又当猜测。
    guesses = [m for m in items
               if m["source"] == "her_inference"
               and 0.6 <= m["confidence"] < 0.8]

    parts = []
    if facts:
        # 矛盾对标「两说未定」，让模型别擅自只选一版、要两版都提并说明不确定
        fact_keys = {(m.get("text"), m.get("created_at")) for m in facts}
        lines = "\n".join(
            f"- {m['text']}" + ("  ⚠️两说未定" if _is_conflict_member(m, fact_keys) else "")
            for m in facts
        )
        parts.append(f"关于他的事实（他说过的，可以当真）：\n{lines}")

    if guesses:
        guess_keys = {(m.get("text"), m.get("created_at")) for m in guesses}
        lines = "\n".join(
            f"- {m['text']}" + ("  ⚠️两说未定" if _is_conflict_member(m, guess_keys) else "")
            for m in guesses
        )
        parts.append(f"你的猜测（不是他说的，别当事实讲）：\n{lines}")

    if third_party:
        tp_keys = {(m.get("text"), m.get("created_at")) for m in third_party}
        lines = "\n".join(
            f"- {m['text']}" + ("  ⚠️两说未定" if _is_conflict_member(m, tp_keys) else "")
            for m in third_party
        )
        parts.append(f"第三方转述/书面信息（不是他亲口说的，别算到他头上）：\n{lines}")

    if self_said:
        self_keys = {(m.get("text"), m.get("created_at")) for m in self_said}
        lines = "\n".join(
            f"- {m['text']}" + ("  ⚠️两说未定" if _is_conflict_member(m, self_keys) else "")
            for m in self_said
        )
        parts.append(f"你之前说过的话（你自己说过的，不是他的事实）：\n{lines}")

    if not parts:
        return ""

    # 若这批里有矛盾对，段尾补一条明确指令：两版都要提，且不擅自定论。
    tail = ""
    if any(_is_conflict_member(m, {(x.get("text"), x.get("created_at")) for x in items})
           for m in items):
        tail = ("\n\n注意：上面标了「两说未定」的条目是彼此矛盾的两种说法，"
                "都没有被推翻。回答时两种说法都要提到，并说明目前无法确定哪个对，"
                "不要只取其中一个当定论。")

    # 原来开头是「（」、结尾补「）」又内嵌一对「（）」，括号是错配的。
    # 这段是要直接喂给模型的提示词，格式乱会削弱「事实/猜测」的分区感。
    return "\n\n".join(parts) + "\n\n用法：聊到相关再说，别主动复述。" + tail

def semantic_recall(llm, items, query, now=None, embedder=None, emb_map=None):
    """
    用模型综合判断：items 里哪些和 query 相关（含时间远近、含反义/过时）。

    参数：
        llm      : 模型函数
        items    : 记忆列表
        query    : 当前对话（用户这句话）
        now      : 今天的日期字符串（如 "2026-05-27"）。不传就用系统当前日期。
        embedder : 可选。语义向量函数 embed(text)->vector，用于粗筛。
        emb_map  : 可选。{text: vector} 缓存，配合 embedder 用。
                   传了 embedder 就先「算 query 向量 → 余弦取 top K」，再让模型细判；
                   不传则退回「全库喂模型」（老行为，向后兼容）。

    返回：
        相关的记忆列表（可能为空）
    """
    # 先过滤掉已失效（墓碑）的记忆
    items = [m for m in items if not m.get("deleted")]
    if not items:
        return []

    # 今天的日期：真实系统里就是「现在」，供模型理解查询里的相对时间词。
    # 不传就用系统当前日期——这样真实对话里用户说「前天/上周」，模型能换算。
    if now is None:
        now = datetime.now().strftime("%Y-%m-%d")

    # —— 语义粗筛：先按向量相似度取 top K，再让模型细判 ——
    # 全库几千条直接喂模型，token 爆炸（P14 实测一次召回喂 4 万字）；
    # 先算 query 向量，只留语义最相关的 EMBED_TOP_K 条，把喂给模型的量砍掉 90%+。
    # 注意：向量粗筛只做「缩小范围」，不砍「反义/过时」——「他爱吃辣」和
    # 「他不吃辣了」语义相关、向量天然接近，粗筛会保留，交给模型细判。
    if embedder is not None and emb_map is not None:
        qvec = embedder(query)
        items = rank_by_similarity(qvec, items, emb_map, limit=EMBED_TOP_K)
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
        "今天的日期是 " + now + "。\n\n"
        "判断时注意：\n"
        "- 相关 = 语义上真正有关（不要只看字面重合）。\n"
        "- 尤其注意「反义/过时」：比如记忆是「他爱吃辣」，但现在说「他不吃辣了」，"
        "那么旧记忆「他爱吃辣」已过时，不要当作相关召回。\n"
        "- 如果这句话里出现「前天/昨天/上周/下周」这类相对时间，"
        "用上面的「今天的日期」换算成绝对日期，再去记忆里找对应日期的内容。\n"
        "- 时间近的优先于时间远的。\n\n"
        "只输出相关的编号（用逗号分隔，比如 0,2）。没有真正相关的就只输出一个词：无\n"
        "不要输出任何其他内容，不要解释。"
    )

    # 3. 调模型
    reply = llm(prompt).strip()

    # 4. 解析编号
    if reply == "无" or reply == "":
        return []

    # 同 conflict.py：只认半角逗号 + 纯数字的话，模型输出全角逗号、
    # 顿号或带一句说明时整批相关性会被丢弃，等于这次召回什么都没捞到。
    ids = []
    for token in re.findall(r"\d+", reply):
        idx = int(token)
        if 0 <= idx < len(items) and idx not in ids:
            ids.append(idx)

    related = [items[i] for i in ids]
    # 矛盾对成对召回：命中一方，带上「仍存活」的另一方（两说未定一起出）。
    # pool 用已过滤墓碑的全部 items，另一方被删了就不会带。
    return _expand_conflicts(related, items)