# test_dates.py —— 测试 dates 模块（相对时间→绝对日期的确定性换算）

from dates import resolve_event_time


def test_explicit_full_date():
    et, kind = resolve_event_time("他 2026-05-25 搬花", now="2026-05-27")
    assert et == "2026-05-25"
    assert kind == "explicit"


def test_explicit_cn_date():
    et, kind = resolve_event_time("他 2026年5月2日 交付", now="2026-05-04")
    assert et == "2026-05-02"
    assert kind == "explicit"


def test_explicit_month_day_uses_now_year():
    et, kind = resolve_event_time("他 5月4日 交付", now="2026-05-04")
    assert et == "2026-05-04"
    assert kind == "explicit"


def test_yesterday():
    et, kind = resolve_event_time("他昨天交了稿", now="2026-05-04")
    assert et == "2026-05-03"
    assert kind == "derived"


def test_relative_next_wednesday():
    # 2026-04-13 是周一，下周三 = 4/22（本周三是 4/15）
    et, kind = resolve_event_time("他下周三约了人", now="2026-04-13")
    assert et == "2026-04-22"
    assert kind == "derived"


def test_relative_next_wednesday_from_wednesday():
    # 2026-06-22 是周一（题目 P20 锚点），下周三 = 7/01
    et, kind = resolve_event_time("他下周三前寄画册", now="2026-06-22")
    assert et == "2026-07-01"
    assert kind == "derived"


def test_relative_monday_is_next_monday():
    # 2026-05-02 是周六，裸「周一」= 5/04（题目 P17 锚点）
    et, kind = resolve_event_time("他周一送合影", now="2026-05-02")
    assert et == "2026-05-04"
    assert kind == "derived"


def test_relative_last_week():
    # 2026-04-13 周一，上周三 = 4/08
    et, kind = resolve_event_time("他上周三去面试", now="2026-04-13")
    assert et == "2026-04-08"
    assert kind == "derived"


def test_no_time_word_is_none():
    et, kind = resolve_event_time("他重感情", now="2026-05-04")
    assert et is None
    assert kind == "none"


def test_no_anchor_returns_none_for_relative():
    # 没锚点，相对词没法换算 → none
    et, kind = resolve_event_time("他下周三约了人", now=None)
    assert et is None
    assert kind == "none"


def test_bare_number_day_is_explicit():
    # 裸「X号」当「几号那天」算日期：13号 → 用 now 的年月补
    et, kind = resolve_event_time("他 13号 交了稿", now="2026-05-07")
    assert et == "2026-05-13"
    assert kind == "explicit"


def test_numbered_object_is_not_date():
    # 「3号楼」「2号电池」是编号/序号，不是「几号那天」，绝不能抠成 event_time
    # （否则会凭空造出「编造日期」记忆，撞判官「编造日期」flag）。
    for text in ("他住在3号楼", "他换了2号电池", "他是1号队员", "他住3号楼501室"):
        et, kind = resolve_event_time(text, now="2026-05-07")
        assert et is None, f"误判成日期: {text} -> {et}"
        assert kind == "none"


def test_explicit_partial_date_without_now_is_none():
    # 「4月13日」「13号」缺年份，没有锚点补不齐，就不该标 explicit（否则把
    # 「4月13日」这个不完整日期当确定日期存进 event_time）。
    for text in ("他 4月13日 交稿", "他 13号 交稿"):
        et, kind = resolve_event_time(text, now=None)
        assert et is None, f"无锚点却抠出日期: {text} -> {et}"
        assert kind == "none"


def test_explicit_full_date_without_now_kept():
    # 完整日期（带年份）不需要锚点，仍然能抠。
    et, kind = resolve_event_time("他 2026-04-13 交稿", now=None)
    assert et == "2026-04-13"
    assert kind == "explicit"


def test_last_month_day():
    # 「上个月X号」= 上个月的 X 号（不是当月）
    et, kind = resolve_event_time("他上个月26号就从设计院出来", now="2026-05-07")
    assert et == "2026-04-26"
    assert kind == "explicit"


def test_next_month_day():
    et, kind = resolve_event_time("他下个月26号交房", now="2026-05-07")
    assert et == "2026-06-26"
    assert kind == "explicit"


def test_this_month_day():
    et, kind = resolve_event_time("他这个月3号前补完", now="2026-05-07")
    assert et == "2026-05-03"
    assert kind == "explicit"


def test_last_month_cross_year():
    # 跨年：now=2026-01，上个月 = 2025-12
    et, kind = resolve_event_time("他上个月20号交稿", now="2026-01-15")
    assert et == "2025-12-20"
    assert kind == "explicit"


def test_next_month_cross_year():
    # 跨年：now=2026-12，下个月 = 2027-01
    et, kind = resolve_event_time("他下个月5号入职", now="2026-12-20")
    assert et == "2027-01-05"
    assert kind == "explicit"


def test_last_week_day():
    # now=2026-05-07 是周四，上周三 = 04-29
    et, kind = resolve_event_time("他上周三交稿", now="2026-05-07")
    assert et == "2026-04-29"
    assert kind == "derived"


def test_this_week_day():
    # now=2026-05-07 是周四，本周三 = 05-06
    et, kind = resolve_event_time("他这周三交稿", now="2026-05-07")
    assert et == "2026-05-06"
    assert kind == "derived"


def test_next_week_day():
    # now=2026-05-07 是周四，下周三 = 05-13
    et, kind = resolve_event_time("他下周三入职", now="2026-05-07")
    assert et == "2026-05-13"
    assert kind == "derived"


def test_two_weeks_ago_day():
    # now=2026-05-07 是周四，上上周三 = 04-22
    et, kind = resolve_event_time("他上上周三交稿", now="2026-05-07")
    assert et == "2026-04-22"
    assert kind == "derived"


def test_two_weeks_later_day():
    # now=2026-05-07 是周四，下下周三 = 05-20
    et, kind = resolve_event_time("他下下周三入职", now="2026-05-07")
    assert et == "2026-05-20"
    assert kind == "derived"


# —— 以下 9 条是 2026-11-15 加的：四处日期缺陷 + 裸号收窄 ——


def test_big_before_yesterday():
    """「大前天」不能被「前天」抢先匹配。"""
    et, kind = resolve_event_time("他大前天去了杭州", now="2026-05-04")
    assert et == "2026-05-01"
    assert kind == "derived"


def test_big_after_tomorrow():
    et, kind = resolve_event_time("他大后天回来", now="2026-05-04")
    assert et == "2026-05-07"
    assert kind == "derived"


def test_cn_numeral_month_day():
    """「七月四号」是中文数字月份，原文解析不出来会退到 created_at 造出编造日期。"""
    et, kind = resolve_event_time("他打算七月四号搬家", now="2026-05-24")
    assert et == "2026-07-04"
    assert kind == "explicit"


def test_cn_numeral_bare_day():
    et, kind = resolve_event_time("他二十号交稿", now="2026-05-24")
    assert et == "2026-05-20"
    assert kind == "explicit"


def test_cn_numeral_thirty_one():
    et, kind = resolve_event_time("他三十一号结账", now="2026-05-24")
    assert et == "2026-05-31"
    assert kind == "explicit"


def test_written_month_not_overridden_by_month_offset():
    """「上个月说6月19号交房租」：月份写明了就是 6 月，「上个月」说的是说话时机。

    旧实现把 _month_delta 的 -1 叠上去，读成 4-19，把用户的 6 月整个丢掉。
    """
    et, kind = resolve_event_time("他上个月说6月19号交房租", now="2026-05-04")
    assert et == "2026-06-19"
    assert kind == "explicit"


def test_last_year_keeps_year():
    """「去年7月4号」不能被补成今年。"""
    et, kind = resolve_event_time("他去年7月4号搬的家", now="2026-05-24")
    assert et == "2025-07-04"
    assert kind == "explicit"


def test_periodic_sentence_is_not_a_date():
    """「每个月5号交房租」是周期句，不能固化成 2026-05-05 这一次。"""
    for text in ("他每个月5号交房租", "他每周三去健身"):
        et, kind = resolve_event_time(text, now="2026-05-24")
        assert et is None, f"周期句被抠成日期: {text} -> {et}"
        assert kind == "none"


def test_periodic_guarded_only_on_the_adjacent_date():
    """周期词只拦它后面紧挨着那个日期，同句里别处的真日期照常抠。

    「他每天都很累，5号那天交了稿」里的 5 号是真的某一天，不能一起拦掉。
    """
    et, kind = resolve_event_time("他每天都很累，5号那天交了稿", now="2026-05-24")
    assert et == "2026-05-05"
    assert kind == "explicit"


def test_periodic_weekday_falls_through_to_real_one():
    """「他每周三去健身，上周三没去」要落到上周三，不能停在「每周三」。"""
    et, kind = resolve_event_time("他每周三去健身，上周三没去", now="2026-05-24")
    assert et == "2026-05-13"
    assert kind == "derived"


def test_numbered_object_extended_negatives():
    """裸「X号」的负向断言要覆盖桌/台风/校区/选手/柜等常见名词。"""
    for text in ("他 3号桌 有人", "8号台风要来了", "他住5号校区",
                 "他是1号选手", "他在7号柜放着"):
        et, kind = resolve_event_time(text, now="2026-05-24")
        assert et is None, f"误判成日期: {text} -> {et}"
        assert kind == "none"
