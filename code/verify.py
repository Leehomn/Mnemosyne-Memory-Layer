# verify.py —— 验证机制（记忆修正的「主动」那一半）

def find_uncertain_impressions(items):
    """
    找出「值得验证」的印象（不确定、有反复、值得求证）。

    规则：
    - source 是 her_inference（我猜的）
    - 置信度中等（0.4 ~ 0.7，太确定不用问，太不确定问了也白问）
    - occurrences >= 2（出现过至少 2 次）
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
        if m.get("occurrences", 0) < 2:
            continue
        result.append(m)
    return result


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