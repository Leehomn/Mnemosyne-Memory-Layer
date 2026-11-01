# test_decay.py —— 测试 decay 模块

import math
from decay import decayed_weight, effective_half_life, should_forget, after_review_fail, days_since

# 测试1：时间衰减 —— 过一个半衰期（14天），权重应该减半
w = decayed_weight(1.0, 14, 0, 1.0, 14)
assert round(w, 3) == 0.5, f"预期 0.5，实际 {w}"

# 测试2：用进废退 —— 被提 2 次，权重应该大于被提 0 次
w0 = decayed_weight(1.0, 14, 0, 1.0, 0)
w2 = decayed_weight(1.0, 14, 2, 1.0, 0)
assert w2 > w0, f"被想起的应该更重，实际 {w2} vs {w0}"

# 测试3：复习让半衰期变长
assert effective_half_life(14, 3) == 35.0

# 测试4：遗忘判定
assert should_forget(0.05) == True
assert should_forget(0.5) == False

# 测试5：复习失败 —— 半衰期和置信度都砍半
new_hl, new_conf = after_review_fail(35, 0.9)
assert new_hl == 17.5, f"预期 17.5，实际 {new_hl}"
assert new_conf == 0.45, f"预期 0.45，实际 {new_conf}"

# 测试6：对数增长 —— 前面涨得快，后面涨得越来越慢
g01 = 1 + math.log(1 + 1)      # hits=1
g02 = 1 + math.log(1 + 2)      # hits=2
rise_small = g02 - g01         # 1→2 的涨幅

g100 = 1 + math.log(1 + 100)
g101 = 1 + math.log(1 + 101)
rise_large = g101 - g100       # 100→101 的涨幅

assert rise_small > rise_large * 20, f"前面应比后面涨幅大得多，实际 {rise_small} vs {rise_large}"

print("hits 1→2 涨幅：", round(rise_small, 4))
print("hits 100→101 涨幅：", round(rise_large, 6))