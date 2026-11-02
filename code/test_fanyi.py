# 临时验证：反义场景
from llm import make_deepseek_llm
from recall import semantic_recall
from item import make_item

llm = make_deepseek_llm()

items = [
    make_item("他爱吃辣", "user_said", 0.9),
    make_item("他喜欢打篮球", "user_said", 0.9),
]

# 用户现在说「不吃辣了」
query = "我现在不吃辣了，改清淡了"

result = semantic_recall(llm, items, query)

print("用户说：", query)
print("召回的相关记忆：")
for m in result:
    print("  -", m["text"])

print("\n（如果这里没有「他爱吃辣」，说明反义识别成功了）")