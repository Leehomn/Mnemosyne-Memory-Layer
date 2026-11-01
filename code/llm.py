# llm.py —— 调用 DeepSeek 模型

import json
from openai import OpenAI


def load_config():
    """读 config.json，返回配置字典。"""
    with open("config.json", "r", encoding="utf-8") as f:
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