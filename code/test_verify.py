# test_verify.py —— 测试验证机制

from verify import (
    find_uncertain_impressions,
    should_ask_now,
    judge_feedback,
    pick_verify_target,
)
from item import make_item


# ===== 原有的两条（不动，保持向后兼容） =====

def test_find_uncertain():
    # 值得验证的：her_inference + 置信度0.5（出现几次都行）
    a = make_item("他可能爱吃辣", "her_inference", 0.5, occurrences=2)
    # 太确定的不问（置信度0.9）
    b = make_item("他可能喜欢篮球", "her_inference", 0.9, occurrences=2)
    # 置信度中等，出现1次也应该验证
    c = make_item("他可能爱熬夜", "her_inference", 0.5, occurrences=1)
    # 他说过的不问（user_said）
    d = make_item("他爱吃辣", "user_said", 0.5, occurrences=2)

    result = find_uncertain_impressions([a, b, c, d])

    # a 和 c 都应该被选中（都是 her_inference + 置信度中等）
    assert len(result) == 2
    texts = [m["text"] for m in result]
    assert "他可能爱吃辣" in texts
    assert "他可能爱熬夜" in texts

def test_should_ask_now():
    # 注意：不能靠 "敞开心扉" in prompt 来造 fake ——
    # 这四个字写在固定模板里，跟用户说的话无关，fake 会永远返回「是」，
    # 测试就退化成 "是" in "是"，测不出任何东西（原版就是假通过）。
    # 这里改成按用户文本分支，才真的在测「函数有没有把模型的答案传对」。
    def fake_llm(prompt):
        return "是" if "好累" in prompt else "否"

    # 用户在倾诉 → 适合问
    assert should_ask_now(fake_llm, "最近好累啊") == True
    # 用户在闲聊 → 不适合问
    assert should_ask_now(fake_llm, "今天天气不错") == False


# ===== 新增：find_uncertain_impressions 的边界 =====

def test_find_uncertain_skips_deleted():
    """已被推翻的猜测不该再拿去问用户——问一条自己都知道失效的记忆很奇怪。"""
    alive = make_item("他可能爱熬夜", "her_inference", 0.5)
    dead = make_item("他可能爱喝咖啡", "her_inference", 0.5)
    dead["deleted"] = True

    result = find_uncertain_impressions([alive, dead])
    assert len(result) == 1
    assert result[0]["text"] == "他可能爱熬夜"


def test_find_uncertain_confidence_edges():
    """0.2 和 0.7 是闭区间端点，必须算进去；0.19 和 0.71 必须排除。"""
    lo_in = make_item("边界下", "her_inference", 0.2)
    hi_in = make_item("边界上", "her_inference", 0.7)
    too_low = make_item("太低", "her_inference", 0.19)
    too_high = make_item("太高", "her_inference", 0.71)

    texts = [m["text"] for m in find_uncertain_impressions([lo_in, hi_in, too_low, too_high])]
    assert "边界下" in texts
    assert "边界上" in texts
    assert "太低" not in texts
    assert "太高" not in texts


def test_find_uncertain_sorts_high_confidence_first():
    """依据不足的猜测(0.2)也能进候选，但要排在正常猜测(0.4~0.7)后面。

    这样 0.2 不会永久搁置，也不会抢正常猜测的优先验证权。
    """
    low = make_item("依据不足", "her_inference", 0.2)
    normal = make_item("正常猜测", "her_inference", 0.5)
    high = make_item("较确定", "her_inference", 0.6)

    result = find_uncertain_impressions([low, normal, high])
    confs = [m["confidence"] for m in result]
    assert confs == [0.6, 0.5, 0.2]


# ===== 新增：should_ask_now 的否定陷阱（回归测试） =====

def test_should_ask_now_rejects_negative_answer():
    """模型答「不是」时不能返回 True。

    旧实现用 `"是" in reply`：「不是」里也含「是」，所以否被读成了是。
    这条测试锁死这个 bug。
    """
    assert should_ask_now(lambda p: "不是", "今天天气不错") is False
    assert should_ask_now(lambda p: "否", "今天天气不错") is False


def test_should_ask_now_empty_reply_is_safe():
    """模型返回空串时不能崩，也不能默认「问」。"""
    assert should_ask_now(lambda p: "", "嗯") is False
    assert should_ask_now(lambda p: "   ", "嗯") is False


def test_should_ask_now_accepts_explicit_yes():
    assert should_ask_now(lambda p: "是", "最近好累") is True
    assert should_ask_now(lambda p: "是。他在倾诉", "最近好累") is True


# ===== 新增：judge_feedback（此前零测试） =====

def test_judge_feedback_three_branches():
    """三个分支各自走对——它决定置信度升到 0.9 还是压到 0.1，判错就是冤杀或放水。"""
    assert judge_feedback(lambda p: "confirm", "对，是我") == "confirm"
    assert judge_feedback(lambda p: "deny", "不对，你弄错了") == "deny"
    assert judge_feedback(lambda p: "unrelated", "今天天气不错") == "unrelated"


def test_judge_feedback_case_insensitive():
    """模型偶尔会输出大写或首字母大写，不能因此掉进 unrelated。"""
    assert judge_feedback(lambda p: "CONFIRM", "对") == "confirm"
    assert judge_feedback(lambda p: "Confirm", "对") == "confirm"
    assert judge_feedback(lambda p: "DENY", "不对") == "deny"


def test_judge_feedback_deny_wins_when_both_words_present():
    """「not confirm」这种混合串必须先判 deny。

    先查 confirm 的话，否认会被读成确认 —— 一条假记忆直接被抬到 0.9。
    """
    assert judge_feedback(lambda p: "not confirm", "不对") == "deny"
    assert judge_feedback(lambda p: "deny, not confirm", "不对") == "deny"


def test_judge_feedback_unknown_reply_is_unrelated():
    """模型答非所问时，宁可当「无关」什么都别动，也不能猜。"""
    assert judge_feedback(lambda p: "", "嗯…") == "unrelated"
    assert judge_feedback(lambda p: "我看不懂", "嗯…") == "unrelated"


def test_judge_feedback_accepts_legacy_argument_order():
    """旧写法 judge_feedback(reply_text, llm) 要能继续用（向后兼容）。"""
    legacy = judge_feedback("对，是我", lambda p: "confirm")
    assert legacy == "confirm"

    # 新写法
    current = judge_feedback(lambda p: "confirm", "对，是我")
    assert current == "confirm"


# ===== 新增：pick_verify_target（此前零测试） =====

def test_pick_verify_target_returns_none_without_candidates():
    """没有不确定印象时，连模型都不该调用（省一次请求，也不会反问空话）。"""
    calls = []

    def llm(prompt):
        calls.append(prompt)
        return "是"

    target, should_ask = pick_verify_target(llm, [], "随便说点什么")
    assert target is None
    assert should_ask is False
    assert calls == []          # 关键：没候选就不该发请求


def test_pick_verify_target_respects_should_ask():
    """有候选但用户此刻不想被问 → 不问。"""
    items = [make_item("他可能爱熬夜", "her_inference", 0.5)]

    target, should_ask = pick_verify_target(lambda p: "否", items, "哈哈哈")
    assert target is None
    assert should_ask is False

    # 用户敞开心扉时才会问
    target, should_ask = pick_verify_target(lambda p: "是", items, "最近好累")
    assert should_ask is True
    assert target is not None
    assert target["text"] == "他可能爱熬夜"
