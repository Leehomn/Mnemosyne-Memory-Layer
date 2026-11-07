# test_reconstruct.py —— 测试 reconstruct 模块

from reconstruct import parse_reply, reconstruct
from index import Cognition


def test_parse_fact_and_guess():
    reply = "[事实] 他是四川人，能吃辣\n[猜测] 他可能不太喜欢被叫大肥鱼"
    items = parse_reply(reply)

    assert len(items) == 2
    assert items[0] == {"text": "他是四川人，能吃辣", "source": "user_said", "evidence": []}
    assert items[1] == {"text": "他可能不太喜欢被叫大肥鱼", "source": "her_inference", "evidence": []}


def test_parse_drop_invalid():
    # 没有前缀的行、空行，都应该被丢弃
    reply = "[事实] 有效的一条\n这是没有前缀的行\n\n[乱写] 这个前缀不认识"
    items = parse_reply(reply)

    assert len(items) == 1
    assert items[0]["text"] == "有效的一条"


def test_parse_wu():
    # 模型输出「无」，应该返回空列表
    items = parse_reply("无")
    assert items == []


def test_parse_drop_boilerplate():
    """模型把提示词里的示例文字原样抄出来时，必须丢弃，不能落库。

    这是「宁可漏记，不可乱记」红线的护栏：示例文字不是用户真实记忆。
    """
    reply = (
        "[事实] 他反复明确表达过的稳定特点\n"
        "[猜测] 你从事件里推断出的规律\n"
        "[事实] 他叫南风\n"
        "[猜测] 他可能想家"
    )
    items = parse_reply(reply)

    assert len(items) == 2
    assert items[0]["text"] == "他叫南风"
    assert items[1]["text"] == "他可能想家"


# ===== 新增：parse_reply 的容错（这些格式以前全会静默丢记忆） =====

def test_parse_numbered_list():
    """模型最爱的编号列表。旧实现只认裸行首的 [事实]，编号一加整段记忆全丢。"""
    items = parse_reply("1. [事实] 他叫南风\n2. [猜测] 他可能爱熬夜")
    assert len(items) == 2
    assert items[0]["text"] == "他叫南风"
    assert items[1]["source"] == "her_inference"


def test_parse_markdown_bold():
    """模型爱加粗标签。旧的 startswith("[事实]") 碰不上。"""
    items = parse_reply("**[事实]** 他叫南风\n**[猜测]** 他怕吵")
    assert len(items) == 2
    assert items[0]["text"] == "他叫南风"
    assert items[1]["text"] == "他怕吵"


def test_parse_fullwidth_brackets():
    """中文输入法下模型可能输出【事实】而不是 [事实]。"""
    items = parse_reply("【事实】他叫南风\n【猜测】他可能爱熬夜")
    assert len(items) == 2
    assert items[0]["source"] == "user_said"
    assert items[1]["source"] == "her_inference"


def test_parse_colon_after_tag():
    """标签后带冒号时，冒号不能混进记忆正文。"""
    items = parse_reply("[事实]：他叫南风\n[猜测]: 他可能爱熬夜")
    assert len(items) == 2
    assert items[0]["text"] == "他叫南风"
    assert items[1]["text"] == "他可能爱熬夜"


def test_parse_stacked_decoration():
    """两层装饰叠在一起（"1. - [事实] xxx"）也要能剥干净。"""
    items = parse_reply("1. - [事实] 他叫南风")
    assert len(items) == 1
    assert items[0]["text"] == "他叫南风"


def test_parse_empty_and_blank_lines():
    """空回复、纯空白行不能崩，也不能产出空记忆。"""
    assert parse_reply("") == []
    assert parse_reply("\n\n  \n") == []
    assert parse_reply("[事实]\n[猜测]   ") == []


def test_reconstruct_passes_now_to_prompt():
    """now 参数要把「当前日期」拼进提示词，让模型能把相对时间换算成绝对日期。

    用假模型把收到的提示词原样返回，断言提示词里出现了日期 + 换算指令。
    """
    seen = {}

    def capture_llm(prompt):
        seen["prompt"] = prompt
        return "无"

    reconstruct(capture_llm, ["用户：我下周三约了人"], lambda *a, **k: None, now="2026-04-13")

    assert "2026-04-13" in seen["prompt"]
    assert "绝对日期" in seen["prompt"]


def test_reconstruct_without_now_keeps_compat():
    """不传 now 时，提示词里不该出现「当前日期」段（向后兼容）。"""
    seen = {}

    def capture_llm(prompt):
        seen["prompt"] = prompt
        return "无"

    reconstruct(capture_llm, ["用户：你好"], lambda *a, **k: None)

    assert "当前日期" not in seen["prompt"]


def test_relative_time_without_date_is_dropped():
    """相对时间词还在、却没换算成绝对日期 → 该拦下（时间信息已坏，不记）。"""
    added = reconstruct(
        lambda p: "[事实] 他下周三约了人",
        ["用户：我下周三约了人"],
        lambda *a, **k: "ok",   # 假 remember：返回非 None，模拟「已写入」
        now="2026-04-13",
    )
    assert added == 0


def test_absolute_date_is_kept():
    """换算成绝对日期后，正常落库。"""
    added = reconstruct(
        lambda p: "[事实] 他 2026-04-13 约了人",
        ["用户：我下周三约了人"],
        lambda *a, **k: "ok",
        now="2026-04-13",
    )
    assert added == 1


def test_no_time_word_is_kept():
    """没有时间词的记忆（如「他是四川人」）不该被误伤，照常落库。"""
    added = reconstruct(
        lambda p: "[事实] 他是四川人，能吃辣",
        ["用户：我是四川人"],
        lambda *a, **k: "ok",
    )
    assert added == 1


def fake_llm(prompt):
    return "[事实] 他叫南风\n[猜测] 他可能喜欢打游戏"


def test_reconstruct_full(tmp_path):
    # 用独立的临时数据目录，避免污染真实数据
    cog = Cognition(data_dir=str(tmp_path))

    # 一段对话（buffer）
    buffer = ["用户：我叫南风", "AI：好的，记住了"]

    # 重构：用假模型 + cog.remember 作为写入函数
    added = reconstruct(fake_llm, buffer, cog.remember)

    # 假模型返回了 1 条事实 + 1 条猜测，应该新增 2 条
    assert added == 2

    # 事实区应该召回「他叫南风」；猜测是 her_inference 默认 0.4，
    # 低于召回门槛 0.6，所以「他可能喜欢打游戏」不该出现在召回块里。
    block = cog.recall_block(limit=8)
    assert "他叫南风" in block
    assert "他可能喜欢打游戏" not in block
