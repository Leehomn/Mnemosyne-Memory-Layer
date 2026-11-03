# test_conflict.py —— 测试冲突检测

from conflict import find_conflicts
from item import make_item


def _items():
    return [
        make_item("他爱吃辣", "user_said", 0.9),
        make_item("他喜欢篮球", "user_said", 0.9),
    ]


def test_no_conflict():
    assert find_conflicts(lambda p: "无", "他喜欢音乐", _items()) == []


def test_semicolon_comma():
    """模型输出半角逗号（标准情况）。"""
    found = find_conflicts(lambda p: "0,1", "他不吃辣了", _items())
    assert [m["text"] for m in found] == ["他爱吃辣", "他喜欢篮球"]


def test_fullwidth_comma():
    """中文模型经常输出全角逗号。旧的 split(",") 会把整批冲突静默丢掉，
    旧记忆不标失效、继续当事实用 —— 直接撞「不可乱记」的红线。"""
    found = find_conflicts(lambda p: "0，1", "他不吃辣了", _items())
    assert [m["text"] for m in found] == ["他爱吃辣", "他喜欢篮球"]


def test_ideographic_comma():
    """顿号分隔。"""
    found = find_conflicts(lambda p: "0、1", "他不吃辣了", _items())
    assert len(found) == 2


def test_with_extra_text():
    """模型多说一句「冲突的编号是…」时，编号仍要被认出来。"""
    found = find_conflicts(lambda p: "冲突的编号：0", "他不吃辣了", _items())
    assert [m["text"] for m in found] == ["他爱吃辣"]


def test_out_of_range_ignored():
    """越界编号要忽略，不能 IndexError。"""
    assert find_conflicts(lambda p: "5,99", "x", _items()) == []


def test_duplicate_ids_not_repeated():
    """同一个编号重复出现时不能返回两条一样的记忆。"""
    found = find_conflicts(lambda p: "0,0,0", "他不吃辣了", _items())
    assert len(found) == 1


def test_empty_reply():
    assert find_conflicts(lambda p: "", "x", _items()) == []


def test_deleted_items_excluded():
    """已失效的记忆不该再参与冲突判断（否则会对一条墓碑反复标记）。"""
    items = _items()
    items[0]["deleted"] = True          # 「他爱吃辣」已被推翻

    # 过滤后只剩「他喜欢篮球」，编号 0 指向它 —— 不能是墓碑那条
    found = find_conflicts(lambda p: "0", "新的话", items)
    assert [m["text"] for m in found] == ["他喜欢篮球"]


def test_all_deleted_skips_llm():
    """全部失效时不该白调一次模型。"""
    items = _items()
    for m in items:
        m["deleted"] = True

    calls = []
    found = find_conflicts(lambda p: calls.append(p) or "0", "新的话", items)
    assert found == []
    assert calls == []
