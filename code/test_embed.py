# test_embed.py —— 测试语义向量与余弦粗筛

from embed import cosine, rank_by_similarity, embed_with_cache, _embed_chunk, EMBED_TOP_K
from item import make_item


def test_cosine_identical():
    assert abs(cosine([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]) - 1.0) < 1e-9


def test_cosine_orthogonal():
    assert abs(cosine([1.0, 0.0], [0.0, 1.0]) - 0.0) < 1e-9


def test_cosine_zero_vector():
    # 零向量没有方向，余弦定义为 0，不能除零报错
    assert cosine([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_cosine_dimension_mismatch():
    try:
        cosine([1.0, 0.0], [1.0, 0.0, 0.0])
        assert False, "维度不一致应抛 ValueError"
    except ValueError:
        pass


def test_rank_by_similarity_orders_desc():
    # 用 2 维向量模拟：query 最接近「他爱吃辣」的向量
    qvec = [1.0, 0.0]
    emb_map = {
        "他爱吃辣": [1.0, 0.0],
        "他喜欢篮球": [0.0, 1.0],
        "他叫南风": [0.5, 0.5],
    }
    items = [
        make_item("他喜欢篮球", "user_said", 0.9),
        make_item("他爱吃辣", "user_said", 0.9),
        make_item("他叫南风", "user_said", 0.9),
    ]
    got = rank_by_similarity(qvec, items, emb_map)
    # 最相关的是「他爱吃辣」（余弦 1.0），最不相关的是「他喜欢篮球」（余弦 0.0）
    assert got[0]["text"] == "他爱吃辣"
    assert got[-1]["text"] == "他喜欢篮球"


def test_rank_by_similarity_skips_missing_embedding():
    # 没缓存的记忆要跳过，不能因为一条没向量就全崩
    qvec = [1.0, 0.0]
    emb_map = {"他爱吃辣": [1.0, 0.0]}
    items = [
        make_item("他爱吃辣", "user_said", 0.9),
        make_item("他喜欢篮球", "user_said", 0.9),  # 没有向量
    ]
    got = rank_by_similarity(qvec, items, emb_map)
    assert [m["text"] for m in got] == ["他爱吃辣"]


def test_rank_by_similarity_limit():
    qvec = [1.0, 0.0]
    emb_map = {
        "a": [1.0, 0.0],   # 余弦 1.0
        "b": [1.0, 1.0],   # 余弦 0.707
        "c": [0.0, 1.0],   # 余弦 0.0
    }
    items = [make_item(t, "user_said", 0.9) for t in ("c", "b", "a")]
    got = rank_by_similarity(qvec, items, emb_map, limit=2)
    assert len(got) == 2
    assert got[0]["text"] == "a"
    assert got[1]["text"] == "b"


def test_rank_by_similarity_min_similarity_filters():
    # 传 min_similarity 时，低于门槛的记忆要被砍掉（"够格才留"）
    qvec = [1.0, 0.0]
    emb_map = {
        "a": [1.0, 0.0],   # 余弦 1.0
        "b": [1.0, 1.0],   # 余弦 0.707
        "c": [0.0, 1.0],   # 余弦 0.0
    }
    items = [make_item(t, "user_said", 0.9) for t in ("c", "b", "a")]
    got = rank_by_similarity(qvec, items, emb_map, min_similarity=0.65)
    # c（0.0）被砍，b（0.707）、a（1.0）留下
    assert [m["text"] for m in got] == ["a", "b"]


def test_rank_by_similarity_min_similarity_none_keeps_all():
    # 不传 min_similarity（None）时保持老行为：无条件按余弦排序，不砍
    qvec = [1.0, 0.0]
    emb_map = {
        "a": [1.0, 0.0],
        "c": [0.0, 1.0],
    }
    items = [make_item(t, "user_said", 0.9) for t in ("c", "a")]
    got = rank_by_similarity(qvec, items, emb_map)
    assert [m["text"] for m in got] == ["a", "c"]


def test_embed_with_cache_batches_and_skips():
    # 假 embedder：把每个字映射成固定向量，返回 list of list
    seen = []

    def fake_embedder(texts):
        seen.append(list(texts))
        return [[float(ord(c))] for c in texts]

    cache = {}
    embed_with_cache(fake_embedder, ["甲", "乙", "丙"], cache, batch_size=2)
    # 分批：["甲","乙"] 一批，["丙"] 一批
    assert cache["甲"] == [float(ord("甲"))]
    assert cache["丙"] == [float(ord("丙"))]
    assert len(seen) == 2

    # 再调一次，已缓存的跳过，不重复请求
    seen.clear()
    embed_with_cache(fake_embedder, ["甲", "丁"], cache, batch_size=2)
    assert seen == [["丁"]]
    assert "丁" in cache


def test_embed_top_k_constant():
    # 粗筛上限要取大一点（宁可多留不漏），但不能是「全库」
    assert EMBED_TOP_K > 0


def test_embed_chunk_batch_ok():
    # 批量成功时原样返回
    def ok(chunk):
        return [[float(ord(c))] for c in chunk]

    assert _embed_chunk(ok, ["甲", "乙"]) == [[float(ord("甲"))], [float(ord("乙"))]]


def test_embed_chunk_batch_fail_then_single_retry():
    # 批量失败 → 拆单条重试；单条成功要返回正确向量
    calls = []

    def flaky(chunk):
        if isinstance(chunk, str):
            calls.append(("single", chunk))
            return [float(ord(chunk))]
        calls.append(("batch", tuple(chunk)))
        raise RuntimeError("瞬时 400")

    got = _embed_chunk(flaky, ["甲", "乙"])
    assert got == [[float(ord("甲"))], [float(ord("乙"))]]
    assert ("batch", ("甲", "乙")) in calls
    assert ("single", "甲") in calls
    assert ("single", "乙") in calls


def test_embed_chunk_single_fail_skips():
    # 批量失败、单条也失败 → 该条置 None，不影响其它条
    state = {"batch_ok": False, "bad": "乙"}

    def flaky(chunk):
        if isinstance(chunk, str):
            if chunk == state["bad"]:
                raise RuntimeError("单条也失败")
            return [float(ord(chunk))]
        if state["batch_ok"]:
            return [[float(ord(c))] for c in chunk]
        raise RuntimeError("瞬时 400")

    got = _embed_chunk(flaky, ["甲", "乙", "丙"])
    assert got[0] == [float(ord("甲"))]
    assert got[1] is None
    assert got[2] == [float(ord("丙"))]


def test_embed_with_cache_skips_failed():
    # 批量失败+单条失败时，该条不写缓存，其余正常写入
    def flaky(chunk):
        if isinstance(chunk, str):
            if chunk == "乙":
                raise RuntimeError("单条也失败")
            return [float(ord(chunk))]
        raise RuntimeError("瞬时 400")

    cache = {}
    embed_with_cache(flaky, ["甲", "乙"], cache, batch_size=8)
    assert "甲" in cache
    assert "乙" not in cache
