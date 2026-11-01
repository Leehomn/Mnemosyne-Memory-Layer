# demo_semantic_recall.py —— 语义召回演示（真 DeepSeek 版）

# 说明：需要先在 config.json 里填好有效的 api_key，否则会调用失败。
# 运行：在 code/ 目录下执行  python demo_semantic_recall.py

from llm import make_deepseek_llm
from index import Cognition


def main():
    llm = make_deepseek_llm()
    cog = Cognition(data_dir="demo_data7", llm=llm)

    # 记几条
    cog.remember("他叫南风", source="user_said")
    cog.remember("他爱吃辣，无辣不欢", source="user_said")
    cog.remember("他最近在找工作，压力大", source="user_said")

    # 语义召回：聊「面试」
    print("=== 聊「面试」时的召回 ===")
    print(cog.semantic_recall_block("我下周要去面试了"))


if __name__ == "__main__":
    main()
