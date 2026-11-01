# reconstruct.py —— 事后重构（把对话提炼成认识）

def parse_reply(reply):
    """
    解析模型的回答，提取 [事实]/[猜测] 条目。

    参数：
        reply : 模型的回答文本

    返回：
        一个列表，每项是 {"text": ..., "source": ...}
    """
    items = []

    for line in reply.split("\n"):
        line = line.strip()

        # 容错：剥掉行首可能的 "- " 或 "* " 或 "• "（模型可能照抄示例格式）
        for mark in ("- ", "* ", "• "):
            if line.startswith(mark):
                line = line[len(mark):]
                break

        if line.startswith("[事实]"):
            text = line.replace("[事实]", "", 1).strip()
            if text:
                items.append({"text": text, "source": "user_said"})

        elif line.startswith("[猜测]"):
            text = line.replace("[猜测]", "", 1).strip()
            if text:
                items.append({"text": text, "source": "her_inference"})

        # 其他行（没有前缀的）→ 丢弃（防止模型乱写）

    return items


def reconstruct(llm, buffer, remember_func):
    """
    事后重构：把一段对话提炼成新认识，写入记忆库。

    参数：
        llm           : 模型函数（给它提示词，返回回答）—— 真模型或 mock 都行
        buffer        : 对话列表（一堆字符串）
        remember_func : 写记忆的函数（通常是 cog.remember）

    返回：
        新增的记忆条数
    """
    # 1. 拼提示词
    prompt = (
            "下面是一段对话。你要从对话里，提炼出「对他这个人的新认识」。\n\n"
            "【严格输出格式，必须遵守】\n"
            "每行一条，只能以下面两种前缀开头，除此之外什么都不能有：\n"
            "[事实] 后面写：他明确说过的事\n"
            "[猜测] 后面写：你推断的、但没直说的事\n"
            "没有新认识，就只输出一个词：无\n"
            "绝对不要写「有」「好的」等其他任何话，不要解释。\n\n"
            "【只记值得长期记的】\n"
            "只提炼「他是谁」的稳定特质，或「近期相对持续」的表现。\n"
            "不要记「最近很累」「今天心情不好」这类临时状态。\n\n"
            "【猜测要谨慎】\n"
            "[猜测] 只能基于「反复出现或稳定的线索」推断。\n"
            "不要从「单次、临时的状态」（比如某天说累）去推断他长期的性格或习惯。\n\n"
            "对话内容：\n"
            + "\n".join(buffer)
    )

    # 2. 调用模型
    reply = llm(prompt)

    # 3. 解析
    items = parse_reply(reply)

    # 4. 逐条写入（remember_func 会做校验 + 去重 + 存盘）
    added = 0
    for it in items:
        result = remember_func(it["text"], source=it["source"])
        if result is not None:   # 没被去重/没失败，才算「新增」
            added += 1

    return added

def consolidate(llm, episodes, remember_func):
    """
    夜间整合：把一堆事件（episode）归纳成印象（impression）。

    关键：归纳出的印象，来源是 observed（反复说的）/ her_inference（推断的），
    绝不标 user_said（那是「用户直接说的即时印象」专属）。

    参数：
        llm           : 模型函数
        episodes      : 事件列表（layer=episode 的记忆）
        remember_func : 写记忆的函数

    返回：
        新增的印象条数
    """
    if not episodes:
        return 0

    # 1. 拼事件列表
    lines = "\n".join(f"- {e['text']}" for e in episodes)

    # 2. 拼提示词
    prompt = (
        "下面是一段时间里发生的若干事件。请从这些事件里，归纳出「反复出现、跨事件的规律」。\n\n"
        "事件：\n" + lines + "\n\n"
        "【严格输出格式，必须遵守】\n"
        "每行一条，只能以下面两种前缀开头，除此之外什么都不能有：\n"
        "[事实] 后面写：他反复明确表达过的稳定特点\n"
        "[猜测] 后面写：你从事件里推断出的规律\n"
        "没有反复出现的规律，就只输出一个词：无\n"
        "不要写「有」「好的」等其他任何话，不要解释。\n"
        "【只归纳「反复出现」的，单次事件不要归纳】\n"
    )

    # 3. 调模型 + 解析
    reply = llm(prompt)
    items = parse_reply(reply)

    # 4. 写入：把 [事实] 的来源从 user_said 改成 observed
    added = 0
    for it in items:
        if it["source"] == "user_said":
            source = "observed"      # 归纳的「事实」= 观察到的反复，不是原话
        else:
            source = "her_inference"
        result = remember_func(
            it["text"],
            source=source,
            layer="impression",
        )
        if result is not None:
            added += 1

    return added