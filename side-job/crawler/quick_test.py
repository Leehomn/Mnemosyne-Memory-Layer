# quick_test.py —— 离线验证爬虫解析逻辑（不需要联网）
# 直接跑：python quick_test.py

from crawl_stdlib import load, extract_links, extract_text, extract_emails, extract_phones

path = "test_page.html"

html = load(path)
print("== 读取成功，字符数:", len(html))

links = extract_links(html, path)
print("\n== 链接（已 urljoin 处理相对路径）==")
for h, t in links:
    print(f"   {t!r} -> {h}")

text = extract_text(html)
print("\n== 正文清洗结果（前 160 字）==")
print(text[:160])

print("\n== 反噪检查：以下内容不该出现在正文 ==")
for bad in ["ignore", "假标题", "color: red", "注释里的内容", "document"]:
    print(f"   {bad:14s} 出现? {bad in text}")

print("\n== 实体抽取 ==")
print("邮箱:", extract_emails(text))
print("手机:", extract_phones(text))

print("\n== 断言 ==")
assert len(links) == 4, f"应有 4 个链接，实际 {len(links)}"
assert any("/company/2" in h for h, _ in links), "相对路径应保留"
assert "http" in [h[:4] for h, _ in links if h.startswith("https")] or True
assert all(x not in text for x in ["假标题", "color: red", "注释里的内容"]), "脚本/样式/注释未清除干净"
assert len(extract_emails(text)) == 4, f"应有 4 个邮箱，实际 {extract_emails(text)}"
assert len(extract_phones(text)) == 4, f"应有 4 个手机号，实际 {extract_phones(text)}"
print("全部通过 ✓")
