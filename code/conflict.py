# conflict.py —— 检测新记忆与旧记忆的冲突（反证）

import re

from embed import rank_by_similarity, EMBED_TOP_K

# 冲突检测前的话题粗筛：只留「和新话字面沾边」的旧记忆，再喂给模型细判。
# 否则新话拿去和全库几千条比对，模型在超长列表里过拟合，把「狗叫瓦片」
# 和「他肩膀紧」这种完全不相关的也判成冲突（P14 实测误删 1128 条）。
# 阈值取低 + 上限取大，宁可多留不漏——漏判真冲突（旧事实继续当真）比
# 多判几条（少删几条）危险得多，呼应「宁可少删，不可乱删」。
_PRESELECT_MIN_JACCARD = 0.15   # 字面重合度门槛（很低，只砍「完全不沾边」的）
_PRESELECT_MAX_ITEMS = 50       # 最多喂给模型细判的条数


def _preselect(new_text, items):
    """
    话题粗筛：按 Jaccard 字面重合度，把 items 里和新话「完全不沾边」的砍掉，
    只留可能相关的一小撮（最多 _PRESELECT_MAX_ITEMS 条），供模型细判冲突。

    注意：这只做「第一道闸」——挡「字面完全不重合」的误删。字面沾边但
    语义反义（「爱吃辣」vs「不吃辣了」）必须留给模型细判，这里不做语义。
    """
    scored = []
    for m in items:
        # 字符级重合：把两句话拆成字符集合算 Jaccard。
        a = set(new_text)
        b = set(m.get("text", ""))
        if not a or not b:
            jac = 0.0
        else:
            jac = len(a & b) / len(a | b)
        scored.append((jac, m))

    # 重合度 >= 门槛的才留；全部按重合度从高到低排，取前 N 条
    scored = [(j, m) for j, m in scored if j >= _PRESELECT_MIN_JACCARD]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for j, m in scored[:_PRESELECT_MAX_ITEMS]]


def _ids_in(segment, n):
    """从一段文字里抓出所有合法编号（0 ~ n-1），去重、越界忽略。"""
    ids = []
    for token in re.findall(r"\d+", segment):
        idx = int(token)
        if 0 <= idx < n and idx not in ids:
            ids.append(idx)
    return ids


def _parse_conflict_reply(reply, n):
    """
    解析 find_conflicts 的模型回复，返回 (superseded_ids, contradiction_ids)。

    模型输出两个区段：
        推翻：0,2   ← 明确纠错，旧版删
        矛盾：1     ← 无信号同维度不同值，两版都留

    健壮性：
    - 只有「推翻」段 → 矛盾为空；只有「矛盾」段 → 推翻为空。
    - 完全认不出分段（纯数字 / 乱格式）→ 默认全部按「矛盾」处理（都不删）。
      理由：宁可漏删，不可乱删。删错的代价（「没解释的矛盾」继续崩 + 假记忆）
      远大于多标几条矛盾对（可被后续明确纠错收敛）。
    """
    superseded = []
    contradictions = []

    if not reply:
        return superseded, contradictions

    text = reply.strip()
    if text == "无":
        return superseded, contradictions

    has_sup = "推翻" in text
    has_con = "矛盾" in text

    if not has_sup and not has_con:
        # 认不出分段 → 默认全矛盾（不删）
        return superseded, _ids_in(text, n)

    # 按关键词切段：每个关键词取「它出现处」到「下一个关键词出现处」之间
    positions = []
    for kw in ("推翻", "矛盾"):
        idx = text.find(kw)
        if idx >= 0:
            positions.append((idx, kw))
    positions.sort()

    segments = {}
    for i, (idx, kw) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        segments[kw] = text[idx:end]

    if "推翻" in segments:
        superseded = _ids_in(segments["推翻"], n)
    if "矛盾" in segments:
        contradictions = _ids_in(segments["矛盾"], n)

    return superseded, contradictions


def find_conflicts(llm, new_text, items, embedder=None, emb_map=None):
    """
    用模型判断：new_text 和 items 里哪些「语义冲突」（如「爱吃辣」vs「不吃辣了」）。

    参数：
        llm      : 模型函数
        new_text : 新信息（用户刚说的）
        items    : 已有记忆列表
        embedder : 可选。语义向量函数 embed(text)->vector，用于冲突前的粗筛。
        emb_map  : 可选。{text: vector} 缓存，配合 embedder 用。
                   传了 embedder 就先「算 new_text 向量 → 余弦取 top K」，
                   再让模型细判；不传则退回字面 Jaccard 粗筛（向后兼容）。

    返回：
        (superseded, contradictions) 两个旧记忆列表：
        - superseded    : 被新话「明确纠错」推翻的旧记忆（调用方应标墓碑删掉）
        - contradictions: 和新话「无信号同维度不同值」的旧记忆（两版都留，标 conflicts_with）
    """
    # 过滤掉已失效的
    items = [m for m in items if not m.get("deleted")]
    if not items:
        return [], []

    # —— 话题约束（写入侧）：先粗筛，只留和新话可能相关的旧记忆 ——
    # 否则「狗叫瓦片」这种新话会拿去和「他肩膀紧」等全库几千条比对，
    # 模型过拟合乱判冲突、误删大量无关记忆（见模块顶部注释）。
    # 有两种粗筛：
    #  1. 语义向量（embedder + emb_map 都传了）：按余弦取 top K，最准；
    #  2. 字面 Jaccard（老行为）：只挡「字面完全不沾边」的，语义反义要留给模型。
    if embedder is not None and emb_map is not None:
        qvec = embedder(new_text)
        items = rank_by_similarity(qvec, items, emb_map, limit=EMBED_TOP_K)
    else:
        items = _preselect(new_text, items)
    if not items:
        return [], []

    # 每条旧记忆后面标注它的「性质」，让模型区分「长期习惯」和「近期状态」。
    # trait = 稳定内核/长期嗜好习惯（近乎永久）；state = 动态表现/近期状态（会变）。
    # 没有 kind 的旧记忆（多为 episode 事件）标「未分类」。
    def _kind_label(m):
        k = m.get("kind")
        if k == "trait":
            return "长期习惯/嗜好"
        if k == "state":
            return "近期状态/行为"
        return "未分类"

    lines = "\n".join(
        f"{i}. {m['text']}（{_kind_label(m)}）" for i, m in enumerate(items)
    )

    prompt = (
        "下面是一批已有的记忆（编号从 0 开始，每条后标注了它的性质）。"
        "用户现在说了一句新的话。\n"
        "请判断：哪些旧记忆和新的话「真正推翻/矛盾」——也就是新的话否定了旧记忆本身的真实性。\n\n"
        "旧记忆：\n" + lines + "\n\n"
        "新的话：「" + new_text + "」\n\n"
        "【总原则：默认不删，宁可少删，不可乱删】\n"
        "删掉一条旧记忆，等于让用户「明明说过的话」消失，是不可逆的伤害。\n"
        "所以：拿不准时一律不删、不判矛盾。你要把结果分成两类输出：\n\n"
        "【推翻】（真正要删的旧记忆）只有一种：\n"
        "  新话带了明确纠错信号（其实不是/我记错了/改过来了/之前说错了/说岔了/更正），\n"
        "  明确否定了旧记忆本身的真实性。这类旧记忆的编号写进「推翻」段。\n\n"
        "【矛盾】（不删，但两说未定）只有一种：\n"
        "  新话没有明确纠错信号，只是对「同一个事实维度」给出了「不同的答案」\n"
        "  （如旧「生日六月九号」vs 新「生日其实是九月二十」——但后者没有「我记错了」这类词）。\n"
        "  这种情况两版都要保留，旧记忆的编号写进「矛盾」段，不能写进「推翻」段。\n\n"
        "除此之外——概括、细化、压缩、换个说法、补充一个侧面、事后补句感慨、\n"
        "状态变化（最近/暂时/这几天）、围绕同一件事做了别的动作——都不算推翻也不算矛盾，\n"
        "两个段都别列。\n\n"
        "注意：\n"
        "- 「长期习惯/嗜好」和「近期状态/行为」不是推翻也不是矛盾，是并存：\n"
        "  旧「他爱吃辣」（长期口味）vs 新「他最近戒辣了」（近期状态）→ 两个段都别列，两条都对。\n"
        "  人改一个行为的原因很多（吃药忌口、口腔溃疡、养生、减肥……），\n"
        "  不等于否定过去的口味或习惯。\n"
        "- 新的话带「最近/暂时/现在/这几天/近期/这段时间」这类时间限定词时，\n"
        "  多半是状态变化，不是推翻旧偏好，两个段都别列。\n"
        "- 只有「新的话否定旧记忆本身」才进推翻；只有「同维度不同值且无纠错信号」才进矛盾。\n"
        "- 不相关的不列（旧「他喜欢篮球」vs 新「他不吃辣了」无关）。\n"
        "- 【不同事实维度不算推翻也不算矛盾】『一件事的日期是多少』和『围绕这件事当天做了什么』\n"
        "  是两个维度，后者不否定前者。新话只是『提到』某件事、围绕它做了什么、\n"
        "  事后补了句感慨，都不等于否定那件事本身。\n"
        "  例：旧「老曹生日是六月九号」vs 新「老曹生日那天我发了条消息」→ 两段都别列，\n"
        "  因为新话没说『生日不是六月九号』，只是说了当天的一个行为。\n"
        "  判断标准：新话是否给出了『同一个事实维度』的『不同答案』。\n"
        "  「生日是哪天」这个维度的不同答案，只能是另一个『月日』（如『其实是9月20』）。\n"
        "  「生日那天我做了什么」是另一个维度，它给的『2026-06-16』是事件日期，\n"
        "  不是『生日是哪天』的答案，不能用来推翻『六月九号』。\n"
        "- 【概括/细化/从属不算推翻也不算矛盾】新话是旧记忆的概括、压缩、一个侧面或从属细节时，\n"
        "  两段都别列，两条可以并存。\n"
        "  例：旧「3-23 他肩膀发紧、脑子木」vs 新「这两天他肩膀有点发紧」→ 两段都别列，\n"
        "  新话只是旧记忆的概括，没否定旧记忆里更具体的细节。\n"
        "  例：旧「他构思怀表故事、齿轮反着走」vs 新「阿拓可能是和他同住的人/宠物」→ 两段都别列，\n"
        "  后者是前者的一个侧面/从属信息，不矛盾。\n\n"
        "严格按下面两行格式输出（没有某类就写「无」）：\n"
        "推翻：<编号，逗号分隔；没有就写 无>\n"
        "矛盾：<编号，逗号分隔；没有就写 无>\n"
        "不要输出其他任何内容。"
    )

    reply = llm(prompt).strip()

    superseded_ids, contradiction_ids = _parse_conflict_reply(reply, len(items))
    superseded = [items[i] for i in superseded_ids]
    contradictions = [items[i] for i in contradiction_ids]
    return superseded, contradictions