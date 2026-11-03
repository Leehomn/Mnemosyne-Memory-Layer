# test_recall.py —— 测试 recall 模块

from recall import recall, format_recall_block
from item import make_item


def test_recall_returns_top_weighted():
    # 造三条记忆：权重明显不同
    m1 = make_item("我叫南风", "user_said", 0.95, hits=3)          # 权重最高
    m2 = make_item("他胃疼那天我说了难听的话", "user_said", 0.5, hits=0)  # 权重最低
    m3 = make_item("他喜欢打游戏", "her_inference", 0.6, hits=1)

    result = recall([m1, m2, m3], limit=2)

    assert len(result) == 2
    assert result[0]["text"] == "我叫南风"       # 权重最高，排第一
    assert result[1]["text"] == "他喜欢打游戏"    # 权重第二


def test_recall_respects_limit():
    m1 = make_item("我叫南风", "user_said", 0.95, hits=3)
    m2 = make_item("他胃疼那天我说了难听的话", "user_said", 0.5, hits=0)
    m3 = make_item("他喜欢打游戏", "her_inference", 0.6, hits=1)

    one = recall([m1, m2, m3], limit=1)
    assert len(one) == 1
    assert one[0]["text"] == "我叫南风"


def test_format_recall_block_keeps_self_out_of_facts():
    # 关于 AI 自己的事，不进事实区（bug 修复验证）
    m_user = make_item("我叫南风", "user_said", 0.95, subject="about_user")
    m_self = make_item("他胃疼那天我说了难听的话", "user_said", 0.95, subject="about_self")
    m_guess = make_item("他喜欢打游戏", "her_inference", 0.6)

    text = format_recall_block([m_user, m_self, m_guess])

    assert "我叫南风" in text                      # 事实区有这个
    assert "他喜欢打游戏" in text                   # 猜测区有这个
    assert "我说了难听的话" not in text              # 关键：关于AI自己的事，被挡在事实区外


def fake_llm(prompt):
    # 假模型：总是说「第 1 条相关」
    return "1"


def test_semantic_recall():
    from recall import semantic_recall

    items = [
        make_item("他叫南风", "user_said", 0.9),
        make_item("他爱吃辣", "user_said", 0.9),
        make_item("他在找工作", "user_said", 0.9),
    ]

    # 假模型说「第 1 条（他爱吃辣）相关」
    result = semantic_recall(fake_llm, items, "今天吃啥")

    assert len(result) == 1
    assert result[0]["text"] == "他爱吃辣"


def test_semantic_recall_none():
    from recall import semantic_recall

    items = [make_item("他叫南风", "user_said", 0.9)]

    # 假模型说「无」
    def fake_none(prompt):
        return "无"

    result = semantic_recall(fake_none, items, "随便聊聊")
    assert result == []


# ===== 新增：semantic_recall 的解析容错 =====

def test_semantic_recall_fullwidth_comma():
    """全角逗号不能导致整批相关记忆被静默丢弃（等于这次召回啥也没捞到）。"""
    from recall import semantic_recall

    items = [make_item("他叫南风", "user_said", 0.9),
             make_item("他爱吃辣", "user_said", 0.9)]

    result = semantic_recall(lambda p: "0，1", items, "今天吃啥")
    assert [m["text"] for m in result] == ["他叫南风", "他爱吃辣"]


def test_semantic_recall_with_extra_text():
    from recall import semantic_recall

    items = [make_item("他爱吃辣", "user_said", 0.9)]
    result = semantic_recall(lambda p: "相关的编号：0", items, "今天吃啥")
    assert len(result) == 1


def test_semantic_recall_excludes_deleted():
    """已失效的记忆不该被召回（墓碑过滤）。"""
    from recall import semantic_recall

    alive = make_item("他叫南风", "user_said", 0.9)
    dead = make_item("他叫小鱼", "user_said", 0.9)
    dead["deleted"] = True

    result = semantic_recall(lambda p: "0", [alive, dead], "你叫什么")
    assert [m["text"] for m in result] == ["他叫南风"]


# ===== 新增：format_recall_block 的格式 =====

def test_format_recall_block_structure():
    """事实区/猜测区要真的分开，且括号不能错配。

    旧实现开头写「（」、结尾补「）」，中间还内嵌一对括号，
    喂给模型的提示词结构是乱的，会削弱「哪个能当真」的分区感。
    """
    from recall import format_recall_block

    block = format_recall_block([
        make_item("他叫南风", "user_said", 0.9),
        make_item("他可能爱熬夜", "her_inference", 0.5),
    ])

    assert "关于他的事实" in block
    assert "你的猜测" in block
    assert block.count("（") == block.count("）")   # 括号必须配对


def test_format_recall_block_fact_requires_high_confidence():
    """低置信度的说法不能进「可以当真」的事实区。"""
    from recall import format_recall_block

    block = format_recall_block([make_item("他好像爱吃辣", "user_said", 0.5)])
    assert "关于他的事实" not in block


def test_format_recall_block_excludes_about_self():
    """关于 AI 自己的事（about_self）不进事实区，避免把 AI 的话当用户的事实。"""
    from recall import format_recall_block

    block = format_recall_block([
        make_item("我说了难听的话", "user_said", 0.9, subject="about_self")
    ])
    assert block == ""
