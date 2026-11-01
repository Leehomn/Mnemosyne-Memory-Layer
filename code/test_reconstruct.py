# test_reconstruct.py —— 测试 reconstruct 模块

from reconstruct import parse_reply, reconstruct
from index import Cognition


def test_parse_fact_and_guess():
    reply = "[事实] 他是四川人，能吃辣\n[猜测] 他可能不太喜欢被叫大肥鱼"
    items = parse_reply(reply)

    assert len(items) == 2
    assert items[0] == {"text": "他是四川人，能吃辣", "source": "user_said"}
    assert items[1] == {"text": "他可能不太喜欢被叫大肥鱼", "source": "her_inference"}


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

    # 库里应该有这两条
    block = cog.recall_block(limit=8)
    assert "他叫南风" in block
    assert "他可能喜欢打游戏" in block
