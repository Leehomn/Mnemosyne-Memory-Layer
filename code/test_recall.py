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
    # 关于 AI 自己的事，不进「事实区」，但进独立的「我说过的话」区
    m_user = make_item("我叫南风", "user_said", 0.95, subject="about_user")
    m_self = make_item("他胃疼那天我说了难听的话", "user_said", 0.95, subject="about_self")
    m_guess = make_item("他喜欢打游戏", "her_inference", 0.6)

    text = format_recall_block([m_user, m_self, m_guess])

    assert "我叫南风" in text                      # 事实区有这个
    assert "他喜欢打游戏" in text                   # 猜测区有这个
    assert "我说了难听的话" in text                  # 进了「我说过的话」区
    assert "你之前说过的话" in text                 # 有「我说过的话」分区标题
    # 关键：AI 自己的话不能混进「关于他的事实」区
    fact_block = text.split("你的猜测", 1)[0]
    assert "我说了难听的话" not in fact_block


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


def test_semantic_recall_passes_today_date_to_prompt():
    """召回提示词要自动带上「今天的日期」（系统当前日期），让模型能理解
    查询里的相对时间词（前天/上周）。真人聊天也会说「前天」，所以这是真实需求：
    模型得知道今天几号，才能把「前天」换算成对应日期。
    """
    from recall import semantic_recall

    items = [make_item("他 2026-05-25 把迷迭香搬到窗边", "user_said", 0.9)]
    seen = {}

    def capture(prompt):
        seen["prompt"] = prompt
        return "无"

    semantic_recall(capture, items, "帮我按前天算算")

    from datetime import datetime
    expected = datetime.now().strftime("%Y-%m-%d")

    assert expected in seen["prompt"]          # 今天的日期（系统当前）进了提示词
    assert "相对时间" in seen["prompt"]         # 有「把相对时间换算成绝对日期」的提示


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
        make_item("他可能爱熬夜", "her_inference", 0.6),
    ])

    assert "关于他的事实" in block
    assert "你的猜测" in block
    assert block.count("（") == block.count("）")   # 括号必须配对


def test_format_recall_block_drops_low_confidence_guesses():
    """低置信度的猜测（<0.6）不该进猜测区，避免 AI 顺着没把握的猜测乱编。

    这是「降低置信度 → 降低出场机会」的最后一环：
    之前猜测区只看来源不看置信度，0.4 的初始猜测照样上场。
    """
    from recall import format_recall_block

    block = format_recall_block([
        make_item("他叫南风", "user_said", 0.9),
        make_item("他可能想家", "her_inference", 0.4),   # 出生默认，没验证过 → 该被拦
        make_item("他可能爱熬夜", "her_inference", 0.7),  # 验证过，够格上场
    ])

    assert "关于他的事实" in block
    assert "你的猜测" in block
    assert "他可能想家" not in block      # 低置信猜测被拦
    assert "他可能爱熬夜" in block        # 高置信猜测保留


def test_format_recall_block_fact_requires_high_confidence():
    """低置信度的说法不能进「可以当真」的事实区。"""
    from recall import format_recall_block

    block = format_recall_block([make_item("他好像爱吃辣", "user_said", 0.5)])
    assert "关于他的事实" not in block


def test_format_recall_block_excludes_about_self():
    """关于 AI 自己的事（about_self）不进事实区，但进独立的「我说过的话」区。"""
    from recall import format_recall_block

    block = format_recall_block([
        make_item("我说了难听的话", "user_said", 0.9, subject="about_self")
    ])
    assert "你之前说过的话" in block
    assert "我说了难听的话" in block
    assert "关于他的事实" not in block   # 不能冒充用户的事实区


def test_confirmed_guess_enters_facts_not_guesses():
    """被验证确认的猜测（her_inference 但置信度 >= 0.8）要进事实区，不能再进猜测区。

    这是「方案乙」：被验证过的记忆应该更强——置信度升到 0.9 后，
    它终于能进「可以当真」的事实区；同时不能再顶着「别当事实」的猜测标签，
    否则一条记忆既被说成事实、又被说成猜测，自相矛盾。
    """
    from recall import format_recall_block

    block = format_recall_block([
        make_item("他可能想家", "her_inference", 0.9),   # 被验证确认，升到 0.9
    ])

    assert "关于他的事实" in block      # 进事实区
    assert "他可能想家" in block        # 文本在
    assert "你的猜测" not in block      # 关键：不能再进猜测区
