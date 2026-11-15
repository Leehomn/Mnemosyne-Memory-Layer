# dates.py —— 相对时间→绝对日期的确定性换算（纯 Python，不调 LLM）
#
# 为什么：reconstruct 之前让 LLM 心算「下周三」「周一」→绝对日期，结果算错
# （P20 下周三算成 6/24、P17 周一算成 5/3）。日期算术是确定性运算，交给
# datetime 比 LLM 稳。LLM 只负责「判断这句话说的是哪天/哪个相对词」，
# 不再负责做算术。

import re
from datetime import datetime, timedelta

# 正文里的绝对日期模式（认 2026-04-13 / 2026年4月13日 / 4月13日 / 4月13号 / 13号）
DATE_PATTERN = re.compile(
    r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?"   # 2026-04-13 / 2026年4月13日
    r"|\d{1,2}月\d{1,2}[日号]"              # 4月13日 / 4月13号
    r"|\d{1,2}号(?!楼|房|室|床|门|线|路|卡|车|队|站|铺|摊|栋|座|区|巷|弄|电)"  # 13号（裸「号」= 几号那天）
)
# 上面的第三段带负向断言：裸「X号」只在「几号那天」时算日期；像「3号楼」「2号电池」
# 「1号队员」这类「X号 + 事物名词」是编号/序号，不是日期，不能误抠成 event_time，
# 否则会凭空造出一个「编造日期」记忆。

# 相对时间词：正文里出现这些词，就可能需要用锚点 now 换算成绝对日期。
HAS_RELATIVE = re.compile(
    r"昨天|今天|明天|前天|后天|上周|下周|这周|本周|几号|周[一二三四五六日天]"
)

# 星期几 → datetime 的 weekday 编码（周一=0 … 周日=6）
_WEEKDAY = {
    "一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6,
    "0": 6, "1": 0, "2": 1, "3": 2, "4": 3, "5": 4, "6": 5, "7": 6,
}


def _parse_iso(s):
    """把 "2026-05-02" 或带时间的 ISO 串解析成 date；失败返回 None。"""
    if not s:
        return None
    s = str(s).strip().split("T")[0][:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _safe_date(y, mo, d):
    """构造合法日期；非法（如 13 月）返回 None。"""
    try:
        return datetime(y, mo, d).strftime("%Y-%m-%d")
    except ValueError:
        return None


def _week_monday(d):
    """回到 d 所在周的周一。"""
    return d - timedelta(days=d.weekday())


def _month_delta(text):
    """从正文检测「上/下/本/这 个月」这种月份偏移词，返回 ±1/0；没有则返回 None。

    注意：只影响「缺年份的部分日期」的补全（如「上个月26号」→ 上月的 26 号）。
    完整带年份的日期（2026-04-13）不受影响。
    """
    m = re.search(r"(上|下)\s*个?\s*月", text)
    if m:
        return -1 if m.group(1) == "上" else 1
    if re.search(r"(本|这)\s*个?\s*月", text):
        return 0
    return None


def _apply_month_delta(year, month, delta):
    """把 (year, month) 的月份加 delta（±1），正确处理跨年。返回 (year, month)。"""
    idx = month - 1 + delta          # 0-based 月份
    return year + idx // 12, idx % 12 + 1


def _align_to_weekday(week_monday, wd):
    """week_monday 是某周的周一，返回同一周内目标星期那天。"""
    return week_monday + timedelta(days=wd)


def _next_weekday(d, wd):
    """返回「不早于 d 的最近一个目标星期」。若 d 本身是目标星期，就返回 d。"""
    return d + timedelta(days=(wd - d.weekday()) % 7)


def _extract_explicit(text, now_d):
    """从正文抠出显式绝对日期，规范化成 "YYYY-MM-DD"；抠不到返回 None。"""
    m = DATE_PATTERN.search(text)
    if not m:
        return None
    raw = m.group(0)

    # 全带年份：2026-04-13 / 2026年4月13日
    m2 = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", raw)
    if m2:
        return _safe_date(int(m2.group(1)), int(m2.group(2)), int(m2.group(3)))

    # 月+日（缺年）：用 now 的年份补，再叠加「上/下/本 个月」的月份偏移；
    # 没锚点补不齐 → 不算显式日期
    m2 = re.search(r"(\d{1,2})月(\d{1,2})", raw)
    if m2:
        if now_d is None:
            return None
        delta = _month_delta(text)
        if delta is None:
            return _safe_date(now_d.year, int(m2.group(1)), int(m2.group(2)))
        y, mo = _apply_month_delta(now_d.year, now_d.month, delta)
        return _safe_date(y, mo, int(m2.group(2)))

    # 只有日（号）：用 now 的年月补，再叠加月份偏移；没锚点补不齐 → 不算显式日期
    m2 = re.search(r"(\d{1,2})", raw)
    if m2:
        if now_d is None:
            return None
        delta = _month_delta(text)
        if delta is None:
            return _safe_date(now_d.year, now_d.month, int(m2.group(1)))
        y, mo = _apply_month_delta(now_d.year, now_d.month, delta)
        return _safe_date(y, mo, int(m2.group(1)))

    return None


def _resolve_relative(text, now_d):
    """从正文解析相对时间词，用 now_d 算出绝对 date；歧义返回 None。"""
    # 固定偏移：前天/昨天/今天/明天/后天
    for word, offset in (("前天", -2), ("昨天", -1), ("今天", 0),
                         ("明天", 1), ("后天", 2)):
        if word in text:
            return now_d + timedelta(days=offset)

    # 周X：上上/下下/上/本/这/下 周 + 星期几（含裸「周X」）
    m = re.search(r"(上上|下下|上|本|这|下)?\s*周([一二三四五六日天0-7])", text)
    if m:
        wd = _WEEKDAY.get(m.group(2))
        if wd is None:
            return None
        prefix = m.group(1)
        if prefix == "上上":
            return _align_to_weekday(_week_monday(now_d) - timedelta(days=14), wd)
        if prefix == "上":
            return _align_to_weekday(_week_monday(now_d) - timedelta(days=7), wd)
        if prefix in ("本", "这"):
            return _align_to_weekday(_week_monday(now_d), wd)
        if prefix == "下":
            return _align_to_weekday(_week_monday(now_d) + timedelta(days=7), wd)
        if prefix == "下下":
            return _align_to_weekday(_week_monday(now_d) + timedelta(days=14), wd)
        # 裸「周X」：最近的未来那一天（今天就是目标星期 → 今天）
        return _next_weekday(now_d, wd)

    return None


def resolve_event_time(text, now=None):
    """给定记忆正文 + 锚点日期，返回 (event_time, date_kind)。

    - event_time：统一 "YYYY-MM-DD"，解析不了就 None
    - date_kind ："explicit"（原文就是绝对日期）
                 / "derived"（原文是相对词，代码推算）
                 / "none"（不涉及具体某天）
    """
    now_d = _parse_iso(now)

    explicit = _extract_explicit(text, now_d)
    if explicit:
        return (explicit, "explicit")

    if now_d is not None:
        derived = _resolve_relative(text, now_d)
        if derived is not None:
            return (derived.strftime("%Y-%m-%d"), "derived")

    return (None, "none")
