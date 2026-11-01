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