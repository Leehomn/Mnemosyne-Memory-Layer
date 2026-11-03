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

    lines = "\n".join(f"{i}. {m['text']}" for i, m in enumerate(items))

    prompt = (
        "下面是一批已有的记忆（编号从 0 开始）。用户现在说了一句新的话。\n"
        "请判断：哪些旧记忆和新的话「语义冲突」——也就是新的话推翻了、或和旧记忆矛盾。\n\n"
        "旧记忆：\n" + lines + "\n\n"
        "新的话：「" + new_text + "」\n\n"
        "注意：\n"
        "- 只有「真正矛盾/推翻」才算冲突（比如旧「他爱吃辣」vs 新「他不吃辣了」）。\n"
        "- 不冲突的不要列出来（比如旧「他喜欢篮球」vs 新「他不吃辣了」无关，不算）。\n\n"
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