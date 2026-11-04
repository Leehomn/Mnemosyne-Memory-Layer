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
    """
    # 1. 确保 data 文件夹存在（不存在就创建）
    folder = os.path.dirname(path)
    if folder and not os.path.exists(folder):
        os.makedirs(folder)

    # 2. 把 Python 对象变成 JSON 文本
    text = json.dumps(items, ensure_ascii=False, indent=2)

    # 3. 写入文件（utf-8 编码，避免中文乱码）
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

    return path

def load_items(path="data/items.json"):
    """
    从硬盘文件读回记忆条目。

    参数：
        path : 文件路径

    返回：
        一个列表，里面是记忆字典；文件不存在则返回空列表
    """
    # 文件不存在，返回空列表（不报错）
    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    # 把 JSON 文本变回 Python 对象
    return json.loads(text)

def backup_file(path):
    """
    把一个文件备份成 .bak-<时间戳>。

    参数：
        path : 要备份的文件路径

    返回：
        备份后的文件路径；如果原文件不存在，返回 None
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
