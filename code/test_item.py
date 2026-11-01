# test_item.py —— 测试 item 模块

from item import make_item, is_valid, HALF_LIVES


# 测试1：合法记忆应该通过
good = make_item("他胃疼", "user_said", 0.9)
assert is_valid(good) == True

# 测试2：空内容应该不合法
bad1 = {"text": "", "source": "user_said", "confidence": 0.9, "layer": "episode"}
assert is_valid(bad1) == False

# 测试3：来源乱写应该不合法
bad2 = make_item("他胃疼", "unknown", 0.9)
assert is_valid(bad2) == False

# 测试4：置信度超出范围应该不合法
bad3 = make_item("他胃疼", "user_said", 5.0)
assert is_valid(bad3) == False

# 测试5：字段缺失应该不合法（用 get 而不是 []，所以不会报错）
bad4 = {"text": "他胃疼"}
assert is_valid(bad4) == False

# 测试6：subject 乱写应该不合法
bad5 = make_item("他胃疼", "user_said", 0.9, subject="about_dog")
assert is_valid(bad5) == False

# 测试7：半衰期分层 —— 不同 layer 自动取不同半衰期
e = make_item("今天他加班了", "observed", 0.8, layer="episode")
i = make_item("他嘴硬但心软", "her_inference", 0.7, layer="impression")
r = make_item("我们关系很好", "observed", 0.9, layer="relationship")

assert e["half_life"] == 14
assert i["half_life"] == 90
assert r["half_life"] == 3650

# 测试8：显式传 half_life 时，用传的值而不是默认
custom = make_item("测试", "user_said", 0.9, layer="episode", half_life=999)
assert custom["half_life"] == 999

# 测试：印象按 kind 细分半衰期
trait = make_item("他本质上很重感情", "her_inference", 0.7, layer="impression", kind="trait")
state = make_item("他最近压力很大", "her_inference", 0.7, layer="impression", kind="state")

assert trait["half_life"] == 3650   # 稳定内核：近乎永久
assert state["half_life"] == 60     # 动态表现：两个月