# demo_llm_verify.py —— 真模型验证：临时状态不进长期记忆 + 语义召回

# 说明：需要先在 config.json 里填好有效的 api_key。
# 运行：在 code/ 目录下执行  python demo_llm_verify.py

from llm import make_deepseek_llm
from reconstruct import reconstruct
from index import Cognition
from recall import semantic_recall
from item import make_item


def verify_temp_state_not_memorized():
    """验证：临时状态（累、心情）不该进长期记忆，只有稳定特质才记。"""
    llm = make_deepseek_llm()

    buffer = [
        "用户：今天好累啊，跑了一天",
        "用户：对了，我其实是学化学的",
        "AI：学化学挺有意思的",
    ]

    cog = Cognition(data_dir="demo_data6", llm=llm)
    added = reconstruct(llm, buffer, cog.remember)

    print("提炼了", added, "条新记忆")
    print("---")
    print(cog.recall_block(limit=8))


def verify_semantic_recall():
    """验证：语义召回能按「相关性」而非字面匹配召回。"""
    llm = make_deepseek_llm()

    items = [
        make_item("他叫南风", "user_said", 0.9),
        make_item("他爱吃辣，无辣不欢", "user_said", 0.9),
        make_item("他最近在找工作，压力大", "user_said", 0.9),
        make_item("他喜欢打篮球", "user_said", 0.9),
    ]

    query = "我下周要去面试了，好紧张"

    result = semantic_recall(llm, items, query)

    print("用户说：", query)
    print("召回的相关记忆：")
    for m in result:
        print("  -", m["text"])


if __name__ == "__main__":
    print("=== 验证 1：临时状态不进长期记忆 ===")
    verify_temp_state_not_memorized()
    print()
    print("=== 验证 2：语义召回 ===")
    verify_semantic_recall()
