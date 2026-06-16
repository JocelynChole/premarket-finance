"""时区修复后回归测试"""
from datetime import datetime, timezone, timedelta
import re as _re
CST = timezone(timedelta(hours=8))
WEEKDAY_CN = {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 5: "周六", 6: "周日"}

TIME_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%a, %d %b %Y %H:%M:%S %z",
    "%a, %d %b %Y %H:%M:%S GMT",
    "%a, %d %b %Y %H:%M:%S",
    "%d %b %Y %H:%M:%S",
]


def parse_pub_time(pub_time_str):
    if not pub_time_str or not isinstance(pub_time_str, str):
        return None
    text = pub_time_str.strip()
    text = text.replace("GMT+0800", "+0800").replace("CST", "").strip()
    text = _re.sub(r'\s+GMT\s*$', ' +0000', text)
    for fmt in TIME_FORMATS:
        try:
            dt = datetime.strptime(text, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=CST)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def extract_time_fields(pub_time_str):
    dt_utc = parse_pub_time(pub_time_str)
    if dt_utc is None:
        return {"raw": pub_time_str, "cst_str": "解析失败"}
    dt_cst = dt_utc.astimezone(CST)
    return {
        "raw": pub_time_str,
        "utc": dt_utc.strftime("%Y-%m-%d %H:%M:%S"),
        "cst": dt_cst.strftime("%Y-%m-%d %H:%M:%S"),
        "display": f"{dt_cst.strftime('%Y-%m-%d %H:%M')} {WEEKDAY_CN.get(dt_cst.weekday(), '')}",
    }


# 模拟 3 个源 + 各种边界情况
test_cases = [
    # 新浪/同花顺（已正确带 +0800）
    ("新浪 18:36 北京",  "Tue, 16 Jun 2026 18:36:00 +0800"),
    ("同花顺 18:36 北京", "Tue, 16 Jun 2026 18:36:00 +0800"),
    # 修复后的东方财富（带 +0800）
    ("东方修后 18:36",   "Tue, 16 Jun 2026 18:36:00 +0800"),
    # 边界 1：跨午夜（前一晚 23:50 北京时间）
    ("前一晚 23:50",     "Mon, 15 Jun 2026 23:50:00 +0800"),
    # 边界 2：凌晨 01:30 北京时间
    ("凌晨 01:30",       "Tue, 16 Jun 2026 01:30:00 +0800"),
    # 边界 3：开盘 09:30
    ("开盘 09:30",       "Tue, 16 Jun 2026 09:30:00 +0800"),
    # 边界 4：收盘 15:00
    ("收盘 15:00",       "Tue, 16 Jun 2026 15:00:00 +0800"),
    # 异常：UTC 源（如果某源用 +0000）
    ("UTC 源 10:36",      "Tue, 16 Jun 2026 10:36:00 +0000"),
    # 异常：GMT 字面量
    ("GMT 字面量 10:36", "Tue, 16 Jun 2026 10:36:00 GMT"),
    # 异常：naive 字符串（理论上不该出现）
    ("naive 18:36",       "2026-06-16 18:36:00"),
]

print(f"{'场景':18s} | {'原始':32s} | {'CST 显示':24s} | UTC")
print("-" * 100)
for name, ts in test_cases:
    r = extract_time_fields(ts)
    print(f"{name:18s} | {r['raw']:32s} | {r['display']:24s} | {r.get('utc', 'N/A')}")
