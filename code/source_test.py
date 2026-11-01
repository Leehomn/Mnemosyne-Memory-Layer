# test_source.py —— 测试 source 模块

from source import default_confidence, is_confirmed, DEFAULT_CONFIDENCE


# 测试1：各来源有确定的置信度
assert default_confidence("user_said") == 0.9
assert default_confidence("observed") == 0.8
assert default_confidence("third_party") == 0.5
assert default_confidence("her_inference") == 0.4

# 测试2：未知来源返回默认 0.5
assert default_confidence("unknown") == 0.5

# 测试3：证实 vs 猜测
assert is_confirmed("user_said") == True
assert is_confirmed("observed") == True
assert is_confirmed("her_inference") == False
assert is_confirmed("unknown") == False

# 测试4：置信度都在 0~1 之间
for v in DEFAULT_CONFIDENCE.values():
    assert 0 <= v <= 1

print("source 全部测试通过 ✅")