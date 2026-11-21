# store.py —— 记忆的读写、备份、审计

import json
import os

def save_items(items, path="data/items.json"):
    """
    把一堆记忆条目保存到硬盘文件。

    参数：
        items : 一个列表，里面是一条条记忆字典
        path  : 保存到的文件路径

    返回：
        保存的文件路径

    写入方式（2026-11-15 改）：先写同目录临时文件，fsync 落盘，再 os.replace
    原子替换。旧写法 `open(path,"w")` 是先截断再写，中途崩一次就留下半截
    JSON——`load_items` 随即 JSONDecodeError，而库里有上万条记忆，等于全丢。
    os.replace 在 Windows 上也是原子的（同一卷内），崩了最坏是保留旧文件。
    """
    # 1. 确保 data 文件夹存在（不存在就创建）
    folder = os.path.dirname(path)
    if folder and not os.path.exists(folder):
        os.makedirs(folder)

    # 2. 把 Python 对象变成 JSON 文本
    text = json.dumps(items, ensure_ascii=False, indent=2)

    # 3. 先写临时文件，落盘后再原子替换
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

    return path

def load_items(path="data/items.json"):
    """
    从硬盘文件读回记忆条目。

    参数：
        path : 文件路径

    返回：
        一个列表，里面是记忆字典；文件不存在则返回空列表

    容错（2026-11-15 加）：文件存在但内容损坏（半截 JSON）时，先试着读
    同目录的 `path + ".tmp"`（可能写完了没来得及替换），再退到最新的
    `path + ".bak-*"`。全都不行才抛错——但报错里带上路径和大小，
    不再是裸 JSONDecodeError，方便当场判断损失范围。
    """
    # 文件不存在，返回空列表（不报错）
    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    try:
        # 把 JSON 文本变回 Python 对象
        return json.loads(text)
    except json.JSONDecodeError as exc:
        rescued, origin = _rescue(path)
        if rescued is not None:
            return rescued
        raise ValueError(
            f"记忆库 {path} 已损坏（{len(text)} 字节，第 {exc.lineno} 行第 "
            f"{exc.colno} 列），且没有可用的临时文件或备份。"
            f"请检查是否在写入过程中崩溃。"
        ) from exc


def _rescue(path):
    """
    JSON 损坏时找一份能用的副本，返回 (items, 来源路径)；找不到返回 (None, None)。

    顺序：先看写入用的临时文件（可能是写完了还没来得及 os.replace），
    再按修改时间倒序试 .bak-* 备份。
    """
    candidates = [path + ".tmp"]
    folder = os.path.dirname(path) or "."
    base = os.path.basename(path)
    try:
        names = os.listdir(folder)
    except OSError:
        names = []
    baks = [os.path.join(folder, n) for n in names if n.startswith(base + ".bak-")]
    baks.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    candidates.extend(baks)

    for cand in candidates:
        if not os.path.exists(cand):
            continue
        try:
            with open(cand, "r", encoding="utf-8") as f:
                return json.loads(f.read()), cand
        except (json.JSONDecodeError, OSError):
            continue
    return None, None

def backup_file(path):
    """
    把一个文件备份成 .bak-<时间戳>。

    参数：
        path : 要备份的文件路径

    返回：
        备份后的文件路径；如果原文件不存在，返回 None

    注意（2026-11-04）：当前项目还没投入应用，数据无价值，
    备份暂不启用——没有入口调用本函数，仅留作将来投入应用时使用。
    """
    if not os.path.exists(path):
        return None

    # 生成带时间戳的备份名：items.json.bak-20261027-183000
    import time
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup_path = path + ".bak-" + stamp

    # 复制原文件内容到备份文件
    with open(path, "r", encoding="utf-8") as src:
        content = src.read()
    with open(backup_path, "w", encoding="utf-8") as dst:
        dst.write(content)

    return backup_path
