# reconstruct.py —— 事后重构（把对话提炼成认识）

import re

# 行首那些「模型爱加但不是内容」的装饰：短横线、星号、圆点、数字编号、
# markdown 加粗符号、引号。剥干净了才认得出 [事实]/[猜测]。
_PREFIX_NOISE = re.compile(
    r"^(?:"
    r"[-*•·]\s+"          # "- " "* " "• " "· "
    r"|\d+[.、)]\s*"      # "1. " "2、" "3) "
    r"|[>#]+\s*"          # 引用 / 标题符号
    r"|\*\*"              # markdown 加粗开头
    r")+"
)

# 标签本身可能写成 [事实] 【事实】 [ 事实 ] **[事实]**
_TAG = re.compile(r"^[\[【]\s*(事实|猜测)\s*[\]】]\s*[:：]?\s*")

# 提示词里出现过的「示例文字 / 说明文字」，模型有时会原样抄进输出。
# 这些不是用户真实记忆，一旦落库就是乱编——宁可漏记，不可乱记，直接丢弃。
_PROMPT_BOILERPLATE = {
    "他反复明确表达过的稳定特点",   # consolidate 旧提示词的示例
    "你从事件里推断出的规律",       # consolidate 旧提示词的示例
    "他明确说过的事",               # reconstruct 提示词的示例
    "你推断的、但没直说的事",       # reconstruct 提示词的示例
    "X",                            # 新占位符，防模型照抄
}


def parse_reply(reply):
    """
    解析模型的回答，提取 [事实]/[猜测] 条目。

    容错：
    - 行首装饰（- * • 1. ** > #）一律剥掉
    - 标签全角/半角都认（[事实] 【事实】）
    - 标签后紧跟的冒号（中英文）一并去掉
    - 模型把提示词里的「示例文字」原样抄出来时，丢弃不落库
      （护栏：宁可漏记，不可乱记）

    参数：
        reply : 模型的回答文本

    返回：
        一个列表，每项是 {"text": ..., "source": ...}
    """
    items = []

    for raw_line in reply.split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        # 反复剥：有的模型会写成 "1. - [事实] xxx" 这种叠了两层装饰的
        for _ in range(3):
            stripped = _PREFIX_NOISE.sub("", line)
            if stripped == line:
                break
            line = stripped

        m = _TAG.match(line)
        if not m:
            continue

        tag = m.group(1)
        text = line[m.end():].strip()

        # 尾巴上的加粗符号也去掉（** 成对出现时）
        text = text.strip("*").strip()

        # —— 拆出「依据」尾巴 ——
        # 模型会写「[猜测] xxx → 依据：事件1、事件3」
        # 把「→ 依据：事件N」从正文里切走，正文和依据编号分开存。
        evidence = []
        m_ev = re.search(r"依据[:：]\s*([^\n]*)", text)
        if m_ev:
            ev_part = m_ev.group(1)
            evidence = [int(x) for x in re.findall(r"\d+", ev_part)]
            text = text[:m_ev.start()].rstrip(" →-—、，,；;").strip()

        if not text:
            continue

        # 护栏：模型把提示词里的「示例文字」原样抄出来了，丢弃
        if text in _PROMPT_BOILERPLATE:
            continue

        source = "user_said" if tag == "事实" else "her_inference"
        items.append({"text": text, "source": source, "evidence": evidence})
    return items

def verify_grounding(llm, guess_text, evidence_episodes):
    """
    语义核对：guess_text 这条归纳，是否真的被 evidence_episodes 这些事件「支撑」。

    参数：
        llm              : 模型函数
        guess_text       : 归纳出来的那句话（猜测正文）
        evidence_episodes: 它声称依据的事件原文列表

    返回：
        True  → 有依据（归纳成立）
        False → 依据不足（归纳是乱编的）
    """
    if not evidence_episodes:
        return False

    lines = "\n".join(f"- {t}" for t in evidence_episodes)
    prompt = (
        "我在判断一句「归纳」是否靠谱。\n\n"
        "归纳：「" + guess_text + "」\n\n"
        "它声称依据的事件：\n" + lines + "\n\n"
        "请判断：这句归纳里的每个关键点，是不是都能在这些事件里找到支撑？\n"
        "- 能支撑 → 输出：是\n"
        "- 支撑不住（归纳里出现了事件里根本没有的信息，或把没关系的两件事硬连起来）→ 输出：否\n\n"
        "只输出一个字：是 或 否。不要解释。"
    )
    reply = llm(prompt).strip()

    # 先判否定，再判肯定（避免「不是」里含「是」被误读）
    if not reply:
        return False
    if "否" in reply or "不" in reply:
        return False
    return "是" in reply or "yes" in reply.lower()

def reconstruct(llm, buffer, remember_func, now=None):
    """
    事后重构：把一段对话提炼成新认识，写入记忆库。

    参数：
        llm           : 模型函数（给它提示词，返回回答）—— 真模型或 mock 都行
        buffer        : 对话列表（一堆字符串）
        remember_func : 写记忆的函数（通常是 cog.remember）
        now           : 可选。这段对话发生的「逻辑日期」字符串（如 "2026-04-13"），
                        用于让模型把「下周三」「前天」这类相对时间换算成绝对日期。
                        不传则不提当前日期（保持向后兼容）。

    返回：
        新增的记忆条数
    """
    # 1. 拼提示词
    now_line = ""
    if now:
        now_line = f"【当前日期】这段对话发生在 {now}。下面提到的「昨天/今天/明天/下周/上周/前天/后天」等相对时间，请以这个日期为基准换算成绝对日期写进正文。\n\n"
    prompt = (
            now_line
            + "下面是一段对话。你要从对话里，提炼出「对他这个人的新认识」。\n\n"
            "【严格输出格式，必须遵守】\n"
            "每行一条，只能以下面两种前缀开头，除此之外什么都不能有：\n"
            "[事实] 后面写：他明确说过的事\n"
            "[猜测] 后面写：你推断的、但没直说的事\n"
            "没有新认识，就只输出一个词：无\n"
            "绝对不要写「有」「好的」等其他任何话，不要解释。\n\n"
            "【只记值得长期记的，按「人脑记什么」来取舍】\n"
            "从对话里挑出下面几类新认识（没有就输出「无」）：\n"
            "1. 事件核心框架：谁、在哪、什么时候、发生了什么、结果怎样。\n"
            "2. 与他自我相关、对他有意义的事（身份、目标、价值观，比如「他第一次上台演讲」「他被老师当众批评」）。\n"
            "3. 时间锚点的事实：约定、日期、时间安排、改口、纠错、变化（比如「下周三约了人」「他改主意不搬家了」「他最近戒辣了」）。\n"
            "4. 社会信息与人际关系（谁对他好、谁让他尴尬、他属于哪个群体）。\n"
            "5. 未完成的事、待办、没问出口的话（这些会反复出现，值得记）。\n"
            "6. 异常、违反预期、意外、转折点（开头、结尾、转折处记得更牢）。\n"
            "7. 情绪高峰与身体感受（最紧张、最开心、最害怕的瞬间）——记「这条记忆当时情绪多强」，用来调制权重。\n\n"
            "【不记的，只有这一类】\n"
            "纯常规、重复、无关的一次性杂讯（比如「今天吃了午饭」「路边有几棵树」这类没有长期价值、也不会影响未来判断的）。\n"
            "临时状态（「今天好累」「现在饿了」）本身不进长期记忆，但「它背后的处境/变化」（比如「他最近在找工作、压力大」）要记。\n\n"
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

def consolidate(llm, episodes, remember_func, kind="state"):
    """
    夜间整合：把一堆事件（episode）归纳成印象（impression）。

    关键：归纳出的印象，来源是 observed（反复说的）/ her_inference（推断的），
    绝不标 user_said（那是「用户直接说的即时印象」专属）。

    参数：
        llm           : 模型函数
        episodes      : 事件列表（layer=episode 的记忆）
        remember_func : 写记忆的函数
        kind          : 印象类型，默认 state（动态表现）——
                        归纳出来的是「近期反复出现的规律」，还不够格算稳定内核；
                        等它自己被反复确认到第 3 次，才由晋升机制改成 trait

    返回：
        新增的印象条数
    """
    if not episodes:
        return 0

    # 1. 拼事件列表
    lines = "\n".join(f"事件{i}：{e['text']}" for i, e in enumerate(episodes))

    # 2. 拼提示词
    prompt = (
        "下面是一段时间里发生的若干事件。请从这些事件里，归纳出「反复出现、跨事件的规律」。\n\n"
        "事件：\n" + lines + "\n\n"
        "【严格输出格式，必须遵守】\n"
        "每行一条，只能用下面两种前缀开头，其余什么都不写：\n"
        "[事实] X\n"
        "[猜测] X\n"
        "（把 X 替换成你要写的那句话，不要照抄这个示例本身）\n"
        "没有反复出现的规律，就只输出一个词：无\n"
        "不要写「有」「好的」等其他任何话，不要解释。\n"
        "【只归纳「反复出现」的，单次事件不要归纳】\n"
        "【每条必须交代依据】\n"
        "每条归纳后面，必须用「 → 依据：事件N、事件M」标注它依据的是哪几条事件。\n"
        "事件编号从 0 开始。依据的事件，必须是「归纳句里的关键信息能在该事件原文里找到」的。\n"
        "拿不出依据编号的，不许输出这条。\n"
    )

    # 3. 调模型 + 解析
    reply = llm(prompt)
    items = parse_reply(reply)

    # 4. 写入：把 [事实] 的来源从 user_said 改成 observed
    added = 0
    for it in items:
        if it["source"] == "user_said":
            source = "observed"  # 归纳的「事实」= 观察到的反复，不是原话
        else:
            source = "her_inference"

        # —— 依据回溯校验（做法 B：语义核对）——
        # 猜测要「保留待验证」而不是丢弃：核对得上→正常 0.4；核对不上→压到 0.2 标待验证。
        confidence = None
        if source == "her_inference":
            evidence_episodes = [
                episodes[i]["text"]
                for i in it.get("evidence", [])
                if 0 <= i < len(episodes)
            ]
            if verify_grounding(llm, it["text"], evidence_episodes):
                confidence = 0.4  # 依据充分：显式写 0.4，不靠下游查默认
            else:
                confidence = 0.2  # 依据不足，压到 0.2，保留待验证

        result = remember_func(
            it["text"],
            source=source,
            layer="impression",
            kind=kind,
            confidence=confidence,
        )
        if result is not None:
            added += 1

    return added