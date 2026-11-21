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
    r"|\d{1,2}号(?![楼|房|室|床|门|线|路|卡|车|队|站|铺|摊|栋|座|区|巷|弄|电"
    r"|桌|窗|柜|馆|厅|院|校|台|风|选|手|箱|盒|瓶|包])"  # 13号（裸「号」= 几号那天）
)
# 上面的第三段带负向断言：裸「X号」只在「几号那天」时算日期；像「3号楼」「2号电池」
# 「1号队员」「3号桌」「8号台风」「5号校区」这类「X号 + 事物名词」是编号/序号，
# 不是日期，不能误抠成 event_time，否则会凭空造出一个「编造日期」记忆。

# 相对时间词：正文里出现这些词，就可能需要用锚点 now 换算成绝对日期。
HAS_RELATIVE = re.compile(
    r"昨天|今天|明天|前天|后天|大前天|大后天|上周|下周|这周|本周|几号|周[一二三四五六日天]"
)

# 周期句：「每个月5号交房租」「每周三去健身」说的是反复发生的事，不是某一天。
# 这类正文里的那个日期不能被抠成 event_time（否则「每个月5号」被固化成
# 「2026-05-05」这一次）。注意只拦「紧跟在周期词后面的那个日期」：
# 「他每天都很累，5号那天交了稿」里的 5 号是真的某一天，不能一起拦掉。
_PERIODIC = re.compile(r"每\s*个?\s*(?:天|周|星期|月|年)|每\s*星期")

# 中文数字 → 阿拉伯数字（只用于日期上下文，不做通用数字转换）
_CN_DIGIT = {"零": 0, "〇": 0, "一": 1, "二": 2, "三": 3, "四": 4,
             "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_DATE = re.compile(
    r"([一二三四五六七八九十]{1,3})\s*月\s*([一二三四五六七八九十]{1,3})\s*([日号])"
    r"|([一二三四五六七八九十]{1,3})\s*([日号])"
)

# 星期几 → datetime 的 weekday 编码（周一=0 … 周日=6）
_WEEKDAY = {
    "一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6,
    "0": 6, "1": 0, "2": 1, "3": 2, "4": 3, "5": 4, "6": 5, "7": 6,
}


def _parse_iso(s):
    """把 "2026-05-02"、"2026-05-02T10:00:00" 或 "2026/5/2" 解析成 date；失败返回 None。"""
    if not s:
        return None
    s = str(s).strip().split("T")[0].split(" ")[0]
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
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


def _periodic_span(text):
    """找出「紧跟在周期词后面的那个日期」在正文里的位置区间；没有返回 None。

    「每个月5号交房租」→ 命中，5 号是周期的一部分，不是某一天。
    「他每天都很累，5号那天交了稿」→ 不命中，5 号是真的很累那天之外的另一天。
    """
    for pm in _PERIODIC.finditer(text):
        tail = text[pm.end():]
        # 周期词和日期之间只允许夹「的 / 空 / 号」这类极短连接词
        mm = re.match(r"[\s的]*", tail)
        skip = mm.end() if mm else 0
        dm = DATE_PATTERN.match(tail[skip:])
        if dm:
            start = pm.end() + skip
            return (start, start + dm.end())
    return None


def _cn_to_int(s):
    """中文数字转整数（只覆盖日期范围：一 ~ 三十一）。认不出返回 None。

    支持：一/十二/二十/二十一/三十/三十一。
    不支持「廿」「卅」这类生僻写法——历史数据里一次都没出现过。
    """
    if not s:
        return None
    if "十" not in s:
        # 单个字：一~九
        return _CN_DIGIT.get(s) if len(s) == 1 else None
    # 含「十」：十 / 十二 / 二十 / 二十一 / 三十
    left, _, right = s.partition("十")
    if len(left) > 1 or len(right) > 1:
        return None
    tens = _CN_DIGIT.get(left) if left else 1
    ones = _CN_DIGIT.get(right) if right else 0
    if tens is None or ones is None:
        return None
    return tens * 10 + ones


def _normalize_cn_dates(text):
    """把正文里的中文数字日期就地换成阿拉伯数字，其余文字不动。

    「他打算七月四号搬家」→「他打算7月4号搬家」，这样后面的 DATE_PATTERN
    和 _extract_explicit 就能按现有逻辑处理，不必再复制一套解析分支。
    历史数据里这类写法共出现 19 次（P17 的「七月四号」占 4 次）。
    """
    def _sub(m):
        if m.group(1):                      # X月Y日/号
            mo = _cn_to_int(m.group(1))
            day = _cn_to_int(m.group(2))
            if mo is None or day is None:
                return m.group(0)
            return f"{mo}月{day}{m.group(3)}"
        day = _cn_to_int(m.group(4))        # 裸「Y号」
        if day is None:
            return m.group(0)
        return f"{day}{m.group(5)}"

    return _CN_DATE.sub(_sub, text)


def _extract_explicit(text, now_d):
    """从正文抠出显式绝对日期，规范化成 "YYYY-MM-DD"；抠不到返回 None。

    周期句（「每个月5号交房租」）里紧跟在周期词后面的那个日期不算 event_time，
    但同一句里别处出现的真日期仍然照常抠（「他每天都很累，5号那天交了稿」）。
    """
    span = _periodic_span(text)

    for m in DATE_PATTERN.finditer(text):
        if span is not None and m.start() == span[0]:
            continue                          # 周期句里的那个日期，跳过
        raw = m.group(0)

        # 全带年份：2026-04-13 / 2026年4月13日
        m2 = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", raw)
        if m2:
            return _safe_date(int(m2.group(1)), int(m2.group(2)), int(m2.group(3)))

        # 月+日（缺年）：用 now 的年份补
        m2 = re.search(r"(\d{1,2})月(\d{1,2})", raw)
        if m2:
            if now_d is None:
                return None
            # 「去年7月4号」「前年12月」：年份偏移。
            # 不处理的话「他去年7月4号搬的家」会被读成今年 7-04。
            ydelta = _year_delta(text)
            year = now_d.year + ydelta if ydelta is not None else now_d.year
            # 月份在正文里已经写明了，就用它写的。
            # 旧实现在这里叠加了「上/下个月」的偏移，把「他上个月说6月19号交房租」
            # 读成 4-19——「上个月」说的是他说话的时机，不是房租的月份。
            return _safe_date(year, int(m2.group(1)), int(m2.group(2)))

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
    # 固定偏移：必须长的在前。「大前天」里含「前天」，若「前天」先匹配
    # 就会把大前天算成前天（now=2026-05-04 时 05-02 而不是 05-01）。
    for word, offset in (("大前天", -3), ("大后天", 3),
                         ("前天", -2), ("昨天", -1), ("今天", 0),
                         ("明天", 1), ("后天", 2)):
        if word in text:
            return now_d + timedelta(days=offset)

    # 周X：上上/下下/上/本/这/下 周 + 星期几（含裸「周X」）
    # 「每周三去健身」里的周三属于周期句，不是某一天，跳过它再找下一个
    # （「他每周三去健身，上周三没去」要落到上周三）。
    for m in re.finditer(r"(上上|下下|上|本|这|下)?\s*周([一二三四五六日天0-7])", text):
        if m.group(1) is None and m.start() > 0 and text[m.start() - 1] == "每":
            continue
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


def _year_delta(text):
    """检测「去年/前年/明年/后年」这种年份偏移词，返回 -1/-2/1/2；没有返回 None。"""
    if re.search(r"前\s*年", text):
        return -2
    if re.search(r"去\s*年", text):
        return -1
    if re.search(r"明\s*年", text):
        return 1
    if re.search(r"后\s*年", text):
        return 2
    return None


def resolve_event_time(text, now=None):
    """给定记忆正文 + 锚点日期，返回 (event_time, date_kind)。

    - event_time：统一 "YYYY-MM-DD"，解析不了就 None
    - date_kind ："explicit"（原文就是绝对日期）
                 / "derived"（原文是相对词，代码推算）
                 / "none"（不涉及具体某天）
    """
    if not isinstance(text, str):
        return (None, "none")

    now_d = _parse_iso(now)

    # 中文数字日期先转成阿拉伯数字，后面走同一套逻辑
    norm = _normalize_cn_dates(text)

    explicit = _extract_explicit(norm, now_d)
    if explicit:
        return (explicit, "explicit")

    if now_d is not None:
        derived = _resolve_relative(norm, now_d)
        if derived is not None:
            return (derived.strftime("%Y-%m-%d"), "derived")

    return (None, "none")
