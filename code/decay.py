# decay.py —— 衰减权重公式

import math
from datetime import datetime


def days_since(timestamp, now=None):
    """
    算「从 timestamp 到现在」过了多少天。

    参数：
        timestamp : 创建时间（时间戳，单位：秒）
        now       : 现在时刻（不传就用系统当前时间）

    返回：
        过了多少天（小数，比如 7.5 表示 7 天半）
    """
    if now is None:
        now = datetime.now()

    # 把「秒级时间戳」转成「datetime 时刻」
    created = datetime.fromtimestamp(timestamp)

    # 两个时刻相减，得到「过了多久」
    delta = now - created

    # 换算成「天」（total_seconds 是总秒数，除以一天的秒数）
    return delta.total_seconds() / 86400


def effective_half_life(base_half_life, hits, review_boost=0.5):
    """
    算「被复习 hits 次后」的半衰期。

    参数：
        base_half_life : 基础半衰期（多少天忘一半）
        hits           : 被复习（想起）的次数
        review_boost   : 每复习一次，半衰期增长的比例（默认 0.5 = +50%）

    返回：
        变长后的半衰期（天）
    """
    return base_half_life * (1 + review_boost * hits)


def decayed_weight(base_weight, half_life, hits, confidence, age_days,
                   boost_k=1.0):
    """
    算一条记忆「现在」的权重。

    参数：
        base_weight : 初始权重（1.0 ~ 2.0）
        half_life   : 半衰期（多少天衰减到一半）
        hits        : 被提及次数
        confidence  : 来源置信度（0 ~ 1）
        age_days    : 已经过去多少天
        boost_k     : 用进废退的增益系数（默认 1.0）

    返回：
        weight : 当前权重
    """
    time_decay = 0.5 ** (age_days / half_life)
    # 用进废退：对数增长，前面快后面缓（像人「提了很多次」的感知）
    use_boost = 1 + boost_k * math.log(1 + hits)
    weight = base_weight * time_decay * use_boost * confidence
    return weight


def should_forget(weight, forget_below=0.12):
    """
    判断一条记忆「该不该被遗忘」。

    参数：
        weight       : 当前权重
        forget_below : 遗忘阈值（默认 0.12，低于它就遗忘）

    返回：
        True  → 该忘了
        False → 还记着
    """
    if weight < forget_below:
        return True
    else:
        return False


def after_review_fail(base_half_life, confidence, reset_ratio=0.5):
    """
    复习失败后，更新半衰期和置信度。

    参数：
        base_half_life : 当前半衰期（天）
        confidence     : 当前置信度（0~1）
        reset_ratio    : 失败后，半衰期缩到原来的几成（默认 0.5 = 砍半）

    返回：
        (新的半衰期, 新的置信度)

    注意（2026-11-04）：本函数对应「间隔重复」的「复习失败」那一半，
    目前还没有接入任何入口——因为它的触发信号（「检索失败」，即系统主动
    问用户「还记不记得」、用户答不上来）这个功能还没做。冲突检测/验证
    否认走的是「墓碑」（mark_deleted）和「降置信度」，语义与「复习失败」
    不同，不能硬接。等间隔重复复习功能落地后再接这里。
    """
    new_half_life = base_half_life * reset_ratio
    new_confidence = confidence * reset_ratio
    return new_half_life, new_confidence