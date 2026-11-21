# recall.py —— 召回

import re
from datetime import datetime, date

from decay import decayed_weight, effective_half_life
from embed import rank_by_similarity, EMBED_TOP_K


def _as_date(v):
    """把 'YYYY-MM-DD' 字符串或 datetime/date 转成 date；失败返回 None。"""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _memory_age_days(m, now):
    """返回「这条记忆讲的事件距 now 多少天」。

    取值顺序（先准后糙）：
      1. event_time —— 事件发生的逻辑日期，最准
      2. story_time —— 这条记忆在剧情里被记下来的那天（回放时的 now）。没有 event_time
         的条目（六库实测 70.3%）靠它才有区分度；created_at 是灌历史那一刻的墙钟
         （2026-11-09），与题目虚拟日期 now（2026-03~09）对不上，算出来恒为负。
      3. created_at —— 只在前两者都缺时兜底（真实对话里它就是准的）
    """
    ref = _as_date(now)
    if ref is None:
        ref = datetime.now().date()

    et_d = _as_date(m.get("event_time"))
    if et_d is not None:
        return (ref - et_d).days

    st_d = _as_date(m.get("story_time"))
    if st_d is not None:
        return (ref - st_d).days

    # 兜底：用 created_at（秒级时间戳），转成日期再算天数
    try:
        ca_d = datetime.fromtimestamp(m.get("created_at", 0)).date()
        return (ref - ca_d).days
    except (TypeError, OSError, ValueError):
        return 0


def _expand_conflicts(selected, pool, max_extra=None):
    """
    把「两说未定」的矛盾对成对召回：selected 里命中任一方，自动带上「仍存活」的
    另一方（从 pool 里按 (text, created_at) 找到）。

    pool 是「已过滤掉墓碑」的全部存活记忆；selected 是当前要返回的一小撮
    （可能因为 limit 或排序被砍掉了矛盾对的另一方）。矛盾对的另一方若已被删
    （不在 pool 里），说明矛盾已解决，不带。

    max_extra : 最多补几条，防止一个大的「矛盾簇」把召回块撑爆。
                不传就不限（老行为）。真实库里最大的簇是 6 条（卷卷猫粮），
                若 top8 里落进两个锚点，一次能补出 4 条——提示词会涨 50%，所以
                recall() 里传 len(top) 作上限，最多翻一倍。
    """
    by_key = {(m.get("text"), m.get("created_at")): m for m in pool}
    out = list(selected)
    seen = {(m.get("text"), m.get("created_at")) for m in out}
    added = 0
    for m in selected:
        for ref in m.get("conflicts_with", []):
            if max_extra is not None and added >= max_extra:
                return out
            key = (ref.get("text"), ref.get("created_at"))
            if key in by_key and key not in seen:
                out.append(by_key[key])
                seen.add(key)
                added += 1
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
        按权重排序后的前 limit 条（矛盾对的另一方会额外补在后面，故可能多于 limit）
    """
    # 先过滤掉已失效（墓碑）的记忆
    alive = [m for m in items if not m.get("deleted")]

    # 1. 给每条记忆算权重，存进 (权重, 记忆) 的列表
    scored = []
    for m in alive:
        # 事件距 now 多少天。未来事件（event_time 晚于 now，如「下周三的计划」）
        # 年龄为负，衰减公式 0.5**(负值) 会把它抬成 >1 的异常高权重，这里钳到 0
        # （未来事件还没「变旧」，不该被衰减，也不该被反向加权）。
        age = max(_memory_age_days(m, now), 0)
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

    # 3. 取前 limit 条
    top = [m for w, m in scored][:limit]

    # 4. 矛盾对成对召回：命中一方，补上「仍存活」的另一方。
    #    必须在 limit 之后扩：先扩再取前 limit，配对占两个名额、反而把别的挤掉；
    #    而且原写法 _expand_conflicts(alive, alive) 传同一个列表，seen 已含全部，
    #    是空操作——注释说的「先扩再排序」从来没发生过。
    #    扩的池子是「全部存活记忆」alive，不是 top 子集：另一方权重低被 limit 砍掉时
    #    也要能找回来，这正是「两说未定」的意义。
    #    补的上限是 len(top)：真实库里最大的矛盾簇有 6 条，不限的话一次能补出好几条，
    #    召回块可能涨一倍、稀释提示词。
    return _expand_conflicts(top, alive, max_extra=len(top))

def _age_label(m, now):
    """返回这条记忆的「多久前/未来」文字标签。

    未来事件（event_time 晚于 now，如「下周三的计划」）不该显示成「刚刚」，
    而是「N天后」；过去事件显示「刚刚 / N天前」。
    """
    age = _memory_age_days(m, now)
    if age > 0:
        return "刚刚" if age < 1 else f"{int(age)}天前"
    if age < 0:
        return "未来" if age > -1 else f"{-int(age)}天后"
    return "今天"


def _line_text(m):
    """渲染一条记忆进提示词：正文 + （可选）推算的绝对日期标注。

    date_kind=derived 时标「≈YYYY-MM-DD（由相对时间推算）」，提醒模型这是推导的；
    explicit 不额外标注（原文就是日期）；none 不标。
    """
    text = m["text"]
    dk = m.get("date_kind")
    et = m.get("event_time")
    if dk == "derived" and et:
        return f"{text}（≈{et}，由相对时间推算）"
    return text


def _split_zones(items):
    """把记忆分进四个区：事实 / 猜测 / 第三方 / 我说过的话。

    抽成独立函数，是为了让调用方（如 index.semantic_recall_block）能问一句
    「这条到底会不会被渲染出来」——以前它抽不出来，于是给一批根本不会显示
    的 0.4 置信度猜测也加了 hits。

    分区判据（与设计定稿 6.x 一致）：
    - 事实区：confidence >= 0.8 且 subject != about_self（不看来源：
      her_inference 升到 0.9 视为「已被验证」，进事实区）
    - 第三方转述：source == third_party（默认 0.5，进不了事实区）
    - 我说过的话：subject == about_self（不设置信度门槛，AI 自己的话是确定的）
    - 猜测区：her_inference 且 0.6 <= confidence < 0.8
    - 都不满足的：返回的四个列表里都没有 → 渲染时被静默丢弃

    注意「四区都不进」是有意为之：< 0.6 的猜测从没被验证过，放进提示词只会引导
    AI 顺着没把握的猜测编造。
    """
    facts = [m for m in items
             if m.get("confidence", 0.5) >= 0.8
             and m.get("subject") != "about_self"]
    third_party = [m for m in items if m.get("source") == "third_party"]
    self_said = [m for m in items if m.get("subject") == "about_self"]
    guesses = [m for m in items
               if m.get("source") == "her_inference"
               and 0.6 <= m.get("confidence", 0.5) < 0.8]
    return facts, guesses, third_party, self_said


def is_rendered(m):
    """这条记忆会不会出现在 format_recall_block 的输出里。

    index.semantic_recall_block 用它做「用进废退」的过滤：只有真正被渲染进提示词、
    真的被「想起来」的记忆才该 hits +1。否则给一条永远不显示的 0.4 猜测加 hits，
    只是把它的半衰期拉长、权重抬高，却在召回里一次都不出现——权重被白白消耗。
    """
    facts, guesses, third_party, self_said = _split_zones([m])
    return bool(facts or guesses or third_party or self_said)


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
    facts, guesses, third_party, self_said = _split_zones(items)

    parts = []
    if facts:
        # 矛盾对标「两说未定」，让模型别擅自只选一版、要两版都提并说明不确定
        fact_keys = {(m.get("text"), m.get("created_at")) for m in facts}
        lines = "\n".join(
            f"- {_line_text(m)}" + ("  ⚠️两说未定" if _is_conflict_member(m, fact_keys) else "")
            for m in facts
        )
        parts.append(f"关于他的事实（他说过的，可以当真）：\n{lines}")

    if guesses:
        guess_keys = {(m.get("text"), m.get("created_at")) for m in guesses}
        lines = "\n".join(
            f"- {_line_text(m)}" + ("  ⚠️两说未定" if _is_conflict_member(m, guess_keys) else "")
            for m in guesses
        )
        parts.append(f"你的猜测（不是他说的，别当事实讲）：\n{lines}")

    if third_party:
        tp_keys = {(m.get("text"), m.get("created_at")) for m in third_party}
        lines = "\n".join(
            f"- {_line_text(m)}" + ("  ⚠️两说未定" if _is_conflict_member(m, tp_keys) else "")
            for m in third_party
        )
        parts.append(f"第三方转述/书面信息（不是他亲口说的，别算到他头上）：\n{lines}")

    if self_said:
        self_keys = {(m.get("text"), m.get("created_at")) for m in self_said}
        lines = "\n".join(
            f"- {_line_text(m)}" + ("  ⚠️两说未定" if _is_conflict_member(m, self_keys) else "")
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
    alive = [m for m in items if not m.get("deleted")]
    items = alive
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
        # 算这条记忆大概「多久前」或「未来多久」的，帮模型判断「近不近」。
        # 用 _memory_age_days 统一按 event_time（事件逻辑日期）算，基准里
        # created_at 是真实墙钟、和题目虚拟日期对不上，这里已一并修掉。
        age_text = _age_label(m, now)
        lines.append(f"{i}. {_line_text(m)}（{age_text}）")
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
    # pool 必须用「全部存活记忆」alive，不能用 items——有 embedder 时 items 已被
    # 向量粗筛成 top100 子集，另一方不在 top100 里就永远扩不进来。
    # alive 里已过滤墓碑，另一方被删了就不会带。
    return _expand_conflicts(related, alive)