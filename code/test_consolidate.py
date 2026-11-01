# test_consolidate.py —— 测试夜间整合

from reconstruct import consolidate
from item import make_item


def fake_llm(prompt):
    return "[事实] 他爱吃辣\n[猜测] 他最近压力有点大"


def test_consolidate():
    # 假的事件列表
    episodes = [
        make_item("他说无辣不欢", "user_said", 0.9, layer="episode"),
        make_item("他说吃火锅要特辣", "user_said", 0.9, layer="episode"),
    ]

    # 用一个假 remember 收集结果
    collected = []

    def fake_remember(text, source, **kwargs):
        collected.append({"text": text, "source": source, **kwargs})
        return {"text": text}

    added = consolidate(fake_llm, episodes, fake_remember)

    assert added == 2
    # 「他爱吃辣」是 [事实]，来源应该是 observed（不是 user_said）
    assert collected[0]["source"] == "observed"
    assert collected[0]["layer"] == "impression"
    # 「他最近压力大」是 [猜测]，来源是 her_inference
    assert collected[1]["source"] == "her_inference"