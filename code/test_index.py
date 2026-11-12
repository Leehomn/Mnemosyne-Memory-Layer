# test_index.py —— 测试 index 模块（Cognition 统一入口）

import time
from index import Cognition, jaccard
from item import make_item
from store import load_items, save_items


def test_remember_and_recall(tmp_path):
    cog = Cognition(data_dir=str(tmp_path))
    cog.remember("我叫南风", source="user_said", confidence=0.95)
    cog.remember("他喜欢打游戏", source="her_inference", confidence=0.6)

    block = cog.recall_block(limit=8)
    assert "我叫南风" in block
    assert "他喜欢打游戏" in block
    assert "事实" in block and "猜测" in block


def test_remember_invalid(tmp_path):
    cog = Cognition(data_dir=str(tmp_path))
    result = cog.remember("测试", source="unknown", confidence=0.9)
    assert result is None


def test_no_duplicate(tmp_path):
    cog = Cognition(data_dir=str(tmp_path))
    cog.remember("我叫南风", source="user_said", confidence=0.95)
    result = cog.remember("我叫南风", source="user_said", confidence=0.95)
    assert result is not None
    assert result["occurrences"] == 2

    left = load_items(cog.path)
    same = [m for m in left if m["text"] == "我叫南风"]
    assert len(same) == 1


def test_similar_dedup(tmp_path):
    cog = Cognition(data_dir=str(tmp_path))
    cog.remember("我爱吃辣", source="user_said", confidence=0.9)
    result = cog.remember("他爱吃辣", source="user_said", confidence=0.9)
    assert result is not None
    assert result["occurrences"] == 2

    left = load_items(cog.path)
    assert len(left) == 1


def test_maintain(tmp_path):
    cog = Cognition(data_dir=str(tmp_path))
    old_item = make_item("一条很老的记忆", "observed", 0.5,
                         created_at=time.time() - 999*86400)
    new_item = make_item("一条新记忆", "user_said", 0.95)
    save_items([old_item, new_item], cog.path)

    removed = cog.maintain()
    assert removed == 1

    # 软删除：过期的条目不再物理删，而是标墓碑留在库里
    left = load_items(cog.path)
    assert len(left) == 2

    # 老的那条被标了墓碑，新的一条还活着
    old = [m for m in left if m["text"] == "一条很老的记忆"]
    new = [m for m in left if m["text"] == "一条新记忆"]
    assert old and old[0]["deleted"] is True
    assert old[0]["deleted_reason"] == "衰减过期"
    assert new and new[0]["deleted"] is False

    # 墓碑不会被召回（recall 先过滤 deleted）
    block = cog.recall_block(limit=8)
    assert "一条很老的记忆" not in block
    assert "一条新记忆" in block


def test_jaccard():
    assert jaccard("辣", "辣") == 1.0
    assert jaccard("辣", "甜") == 0.0
    assert 0 < jaccard("我爱吃辣", "他爱吃辣") < 1.0


def test_enhance(tmp_path):
    cog = Cognition(data_dir=str(tmp_path))
    cog.remember("我爱吃辣", source="user_said", confidence=0.9)
    result = cog.remember("他爱吃辣", source="user_said", confidence=0.9)
    assert result is not None
    assert result["occurrences"] == 2

def test_promote_state_to_trait(tmp_path):
    from item import IMPRESSION_HALF_LIVES

    cog = Cognition(data_dir=str(tmp_path))

    # 记一条 state（动态表现），然后让它「反复出现」3 次
    cog.remember("他最近很努力", source="observed", layer="impression", kind="state")
    cog.remember("他最近很努力", source="observed", layer="impression", kind="state")
    result = cog.remember("他最近很努力", source="observed", layer="impression", kind="state")

    # 第 3 次出现 → 应该晋升成 trait
    assert result["kind"] == "trait"
    assert result["half_life"] == 3650
    assert result["occurrences"] == 3

def test_consolidate_method(tmp_path):
    from index import Cognition

    def fake_llm(prompt):
        return "[事实] 他爱吃辣"

    cog = Cognition(data_dir=str(tmp_path), llm=fake_llm)

    # 记几条 episode
    cog.remember("他说无辣不欢", source="user_said", layer="episode")
    cog.remember("他说吃火锅要特辣", source="user_said", layer="episode")

    # 夜间整合（自动读 episode）
    added = cog.consolidate()

    assert added == 1

    # 库里应该多了一条 impression
    block = cog.recall_block(limit=10)
    assert "他爱吃辣" in block

def test_consolidate_promotes_existing(tmp_path):
    from index import Cognition

    def fake_llm(prompt):
        return "[事实] 他爱吃辣"

    cog = Cognition(data_dir=str(tmp_path), llm=fake_llm)

    # 库里先有一条「他爱吃辣」的印象（state）
    cog.remember("他爱吃辣", source="observed", layer="impression", kind="state")

    # 又积累了一堆事件（反复说吃辣）
    cog.remember("他说无辣不欢", source="user_said", layer="episode")
    cog.remember("他说火锅要特辣", source="user_said", layer="episode")

    # 夜间整合
    cog.consolidate()

    # 关键：库里应该只有「一条」关于吃辣的记忆（没新建重复的）
    items = load_items(cog.path)
    chila = [m for m in items if "辣" in m.get("text", "")]
    print("吃辣相关的记忆条数：", len(chila))
    for m in chila:
        print("  -", m["text"], "| occurrences =", m.get("occurrences"))

def test_conflict_marks_deleted(tmp_path):
    from index import Cognition

    # 假模型：回答「推翻：0」（第 0 条被明确纠错推翻）
    def fake_llm(prompt):
        # 冲突检测时会返回「推翻：0」（第 0 条冲突）
        if "推翻" in prompt:
            return "推翻：0"
        # 其他情况返回无
        return "推翻：无\n矛盾：无"

    cog = Cognition(data_dir=str(tmp_path), llm=fake_llm)

    # 先存「他爱吃辣」
    cog.remember("他爱吃辣", source="user_said", confidence=0.9)

    # 用户说「我记错了，我不吃辣」→ 触发冲突检测（明确纠错 → 推翻）
    cog.remember("我记错了，我不吃辣", source="user_said", confidence=0.9)

    # 检查：「他爱吃辣」应该被标 deleted=True
    from store import load_items
    items = load_items(cog.path)
    chila = [m for m in items if "爱吃辣" in m.get("text", "")]
    assert len(chila) == 1
    assert chila[0]["deleted"] == True          # 被标失效
    assert chila[0]["superseded_by"] == "我记错了，我不吃辣"  # 记录了被谁推翻


def test_conflict_contradiction_links(tmp_path):
    """无纠错信号的「同维度不同值」→ 两版都留，双向标 conflicts_with。

    这是「没解释的矛盾」的修复核心：旧版不再被删成墓碑，
    而是和新版互相标「两说未定」，召回时一起带出。
    """
    from index import Cognition

    def fake_llm(prompt):
        if "推翻" in prompt:
            return "推翻：无\n矛盾：0"
        return "推翻：无\n矛盾：无"

    cog = Cognition(data_dir=str(tmp_path), llm=fake_llm)

    # 旧：地板浅灰（无纠错信号，只是后来说了米色）
    cog.remember("他住在合租房，客厅地板是浅灰色", source="user_said", confidence=0.9)
    # 新：地板米色，没有「我记错了」
    cog.remember("他拖了客厅地板，说地板是米色", source="user_said", confidence=0.9)

    from store import load_items
    items = load_items(cog.path)
    assert all(not m.get("deleted") for m in items), "无纠错信号的两版都不该被删"

    grey = [m for m in items if "浅灰" in m["text"]][0]
    beige = [m for m in items if "米色" in m["text"]][0]

    # 双向标注
    grey_refs = [(x["text"], x["created_at"]) for x in grey.get("conflicts_with", [])]
    beige_refs = [(x["text"], x["created_at"]) for x in beige.get("conflicts_with", [])]
    assert (beige["text"], beige["created_at"]) in grey_refs
    assert (grey["text"], grey["created_at"]) in beige_refs


def test_contradiction_not_merged_by_dedup(tmp_path):
    """字面高度相似的两个矛盾版本不能被去重合并吞掉。

    阶段2 P12 实测踩到：『两条封条』vs『三条封条』jaccard>=0.5，
    去重循环抢在矛盾对挂钩之前把新版吞进旧版（occurrences 变 2），
    矛盾另一方消失，召回只剩一版。矛盾方必须跳过合并、强制新增。
    """
    from index import Cognition

    def fake_llm(prompt):
        if "推翻" in prompt:
            return "推翻：无\n矛盾：0"
        return "推翻：无\n矛盾：无"

    cog = Cognition(data_dir=str(tmp_path), llm=fake_llm)

    # 旧：两条封条
    cog.remember("周一到的黄油箱外面有两条封条", source="user_said", confidence=0.9)
    # 新：三条封条（无纠错信号，仅一个数字之差，jaccard 高，会被判矛盾）
    cog.remember("周一到的黄油箱外面有三条封条", source="user_said", confidence=0.9)

    from store import load_items
    items = load_items(cog.path)
    assert all(not m.get("deleted") for m in items), "两版都不该被删"
    assert len(items) == 2, "矛盾双方不能被去重合并成一条"

    two = [m for m in items if "两条封条" in m["text"]][0]
    three = [m for m in items if "三条封条" in m["text"]][0]
    assert two["occurrences"] == 1 and three["occurrences"] == 1

    # 双向矛盾对挂钩
    two_refs = [(x["text"], x["created_at"]) for x in two.get("conflicts_with", [])]
    assert (three["text"], three["created_at"]) in two_refs


def test_inference_does_not_trigger_conflict(tmp_path):
    """归纳的印象（observed/her_inference）之间不互相判冲突。

    这是「印象 vs 印象」误删的根因：consolidate 归纳出的概括/推测，
    会被 find_conflicts 拿去和别的印象比对，互相判冲突软删，把 50.9%
    的记忆都标成墓碑。只有 user_said（用户亲口说的）才有资格推翻旧记忆，
    observed/her_inference 是概括或推断，没资格推翻另一条记忆。
    """
    from index import Cognition

    calls = []

    def fake_llm(prompt):
        calls.append(prompt)
        # 若真的调了冲突检测，返回「0」会把第 0 条标墓碑
        return "0"

    cog = Cognition(data_dir=str(tmp_path), llm=fake_llm)

    # 先有一条印象
    cog.remember("他最近心思被图纸占据，容易焦虑失眠",
                 source="her_inference", layer="impression", kind="state")

    # 又归纳出一条不同角度但同话题的印象 → 不该触发冲突检测
    cog.remember("他近期有图纸相关的工作任务，但处于松弛期",
                 source="observed", layer="impression", kind="state")

    # 关键：find_conflicts 压根不该被调用（无「语义冲突」提示词）
    assert not any("推翻" in p for p in calls), "归纳的印象不该触发冲突检测"

    # 两条印象都应该活着，没有谁被标墓碑
    from store import load_items
    items = load_items(cog.path)
    assert all(not m.get("deleted") for m in items)
    assert len(items) == 2


# ===== 链路测试：模块单独测都对，接起来会不会断电 =====

def test_guess_gets_low_confidence(tmp_path):
    """猜的东西不传置信度时，必须拿 0.4，而不是和「他说的」一样的 0.9。"""
    cog = Cognition(data_dir=str(tmp_path))
    item = cog.remember("他可能喜欢安静", source="her_inference")
    assert item["confidence"] == 0.4


def test_verify_finds_the_guess(tmp_path):
    """reconstruct → remember → verify：这条线以前一次都没通。

    改前猜测一律 0.9，掉不出 verify 要的 0.4~0.7 区间，永远筛不到人。
    """
    from reconstruct import reconstruct
    from verify import find_uncertain_impressions

    cog = Cognition(data_dir=str(tmp_path))
    reconstruct(lambda p: "[猜测] 他喜欢安静",
                ["他说人多的时候有点累"], cog.remember)

    found = find_uncertain_impressions(load_items(cog.path))
    assert len(found) == 1
    assert found[0]["text"] == "他喜欢安静"


def test_repeat_does_not_bump_hits(tmp_path):
    """用户重复说同一句话：occurrences 涨（出现次数），hits 不涨（没被「想起」）。

    这是「拆开两个计数器」的核心：hits 只该由语义召回（AI 主动想起来用）触发，
    用户重说算 occurrences，不能混成 hits，否则晋升和用进废退的计数全错。
    """
    cog = Cognition(data_dir=str(tmp_path))
    cog.remember("我爱吃辣", source="user_said")
    result = cog.remember("我爱吃辣", source="user_said")

    assert result["occurrences"] == 2
    assert result["hits"] == 0


def test_semantic_recall_bumps_hits(tmp_path):
    """语义召回命中：hits +1（被想起来了），且只 +1 命中的那几条。

    fake_llm 必须区分两种调用：
    - 冲突检测（提示词含「语义冲突」）→ 回「无」，表示没有冲突；
    - 语义召回（提示词含「当前这句话」）→ 按用户原话判断命中哪条。
    否则同一个「0」在冲突检测里会被当成「第 0 条冲突」，把无辜记忆标成墓碑。
    """
    def fake_llm(prompt):
        if "语义冲突" in prompt:
            return "无"          # 冲突检测：无冲突
        if "今天吃什么" in prompt:
            return "0"           # 召回：只命中「我爱吃辣」（第 0 条）
        return "无"

    cog = Cognition(data_dir=str(tmp_path), llm=fake_llm)
    cog.remember("我爱吃辣", source="user_said")
    cog.remember("我喜欢打篮球", source="user_said")

    cog.semantic_recall_block("今天吃什么", limit=5)

    items = load_items(cog.path)
    spicy = [m for m in items if m["text"] == "我爱吃辣"]
    basketball = [m for m in items if m["text"] == "我喜欢打篮球"]

    # 只有「我爱吃辣」被命中，hits 应该 +1
    assert spicy[0]["hits"] == 1
    # 「打篮球」没被召回，hits 应该保持 0
    assert basketball[0]["hits"] == 0


def test_semantic_recall_block_forwards_now(tmp_path):
    """语义召回块的 now 参数要透传给 semantic_recall，写进「今天的日期」。

    虚拟时间（跑基准时题目的 now）就靠这个透传进召回提示词，
    让模型能把查询里的「前天/上周」换算成绝对日期。不传则回退系统今天。
    """
    seen = {}

    def fake_llm(prompt):
        seen["prompt"] = prompt
        return "无"

    cog = Cognition(data_dir=str(tmp_path), llm=fake_llm)
    cog.remember("他 2026-05-25 把迷迭香搬到窗边", source="user_said")

    cog.semantic_recall_block("迷迭香是哪天搬的", limit=5, now="2026-05-27")

    assert "今天的日期是 2026-05-27" in seen["prompt"]


def test_embed_cache_reused_across_recalls(tmp_path):
    """embedder 缓存要活在整个 Cognition 实例里：同一个人物只向量化一次。

    否则每次 semantic_recall_block 都传空 {}，同一批记忆被反复打向量，
    跑基准时 82 题 = 82 次全库向量化，纯浪费 embedding 请求和时间。
    """
    calls = []

    def fake_embedder(x):
        calls.append(x)
        if isinstance(x, str):
            return [0.0, 0.0, 1.0]
        return [[0.0, 0.0, 1.0] for _ in x]

    def fake_llm(prompt):
        return "无"

    cog = Cognition(data_dir=str(tmp_path), llm=fake_llm, embedder=fake_embedder)
    cog.remember("他 2026-05-25 把迷迭香搬到窗边", source="user_said")
    cog.remember("他 2026-05-27 把迷迭香换到阴处", source="user_said")

    cog.semantic_recall_block("迷迭香哪天搬的", limit=5)
    # 第二次：记忆文本全命中缓存，embedder 只该被 query 调用一次（str），
    # 不该再批量重算那 2 条记忆。
    cog.semantic_recall_block("迷迭香哪天换的", limit=5)

    batch_calls = [c for c in calls if isinstance(c, list)]
    # 只有第一次召回时批量算过 2 条记忆；第二次全部命中缓存，批量调用为 0
    assert len(batch_calls) == 1


def test_consolidate_marks_state_and_digests(tmp_path):
    """夜间整合出来的印象 kind 必须是 state；事件消化过就不该再被吃一遍。

    没有 digested 标记的话，同一批事件每晚重复归纳一次，
    三晚就能把一条印象顶成永久的 trait —— 一条新证据都没有。
    """
    cog = Cognition(data_dir=str(tmp_path), llm=lambda p: "[事实] 他爱吃辣")
    cog.remember("他说无辣不欢", source="user_said", layer="episode")
    cog.remember("他说火锅要特辣", source="user_said", layer="episode")

    added = cog.consolidate()
    assert added == 1

    items = load_items(cog.path)
    impression = [m for m in items if m.get("layer") == "impression"]
    assert impression and impression[0]["kind"] == "state"
    assert impression[0]["occurrences"] == 1        # 只被归纳过一次

    # 再跑一次：这批事件已经消化过，什么都不该发生
    assert cog.consolidate() == 0
    items = load_items(cog.path)
    impression = [m for m in items if m.get("layer") == "impression"]
    assert impression[0]["occurrences"] == 1
    assert impression[0]["kind"] == "state"


def test_consolidate_skips_self_said(tmp_path):
    """AI 自己说过的话（about_self）不能被拿去归纳「用户的规律」。

    否则 AI 的建议/自述会混进「对他这个人的认识」，污染归纳结果。
    """
    from index import Cognition

    # 假模型：归纳时把喂进来的事件原样输出成 [事实]（除 about_self 外不该出现）
    def fake_llm(prompt):
        if "事件：" in prompt:
            return "[事实] 他爱吃辣"
        return "无"

    cog = Cognition(data_dir=str(tmp_path), llm=fake_llm)

    # 一条用户事件 + 一条 AI 自述事件
    cog.remember("他说无辣不欢", source="user_said", layer="episode")
    cog.remember("我建议他理票先按日期分堆", source="self_said", layer="episode",
                 subject="about_self")

    cog.consolidate()

    # 归纳输入里不该包含 about_self 的条目——AI 自述事件不能被消化
    items = load_items(cog.path)
    self_said_episode = [m for m in items
                         if m.get("subject") == "about_self"
                         and m.get("layer") == "episode"]
    # 它还在，且没被标 digested（没参与归纳）
    assert self_said_episode and not self_said_episode[0].get("digested")


def test_remember_skips_tombstone(tmp_path):
    """墓碑不能被去重合并：用户改口说回一条已被推翻的话，新话必须另起一条，
    而不是被吞进死记录里（否则召回时又被过滤，等于白说）。"""
    from index import Cognition

    def fake_llm(prompt):
        # 冲突检测时不判冲突（避免干扰），其余返回无
        return "无"

    cog = Cognition(data_dir=str(tmp_path), llm=fake_llm)

    # 先存「他叫小鱼」
    cog.remember("他叫小鱼", source="user_said", confidence=0.9)

    # 手动把「他叫小鱼」标成墓碑（模拟被推翻）
    items = load_items(cog.path)
    items[0]["deleted"] = True
    items[0]["deleted_reason"] = "被新信息推翻"
    save_items(items, cog.path)

    # 用户又改口说「他叫小鱼」——不该被吞进墓碑
    cog.remember("他叫小鱼", source="user_said", confidence=0.9)

    left = load_items(cog.path)
    # 应该有一条活「他叫小鱼」+ 一条墓碑「他叫小鱼」
    alive = [m for m in left if m["text"] == "他叫小鱼" and not m.get("deleted")]
    assert len(alive) == 1
    assert alive[0]["deleted"] is False


def test_maintain_vacuums_old_tombstone(tmp_path):
    """墓碑躺太久（超过 TOMBSTONE_RETENTION_DAYS）要被物理清理，防止死人堆满。"""
    from index import TOMBSTONE_RETENTION_DAYS

    cog = Cognition(data_dir=str(tmp_path))
    old_tombstone = make_item("一条早该清掉的墓碑", "observed", 0.5)
    old_tombstone["deleted"] = True
    old_tombstone["deleted_reason"] = "衰减过期"
    old_tombstone["deleted_at"] = time.time() - (TOMBSTONE_RETENTION_DAYS + 10) * 86400

    fresh_tombstone = make_item("一条刚过期的墓碑", "observed", 0.5)
    fresh_tombstone["deleted"] = True
    fresh_tombstone["deleted_reason"] = "衰减过期"
    fresh_tombstone["deleted_at"] = time.time() - 5 * 86400

    save_items([old_tombstone, fresh_tombstone], cog.path)

    cog.maintain()

    left = load_items(cog.path)
    texts = [m["text"] for m in left]
    assert "一条早该清掉的墓碑" not in texts     # 躺太久，被物理删
    assert "一条刚过期的墓碑" in texts          # 还没到清理时间，留着

def test_consolidate_skips_tombstone(tmp_path):
    """墓碑（deleted）不能被夜间整合拿去归纳。

    否则已被反义推翻的旧事件会被重新捞起来总结，甚至反过来把
    「戒辣」这类最新事实又标死（通电验证实测踩到过这个 bug）。

    假模型基于「喂进来的事件」归纳：事件列表里有哪些活事件，
    它就原样归纳出哪些印象。这样墓碑漏没漏进归纳输入，一目了然。
    """
    from index import Cognition

    def fake_llm(prompt):
        if "事件：" in prompt:
            body = prompt.split("事件：", 1)[1].split("【严格输出格式】", 1)[0]
            lines = [ln.strip("- ").strip() for ln in body.splitlines()
                     if ln.strip().startswith("- ")]
            return "\n".join(f"[事实] {ln}" for ln in lines)
        return "无"

    cog = Cognition(data_dir=str(tmp_path), llm=fake_llm)

    # 一条活事件 + 一条墓碑事件
    cog.remember("他最近戒辣了", source="user_said", layer="episode")
    cog.remember("他超爱吃辣", source="user_said", layer="episode")
    items = load_items(cog.path)
    for m in items:
        if m["text"] == "他超爱吃辣":
            m["deleted"] = True
            m["deleted_reason"] = "被新信息推翻"
    save_items(items, cog.path)

    # 夜间整合：归纳输入里不该包含墓碑「爱吃辣」
    cog.consolidate()

    # 关键：整个记忆库里，不该有任何「爱吃辣」的活印象/条目（墓碑除外）
    items = load_items(cog.path)
    spicy_live = [m for m in items
                  if "爱吃辣" in m.get("text", "") and not m.get("deleted")]
    assert spicy_live == [], "墓碑「爱吃辣」不该被归纳成活条目"


def test_digested_episode_not_merged(tmp_path):
    """已被夜间整合消化过的 episode，不再参与去重合并。

    否则「第二遍说相似的话」会被吞进一条已经 digested 的旧事件里，
    夜里归纳再也看不见它，晋升证据（occurrences）永远到不了 3。
    """
    from index import Cognition

    def fake_llm(prompt):
        # 冲突检测不判冲突，避免干扰
        return "无"

    cog = Cognition(data_dir=str(tmp_path), llm=fake_llm)

    # 第 1 天：说「找工作挺累的」，夜里整合后它变成 digested
    cog.remember("找工作挺累的", source="user_said", layer="episode")
    items = load_items(cog.path)
    items[0]["digested"] = True
    save_items(items, cog.path)

    # 第 2 天：又说几乎一样的话「找工作好累啊」
    # 因为旧的那条已经 digested，不该被合并，应该记成一条新 episode
    result = cog.remember("找工作好累啊", source="user_said", layer="episode")

    # 关键断言：新话没有被吞进旧条目，而是独立成了一条
    items = load_items(cog.path)
    assert len(items) == 2
    # 新那条的 occurrences 应该是 1（没被合并撑大）
    assert result["occurrences"] == 1
    # 旧那条的 occurrences 应该还是 1（没吃到新话）
    old = [m for m in items if m["text"] == "找工作挺累的"][0]
    assert old["occurrences"] == 1