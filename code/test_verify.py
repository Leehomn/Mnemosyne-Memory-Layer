# test_verify.py —— 测试验证机制

from verify import find_uncertain_impressions
from item import make_item


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
    from verify import should_ask_now

    def fake_llm(prompt):
        return "是" if "敞开心扉" in prompt else "否"

    # 用户在倾诉 → 适合问
    assert should_ask_now(fake_llm, "最近好累啊") == True