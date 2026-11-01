# source.py —— 来源与置信度管理

# 各来源的默认置信度
DEFAULT_CONFIDENCE = {
    "user_said": 0.9,       # 用户说的：高置信（证实）
    "observed": 0.8,        # 观察到的：较高（客观数据）
    "third_party": 0.5,     # 第三方说的：中置信（可能传话失真）
    "her_inference": 0.4,   # AI 推断的：低置信（这是「猜」）
}


def default_confidence(source):
    """
    根据来源，返回默认置信度。

    参数：
        source : 来源（user_said / observed / third_party / her_inference）

    返回：
        默认置信度（0~1）；未知来源返回 0.5
    """
    return DEFAULT_CONFIDENCE.get(source, 0.5)


def is_confirmed(source):
    """
    判断这个来源是不是「证实」的（而不是「猜」的）。

    参数：
        source : 来源

    返回：
        True  → 证实（user_said / observed / third_party）
        False → 猜测（her_inference 或未知）
    """
    return source in ("user_said", "observed", "third_party")