# conflict.py —— 检测新记忆与旧记忆的冲突（反证）

import re

def find_conflicts(llm, new_text, items):
    """
    用模型判断：new_text 和 items 里哪些「语义冲突」（如「爱吃辣」vs「不吃辣了」）。

    参数：
        llm      : 模型函数
        new_text : 新信息（用户刚说的）
        items    : 已有记忆列表

    返回：
        冲突的旧记忆列表
    """
    # 过滤掉已失效的
    items = [m for m in items if not m.get("deleted")]
    if not items:
        return []

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
        "注意：\n"
        "- 「长期习惯/嗜好」和「近期状态/行为」不是冲突，是并存：\n"
        "  旧「他爱吃辣」（长期口味）vs 新「他最近戒辣了」（近期状态）→ 不冲突，两条都对。\n"
        "  人改一个行为的原因很多（吃药忌口、口腔溃疡、养生、减肥……），\n"
        "  不等于否定过去的口味或习惯。\n"
        "- 新的话带「最近/暂时/现在/这几天/近期/这段时间」这类时间限定词时，\n"
        "  多半是状态变化，不是推翻旧偏好，不要标冲突。\n"
        "- 只有「新的话否定旧记忆本身」才冲突（如旧「他叫小鱼」vs 新「他其实叫南风」）。\n"
        "- 不相关的不列（旧「他喜欢篮球」vs 新「他不吃辣了」无关）。\n\n"
        "只输出冲突的编号（逗号分隔，比如 0,2）。没有冲突就只输出：无\n"
        "不要输出其他任何内容。"
    )

    reply = llm(prompt).strip()

    if reply == "无" or reply == "":
        return []

    # 不能只 split(",") 后判 isdigit —— 模型一旦输出全角逗号（0，1）、
    # 顿号（0、1）或带一句说明（"冲突的编号: 0"），每个片段都不是纯数字，
    # 整批冲突会被静默丢弃：旧记忆不标失效，继续当事实使用 → 「乱记」。
    # 改成用正则把回复里所有独立数字抓出来，分隔符是什么都无所谓。
    ids = []
    for token in re.findall(r"\d+", reply):
        idx = int(token)
        if 0 <= idx < len(items) and idx not in ids:
            ids.append(idx)

    return [items[i] for i in ids]