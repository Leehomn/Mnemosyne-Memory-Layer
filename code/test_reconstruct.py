# test_reconstruct.py —— 测试 reconstruct 模块

from reconstruct import parse_reply, reconstruct
from index import Cognition


def test_parse_fact_and_guess():
    reply = "[事实] 他是四川人，能吃辣\n[猜测] 他可能不太喜欢被叫大肥鱼"
    items = parse_reply(reply)

    assert len(items) == 2
    assert items[0] == {"text": "他是四川人，能吃辣", "source": "user_said",
                        "subject": "about_user", "evidence": [], "topic": None,
                        "who": None, "what": None, "value": None, "tier": None}
    assert items[1] == {"text": "他可能不太喜欢被叫大肥鱼", "source": "her_inference",
                        "subject": "about_user", "evidence": [], "topic": None,
                        "who": None, "what": None, "value": None, "tier": None}


def test_parse_self_said():
    """[我说] 前缀 → source=self_said + subject=about_self（AI 自己说的话，独立一格）。"""
    reply = "[我说] 我建议他理票先按日期分堆\n[事实] 他叫南风"
    items = parse_reply(reply)

    assert len(items) == 2
    assert items[0]["text"] == "我建议他理票先按日期分堆"
    assert items[0]["source"] == "self_said"
    assert items[0]["subject"] == "about_self"
    assert items[1]["source"] == "user_said"
    assert items[1]["subject"] == "about_user"


def test_parse_third_party():
    """[转述] 前缀 → source=third_party，说话人写进 who，主体仍 about_user。"""
    reply = "[转述] 房东说钥匙他已经收到了 #人物：房东"
    items = parse_reply(reply)

    assert len(items) == 1
    assert items[0]["text"] == "房东说钥匙他已经收到了"
    assert items[0]["source"] == "third_party"
    assert items[0]["subject"] == "about_user"
    assert items[0]["who"] == "房东"


def test_parse_third_party_preserves_speaker_in_text():
    """[转述] 正文必须保留说话人，不许拍平成「他做了 X」。"""
    items = parse_reply("[转述] 桥哥说店里要关门换玻璃 #人物：桥哥")
    assert items[0]["source"] == "third_party"
    assert "桥哥说" in items[0]["text"]
    assert items[0]["who"] == "桥哥"


def test_parse_drop_invalid():
    # 没有前缀的行、空行，都应该被丢弃
    reply = "[事实] 有效的一条\n这是没有前缀的行\n\n[乱写] 这个前缀不认识"
    items = parse_reply(reply)

    assert len(items) == 1
    assert items[0]["text"] == "有效的一条"


def test_parse_wu():
    # 模型输出「无」，应该返回空列表
    items = parse_reply("无")
    assert items == []


def test_parse_drop_boilerplate():
    """模型把提示词里的示例文字原样抄出来时，必须丢弃，不能落库。

    这是「宁可漏记，不可乱记」红线的护栏：示例文字不是用户真实记忆。
    """
    reply = (
        "[事实] 他反复明确表达过的稳定特点\n"
        "[猜测] 你从事件里推断出的规律\n"
        "[事实] 他叫南风\n"
        "[猜测] 他可能想家"
    )
    items = parse_reply(reply)

    assert len(items) == 2
    assert items[0]["text"] == "他叫南风"
    assert items[1]["text"] == "他可能想家"


# ===== 新增：parse_reply 的容错（这些格式以前全会静默丢记忆） =====

def test_parse_numbered_list():
    """模型最爱的编号列表。旧实现只认裸行首的 [事实]，编号一加整段记忆全丢。"""
    items = parse_reply("1. [事实] 他叫南风\n2. [猜测] 他可能爱熬夜")
    assert len(items) == 2
    assert items[0]["text"] == "他叫南风"
    assert items[1]["source"] == "her_inference"


def test_parse_markdown_bold():
    """模型爱加粗标签。旧的 startswith("[事实]") 碰不上。"""
    items = parse_reply("**[事实]** 他叫南风\n**[猜测]** 他怕吵")
    assert len(items) == 2
    assert items[0]["text"] == "他叫南风"
    assert items[1]["text"] == "他怕吵"


def test_parse_fullwidth_brackets():
    """中文输入法下模型可能输出【事实】而不是 [事实]。"""
    items = parse_reply("【事实】他叫南风\n【猜测】他可能爱熬夜")
    assert len(items) == 2
    assert items[0]["source"] == "user_said"
    assert items[1]["source"] == "her_inference"


def test_parse_colon_after_tag():
    """标签后带冒号时，冒号不能混进记忆正文。"""
    items = parse_reply("[事实]：他叫南风\n[猜测]: 他可能爱熬夜")
    assert len(items) == 2
    assert items[0]["text"] == "他叫南风"
    assert items[1]["text"] == "他可能爱熬夜"


def test_parse_stacked_decoration():
    """两层装饰叠在一起（"1. - [事实] xxx"）也要能剥干净。"""
    items = parse_reply("1. - [事实] 他叫南风")
    assert len(items) == 1
    assert items[0]["text"] == "他叫南风"


def test_parse_empty_and_blank_lines():
    """空回复、纯空白行不能崩，也不能产出空记忆。"""
    assert parse_reply("") == []
    assert parse_reply("\n\n  \n") == []
    assert parse_reply("[事实]\n[猜测]   ") == []


def test_reconstruct_passes_now_to_prompt():
    """now 参数要把「当前日期」拼进提示词，让模型保留相对时间表述（不再让它心算）。

    用假模型把收到的提示词原样返回，断言提示词里出现了日期 + 保留相对表述的指令。
    """
    seen = {}

    def capture_llm(prompt):
        seen["prompt"] = prompt
        return "无"

    reconstruct(capture_llm, ["用户：我下周三约了人"], lambda *a, **k: None, now="2026-04-13")

    assert "2026-04-13" in seen["prompt"]
    assert "相对表述" in seen["prompt"]


def test_reconstruct_without_now_keeps_compat():
    """不传 now 时，提示词里不该出现「当前日期」段（向后兼容）。"""
    seen = {}

    def capture_llm(prompt):
        seen["prompt"] = prompt
        return "无"

    reconstruct(capture_llm, ["用户：你好"], lambda *a, **k: None)

    assert "当前日期" not in seen["prompt"]


def test_relative_time_is_kept_and_derived():
    """正文保留相对时间词，event_time 由代码确定性换算，date_kind=derived。

    这是反转旧行为：以前「相对词还在+没绝对日期」会被拦下不记，现在要记，
    且绝对日期由 dates.py 从锚点 now 算出（不靠 LLM）。
    """
    captured = {}

    def remember(text, **kwargs):
        captured["text"] = text
        captured["event_time"] = kwargs.get("event_time")
        captured["date_kind"] = kwargs.get("date_kind")
        return "ok"

    reconstruct(
        lambda p: "[事实] 他下周三约了人",
        ["用户：我下周三约了人"],
        remember,
        now="2026-04-13",
    )
    assert captured["text"] == "他下周三约了人"       # 相对表述忠实保留
    assert captured["event_time"] == "2026-04-22"     # 4/13 是周一，下周三 = 4/22
    assert captured["date_kind"] == "derived"


def test_absolute_date_is_kept():
    """正文带绝对日期时，正常落库，date_kind=explicit。"""
    captured = {}

    def remember(text, **kwargs):
        captured["text"] = text
        captured["event_time"] = kwargs.get("event_time")
        captured["date_kind"] = kwargs.get("date_kind")
        return "ok"

    reconstruct(
        lambda p: "[事实] 他 2026-04-13 约了人",
        ["用户：我下周三约了人"],
        remember,
        now="2026-04-13",
    )
    assert captured["text"] == "他 2026-04-13 约了人"
    assert captured["event_time"] == "2026-04-13"
    assert captured["date_kind"] == "explicit"


def test_no_time_word_is_kept():
    """没有时间词的记忆（如「他是四川人」）不该被误伤，照常落库。"""
    added = reconstruct(
        lambda p: "[事实] 他是四川人，能吃辣",
        ["用户：我是四川人"],
        lambda *a, **k: "ok",
    )
    assert added == 1


def test_event_time_extracted_from_date():
    """正文里的绝对日期要结构化抠出来，写进 event_time，date_kind=explicit。"""
    captured = {}

    def remember(text, **kwargs):
        captured["event_time"] = kwargs.get("event_time")
        captured["date_kind"] = kwargs.get("date_kind")
        return "ok"

    reconstruct(
        lambda p: "[事实] 他 2026-05-25 把迷迭香搬到窗边",
        ["用户：前天把迷迭香搬到窗边"],
        remember,
        now="2026-05-27",
    )
    assert captured["event_time"] == "2026-05-25"
    assert captured["date_kind"] == "explicit"


def test_event_time_none_without_date():
    """正文里没有日期时，event_time 传 None（表示不涉及具体某天），date_kind=none。"""
    captured = {}

    def remember(text, **kwargs):
        captured["event_time"] = kwargs.get("event_time")
        captured["date_kind"] = kwargs.get("date_kind")
        return "ok"

    reconstruct(
        lambda p: "[事实] 他重感情",
        ["用户：我很重感情"],
        remember,
    )
    assert captured["event_time"] is None
    assert captured["date_kind"] == "none"


def test_self_said_gets_now_when_assistant_delivered():
    """助手这一轮真的交付了 → [我说] 条目用 now 兜底填 event_time，date_kind=derived。

    这是 P17-CASE-008 那类题的根因：助手第 91 轮说「写好了，交稿。夜雾从…」，
    提炼成 [我说] 后正文里既没有日期也没有相对词，event_time 就成了 None，
    「是我写的」进了库、「4 月 13 日写的」丢了，日期题答不出来。
    信号在助手原话里（buffer 现成），不在提炼后的话里。
    """
    captured = {}

    def remember(text, **kwargs):
        captured["event_time"] = kwargs.get("event_time")
        captured["date_kind"] = kwargs.get("date_kind")
        return "ok"

    reconstruct(
        lambda p: "[我说] 我写的夜雾段落：雾从樟树渡口的水面漫上来",
        ["用户：夜雾那段写好了没", "助手：写好了，交稿。夜雾从樟树渡口的水面漫上来"],
        remember,
        now="2026-04-13",
    )
    assert captured["event_time"] == "2026-04-13"
    assert captured["date_kind"] == "derived"


def test_self_said_no_now_when_assistant_just_advised():
    """助手只是给建议（没说交付）→ [我说] 不兜底，event_time 仍为 None。

    护栏：不能因为「AI 说过话」就给每条 self_said 都盖日期。
    P17 实测 314 条 self_said 里 105 条是「我建议他…」，全盖日期会让召回涨噪声、乱排序。
    """
    captured = {}

    def remember(text, **kwargs):
        captured["event_time"] = kwargs.get("event_time")
        captured["date_kind"] = kwargs.get("date_kind")
        return "ok"

    reconstruct(
        lambda p: "[我说] 我建议他在办公室备一件外套",
        ["用户：窗边忽冷忽热", "助手：建议你在办公室备一件外套，风大就披上"],
        remember,
        now="2026-04-13",
    )
    assert captured["event_time"] is None
    assert captured["date_kind"] == "none"


def test_user_said_never_gets_now_fallback():
    """用户说的 [事实] 永远不吃 now 兜底——哪怕助手这一轮交付了。

    红线：「他前天去了杭州」的「前天」是相对上一轮说的，
    按本轮 now 填就全错。这是 date_kind 三态存在的理由。
    """
    captured = {}

    def remember(text, **kwargs):
        captured["event_time"] = kwargs.get("event_time")
        captured["date_kind"] = kwargs.get("date_kind")
        return "ok"

    reconstruct(
        lambda p: "[事实] 他重感情",
        ["用户：我很重感情", "助手：写好了，交稿。夜雾从樟树渡口的水面漫上来"],
        remember,
        now="2026-04-13",
    )
    assert captured["event_time"] is None
    assert captured["date_kind"] == "none"


def test_parse_topic_tag():
    """正文后面的「#话题：X」要切走，话题词单独存进 topic 字段，正文里不残留。"""
    items = parse_reply("[事实] 他养了狗叫瓦片 #话题：养狗\n[猜测] 他最近压力大 #话题：工作")

    assert len(items) == 2
    assert items[0]["text"] == "他养了狗叫瓦片"
    assert items[0]["topic"] == "养狗"
    assert items[1]["text"] == "他最近压力大"
    assert items[1]["topic"] == "工作"
def test_parse_who_what_value_tags():
    """正文后面的「#人物/#维度/#值」要切走，单独存进对应字段，正文不残留。"""
    items = parse_reply(
        "[事实] 老曹生日是六月九号 #话题：生日 #人物：老曹 #维度：生日 #值：六月九号 #关系：2"
    )

    assert len(items) == 1
    assert items[0]["text"] == "老曹生日是六月九号"
    assert items[0]["who"] == "老曹"
    assert items[0]["what"] == "生日"
    assert items[0]["value"] == "六月九号"
    assert items[0]["tier"] == 2
    assert items[0]["topic"] == "生日"


def test_parse_no_who_what_value_is_none():
    """没写 #人物/#维度/#值 时，对应字段为 None（不误抽）。"""
    items = parse_reply("[事实] 他叫南风")
    assert items[0]["who"] is None
    assert items[0]["what"] is None
    assert items[0]["value"] is None
    assert items[0]["tier"] is None


def test_parse_tier_invalid_is_none():
    """#关系 写了非法值（如 9）时，tier 判 None，宁可漏判不乱标档。"""
    items = parse_reply("[事实] 老曹生日是六月九号 #关系：9")
    assert items[0]["tier"] is None
    # 非法关系尾巴仍要从正文里删掉，不能残留「#关系：9」
    assert items[0]["text"] == "老曹生日是六月九号"


def test_who_what_value_passed_to_remember():
    """who/what/value 要透传给 remember_func 的对应参数。"""
    captured = {}

    def remember(text, **kwargs):
        captured["who"] = kwargs.get("who")
        captured["what"] = kwargs.get("what")
        captured["value"] = kwargs.get("value")
        captured["tier"] = kwargs.get("tier")
        return "ok"

    reconstruct(
        lambda p: "[事实] 老曹生日是六月九号 #人物：老曹 #维度：生日 #值：六月九号 #关系：2",
        ["用户：老曹生日是六月九号"],
        remember,
    )
    assert captured["who"] == "老曹"
    assert captured["what"] == "生日"
    assert captured["value"] == "六月九号"
    assert captured["tier"] == 2


def test_parse_no_topic_is_none():
    """没写 #话题 时，topic 为 None（不打标签）。"""
    items = parse_reply("[事实] 他叫南风")
    assert items[0]["topic"] is None


def test_topic_passed_to_remember():
    """话题标签要透传给 remember_func 的 topic 参数。"""
    captured = {}

    def remember(text, **kwargs):
        captured["topic"] = kwargs.get("topic")
        return "ok"

    reconstruct(
        lambda p: "[事实] 他养了狗 #话题：养狗",
        ["用户：我养了条狗"],
        remember,
    )
    assert captured["topic"] == "养狗"


def fake_llm(prompt):
    return "[事实] 他叫南风\n[猜测] 他可能喜欢打游戏"


def test_reconstruct_full(tmp_path):
    # 用独立的临时数据目录，避免污染真实数据
    cog = Cognition(data_dir=str(tmp_path))

    # 一段对话（buffer）
    buffer = ["用户：我叫南风", "AI：好的，记住了"]

    # 重构：用假模型 + cog.remember 作为写入函数
    added = reconstruct(fake_llm, buffer, cog.remember)

    # 假模型返回了 1 条事实 + 1 条猜测，应该新增 2 条
    assert added == 2

    # 事实区应该召回「他叫南风」；猜测是 her_inference 默认 0.4，
    # 低于召回门槛 0.6，所以「他可能喜欢打游戏」不该出现在召回块里。
    block = cog.recall_block(limit=8)
    assert "他叫南风" in block
    assert "他可能喜欢打游戏" not in block
