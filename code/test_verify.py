# test_verify.py —— 测试验证机制

from verify import find_uncertain_impressions
from item import make_item


def test_find_uncertain():
    # 值得验证的：her_inference + 置信度0.5 + 出现2次
    a = make_item("他可能爱吃辣", "her_inference", 0.5, occurrences=2)
    # 太确定的不问（置信度0.9）
    b = make_item("他可能喜欢篮球", "her_inference", 0.9, occurrences=2)
    # 出现次数不够（1次）
    c = make_item("他可能爱熬夜", "her_inference", 0.5, occurrences=1)
    # 他说过的不问（user_said）
    d = make_item("他爱吃辣", "user_said", 0.5, occurrences=2)

    result = find_uncertain_impressions([a, b, c, d])

    assert len(result) == 1
    assert result[0]["text"] == "他可能爱吃辣"