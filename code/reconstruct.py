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

# 标签本身可能写成 [事实] 【事实】 [ 事实 ] **[事实]** 或 [我说]
_TAG = re.compile(r"^[\[【]\s*(事实|猜测|我说)\s*[\]】]\s*[:：]?\s*")

# 提示词里出现过的「示例文字 / 说明文字」，模型有时会原样抄进输出。
# 这些不是用户真实记忆，一旦落库就是乱编——宁可漏记，不可乱记，直接丢弃。
_PROMPT_BOILERPLATE = {
    "他反复明确表达过的稳定特点",   # consolidate 旧提示词的示例
    "你从事件里推断出的规律",       # consolidate 旧提示词的示例
    "他明确说过的事",               # reconstruct 提示词的示例
    "你推断的、但没直说的事",       # reconstruct 提示词的示例
    "X",                            # 新占位符，防模型照抄
}

# 正文里该有的「绝对日期」模式。C1 用它做「带时间的事件，正文到底带没带日期」的校验。
# 认：2026-04-13 / 2026年4月13日 / 4月13日 / 4月13号 / 13号
_DATE_PATTERN = re.compile(
    r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?"   # 2026-04-13 / 2026年4月13日
    r"|\d{1,2}月\d{1,2}[日号]"              # 4月13日 / 4月13号
    r"|\d{1,2}[号]"                          # 13号（最宽松）
)

# 相对时间词：正文里还留着这些词、却没换算成绝对日期，说明模型漏换算，这条要拦下。
_HAS_RELATIVE = re.compile(
    r"昨天|今天|明天|前天|后天|上周|下周|这周|几号|周[一二三四五六日天]"
)


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

                # —— 拆出「话题」尾巴 ——
        # 模型会写「[事实] 他养了狗 #话题：养狗」
        # 用 re.sub 把「#话题：X」从正文里删掉，话题词单独存。
        # 注意：不能用 text[:start] 截断——因为「#人物/#维度/#值」可能排在话题后面，
        # 截断会把它们一起切掉。这里用 sub 只删话题这一段，后面的标签保留。
        topic = None
        m_topic = re.search(r"#\s*话题\s*[:：]\s*([^\n#]*)", text)
        if m_topic:
            topic = m_topic.group(1).strip(" ，,。.、;；")
            text = re.sub(r"#\s*话题\s*[:：]\s*[^\n#]*", "", text, count=1)
            text = text.rstrip(" →-—、，,;； ").strip()

        # —— 拆出「人物」尾巴 ——
        # 谁都不写 = 用户本人（提炼时「他」= 对话对象）。写名 = 第三方。
        who = None
        m_who = re.search(r"#\s*人物\s*[:：]\s*([^\n#]*)", text)
        if m_who:
            who = m_who.group(1).strip(" ，,。.、;；")
            text = re.sub(r"#\s*人物\s*[:：]\s*[^\n#]*", "", text, count=1)
            text = text.rstrip(" →-—、，,;； ").strip()

        # —— 拆出「维度」尾巴 ——
        # 事实维度：这条记忆讲的是「哪一类事实」（生日/住处/护膝放哪…）。
        what = None
        m_what = re.search(r"#\s*维度\s*[:：]\s*([^\n#]*)", text)
        if m_what:
            what = m_what.group(1).strip(" ，,。.、;；")
            text = re.sub(r"#\s*维度\s*[:：]\s*[^\n#]*", "", text, count=1)
            text = text.rstrip(" →-—、，,;； ").strip()

        # —— 拆出「值」尾巴 ——
        # 具体值：与维度配对，将来「同维度+同人+不同值 → 判冲突」。
        value = None
        m_value = re.search(r"#\s*值\s*[:：]\s*([^\n#]*)", text)
        if m_value:
            value = m_value.group(1).strip(" ，,。.、;；")
            text = re.sub(r"#\s*值\s*[:：]\s*[^\n#]*", "", text, count=1)
            text = text.rstrip(" →-—、，,;； ").strip()

        # —— 拆出「关系」尾巴 ——
        # 模型会写「[事实] 老曹生日是六月九号 #关系：2」
        # 四档：0=用户本人，1=亲密的人，2=一般关系，3=遇到的陌生人。
        # 谁都不写 = 0（用户本人）。这是「按关系等级物理分库」的前提。
        tier = None
        m_tier = re.search(r"#\s*关系\s*[:：]\s*([^\n#]*)", text)
        if m_tier:
            tier_raw = m_tier.group(1).strip(" ，,。.、;；")
            # 只认 0/1/2/3，其余（模型乱写）当 None，宁可漏判不乱标档
            if tier_raw in ("0", "1", "2", "3"):
                tier = int(tier_raw)
            text = re.sub(r"#\s*关系\s*[:：]\s*[^\n#]*", "", text, count=1)
            text = text.rstrip(" →-—、，,;； ").strip()

        if not text:
            continue

        # 护栏：模型把提示词里的「示例文字」原样抄出来了，丢弃
        if text in _PROMPT_BOILERPLATE:
            continue

        source = "user_said" if tag == "事实" else "her_inference"
        subject = "about_user"
        if tag == "我说":
            # AI 自己说过的话：来源是 self_said（自己说的，不是用户/观察/推断），
            # 主体是 about_self（关于 AI 自己）。这是独立的一格，不能混进用户事实。
            source = "self_said"
            subject = "about_self"
        items.append({"text": text, "source": source, "subject": subject,
                      "evidence": evidence, "topic": topic,
                      "who": who, "what": what, "value": value, "tier": tier})
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
            + "下面是一段对话。你要从对话里，提炼出「对他这个人的新认识」，以及「你（AI）自己说过、且他可能回头问的话」。\n\n"
            "【严格输出格式，必须遵守】\n"
            "每行一条，只能以下面三种前缀开头，除此之外什么都不能有：\n"
            "[事实] 后面写：他明确说过的事\n"
            "[猜测] 后面写：你推断的、但没直说的事\n"
            "[我说] 后面写：你（AI）自己说过、且他可能回头问的事（承诺、建议、你的自述、关系约定）\n"
            "每条正文后面，用「 #话题：X」标注这句话属于什么话题（X 用一个简短的名词短语，如「养狗」「工作」「生日」）。\n"
            "如果这条记忆涉及「某个具体的第三方」（比如老曹、周宁、李楠），在话题后面加「 #人物：名字」。\n"
            "如果这条记忆说的是用户本人的，就不写 #人物（默认就是他）。\n"
            "同时判断「这个人和用户的关系等级」，在人物后面加「 #关系：数字」：\n"
            "  0 = 用户本人；1 = 亲密的人（家人/恋人/挚友）；2 = 一般关系（同事/同学/普通朋友）；3 = 遇到的陌生人。\n"
            "  说的是用户本人时写 #关系：0，或干脆不写（默认就是 0）。\n"
            "如果这条记忆是一个「具体事实」（生日、住处、职业、某个东西放哪、某个约定等），加「 #维度：X #值：Y」标注它属于哪一类事实、具体值是什么（X/Y 用简短短语，如「 #维度：生日 #值：六月九号」）。\n"
            "纯特质、纯情绪、纯关系这些没有「具体值」的，不写 #维度/#值。\n"
            "没有新认识，就只输出一个词：无\n"
            "绝对不要写「有」「好的」等其他任何话，不要解释。\n\n"
            "【只记值得长期记的，按「人脑记什么」来取舍】\n"
            "从对话里挑出下面几类新认识（没有就输出「无」）：\n"
            "1. 事件核心框架：谁、在哪、什么时候、发生了什么、结果怎样。\n"
            "2. 与他自我相关、对他有意义的事（身份、目标、价值观，比如「他第一次上台演讲」「他被老师当众批评」）。\n"
            "3. 【最重要】任何「带时间的事件」都必须记，且必须把时间换算成绝对日期写进正文。\n"
            "   - 只要对话里出现了「昨天/今天/明天/前天/后天/上周/下周/几号/周几/某月某日」，\n"
            "     或者任何「在某个时间点发生/约定/计划」的事，就必须输出一条 [事实]。\n"
            "   - 例：「前天把迷迭香搬到窗边」→ 必须写成「他 2026-05-25 把迷迭香搬到窗边」。\n"
            "   - 禁止因为「看起来像日常琐事」就不记——带时间的琐事也是时间题要考的。\n"
            "4. 改口、纠错、变化（比如「他改主意不搬家了」「他最近戒辣了」）。\n"
            "5. 社会信息与人际关系（谁对他好、谁让他尴尬、他属于哪个群体）。\n"
            "6. 未完成的事、待办、没问出口的话（这些会反复出现，值得记）。\n"
            "7. 异常、违反预期、意外、转折点（开头、结尾、转折处记得更牢）。\n"
            "8. 情绪高峰与身体感受（最紧张、最开心、最害怕的瞬间）——记「这条记忆当时情绪多强」，用来调制权重。\n"
            "9. 你（AI）自己说过、且他可能回头问的话——用 [我说] 前缀。\n"
            "   - 例：你建议「理票先按日期分堆」、你答应「帮他记配方」、你自述「我叫小满」。\n"
            "   - 只记「承诺 / 建议 / 自述 / 关系约定」这类有长期价值、他可能回头问的。\n"
            "   - 寒暄、客套（「好嘞」「费腰吧」这类随口应和）不记——跟「临时状态不记」同一条红线。\n\n"
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
        text = it["text"]
        # —— C1 校验：正文里若还留着相对时间词、却没换算成绝对日期 ——
        # 「相对时间词还在 + 没有绝对日期」说明模型漏换算，这条的时间信息是坏的，
        # 记一个「下周三」这种基准已丢的半截时间，比不记更害人。宁可漏记，不可乱记。
        if _HAS_RELATIVE.search(text) and not _DATE_PATTERN.search(text):
            continue
        # —— 把正文里的绝对日期结构化抠出来，写进 event_time ——
        # 正文里「他 2026-05-25 搬花」这类日期，是这条记忆描述的事件发生的逻辑日期。
        # 存成独立字段，以后可以按日期检索/排序，而不是只埋在正文字符串里。
        # 抠不到日期就传 None（表示这条记忆不涉及具体某天，比如纯特质「他重感情」）。
        event_time = None
        m_date = _DATE_PATTERN.search(text)
        if m_date:
            event_time = m_date.group(0)
        result = remember_func(text, source=it["source"], subject=it["subject"],
                               event_time=event_time, topic=it.get("topic"),
                               who=it.get("who"), what=it.get("what"),
                               value=it.get("value"), tier=it.get("tier"))
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

    # 4. 写入：归纳出的来源要做映射
    #    [事实] 的来源从 user_said 改成 observed（归纳的「事实」= 观察到的反复，不是原话）
    #    [我说] 保持 self_said（AI 自己说过的身份不能丢，不能被误标成推断）
    #    其余（[猜测]）标 her_inference
    added = 0
    for it in items:
        if it["source"] == "user_said":
            source = "observed"  # 归纳的「事实」= 观察到的反复，不是原话
        elif it["source"] == "self_said":
            source = "self_said"  # AI 自己说的保持身份，别降成推断
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