# test_llm.py —— 验证「临时状态不进长期记忆」+「猜测谨慎」

from llm import make_deepseek_llm
from reconstruct import reconstruct
from index import Cognition


def main():
    llm = make_deepseek_llm()

    buffer = [
        "用户：今天好累啊，跑了一天",
        "用户：对了，我其实是学化学的",
        "AI：学化学挺有意思的",
    ]

    cog = Cognition(data_dir="demo_data6")
    added = reconstruct(llm, buffer, cog.remember)

    print("提炼了", added, "条新记忆")
    print("---")
    print(cog.recall_block(limit=8))

# 用真模型测语义召回

from llm import make_deepseek_llm
from recall import semantic_recall
from item import make_item


def main():
    llm = make_deepseek_llm()

    # 一批记忆
    items = [
        make_item("他叫南风", "user_said", 0.9),
        make_item("他爱吃辣，无辣不欢", "user_said", 0.9),
        make_item("他最近在找工作，压力大", "user_said", 0.9),
        make_item("他喜欢打篮球", "user_said", 0.9),
    ]

    # 用户说：和「找工作」相关
    query = "我下周要去面试了，好紧张"

    result = semantic_recall(llm, items, query)

    print("用户说：", query)
    print("召回的相关记忆：")
    for m in result:
        print("  -", m["text"])


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()