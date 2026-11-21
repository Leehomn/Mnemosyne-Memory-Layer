# llm.py —— 调用 DeepSeek 模型

import json
import os
from openai import OpenAI


# 单价（元 / 百万 token）。与 memory-bench/_probe_cache.py 用同一组，
# 改价只改这一处，别在别处再抄一遍。
_PRICE_IN_HIT = 0.02
_PRICE_IN_MISS = 1.0
_PRICE_OUT = 4.0

# 记账：所有 LLM 调用都经过 llm()，在这里累计 token 与费用。
# 不在这里打印——一轮对话会调好几次，逐个打印会把日志淹掉，
# 由调用方（跑评测的脚本）在结束时调 format_usage() 报一次。
_USAGE = {"calls": 0, "prompt": 0, "hit": 0, "miss": 0, "completion": 0}


def _record(usage):
    """把一次响应的 usage 记进全局账本。

    DeepSeek 会把输入拆成「命中缓存」和「未命中缓存」两部分，两者单价差 50 倍，
    所以必须分开记，只记 prompt_tokens 会把成本算错一个数量级。
    非 DeepSeek 端点没有这几个字段时，退化成「全部算未命中」。
    """
    if usage is None:
        return
    prompt = getattr(usage, "prompt_tokens", 0) or 0
    completion = getattr(usage, "completion_tokens", 0) or 0
    hit = getattr(usage, "prompt_cache_hit_tokens", None)
    miss = getattr(usage, "prompt_cache_miss_tokens", None)
    if hit is None or miss is None:
        details = getattr(usage, "prompt_tokens_details", None)
        cached = getattr(details, "cached_tokens", 0) if details else 0
        hit = cached or 0
        miss = max(prompt - hit, 0)
    _USAGE["calls"] += 1
    _USAGE["prompt"] += prompt
    _USAGE["hit"] += hit
    _USAGE["miss"] += miss
    _USAGE["completion"] += completion


def get_usage():
    """返回当前账本的一份拷贝。"""
    return dict(_USAGE)


def reset_usage():
    """清零账本，跑新的一次评测前调用。"""
    for k in _USAGE:
        _USAGE[k] = 0


def format_usage():
    """把账本渲染成一行中文，含 token 明细和估算费用。"""
    u = _USAGE
    yuan = (u["hit"] * _PRICE_IN_HIT
            + u["miss"] * _PRICE_IN_MISS
            + u["completion"] * _PRICE_OUT) / 1_000_000
    hit_rate = (u["hit"] / u["prompt"] * 100) if u["prompt"] else 0.0
    return (f"LLM 调用 {u['calls']} 次 | "
            f"输入 {u['prompt']:,} token（命中 {u['hit']:,} / "
            f"未命中 {u['miss']:,}，命中率 {hit_rate:.1f}%）| "
            f"输出 {u['completion']:,} token | 约 ¥{yuan:.3f}")


def load_config():
    """读 config.json，返回配置字典。

    config.json 锚定在 llm.py 自己所在的目录（而不是当前工作目录），
    这样不管从哪个目录运行脚本，都能找到配置文件，不会因为
    「相对路径换了个 cwd 就找不到」而崩。
    """
    path = os.path.join(os.path.dirname(__file__), "config.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def make_deepseek_llm(temperature=None):
    """
    返回一个「能调用 DeepSeek 的函数」。
    符合 reconstruct 的 llm 接口：给它 prompt，返回回答文本。
    每次调用都会把 usage 记进全局账本（见 format_usage）。

    temperature : 不传就走服务端默认（DeepSeek 是 1.0）。跑评测时应该显式传 0，
                  否则同一条题每次采样答案都可能不同，改动效果会被噪声淹没
                  （实测同一召回块连跑 6 次：3 次说不记得、2 次编出错日期、1 次答对）。
    """
    config = load_config()
    client = OpenAI(api_key=config["api_key"], base_url=config["base_url"])

    kwargs = {}
    if temperature is not None:
        kwargs["temperature"] = temperature

    def llm(prompt):
        response = client.chat.completions.create(
            model=config["model"],
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )
        _record(getattr(response, "usage", None))
        return response.choices[0].message.content

    return llm
