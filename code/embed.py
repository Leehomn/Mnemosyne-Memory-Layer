# embed.py —— 语义向量（embedding）与余弦相似度
#
# 用途：给「语义召回」做廉价粗筛——先把 query 和记忆都算成向量，
# 用余弦相似度取最相关的 top N 条，再让 DeepSeek 细判相关性。
# 避免「拿全库几千条喂模型」的 token 爆炸（P14 实测一次召回喂 4 万字）。
#
# 用硅基流动的 BAAI/bge-m3（免费、OpenAI 兼容、1024 维），
# 复用项目已有的 openai 库，不新增 torch 等重依赖。
# 余弦相似度用纯 Python 实现，不依赖 numpy（系统 Python 没装 numpy）。

import json
import math
import os
from openai import OpenAI

# 语义粗筛时，最多取多少条「向量最相关」的记忆喂给 DeepSeek 细判。
# 取大一点（宁可多留不漏）：漏召回 = 答不出题，比多喂几条危险得多。
# 全库几千条 → 100 条，token 砍掉 90%+，同时几乎不损失召回质量。
EMBED_TOP_K = 100


def make_siliconflow_embedder(api_key, base_url="https://api.siliconflow.cn/v1",
                              model="BAAI/bge-m3"):
    """
    返回一个「把文字变成向量」的函数，支持单个字符串或字符串列表（批量）。

    参数：
        api_key  : 硅基流动的 API key
        base_url : 硅基流动端点（OpenAI 兼容）
        model    : embedding 模型（默认 BAAI/bge-m3，1024 维）

    返回：
        embed(text) -> list[float]                  （传入 str）
        embed([t1, t2, ...]) -> [list, list, ...]   （传入 list，批量）
    """
    client = OpenAI(api_key=api_key, base_url=base_url)

    def embed(text):
        single = isinstance(text, str)
        texts = [text] if single else list(text)
        resp = client.embeddings.create(model=model, input=texts)
        vecs = [d.embedding for d in resp.data]
        return vecs[0] if single else vecs

    return embed


def make_embedder_from_config():
    """
    从 config.json 读 embedding 配置，返回 embedder 函数；没配置则返回 None。

    config.json 锚定在 embed.py 自己所在的目录（和 llm.py 的 load_config 同一套约定），
    这样不管从哪个目录运行脚本都能找到配置。
    """
    path = os.path.join(os.path.dirname(__file__), "config.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return None

    emb = cfg.get("embedding")
    if not emb or not emb.get("api_key"):
        return None
    return make_siliconflow_embedder(
        emb["api_key"],
        emb.get("base_url", "https://api.siliconflow.cn/v1"),
        emb.get("model", "BAAI/bge-m3"),
    )


def embed_with_cache(embedder, texts, cache, batch_size=64):
    """
    批量算向量，结果写进 cache（text -> vector），已缓存的跳过。

    参数：
        embedder   : embed(text) 或 embed([...]) 函数
        texts      : 要算向量的文字列表
        cache      : {text: vector} 字典（会在原地填充）
        batch_size : 每次请求最多几条（硅基流动批量有大小限制，分批稳妥）

    返回：
        cache（同一字典，原地更新后返回，方便链式使用）
    """
    missing = [t for t in texts if t not in cache]
    for i in range(0, len(missing), batch_size):
        chunk = missing[i:i + batch_size]
        for t, v in zip(chunk, _embed_chunk(embedder, chunk)):
            # 单条还失败时 v 为 None，跳过这条（不写缓存），后续按「无向量」处理
            if v is not None:
                cache[t] = v
    return cache


def _embed_chunk(embedder, chunk):
    """
    算一批文字的向量，返回和 chunk 等长的列表。

    批量请求失败（如服务端瞬时 400）时，自动拆成单条重试；
    单条也失败的置为 None（跳过），不拖垮整场跑。
    """
    try:
        return embedder(chunk)
    except Exception:
        pass

    result = []
    for t in chunk:
        try:
            result.append(embedder(t))
        except Exception:
            result.append(None)
    return result


def cosine(a, b):
    """
    两个向量的余弦相似度（0~1，越大越相关）。
    纯 Python 实现，不依赖 numpy（系统 Python 没装 numpy）。
    """
    if len(a) != len(b):
        raise ValueError(f"向量维度不一致：{len(a)} vs {len(b)}")

    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y

    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def rank_by_similarity(query_vec, items, emb_map, limit=None, min_similarity=None):
    """
    按「query 向量」和每条记忆的向量（从 emb_map 按 text 查）的余弦相似度，
    从高到低排序。

    参数：
        query_vec      : query 的向量（list[float]）
        items          : 记忆列表（每条要有 text 字段）
        emb_map        : {text: vector} 的映射（在内存里，不写回 items.json）
        limit          : 最多返回几条（None = 全返回，但已经排好序）
        min_similarity : 相似度门槛。传了就把余弦 < 该值的记忆砍掉（"够格才留"），
                         不传则无条件按余弦取前 limit（老行为，向后兼容）。
                         加它是因为：向量粗筛无条件塞满 top K，会把「相似度 0.5 上下的
                         噪音」也喂给模型细判；而真相关的记忆相似度明显更高（实测 >= 0.69）。
                         砍掉噪音能把每次细判的喂入量从 100 条降到个位数。

    返回：
        按相似度降序的记忆列表（保持原 item 对象不变，不往上面挂字段）
    """
    scored = []
    for m in items:
        vec = emb_map.get(m.get("text"))
        if vec is None:
            continue
        sim = cosine(query_vec, vec)
        if min_similarity is not None and sim < min_similarity:
            continue
        scored.append((sim, m))

    scored.sort(key=lambda x: x[0], reverse=True)
    result = [m for _, m in scored]
    if limit is not None:
        result = result[:limit]
    return result

