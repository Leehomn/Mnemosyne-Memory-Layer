# test_store.py —— 测试 store 模块

import os
from store import save_items, load_items, backup_file
from item import make_item


def test_save_and_load(tmp_path):
    # 用临时目录，避免污染真实 data/
    path = str(tmp_path / "items.json")

    # 存两条
    m1 = make_item("他胃疼那天我说了难听的话", "user_said", 0.95)
    m2 = make_item("我叫南风", "user_said", 0.9)
    save_items([m1, m2], path)

    # 读回来，应该还是 2 条
    loaded = load_items(path)
    assert len(loaded) == 2
    assert loaded[0]["text"] == "他胃疼那天我说了难听的话"
    assert loaded[1]["text"] == "我叫南风"


def test_load_empty(tmp_path):
    # 读一个不存在的文件，应该返回空列表，而不是报错
    result = load_items(str(tmp_path / "不存在.json"))
    assert result == []


def test_backup(tmp_path):
    # 备份一个存在的文件，应该生成 .bak 文件
    path = str(tmp_path / "items.json")
    save_items([make_item("测试备份", "user_said", 0.9)], path)
    b = backup_file(path)
    assert b is not None
    assert os.path.exists(b)


# —— 以下 4 条是 2026-11-15 加的：原子写 + 损坏容错 ——


def test_save_is_atomic_no_tmp_left(tmp_path):
    """写完不留临时文件，且内容完整。"""
    path = str(tmp_path / "items.json")
    save_items([make_item("原子写", "user_said", 0.9)], path)
    assert not os.path.exists(path + ".tmp")
    assert load_items(path)[0]["text"] == "原子写"


def test_save_keeps_old_file_when_json_fails(tmp_path, monkeypatch):
    """序列化途中抛异常时，磁盘上的旧文件必须原样还在。

    旧写法 open(path,"w") 会先截断再写，序列化失败 = 旧数据当场清零。
    新写法先写 .tmp，异常时 os.replace 还没执行，旧文件毫发无损。
    """
    path = str(tmp_path / "items.json")
    save_items([make_item("旧数据", "user_said", 0.9)], path)

    import json as _json
    import store as _store

    def boom(*a, **kw):
        raise TypeError("模拟序列化失败")

    monkeypatch.setattr(_store.json, "dumps", boom)
    try:
        save_items([make_item("新数据", "user_said", 0.9)], path)
    except TypeError:
        pass
    else:
        raise AssertionError("应当抛出")

    # 旧文件仍在，且内容完整
    assert load_items(path)[0]["text"] == "旧数据"


def test_load_recovers_from_tmp(tmp_path):
    """主文件半截损坏、临时文件完整时，自动用临时文件救回来。"""
    path = str(tmp_path / "items.json")
    save_items([make_item("完整数据", "user_said", 0.9)], path)
    # 把主文件砸成半截，模拟写到一半崩溃
    import shutil
    shutil.copy(path, path + ".tmp")
    with open(path, "w", encoding="utf-8") as f:
        f.write('[{"text": "半截')
    assert load_items(path)[0]["text"] == "完整数据"


def test_load_recovers_from_bak(tmp_path):
    """没有临时文件时，退到最新的 .bak-* 备份。"""
    path = str(tmp_path / "items.json")
    save_items([make_item("备份里的", "user_said", 0.9)], path)
    backup_file(path)
    with open(path, "w", encoding="utf-8") as f:
        f.write('[{"text": "半截')
    assert load_items(path)[0]["text"] == "备份里的"


def test_load_raises_clear_error_when_unrecoverable(tmp_path):
    """主文件损坏、又没有任何副本时，报的错要能看出是哪份文件、多大。"""
    path = str(tmp_path / "items.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write('[{"text": "半截')
    try:
        load_items(path)
    except ValueError as exc:
        assert "items.json" in str(exc)
        assert "损坏" in str(exc)
    else:
        raise AssertionError("应当抛出 ValueError")
