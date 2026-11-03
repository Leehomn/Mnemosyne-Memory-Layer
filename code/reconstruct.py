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


def parse_reply(reply):
    """
    解析模型的回答，提取 [事实]/[猜测] 条目。

    容错：
    - 行首装饰（- * • 1. ** > #）一律剥掉
    - 标签全角/半角都认（[事实] 【事实】）
    - 标签后紧跟的冒号（中英文）一并去掉

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
        if not text:
            continue

        source = "user_said" if tag == "事实" else "her_inference"
        items.append({"text": text, "source": source})

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
            kind=kind,
        )
        if result is not None:
            added += 1

    return added