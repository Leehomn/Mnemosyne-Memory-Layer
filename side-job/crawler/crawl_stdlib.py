# crawl_stdlib.py —— 爬虫「零依赖版」（只用 Python 自带库）
#
# 用法：
#   python crawl_stdlib.py <URL> [-o out.csv] [--limit 5]
#
# 什么时候用这个：
#   交付给客户时不用他 pip install 任何东西，双击就能跑。
#   缺点是只有基础解析能力；复杂页面换 requests 版。
#
# 关键设计：
#   - 带真实 User-Agent（很多站点拒绝默认的 python-urllib）
#   - 自动识别编码（国内站很多是 GBK，不识别就是乱码）
#   - 按 token 限速（每秒 1 次），不做请求轰炸

import argparse
import csv
import gzip
import io
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

_last_request = [0.0]


def polite_wait(seconds=1.0):
    """限速：距上次请求不足 seconds 就等一会儿。别把人家网站搞崩，也别被封 IP。"""
    gap = time.time() - _last_request[0]
    if gap < seconds:
        time.sleep(seconds - gap)
    _last_request[0] = time.time()


def read_local_file(path):
    """
    读本地 HTML 文件，自动处理 UTF-8 / GBK 两种编码。

    为什么需要：客户经常直接甩一个「网页另存为」的 html 给你，
    或者网络受限时先让人另存，脚本照样能跑。
    这种 light/? 的情况（本地 vs URL）要的是「同一套解析逻辑两种输入」，
    所以抽出这一层，让 process 逻辑不被输入方式绑死。
    """
    raw = open(path, "rb").read()
    for enc in ("utf-8", "gbk", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def load(url_or_path, timeout=15, retries=2):
    """
    统一入口：给 URL 就联网抓，给本地路径就读文件。

    参数：
        url_or_path : http(s):// 开头的 URL，或本地 html 文件路径

    返回：HTML 文本（已正确解码）
    """
    if urlish(url_or_path):
        return fetch(url_or_path, timeout=timeout, retries=retries)
    print(f"  （本地文件模式）读取 {url_or_path}")
    return read_local_file(url_or_path)


def urlish(s):
    """判断是不是一个 URL（而不是本地路径）。"""
    return bool(re.match(r"^(https?|file)://", s, re.I))


def fetch(url, timeout=15, retries=2):
    """
    抓取一个 URL，返回 HTML 文本（已解码为中文）。

    处理了：超时重试、gzip 压缩、GBK/UTF-8 编码识别。
    """
    # file:// 也走一遍——本地 file 协议用 urllib 打开是可靠的
    if url.lower().startswith("file://"):
        return read_local_file(urllib.request.url2pathname(url[7:]))
    for attempt in range(retries + 1):
        polite_wait()
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)

                # 编码识别：优先 HTTP 头 → 再看 <meta charset> → 兜底 utf-8
                enc = resp.headers.get_content_charset()
                if not enc:
                    m = re.search(rb'charset=["\']?([\w-]+)', raw[:2048])
                    enc = m.group(1).decode("ascii", "ignore") if m else None
                try:
                    return raw.decode(enc or "utf-8", errors="replace")
                except LookupError:      # 遇到了 Python 不认识的编码名
                    return raw.decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == retries:
                raise
            print(f"  第 {attempt + 1} 次失败（{e}），重试…")
            time.sleep(2 ** attempt)


class LinkCollector(HTMLParser):
    """抽出所有 <a href> 的绝对地址和文字。"""

    def __init__(self, base_url):
        super().__init__()
        self.base = base_url
        self.links = []
        # 必须是 None，不能是 []：否则第一个 <a> 之前的正文会去访问空列表的下标 1
        self._text = None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append([urllib.parse.urljoin(self.base, href), ""])
                self._text = self.links[-1]

    def handle_endtag(self, tag):
        # 标签闭合就断开关联，否则 </a> 后面的正文会粘到上一个链接标题上
        if tag == "a":
            self._text = None

    def handle_data(self, data):
        if self._text is not None and len(self._text) > 1 and data.strip():
            self._text[1] += data.strip()


def extract_links(html, base_url):
    """从 HTML 提取 [(链接, 文字)]。"""
    c = LinkCollector(base_url)
    c.feed(html)
    return [tuple(x) for x in c.links if x[1]]


def extract_text(html):
    """去掉 <script>/<style>/标签，只留正文文字。"""
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    html = re.sub(r"(?s)<!--.*?-->", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;?", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    return re.sub(r"[ \t\r\f\v]+", " ", text).strip()


def extract_emails(text):
    """抽邮箱——很多来找你写爬虫的客户，真正要的就是这个。"""
    return sorted(set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)))


def extract_phones(text):
    """抽手机号。"""
    return sorted(set(re.findall(r"(?<!\d)1[3-9]\d{9}(?!\d)", text)))


def demo_listing(url, limit=5, exc=None):
    """示例：把一个页面的链接抽出来，返回结构化数据。"""
    html = load(url) if exc is None else exc
    links = extract_links(html, url)
    rows = [{"来源页": url, "链接": href, "标题": title[:80]} for href, title in links[:limit]]
    return rows, html


def save_csv(rows, path):
    if not rows:
        print("没有数据，不写文件")
        return
    with open(path, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig：Excel 打开中文不乱码
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"已保存 {len(rows)} 行 → {path}")


def main():
    ap = argparse.ArgumentParser(description="零依赖爬虫模板")
    ap.add_argument("url", help="起始 URL")
    ap.add_argument("-o", "--output", default="result.csv", help="输出 csv")
    ap.add_argument("--limit", type=int, default=5, help="最多抽几条")
    args = ap.parse_args()

    rows, html = demo_listing(args.url, args.limit)
    save_csv(rows, args.output)

    text = extract_text(html)
    phones = extract_phones(text)
    if phones:
        print(f"页面里发现手机号 {len(phones)} 个：{phones[:3]}")


if __name__ == "__main__":
    main()
