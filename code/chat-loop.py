# chat-loop.py —— 端到端演示（真模型版）

from index import Cognition
from reconstruct import reconstruct
from llm import make_deepseek_llm


def main():
    print("=" * 50)
    print("Mnemosyne 记忆系统 · 端到端演示（真 DeepSeek）")
    print("=" * 50)

    # 真模型
    llm = make_deepseek_llm()
    cog = Cognition(data_dir="demo_data3")

    # 一段对话
    buffer = [
        "用户：我叫南风，我是四川人",
        "AI：好的，南风你好呀",
        "用户：我超爱吃辣的，无辣不欢",
        "AI：四川人是挺能吃辣的",
    ]
    print("\n② 一段对话：")
    for line in buffer:
        print("   ", line)

    # 真模型重构
    added = reconstruct(llm, buffer, cog.remember)
    print(f"\n③ 重构：真模型从对话提炼了 {added} 条新记忆")

    # 召回
    block = cog.recall_block(limit=8)
    print("\n④ 当前记住的（事实/猜测分区）：")
    print(block)

    # 维护
    removed = cog.maintain()
    print(f"\n⑤ 维护：淘汰了 {removed} 条过期记忆")

    print("\n" + "=" * 50)
    print("演示结束")
    print("=" * 50)


if __name__ == "__main__":
    main()