# test_llm.py —— 测试调用记账

from types import SimpleNamespace

import llm as _llm


def _usage(**kw):
    """造一个假的 usage 对象，模拟 openai 的返回结构。"""
    return SimpleNamespace(**kw)


def setup_function(_fn):
    """每条用例前清零，避免互相污染。"""
    _llm.reset_usage()


def test_record_splits_hit_and_miss():
    # 输入 1000（命中 800 / 未命中 200），输出 300
    _llm._record(_usage(prompt_tokens=1000, completion_tokens=300,
                        prompt_cache_hit_tokens=800,
                        prompt_cache_miss_tokens=200))
    u = _llm.get_usage()
    assert u["calls"] == 1
    assert u["prompt"] == 1000
    assert u["hit"] == 800
    assert u["miss"] == 200
    assert u["completion"] == 300


def test_cost_uses_two_input_prices():
    # 命中 100 万 token = ¥0.02，未命中 100 万 = ¥1.0，输出 100 万 = ¥4.0
    _llm._record(_usage(prompt_tokens=2_000_000, completion_tokens=1_000_000,
                        prompt_cache_hit_tokens=1_000_000,
                        prompt_cache_miss_tokens=1_000_000))
    # 只断费用那一截，避免依赖整行措辞
    line = _llm.format_usage()
    assert "¥5.020" in line


def test_record_falls_back_to_all_miss():
    # 没有缓存字段的端点：全部算未命中，不能丢掉输入
    _llm._record(_usage(prompt_tokens=500, completion_tokens=100))
    u = _llm.get_usage()
    assert u["prompt"] == 500
    assert u["hit"] == 0
    assert u["miss"] == 500


def test_record_reads_prompt_tokens_details():
    # 只给 openai 标准字段（cached_tokens）时也要能拆出命中
    details = SimpleNamespace(cached_tokens=120)
    _llm._record(_usage(prompt_tokens=400, completion_tokens=50,
                        prompt_tokens_details=details))
    u = _llm.get_usage()
    assert u["hit"] == 120
    assert u["miss"] == 280


def test_record_ignores_none_usage():
    # 端点没返回 usage 时不能崩，只是不记账
    _llm._record(None)
    u = _llm.get_usage()
    assert u["calls"] == 0
    assert u["prompt"] == 0


def test_reset_usage_clears_everything():
    _llm._record(_usage(prompt_tokens=10, completion_tokens=5,
                        prompt_cache_hit_tokens=0,
                        prompt_cache_miss_tokens=10))
    _llm.reset_usage()
    u = _llm.get_usage()
    assert u == {"calls": 0, "prompt": 0, "hit": 0, "miss": 0, "completion": 0}


def test_format_usage_reports_hit_rate():
    _llm._record(_usage(prompt_tokens=1000, completion_tokens=0,
                        prompt_cache_hit_tokens=690,
                        prompt_cache_miss_tokens=310))
    line = _llm.format_usage()
    assert "命中率 69.0%" in line
    assert "调用 1 次" in line


def test_get_usage_returns_copy():
    # 拿到的是拷贝，改它不能影响账本
    u = _llm.get_usage()
    u["calls"] = 999
    assert _llm.get_usage()["calls"] == 0
