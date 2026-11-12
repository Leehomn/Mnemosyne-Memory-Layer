# test_conflict.py —— 测试冲突检测

from conflict import find_conflicts, _preselect, _parse_conflict_reply
from item import make_item


def _fake_embedder(vectors):
    """造一个假的向量函数：text -> 给定向量（按传入顺序）。"""
    def embed(text):
        if isinstance(text, str):
            return vectors[0]
        return vectors
    return embed


def _items():
    # 两条字面都和「吃辣/饮食」沾边，粗筛不会砍掉，编号解析测试才能独立验证。
    return [
        make_item("他爱吃辣", "user_said", 0.9),
        make_item("他爱吃火锅", "user_said", 0.9),
    ]


def test_no_conflict():
    assert find_conflicts(lambda p: "无", "他喜欢音乐", _items()) == ([], [])


def test_semicolon_comma():
    """模型输出「推翻：0,1」（半角逗号，标准情况）。"""
    sup, con = find_conflicts(lambda p: "推翻：0,1", "他不吃辣了", _items())
    assert [m["text"] for m in sup] == ["他爱吃辣", "他爱吃火锅"]
    assert con == []


def test_fullwidth_comma():
    """中文模型经常输出全角逗号。旧的 split(",") 会把整批冲突静默丢掉。"""
    sup, con = find_conflicts(lambda p: "推翻：0，1", "他不吃辣了", _items())
    assert [m["text"] for m in sup] == ["他爱吃辣", "他爱吃火锅"]


def test_ideographic_comma():
    """顿号分隔。"""
    sup, con = find_conflicts(lambda p: "推翻：0、1", "他不吃辣了", _items())
    assert len(sup) == 2


def test_with_extra_text():
    """模型多说一句「冲突的编号是…」时，编号仍要被认出来。"""
    sup, con = find_conflicts(lambda p: "推翻的编号：0", "他不吃辣了", _items())
    assert [m["text"] for m in sup] == ["他爱吃辣"]


def test_out_of_range_ignored():
    """越界编号要忽略，不能 IndexError。"""
    assert find_conflicts(lambda p: "推翻：5,99", "x", _items()) == ([], [])


def test_duplicate_ids_not_repeated():
    """同一个编号重复出现时不能返回两条一样的记忆。"""
    sup, con = find_conflicts(lambda p: "推翻：0,0,0", "他不吃辣了", _items())
    assert len(sup) == 1


def test_empty_reply():
    assert find_conflicts(lambda p: "", "x", _items()) == ([], [])


def test_deleted_items_excluded():
    """已失效的记忆不该再参与冲突判断（否则会对一条墓碑反复标记）。"""
    items = _items()
    items[0]["deleted"] = True          # 「他爱吃辣」已被推翻

    # 过滤后只剩「他爱吃火锅」，编号 0 指向它 —— 不能是墓碑那条
    sup, con = find_conflicts(lambda p: "推翻：0", "他不吃辣了", items)
    assert [m["text"] for m in sup] == ["他爱吃火锅"]


def test_all_deleted_skips_llm():
    """全部失效时不该白调一次模型。"""
    items = _items()
    for m in items:
        m["deleted"] = True

    calls = []
    found = find_conflicts(lambda p: calls.append(p) or "推翻：0", "新的话", items)
    assert found == ([], [])
    assert calls == []


def test_kind_labeled_in_prompt():
    """提示词必须把旧记忆的 kind 标注出来（trait→长期习惯、state→近期状态），
    这样模型才能区分「长期偏好 vs 近期状态」、避免误判冲突。"""
    items = [
        make_item("他爱吃辣", "user_said", 0.9, layer="impression", kind="trait"),
        make_item("他最近压力大", "user_said", 0.9, layer="impression", kind="state"),
    ]
    seen = []

    def llm(prompt):
        seen.append(prompt)
        return "推翻：无\n矛盾：无"

    find_conflicts(llm, "他最近戒辣了", items)
    prompt = seen[0]
    assert "长期习惯/嗜好" in prompt
    assert "近期状态/行为" in prompt


def test_state_does_not_overthrow_trait():
    """「近期状态」不推翻「长期嗜好」：模型看到 kind 标注后应判并存、不冲突。"""
    items = [
        make_item("他爱吃辣", "user_said", 0.9, layer="impression", kind="trait"),
    ]

    # 假模型：收到带「长期习惯/嗜好」标注的提示词，判断「他最近戒辣」是状态变化 → 无
    found = find_conflicts(lambda p: "推翻：无\n矛盾：无", "他最近戒辣了", items)
    assert found == ([], [])


def test_dimension_rule_in_prompt():
    """提示词必须写清「不同事实维度不算推翻也不算矛盾」，并用生日这个实际踩过的坑做例子。"""
    items = [
        make_item("他记得老曹的生日是六月九号", "user_said", 0.9),
    ]
    seen = []

    def llm(prompt):
        seen.append(prompt)
        return "推翻：无\n矛盾：无"

    find_conflicts(llm, "老曹生日那天他发了条消息", items)
    prompt = seen[0]
    assert "不同事实维度" in prompt
    assert "老曹生日是六月九号" in prompt
    assert "生日那天我发了条消息" in prompt


def test_summarization_rule_in_prompt():
    """提示词必须写清「概括/细化/从属不算推翻也不算矛盾」。"""
    items = [
        make_item("3-23 他肩膀发紧、脑子木", "user_said", 0.9),
    ]
    seen = []

    def llm(prompt):
        seen.append(prompt)
        return "推翻：无\n矛盾：无"

    find_conflicts(llm, "这两天他肩膀有点发紧", items)
    prompt = seen[0]
    assert "概括/细化/从属" in prompt
    assert "这两天他肩膀有点发紧" in prompt
    assert "其实不是" in prompt


def test_two_segment_parse():
    """标准两段输出：推翻段和矛盾段各自解析。

    注意：find_conflicts 会先 _preselect 按 Jaccard 重排 items，编号基于
    重排后的顺序，所以这里按「集合」断言，不纠结顺序（分段解析的精确行为
    已由 test_parse_conflict_reply_* 直接覆盖）。
    """
    items = _items() + [make_item("他爱吃面", "user_said", 0.9)]
    sup, con = find_conflicts(lambda p: "推翻：0\n矛盾：1,2", "他吃辣火锅面", items)
    assert [m["text"] for m in sup] == ["他爱吃火锅"]
    assert {m["text"] for m in con} == {"他爱吃辣", "他爱吃面"}


def test_contradiction_only_segment():
    """只有矛盾段，没有推翻段。"""
    items = _items()
    sup, con = find_conflicts(lambda p: "矛盾：0", "他吃辣火锅", items)
    assert sup == []
    assert [m["text"] for m in con] == ["他爱吃火锅"]


def test_plain_numbers_default_to_contradiction():
    """认不出「推翻/矛盾」分段的纯数字输出 → 默认全矛盾（都不删），呼应宁可漏删不可乱删。"""
    items = _items()
    sup, con = find_conflicts(lambda p: "0,1", "他吃辣火锅", items)
    assert sup == []
    assert {m["text"] for m in con} == {"他爱吃辣", "他爱吃火锅"}


def test_parse_conflict_reply_plain_numbers():
    """_parse_conflict_reply 纯数字 → 全矛盾。"""
    sup, con = _parse_conflict_reply("0,1", 3)
    assert sup == []
    assert con == [0, 1]


def test_parse_conflict_reply_both_segments():
    sup, con = _parse_conflict_reply("推翻：0,2\n矛盾：1", 3)
    assert sup == [0, 2]
    assert con == [1]


def test_parse_conflict_reply_none():
    assert _parse_conflict_reply("无", 3) == ([], [])


def test_preselect_drops_unrelated():
    """话题粗筛：新话「狗叫瓦片」不该和「他肩膀紧」这类字面完全不沾边的旧话比对。"""
    items = [
        make_item("他肩膀发紧", "user_said", 0.9),
        make_item("他的狗叫瓦片", "user_said", 0.9),
    ]
    got = _preselect("他养了狗叫瓦片", items)
    texts = [m["text"] for m in got]
    assert "他的狗叫瓦片" in texts
    assert "他肩膀发紧" not in texts


def test_preselect_keeps_related():
    """字面沾边的旧话要留下（哪怕语义是反义，也得交给模型细判，不能粗筛砍掉）。"""
    items = [
        make_item("他爱吃辣", "user_said", 0.9),
        make_item("他喜欢篮球", "user_said", 0.9),
    ]
    got = _preselect("他不吃辣了", items)
    texts = [m["text"] for m in got]
    assert "他爱吃辣" in texts


def test_preselect_empty_when_no_overlap():
    """完全不沾边时返回空，find_conflicts 不该再调模型。"""
    items = [
        make_item("他肩膀发紧", "user_said", 0.9),
    ]
    calls = []
    found = find_conflicts(lambda p: calls.append(p) or "推翻：0", "他的狗叫瓦片", items)
    assert found == ([], [])
    assert calls == []


def test_preselect_limits_to_max():
    """超过上限时只取重合度最高的前 N 条，不把全库塞给模型。"""
    items = [
        make_item(f"他喜欢运动{i}", "user_said", 0.9) for i in range(100)
    ]
    got = _preselect("他喜欢运动", items)
    assert len(got) <= 50


def test_embedder_preselect_used_when_provided():
    """传了 embedder + emb_map 时，冲突检测走「语义向量粗筛」，而不是字面 Jaccard。"""
    items = [
        make_item("他去面试了", "user_said", 0.9),
    ]
    qvec = [1.0, 0.0]
    emb_map = {"他去面试了": [1.0, 0.0]}   # 和 qvec 余弦 = 1
    embedder = _fake_embedder([qvec])

    seen = []

    def llm(prompt):
        seen.append(prompt)
        return "推翻：无\n矛盾：无"

    find_conflicts(llm, "他在找工作", items,
                   embedder=embedder, emb_map=emb_map)

    # 语义粗筛把「他去面试了」留下了，模型收到提示词
    assert seen, "语义粗筛应该留下语义相关但字面无关的记忆"
    assert "他去面试了" in seen[0]


def test_no_embedder_falls_back_to_jaccard():
    """不传 embedder 时，退回字面 Jaccard 粗筛（老行为不变）。"""
    items = [
        make_item("他去面试了", "user_said", 0.9),
    ]
    calls = []

    def llm(prompt):
        calls.append(prompt)
        return "推翻：0\n矛盾：无"

    found = find_conflicts(llm, "他在找工作", items)
    assert found == ([], [])
    assert calls == [], "字面 Jaccard 应该砍掉字面无关的记忆，不再调模型"
