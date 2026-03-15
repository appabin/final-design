import os
import math # 导入数学库，支持 sqrt, sin 等高级运算
from dotenv import load_dotenv
from datetime import datetime

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

load_dotenv()

# --- 1. 定义工具 ---

@tool
def get_current_time():
    """获取当前的具体时间。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# 🟢 这是一个全能计算器工具
@tool
def calculator(expression: str) -> str:
    """
    这是一个通用的数学计算器。
    当你需要进行任何数学运算（加减乘除、乘方、开方等）时，请使用此工具。
    输入应该是一个有效的 Python 数学表达式字符串，例如 "(123 + 456) * 78"。
    """
    try:
        # 限制 eval 的作用域，只允许使用 math 库和基础运算，防止安全风险
        # 这样 Agent 甚至可以使用 math.sqrt(100)
        allowed_names = {"math": math}
        result = eval(expression, {"__builtins__": None}, allowed_names)
        
        print(f"\n[计算器] 正在计算表达式: {expression}")
        print(f"[计算器] 结果: {result}")
        
        return str(result)
    except Exception as e:
        return f"计算出错: {e}"

# 🟢 更新工具列表
tools = [get_current_time, calculator]

# --- 2. 初始化模型 ---
model = ChatOpenAI(
    model=os.getenv("LLM_MODEL_ID", "deepseek-chat"),
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL"),
    temperature=0
)

# --- 3. 创建 Agent ---
checkpointer = InMemorySaver()

agent = create_agent(
    model=model,
    tools=tools,
    system_prompt="你是一个精通数学的助手。遇到计算问题，请将自然语言转换为 Python 数学表达式，并调用 calculator 工具求解。",
    checkpointer=checkpointer
)

# --- 4. 运行高难度测试 ---
print("----- 测试全能计算器 -----")

config = {"configurable": {"thread_id": "math_pro_1"}}

# 这是一个包含：大数、乘法、加法、乘方(^) 的复杂问题
# DeepSeek 会把它翻译成 Python 语法： 123456789 * 987654321 + 2**10
query = "请帮我算一下：一亿两千三百四十五万六千七百八十九 乘以 九亿八千七百六十五万四千三百二十一，然后再加上 2 的 10 次方，结果是多少？"

print(f"\nUser: {query}")
response = agent.invoke(
    {"messages": [{"role": "user", "content": query}]},
    config=config
)

print(f"Agent: {response['messages'][-1].content}")