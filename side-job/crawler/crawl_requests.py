# crawl_requests.py —— 爬虫「增强版」（需要 requests + bs4）
#
# 安装：
#   pip install requests beautifulsoup4
#
# 相比零依赖版多了：会话复用、自动重试、robots 检查、更稳的选择器解析。
# 客户环境能装包的时候用这个；装不了就用 crawl_stdlib.py。

import argparse
import csv
import sys
import time
import urllib.parse
import urllib.robotparser

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("缺依赖，先运行：pip install requests beautifulsoup4\n"
             "（或者改用零依赖版：python crawl_stdlib.py <URL>）")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")


def make_session():
    """建一个会复用连接、带请求头的 session。"""
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    return s


def allowed_by_robots(url, user_agent=UA):
    """
    检查 robots.txt 是否允许抓取。不允许就返回 False。
    接商业单前务必跑这个——对方投诉的话，平台会封你号。
    """
    parts = urllib.parse.urlparse(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
    except Exception:
        return True          # 读不到 robots.txt，视为允许
    return rp.can_fetch(user_agent, url)


class PoliteFetcher:
    """带限速和重试的下载器。"""

    def __init__(self, session=None, delay=1.0, retries=3):
        self.session = session or make_session()
        self.delay = delay
        self.retries = retries
        self.last = 0.0

    def get(self, url, **kw):
        for attempt in range(self.retries + 1):
            gap = time.time() - self.last
            if gap < self.delay:
                time.sleep(self.delay - gap)
            try:
                r = self.session.get(url, timeout=15, **kw)
                r.raise_for_status()
                # requests 猜错编码是国内站乱码的主因（GBK 站被猜成 ISO-8859-1）
                if "charset" not in (r.headers.get("Content-Type") or "").lower():
                    r.encoding = r.apparent_encoding
                self.last = time.time()
                return r.text
            except requests.RequestException as e:
                if attempt == self.retries:
                    raise
                print(f"  第 {attempt + 1} 次失败（{e}），退避重试…")
                time.sleep(2 ** attempt)


def parse_with_selectors(html, selectors):
    """
    按 CSS 选择器抽结构化数据。

    参数：
        html       : HTML 文本
        selectors  : dict，如 {"标题": "h2.title", "价格": "span.price"}

    返回：list[dict]
    """
    soup = BeautifulSoup(html, "html.parser")
    # 先按第一个选择器找到「条目容器」，再在容器内取各项
    first = list(selectors.values())[0]
    first_nodes = soup.select(first)
    if not first_nodes:
        return []

    container = first_nodes[0].parent
    items = [container] if len(first_nodes) == 1 else container.find_all(
        first_nodes[0].name, recursive=False) or [container]

    rows = []
    for item in items:
        row = {}
        for field, sel in selectors.items():
            node = item.select_one(sel)
            row[field] = node.get_text(strip=True) if node else ""
        rows.append(row)
    return rows


def save_csv(rows, path):
    if not rows:
        print("没有抓到数据，检查选择器是否正确")
        return
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"已保存 {len(rows)} 行 → {path}")


SELECTOR_PRESETS = {
    # 客户常要的几类站点，选择器先存这里，接单时改一改就能用
    "generic_links": {
        "标题": "a",
        "链接": "a[href]",
    },
}


def main():
    ap = argparse.ArgumentParser(description="requests 版爬虫模板")
    ap.add_argument("url", help="目标 URL")
    ap.add_argument("-o", "--output", default="result.csv", help="输出 csv")
    ap.add_argument("-s", "--selector", default=None,
                    help='CSS 选择器，如 \'{"标题":"h2 a","摘要":"p.desc"}\'')
    ap.add_argument("--ignore-robots", action="store_true", help="跳过 robots 检查（仅在自己有权限时）")
    args = ap.parse_args()

    if not args.ignore_robots and not allowed_by_robots(args.url):
        print(f"robots.txt 禁止抓取：{args.url}\n"
              f"仅限你自己有权限的站点再加 --ignore-robots")
        return

    html = PoliteFetcher().get(args.url)
    print(f"抓到 {len(html)} 字符")

    selectors = None
    if args.selector:
        import json
        selectors = json.loads(args.selector)
    elif SELECTOR_PRESETS.get("generic_links"):
        selectors = SELECTOR_PRESETS["generic_links"]

    rows = parse_with_selectors(html, selectors) if selectors else []
    save_csv(rows, args.output)


if __name__ == "__main__":
    main()
