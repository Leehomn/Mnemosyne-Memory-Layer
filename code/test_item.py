# test_item.py —— 测试 item 模块（数据结构与校验）

from item import make_item, is_valid, HALF_LIVES


def test_valid_item_passes():
    # 合法记忆应该通过
    good = make_item("他胃疼", "user_said", 0.9)
    assert is_valid(good) is True


def test_empty_text_invalid():
    # 空内容不合法
    bad = {"text": "", "source": "user_said", "confidence": 0.9, "layer": "episode"}
    assert is_valid(bad) is False


def test_unknown_source_invalid():
    # 来源乱写不合法
    bad = make_item("他胃疼", "unknown", 0.9)
    assert is_valid(bad) is False


def test_confidence_out_of_range_invalid():
    # 置信度超出范围不合法
    bad = make_item("他胃疼", "user_said", 5.0)
    assert is_valid(bad) is False


def test_missing_fields_invalid():
    # 字段缺失不合法（is_valid 内部用 get，不会报错）
    bad = {"text": "他胃疼"}
    assert is_valid(bad) is False


def test_bad_subject_invalid():
    # subject 乱写不合法
    bad = make_item("他胃疼", "user_said", 0.9, subject="about_dog")
    assert is_valid(bad) is False


def test_layer_maps_to_default_half_life():
    # 半衰期分层：不同 layer 自动取不同半衰期
    e = make_item("今天他加班了", "observed", 0.8, layer="episode")
    i = make_item("他嘴硬但心软", "her_inference", 0.7, layer="impression")
    r = make_item("我们关系很好", "observed", 0.9, layer="relationship")

    assert e["half_life"] == 14
    assert i["half_life"] == 90
    assert r["half_life"] == 3650


def test_explicit_half_life_overrides_default():
    # 显式传 half_life 时，用传的值
    custom = make_item("测试", "user_said", 0.9, layer="episode", half_life=999)
    assert custom["half_life"] == 999


def test_impression_kind_subdivides_half_life():
    # 印象按 kind 细分半衰期
    trait = make_item("他本质上很重感情", "her_inference", 0.7, layer="impression", kind="trait")
    state = make_item("他最近压力很大", "her_inference", 0.7, layer="impression", kind="state")

    assert trait["half_life"] == 3650   # 稳定内核：近乎永久
    assert state["half_life"] == 60     # 动态表现：两个月
