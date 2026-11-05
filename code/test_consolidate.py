# test_consolidate.py —— 测试夜间整合

from reconstruct import consolidate, verify_grounding
from item import make_item


def fake_llm(prompt):
    """假模型：看提示词内容分流。
    - 归纳提示词 → 返回带「依据」的归纳（依据事件0）
    - 核对提示词 → 返回「是」或「否」，用 flag 控制
    """
    if "依据" in prompt and "支撑" in prompt:
        # 这是 verify_grounding 的核对提示词
        return fake_llm.grounding_answer
    # 这是 consolidate 的归纳提示词
    return (
        "[事实] 他爱吃辣 → 依据：事件0\n"
        "[猜测] 他最近压力有点大 → 依据：事件0"
    )


fake_llm.grounding_answer = "是"


def test_consolidate():
    episodes = [
        make_item("他说无辣不欢", "user_said", 0.9, layer="episode"),
        make_item("他说吃火锅要特辣", "user_said", 0.9, layer="episode"),
    ]

    collected = []

    def fake_remember(text, source, **kwargs):
        collected.append({"text": text, "source": source, **kwargs})
        return {"text": text}

    added = consolidate(fake_llm, episodes, fake_remember)

    assert added == 2
    assert collected[0]["source"] == "observed"
    assert collected[0]["layer"] == "impression"
    assert collected[1]["source"] == "her_inference"
    # 依据充分（核对返回「是」）→ 猜测置信度显式写 0.4
    assert collected[1]["confidence"] == 0.4


def test_consolidate_guesses_without_grounding_get_low_confidence():
    """依据不足的猜测：不丢弃，而是压到 0.2 保留待验证。"""
    fake_llm.grounding_answer = "否"

    episodes = [
        make_item("他说无辣不欢", "user_said", 0.9, layer="episode"),
    ]

    collected = []

    def fake_remember(text, source, **kwargs):
        collected.append({"text": text, "source": source, **kwargs})
        return {"text": text}

    added = consolidate(fake_llm, episodes, fake_remember)

    # 猜测仍然被保留（不丢弃）
    assert added == 2
    guess = [c for c in collected if c["source"] == "her_inference"][0]
    # 依据不足 → 压到 0.2，不是默认 0.4
    assert guess["confidence"] == 0.2
