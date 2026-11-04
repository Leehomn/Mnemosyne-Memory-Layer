# test_decay.py —— 测试 decay 模块（衰减与遗忘）

import math
from decay import decayed_weight, effective_half_life, should_forget, after_review_fail


def test_time_decay_halves_at_half_life():
    # 过一个半衰期（14天），权重减半
    w = decayed_weight(1.0, 14, 0, 1.0, 14)
    assert round(w, 3) == 0.5, f"预期 0.5，实际 {w}"


def test_use_boost_makes_recalled_heavier():
    # 被提 2 次，权重应大于被提 0 次
    w0 = decayed_weight(1.0, 14, 0, 1.0, 0)
    w2 = decayed_weight(1.0, 14, 2, 1.0, 0)
    assert w2 > w0, f"被想起的应该更重，实际 {w2} vs {w0}"


def test_review_lengthens_half_life():
    # 复习让半衰期变长（对数增长：前面快，后面慢）
    # 14 天、被想起 3 次 → 14 × (1 + 0.5 × ln(1+3)) ≈ 23.7 天
    expected = round(14 * (1 + 0.5 * math.log(1 + 3)), 6)
    assert round(effective_half_life(14, 3), 6) == expected


def test_review_half_life_growth_slows_down():
    # 半衰期增长也要「前面快、后面慢」（对数），而不是线性无上限
    # 1→2 次的增幅，应远大于 100→101 次的增幅
    base = 14
    rise_1_2 = effective_half_life(base, 2) - effective_half_life(base, 1)
    rise_100_101 = effective_half_life(base, 101) - effective_half_life(base, 100)
    assert rise_1_2 > rise_100_101 * 20


def test_should_forget_threshold():
    # 遗忘判定
    assert should_forget(0.05) is True
    assert should_forget(0.5) is False


def test_review_fail_halves_half_life_and_confidence():
    # 复习失败：半衰期和置信度都砍半
    new_hl, new_conf = after_review_fail(35, 0.9)
    assert new_hl == 17.5, f"预期 17.5，实际 {new_hl}"
    assert new_conf == 0.45, f"预期 0.45，实际 {new_conf}"


def test_log_growth_slows_down():
    # 对数增长：前面涨得快，后面越来越慢
    g01 = 1 + math.log(1 + 1)      # hits=1
    g02 = 1 + math.log(1 + 2)      # hits=2
    rise_small = g02 - g01         # 1→2 的涨幅

    g100 = 1 + math.log(1 + 100)
    g101 = 1 + math.log(1 + 101)
    rise_large = g101 - g100       # 100→101 的涨幅

    assert rise_small > rise_large * 20, f"前面应比后面涨幅大得多，实际 {rise_small} vs {rise_large}"
