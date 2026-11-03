# test_index.py —— 测试 index 模块（Cognition 统一入口）

import time
from index import Cognition, jaccard
from item import make_item
from store import load_items, save_items


def test_remember_and_recall(tmp_path):
    cog = Cognition(data_dir=str(tmp_path))
    cog.remember("我叫南风", source="user_said", confidence=0.95)
    cog.remember("他喜欢打游戏", source="her_inference", confidence=0.6)

    block = cog.recall_block(limit=8)
    assert "我叫南风" in block
    assert "他喜欢打游戏" in block
    assert "事实" in block and "猜测" in block


def test_remember_invalid(tmp_path):
    cog = Cognition(data_dir=str(tmp_path))
    result = cog.remember("测试", source="unknown", confidence=0.9)
    assert result is None


def test_no_duplicate(tmp_path):
    cog = Cognition(data_dir=str(tmp_path))
    cog.remember("我叫南风", source="user_said", confidence=0.95)
    result = cog.remember("我叫南风", source="user_said", confidence=0.95)
    assert result is not None
    assert result["occurrences"] == 2

    left = load_items(cog.path)
    same = [m for m in left if m["text"] == "我叫南风"]
    assert len(same) == 1


def test_similar_dedup(tmp_path):
    cog = Cognition(data_dir=str(tmp_path))
    cog.remember("我爱吃辣", source="user_said", confidence=0.9)
    result = cog.remember("他爱吃辣", source="user_said", confidence=0.9)
    assert result is not None
    assert result["occurrences"] == 2

    left = load_items(cog.path)
    assert len(left) == 1


def test_maintain(tmp_path):
    cog = Cognition(data_dir=str(tmp_path))
    old_item = make_item("一条很老的记忆", "observed", 0.5,
                         created_at=time.time() - 999*86400)
    new_item = make_item("一条新记忆", "user_said", 0.95)
    save_items([old_item, new_item], cog.path)

    removed = cog.maintain()
    assert removed == 1

    left = load_items(cog.path)
    assert len(left) == 1
    assert left[0]["text"] == "一条新记忆"


def test_jaccard():
    assert jaccard("辣", "辣") == 1.0
    assert jaccard("辣", "甜") == 0.0
    assert 0 < jaccard("我爱吃辣", "他爱吃辣") < 1.0


def test_enhance(tmp_path):
    cog = Cognition(data_dir=str(tmp_path))
    cog.remember("我爱吃辣", source="user_said", confidence=0.9)
    result = cog.remember("他爱吃辣", source="user_said", confidence=0.9)
    assert result is not None
    assert result["occurrences"] == 2

def test_promote_state_to_trait(tmp_path):
    from item import IMPRESSION_HALF_LIVES

    cog = Cognition(data_dir=str(tmp_path))

    # 记一条 state（动态表现），然后让它「反复出现」3 次
    cog.remember("他最近很努力", source="observed", layer="impression", kind="state")
    cog.remember("他最近很努力", source="observed", layer="impression", kind="state")
    result = cog.remember("他最近很努力", source="observed", layer="impression", kind="state")

    # 第 3 次出现 → 应该晋升成 trait
    assert result["kind"] == "trait"
    assert result["half_life"] == 3650
    assert result["occurrences"] == 3

def test_consolidate_method(tmp_path):
    from index import Cognition

    def fake_llm(prompt):
        return "[事实] 他爱吃辣"

    cog = Cognition(data_dir=str(tmp_path), llm=fake_llm)

    # 记几条 episode
    cog.remember("他说无辣不欢", source="user_said", layer="episode")
    cog.remember("他说吃火锅要特辣", source="user_said", layer="episode")

    # 夜间整合（自动读 episode）
    added = cog.consolidate()

    assert added == 1

    # 库里应该多了一条 impression
    block = cog.recall_block(limit=10)
    assert "他爱吃辣" in block

def test_consolidate_promotes_existing(tmp_path):
    from index import Cognition

    def fake_llm(prompt):
        return "[事实] 他爱吃辣"

    cog = Cognition(data_dir=str(tmp_path), llm=fake_llm)

    # 库里先有一条「他爱吃辣」的印象（state）
    cog.remember("他爱吃辣", source="observed", layer="impression", kind="state")

    # 又积累了一堆事件（反复说吃辣）
    cog.remember("他说无辣不欢", source="user_said", layer="episode")
    cog.remember("他说火锅要特辣", source="user_said", layer="episode")

    # 夜间整合
    cog.consolidate()

    # 关键：库里应该只有「一条」关于吃辣的记忆（没新建重复的）
    items = load_items(cog.path)
    chila = [m for m in items if "辣" in m.get("text", "")]
    print("吃辣相关的记忆条数：", len(chila))
    for m in chila:
        print("  -", m["text"], "| occurrences =", m.get("occurrences"))

def test_conflict_marks_deleted(tmp_path):
    from index import Cognition

    # 假模型：回答「冲突的编号是 0」
    def fake_llm(prompt):
        # 冲突检测时会返回「0」（第 0 条冲突）
        if "冲突" in prompt:
            return "0"
        # 其他情况返回无
        return "无"

    cog = Cognition(data_dir=str(tmp_path), llm=fake_llm)

    # 先存「他爱吃辣」
    cog.remember("他爱吃辣", source="user_said", confidence=0.9)

    # 用户说「我不吃辣了」→ 触发冲突检测
    cog.remember("我不吃辣了", source="user_said", confidence=0.9)

    # 检查：「他爱吃辣」应该被标 deleted=True
    from store import load_items
    items = load_items(cog.path)
    chila = [m for m in items if "爱吃辣" in m.get("text", "")]
    assert len(chila) == 1
    assert chila[0]["deleted"] == True          # 被标失效
    assert chila[0]["superseded_by"] == "我不吃辣了"  # 记录了被谁推翻


# ===== 链路测试：模块单独测都对，接起来会不会断电 =====

def test_guess_gets_low_confidence(tmp_path):
    """猜的东西不传置信度时，必须拿 0.4，而不是和「他说的」一样的 0.9。"""
    cog = Cognition(data_dir=str(tmp_path))
    item = cog.remember("他可能喜欢安静", source="her_inference")
    assert item["confidence"] == 0.4


def test_verify_finds_the_guess(tmp_path):
    """reconstruct → remember → verify：这条线以前一次都没通。

    改前猜测一律 0.9，掉不出 verify 要的 0.4~0.7 区间，永远筛不到人。
    """
    from reconstruct import reconstruct
    from verify import find_uncertain_impressions

    cog = Cognition(data_dir=str(tmp_path))
    reconstruct(lambda p: "[猜测] 他喜欢安静",
                ["他说人多的时候有点累"], cog.remember)

    found = find_uncertain_impressions(load_items(cog.path))
    assert len(found) == 1
    assert found[0]["text"] == "他喜欢安静"


def test_hits_grow_when_repeated(tmp_path):
    """同一条信息被提起第二次，hits 要涨，半衰期要跟着变长。"""
    from decay import effective_half_life

    cog = Cognition(data_dir=str(tmp_path))
    cog.remember("我爱吃辣", source="user_said")
    result = cog.remember("我爱吃辣", source="user_said")

    assert result["hits"] == 1
    assert effective_half_life(result["half_life"], result["hits"]) > result["half_life"]


def test_consolidate_marks_state_and_digests(tmp_path):
    """夜间整合出来的印象 kind 必须是 state；事件消化过就不该再被吃一遍。

    没有 digested 标记的话，同一批事件每晚重复归纳一次，
    三晚就能把一条印象顶成永久的 trait —— 一条新证据都没有。
    """
    cog = Cognition(data_dir=str(tmp_path), llm=lambda p: "[事实] 他爱吃辣")
    cog.remember("他说无辣不欢", source="user_said", layer="episode")
    cog.remember("他说火锅要特辣", source="user_said", layer="episode")

    added = cog.consolidate()
    assert added == 1

    items = load_items(cog.path)
    impression = [m for m in items if m.get("layer") == "impression"]
    assert impression and impression[0]["kind"] == "state"
    assert impression[0]["occurrences"] == 1        # 只被归纳过一次

    # 再跑一次：这批事件已经消化过，什么都不该发生
    assert cog.consolidate() == 0
    items = load_items(cog.path)
    impression = [m for m in items if m.get("layer") == "impression"]
    assert impression[0]["occurrences"] == 1
    assert impression[0]["kind"] == "state"