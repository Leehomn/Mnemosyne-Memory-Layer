# test_recall.py —— 测试 recall 模块

from recall import recall, format_recall_block, _expand_conflicts
from item import make_item


def test_recall_returns_top_weighted():
    # 造三条记忆：权重明显不同
    m1 = make_item("我叫南风", "user_said", 0.95, hits=3)          # 权重最高
    m2 = make_item("他胃疼那天我说了难听的话", "user_said", 0.5, hits=0)  # 权重最低
    m3 = make_item("他喜欢打游戏", "her_inference", 0.6, hits=1)

    result = recall([m1, m2, m3], limit=2)

    assert len(result) == 2
    assert result[0]["text"] == "我叫南风"       # 权重最高，排第一
    assert result[1]["text"] == "他喜欢打游戏"    # 权重第二


def test_recall_respects_limit():
    m1 = make_item("我叫南风", "user_said", 0.95, hits=3)
    m2 = make_item("他胃疼那天我说了难听的话", "user_said", 0.5, hits=0)
    m3 = make_item("他喜欢打游戏", "her_inference", 0.6, hits=1)

    one = recall([m1, m2, m3], limit=1)
    assert len(one) == 1
    assert one[0]["text"] == "我叫南风"


def test_format_recall_block_keeps_self_out_of_facts():
    # 关于 AI 自己的事，不进「事实区」，但进独立的「我说过的话」区
    m_user = make_item("我叫南风", "user_said", 0.95, subject="about_user")
    m_self = make_item("他胃疼那天我说了难听的话", "user_said", 0.95, subject="about_self")
    m_guess = make_item("他喜欢打游戏", "her_inference", 0.6)

    text = format_recall_block([m_user, m_self, m_guess])

    assert "我叫南风" in text                      # 事实区有这个
    assert "他喜欢打游戏" in text                   # 猜测区有这个
    assert "我说了难听的话" in text                  # 进了「我说过的话」区
    assert "你之前说过的话" in text                 # 有「我说过的话」分区标题
    # 关键：AI 自己的话不能混进「关于他的事实」区
    fact_block = text.split("你的猜测", 1)[0]
    assert "我说了难听的话" not in fact_block


def fake_llm(prompt):
    # 假模型：总是说「第 1 条相关」
    return "1"


def test_semantic_recall():
    from recall import semantic_recall

    items = [
        make_item("他叫南风", "user_said", 0.9),
        make_item("他爱吃辣", "user_said", 0.9),
        make_item("他在找工作", "user_said", 0.9),
    ]

    # 假模型说「第 1 条（他爱吃辣）相关」
    result = semantic_recall(fake_llm, items, "今天吃啥")

    assert len(result) == 1
    assert result[0]["text"] == "他爱吃辣"


def test_semantic_recall_none():
    from recall import semantic_recall

    items = [make_item("他叫南风", "user_said", 0.9)]

    # 假模型说「无」
    def fake_none(prompt):
        return "无"

    result = semantic_recall(fake_none, items, "随便聊聊")
    assert result == []


def test_semantic_recall_passes_today_date_to_prompt():
    """召回提示词要自动带上「今天的日期」（系统当前日期），让模型能理解
    查询里的相对时间词（前天/上周）。真人聊天也会说「前天」，所以这是真实需求：
    模型得知道今天几号，才能把「前天」换算成对应日期。
    """
    from recall import semantic_recall

    items = [make_item("他 2026-05-25 把迷迭香搬到窗边", "user_said", 0.9)]
    seen = {}

    def capture(prompt):
        seen["prompt"] = prompt
        return "无"

    semantic_recall(capture, items, "帮我按前天算算")

    from datetime import datetime
    expected = datetime.now().strftime("%Y-%m-%d")

    assert expected in seen["prompt"]          # 今天的日期（系统当前）进了提示词
    assert "相对时间" in seen["prompt"]         # 有「把相对时间换算成绝对日期」的提示


# ===== 新增：semantic_recall 的解析容错 =====

def test_semantic_recall_fullwidth_comma():
    """全角逗号不能导致整批相关记忆被静默丢弃（等于这次召回啥也没捞到）。"""
    from recall import semantic_recall

    items = [make_item("他叫南风", "user_said", 0.9),
             make_item("他爱吃辣", "user_said", 0.9)]

    result = semantic_recall(lambda p: "0，1", items, "今天吃啥")
    assert [m["text"] for m in result] == ["他叫南风", "他爱吃辣"]


def test_semantic_recall_with_extra_text():
    from recall import semantic_recall

    items = [make_item("他爱吃辣", "user_said", 0.9)]
    result = semantic_recall(lambda p: "相关的编号：0", items, "今天吃啥")
    assert len(result) == 1


def test_semantic_recall_excludes_deleted():
    """已失效的记忆不该被召回（墓碑过滤）。"""
    from recall import semantic_recall

    alive = make_item("他叫南风", "user_said", 0.9)
    dead = make_item("他叫小鱼", "user_said", 0.9)
    dead["deleted"] = True

    result = semantic_recall(lambda p: "0", [alive, dead], "你叫什么")
    assert [m["text"] for m in result] == ["他叫南风"]


# ===== 新增：format_recall_block 的格式 =====

def test_format_recall_block_structure():
    """事实区/猜测区要真的分开，且括号不能错配。

    旧实现开头写「（」、结尾补「）」，中间还内嵌一对括号，
    喂给模型的提示词结构是乱的，会削弱「哪个能当真」的分区感。
    """
    from recall import format_recall_block

    block = format_recall_block([
        make_item("他叫南风", "user_said", 0.9),
        make_item("他可能爱熬夜", "her_inference", 0.6),
    ])

    assert "关于他的事实" in block
    assert "你的猜测" in block
    assert block.count("（") == block.count("）")   # 括号必须配对


def test_format_recall_block_drops_low_confidence_guesses():
    """低置信度的猜测（<0.6）不该进猜测区，避免 AI 顺着没把握的猜测乱编。

    这是「降低置信度 → 降低出场机会」的最后一环：
    之前猜测区只看来源不看置信度，0.4 的初始猜测照样上场。
    """
    from recall import format_recall_block

    block = format_recall_block([
        make_item("他叫南风", "user_said", 0.9),
        make_item("他可能想家", "her_inference", 0.4),   # 出生默认，没验证过 → 该被拦
        make_item("他可能爱熬夜", "her_inference", 0.7),  # 验证过，够格上场
    ])

    assert "关于他的事实" in block
    assert "你的猜测" in block
    assert "他可能想家" not in block      # 低置信猜测被拦
    assert "他可能爱熬夜" in block        # 高置信猜测保留


def test_format_recall_block_fact_requires_high_confidence():
    """低置信度的说法不能进「可以当真」的事实区。"""
    from recall import format_recall_block

    block = format_recall_block([make_item("他好像爱吃辣", "user_said", 0.5)])
    assert "关于他的事实" not in block


def test_format_recall_block_excludes_about_self():
    """关于 AI 自己的事（about_self）不进事实区，但进独立的「我说过的话」区。"""
    from recall import format_recall_block

    block = format_recall_block([
        make_item("我说了难听的话", "user_said", 0.9, subject="about_self")
    ])
    assert "你之前说过的话" in block
    assert "我说了难听的话" in block
    assert "关于他的事实" not in block   # 不能冒充用户的事实区


def test_format_recall_block_third_party_own_zone():
    """第三方转述（source=third_party，置信 0.5）进独立区，不进事实区也不进猜测区。"""
    from recall import format_recall_block

    block = format_recall_block([
        make_item("房东说钥匙他已经收到了", "third_party", 0.5, who="房东"),
    ])

    assert "第三方转述" in block
    assert "房东说钥匙他已经收到了" in block
    assert "关于他的事实" not in block   # 不能冒充用户亲口的事实
    assert "你的猜测" not in block        # 不是 her_inference，不能进猜测区


def test_confirmed_guess_enters_facts_not_guesses():
    """被验证确认的猜测（her_inference 但置信度 >= 0.8）要进事实区，不能再进猜测区。

    这是「方案乙」：被验证过的记忆应该更强——置信度升到 0.9 后，
    它终于能进「可以当真」的事实区；同时不能再顶着「别当事实」的猜测标签，
    否则一条记忆既被说成事实、又被说成猜测，自相矛盾。
    """
    from recall import format_recall_block

    block = format_recall_block([
        make_item("他可能想家", "her_inference", 0.9),   # 被验证确认，升到 0.9
    ])

    assert "关于他的事实" in block      # 进事实区
    assert "他可能想家" in block        # 文本在
    assert "你的猜测" not in block      # 关键：不能再进猜测区


# ===== 新增：矛盾对召回与格式化 =====

def test_expand_conflicts_brings_partner():
    """命中矛盾对一方，自动带上仍存活的另一方。"""
    a = make_item("他住在合租房，客厅地板是浅灰色", "user_said", 0.9)
    b = make_item("他拖了客厅地板，说地板是米色", "user_said", 0.9)
    a["conflicts_with"] = [{"text": b["text"], "created_at": b["created_at"]}]
    b["conflicts_with"] = [{"text": a["text"], "created_at": a["created_at"]}]

    got = _expand_conflicts([a], [a, b])
    texts = [m["text"] for m in got]
    assert "浅灰" in "".join(texts)
    assert "米色" in "".join(texts)


def test_expand_conflicts_skips_deleted_partner():
    """另一方已被删（墓碑）时，说明矛盾已解决，不带。"""
    a = make_item("他住在合租房，客厅地板是浅灰色", "user_said", 0.9)
    a["conflicts_with"] = [{"text": "米色", "created_at": 123}]

    got = _expand_conflicts([a], [a])
    assert len(got) == 1  # 另一方不在存活池，不带


def test_format_recall_block_marks_conflict_pair():
    """矛盾对在事实区要标「两说未定」，并加段尾提示两版都提。"""
    a = make_item("他住在合租房，客厅地板是浅灰色", "user_said", 0.9)
    b = make_item("他拖了客厅地板，说地板是米色", "user_said", 0.9)
    a["conflicts_with"] = [{"text": b["text"], "created_at": b["created_at"]}]
    b["conflicts_with"] = [{"text": a["text"], "created_at": a["created_at"]}]

    block = format_recall_block([a, b])
    assert "两说未定" in block
    assert "无法确定" in block


def test_format_recall_block_derived_date_annotated():
    """date_kind=derived 的记忆要标「≈日期，由相对时间推算」，提醒模型这是推导的。"""
    m = make_item("他下周三约了人", "user_said", 0.9,
                  event_time="2026-04-15", date_kind="derived")
    block = format_recall_block([m])
    assert "≈2026-04-15" in block
    assert "由相对时间推算" in block


def test_format_recall_block_explicit_date_not_annotated():
    """date_kind=explicit 不额外标注（原文就是日期）。"""
    m = make_item("他 2026-04-13 约了人", "user_said", 0.9,
                  event_time="2026-04-13", date_kind="explicit")
    block = format_recall_block([m])
    assert "≈" not in block
    assert "由相对时间推算" not in block


def test_recall_orders_by_event_time_not_created_at():
    """时间近优先要用 event_time（事件逻辑日期），不是 created_at（系统墙钟）。

    两条记忆 created_at 相同（喂历史那一刻），但事件日期一近一远；召回排序时
    「近的那条」必须排前。这是基准里时间题的根因修复。
    """
    near = make_item("他 2026-05-04 交了稿", "user_said", 0.9,
                     event_time="2026-05-04", date_kind="explicit")
    far = make_item("他 2026-03-01 交了稿", "user_said", 0.9,
                    event_time="2026-03-01", date_kind="explicit")
    # 强制 created_at 相同，排除「靠墙钟顺序」碰巧排对的可能
    far["created_at"] = near["created_at"]

    got = recall([far, near], limit=2, now="2026-05-07")
    assert got[0]["text"] == near["text"]


def test_recall_future_event_not_overweighted():
    """未来事件（event_time 晚于 now）不能被衰减公式抬成异常高权重。

    「下周三的计划」事件日期在 now 之后，age 为负时 0.5**(负) > 1，会把未来
    事件顶到最前。修复后应钳到 0（未来事件权重 = base*hits*confidence，不额外加码）。
    """
    future = make_item("他下周三约了人", "user_said", 0.9,
                       event_time="2026-04-15", date_kind="derived")
    past = make_item("他上周三去面试", "user_said", 0.9,
                     event_time="2026-04-08", date_kind="derived")

    got = recall([future, past], limit=2, now="2026-04-13")
    # 两条 base/conf/hits 相同，age 都为非负后权重应相等；未来不因负 age 被抬到 >1。
    # 这里只断言不会因为负 age 崩掉、且两条都返回。
    assert len(got) == 2


def test_age_label_future_event_shown_as_days_later():
    """未来事件（event_time 晚于 now）标签应显示「N天后」，不是「刚刚」。

    「刚刚」会误导模型以为这事已经发生了；未来计划该标成「未来/N天后」，
    让模型知道这是还没发生的安排。
    """
    from recall import _age_label
    m = make_item("他下周三约了人", "user_said", 0.9,
                  event_time="2026-04-15", date_kind="derived")
    # now=2026-04-13，事件 04-15 → 2 天后
    assert _age_label(m, "2026-04-13") == "2天后"


def test_age_label_today_event_shown_as_today():
    """事件就在今天，标签是「今天」。"""
    from recall import _age_label
    m = make_item("他今天去体检", "user_said", 0.9,
                  event_time="2026-04-13", date_kind="explicit")
    assert _age_label(m, "2026-04-13") == "今天"


def test_recall_pulls_conflict_partner_even_below_limit():
    """矛盾对另一方即使权重低、被 limit 砍掉，也要补回来。

    原写法 _expand_conflicts(alive, alive) 传同一个列表，seen 一开始就含全部，
    整个函数是空操作——注释说的「先扩矛盾对再排序」从来没生效过。
    修复后扩发生在 limit 之后，用全部存活记忆做池。
    """
    high = make_item("他住在合租房，客厅地板是浅灰色", "user_said", 0.95, hits=5)
    low = make_item("他拖了客厅地板，说地板是米色", "user_said", 0.85)
    high["conflicts_with"] = [{"text": low["text"], "created_at": low["created_at"]}]
    low["conflicts_with"] = [{"text": high["text"], "created_at": high["created_at"]}]

    # limit=1 只取权重最高的 high，另一方必须被补进来
    got = recall([high, low], limit=1)
    texts = [m["text"] for m in got]
    assert len(got) == 2
    assert any("浅灰" in t for t in texts)
    assert any("米色" in t for t in texts)


def test_recall_excludes_deleted_before_scoring():
    """墓碑记忆不参与打分，也不该被矛盾对扩容带回来。"""
    alive_m = make_item("他养了狗", "user_said", 0.9)
    dead = make_item("他养了猫", "user_said", 0.9)
    dead["deleted"] = True
    alive_m["conflicts_with"] = [{"text": dead["text"], "created_at": dead["created_at"]}]

    got = recall([alive_m, dead], limit=5)
    assert [m["text"] for m in got] == ["他养了狗"]


def test_expand_conflicts_respects_max_extra():
    """扩容要设上限，免得一个大的「矛盾簇」把召回块撑爆。"""
    from recall import _expand_conflicts

    anchor = make_item("卷卷不吃鸡肉味了", "user_said", 0.9)
    cluster = [make_item(f"旧说法{i}", "user_said", 0.8) for i in range(6)]
    anchor["conflicts_with"] = [{"text": m["text"], "created_at": m["created_at"]}
                                for m in cluster]

    pool = [anchor] + cluster
    assert len(_expand_conflicts([anchor], pool)) == 7        # 不限 → 全带上
    assert len(_expand_conflicts([anchor], pool, max_extra=2)) == 3  # 限 2 → 只带 2


def test_recall_conflict_expansion_capped_at_limit(tmp_path):
    """recall 里扩容上限 = len(top)：最多翻一倍，不会因为多个簇叠起来失控。"""
    anchor = make_item("卷卷不吃鸡肉味了", "user_said", 0.99, hits=10)
    cluster = [make_item(f"旧说法{i}", "user_said", 0.8) for i in range(6)]
    anchor["conflicts_with"] = [{"text": m["text"], "created_at": m["created_at"]}
                                for m in cluster]

    got = recall([anchor] + cluster, limit=2, now="2026-05-12")
    assert len(got) <= 4      # limit=2，最多再补 2 条


def test_split_zones_returns_four_groups():
    """四个分区判据：事实/猜测/第三方/我说过的话。"""
    from recall import _split_zones

    fact = make_item("他养了狗", "user_said", 0.9)
    guess = make_item("他可能压力很大", "her_inference", 0.6)
    tp = make_item("他妈说他换了工作", "third_party", 0.5)
    mine = make_item("我答应帮他改简历", "self_said", 0.9, subject="about_self")
    nobody = make_item("他大概不太高兴", "her_inference", 0.4)

    facts, guesses, third_party, self_said = _split_zones([fact, guess, tp, mine, nobody])
    assert [m["text"] for m in facts] == ["他养了狗"]
    assert [m["text"] for m in guesses] == ["他可能压力很大"]
    assert [m["text"] for m in third_party] == ["他妈说他换了工作"]
    assert [m["text"] for m in self_said] == ["我答应帮他改简历"]
    # 0.4 的猜测四区都不进——这是有意为之，不是漏掉
    all_zones = facts + guesses + third_party + self_said
    assert nobody not in all_zones


def test_is_rendered_matches_zone_rules():
    """is_rendered 要和 format_recall_block 的分区规则完全一致。

    index.semantic_recall_block 用它决定给谁 hits +1。两者一旦不同步，
    就会出现「加了权重却永远不显示」或者「显示了却不算用过」。
    """
    from recall import is_rendered

    shown = [
        make_item("他养了狗", "user_said", 0.9),                        # 事实区
        make_item("他可能压力很大", "her_inference", 0.6),               # 猜测区
        make_item("他妈说他换了工作", "third_party", 0.5),               # 第三方区
        make_item("我答应帮他改简历", "self_said", 0.9, subject="about_self"),  # 我说区
    ]
    hidden = [
        make_item("他大概不太高兴", "her_inference", 0.4),               # 太低，四区都不进
        make_item("他在犹豫", "her_inference", 0.2),                    # 同上
    ]
    for m in shown:
        assert is_rendered(m) is True, m["text"]
    for m in hidden:
        assert is_rendered(m) is False, m["text"]


def test_story_time_used_when_no_event_time():
    """没有 event_time 的条目，年龄要用 story_time（剧情日期），不是 created_at（墙钟）。

    回放基准时 created_at 全是灌历史那一刻（2026-11-09），比题目的 now 还晚，
    算出来是负数、被钳成 0，于是「越没时间信息的记忆权重越高」。
    """
    from recall import _memory_age_days

    m = make_item("他重感情", "user_said", 0.9, story_time="2026-05-14")
    assert m["event_time"] is None
    assert _memory_age_days(m, "2026-05-20") == 6


def test_event_time_wins_over_story_time():
    """event_time 比 story_time 更准（讲的是哪天的事 vs 哪天被记下），优先用它。"""
    from recall import _memory_age_days

    m = make_item("他 2026-05-01 搬了家", "user_said", 0.9,
                  event_time="2026-05-01", date_kind="explicit",
                  story_time="2026-05-19")
    assert _memory_age_days(m, "2026-05-21") == 20


def test_created_at_still_covers_old_items_without_story_time():
    """老数据没有 story_time 字段时，仍回落 created_at——不能把它们全算成 0 天。"""
    from datetime import datetime
    from recall import _memory_age_days

    m = make_item("他养了狗", "user_said", 0.9)
    assert m["story_time"] is None
    m["created_at"] = datetime(2026, 5, 1, 12, 0, 0).timestamp()
    assert _memory_age_days(m, "2026-05-11") == 10


def test_recall_prefers_recent_story_time():
    """两条都没 event_time，只差 story_time：近的那条排前。"""
    old = make_item("他爱吃面", "user_said", 0.9, story_time="2026-03-01")
    new = make_item("他爱吃米饭", "user_said", 0.9, story_time="2026-05-10")
    # 强制 created_at 相同，排除墙钟碰巧排对
    old["created_at"] = new["created_at"]

    got = recall([old, new], limit=2, now="2026-05-12")
    assert got[0]["text"] == new["text"]

