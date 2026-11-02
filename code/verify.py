# verify.py —— 验证机制（记忆修正的「主动」那一半）

def find_uncertain_impressions(items):
    """
    找出「值得验证」的印象（不确定、值得求证）。

    规则：
    - source 是 her_inference（我猜的）
    - 置信度中等（0.4 ~ 0.7）
    - 没被标记失效（deleted）

    返回：
        值得验证的印象列表
    """
    result = []
    for m in items:
        if m.get("deleted"):
            continue
        if m.get("source") != "her_inference":
            continue
        conf = m.get("confidence", 0)
        if not (0.4 <= conf <= 0.7):
            continue
        result.append(m)
    return result


def should_ask_now(llm, user_text):
    """
    判断：用户这句话，是否「敞开心扉、希望被关心/询问」。

    返回：
        True  → 适合顺嘴求证
        False → 不适合（用户在闲聊/心情好/没想被问）
    """
    prompt = (
        "用户在说一句话。请判断：他此刻是不是「敞开心扉、希望被关心或询问」的状态？\n\n"
        "用户的话：「" + user_text + "」\n\n"
        "判断标准：\n"
        "- 适合关心：他表达了情绪（累、烦、低落、隐晦地求助、说到自己）。\n"
        "- 不适合：他在闲聊、开玩笑、问无关的事、心情明显很好不需要关心。\n\n"
        "只输出一个词：是 或 否\n"
        "不要输出其他任何内容。"
    )
    reply = llm(prompt).strip()
    return "是" in reply


def judge_feedback(reply_text, llm):
    """
    判断用户对「求证」的回答，是「确认 / 否认 / 无关」。

    返回：
        "confirm" / "deny" / "unrelated"
    """
    prompt = (
        "用户在回应一个「求证」。请判断他的态度：\n"
        "求证的内容是关于他的一个猜测。\n\n"
        "用户的回应：「" + reply_text + "」\n\n"
        "只输出一个词：\n"
        "confirm   —— 他确认了（对、是、嗯、没错、确实）\n"
        "deny      —— 他否认了（不对、不是、没有、别乱说）\n"
        "unrelated —— 他没正面回应，或聊了别的\n"
        "不要输出其他任何内容。"
    )
    reply = llm(prompt).strip()
    if "deny" in reply:
        return "deny"
    if "confirm" in reply:
        return "confirm"
    return "unrelated"


def pick_verify_target(llm, items, user_text):
    """
    综合判断：现在该不该验证、验证哪一条。

    返回：
        (印象, 是否该问) —— 该问时返回 (印象, True)，否则 (None, False)
    """
    candidates = find_uncertain_impressions(items)
    if not candidates:
        return None, False

    # 判断用户此刻是否希望被问
    if not should_ask_now(llm, user_text):
        return None, False

    return candidates[0], True