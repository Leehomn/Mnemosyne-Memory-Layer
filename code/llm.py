# llm.py —— 调用 DeepSeek 模型

import json
import os
from openai import OpenAI


def load_config():
    """读 config.json，返回配置字典。

    config.json 锚定在 llm.py 自己所在的目录（而不是当前工作目录），
    这样不管从哪个目录运行脚本，都能找到配置文件，不会因为
    「相对路径换了个 cwd 就找不到」而崩。
    """
    path = os.path.join(os.path.dirname(__file__), "config.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def make_deepseek_llm():
    """
    返回一个「能调用 DeepSeek 的函数」。
    符合 reconstruct 的 llm 接口：给它 prompt，返回回答文本。
    """
    config = load_config()
    client = OpenAI(api_key=config["api_key"], base_url=config["base_url"])

    def llm(prompt):
        response = client.chat.completions.create(
            model=config["model"],
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content

    return llm