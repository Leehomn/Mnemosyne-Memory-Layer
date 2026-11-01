# test_source.py —— 测试 source 模块（来源与置信度）

from source import default_confidence, is_confirmed, DEFAULT_CONFIDENCE


def test_known_sources_have_fixed_confidence():
    # 各来源有确定的置信度
    assert default_confidence("user_said") == 0.9
    assert default_confidence("observed") == 0.8
    assert default_confidence("third_party") == 0.5
    assert default_confidence("her_inference") == 0.4


def test_unknown_source_falls_back_to_default():
    # 未知来源返回默认 0.5
    assert default_confidence("unknown") == 0.5


def test_is_confirmed_true_for_verified_sources():
    # 证实：用户说的 / 观察到的 / 第三方
    assert is_confirmed("user_said") is True
    assert is_confirmed("observed") is True
    assert is_confirmed("third_party") is True


def test_is_confirmed_false_for_inference_and_unknown():
    # 猜测：AI 推断的 / 未知
    assert is_confirmed("her_inference") is False
    assert is_confirmed("unknown") is False


def test_all_default_confidences_in_range():
    # 所有置信度都在 0~1 之间
    for v in DEFAULT_CONFIDENCE.values():
        assert 0 <= v <= 1
