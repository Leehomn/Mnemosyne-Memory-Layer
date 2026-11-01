# test_store.py —— 测试 store 模块

import os
from store import save_items, load_items, backup_file
from item import make_item


def test_save_and_load():
    # 存两条
    m1 = make_item("他胃疼那天我说了难听的话", "user_said", 0.95)
    m2 = make_item("我叫南风", "user_said", 0.9)
    save_items([m1, m2])

    # 读回来，应该还是 2 条
    loaded = load_items()
    assert len(loaded) == 2
    assert loaded[0]["text"] == "他胃疼那天我说了难听的话"
    assert loaded[1]["text"] == "我叫南风"


def test_load_empty():
    # 读一个不存在的文件，应该返回空列表，而不是报错
    result = load_items("data/不存在.json")
    assert result == []


def test_backup():
    # 备份一个存在的文件，应该生成 .bak 文件
    save_items([make_item("测试备份", "user_said", 0.9)])
    b = backup_file("data/items.json")
    assert b is not None
    assert os.path.exists(b)


print("store 全部测试通过 ✅")