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

    # 不能用 "是" in reply —— "不是" 里也含 "是"，会把否定读成肯定。
    # 先判否定，再判肯定；两边都不沾就当作「不适合问」。
    if not reply:
        return False
    if "否" in reply or "不" in reply:
        return False
    return "是" in reply or "yes" in reply.lower()


def judge_feedback(llm, reply_text):
    """
    判断用户对「求证」的回答，是「确认 / 否认 / 无关」。

    参数顺序与全项目一致：llm 在前。
    兼容旧写法 judge_feedback(reply_text, llm) —— 见下方自动纠正。

    返回：
        "confirm" / "deny" / "unrelated"
    """
    # 兼容旧调用：老代码把 llm 放在第二位，这里自动换回来，不让它静默算错。
    if callable(reply_text) and not callable(llm):
        llm, reply_text = reply_text, llm
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
    reply = llm(prompt).strip().lower()

    # 判定顺序很重要：
    # 1) 先认 deny（模型照格式回答时最常见）
    # 2) 再认「含有否定词的 confirm」—— "not confirm" 这种串里没有 deny 字样，
    #    只查 deny 会漏掉，最后被 confirm 捡走，否认就变成了确认。
    # 3) 最后才认干净的 confirm
    if "deny" in reply:
        return "deny"
    if "confirm" in reply:
        negations = ("not", "n't", "no ", "非", "不", "否")
        if any(neg in reply.replace("confirm", "") for neg in negations):
            return "deny"
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