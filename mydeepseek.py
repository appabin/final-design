import os
from dotenv import load_dotenv
from datetime import datetime

# 1. 导入新版核心组件
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI  # 我们依然用这个类来连接 DeepSeek
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver # 用于记忆

# 加载 .env
load_dotenv()

# --- 2. 定义工具 (保持不变) ---
@tool
def get_current_time():
    """获取当前的具体时间。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

@tool
def count_letters(word: str) -> int:
    """计算一个单词的字母数量。"""
    return len(word)

@tool
def add(a: int, b: int) -> int:
    """计算两个整数相加的结果。当用户要求做加法计算时使用此工具。"""
    return a + b


tools = [get_current_time, count_letters ,add]

# --- 3. 初始化模型 (关键点) ---
# 虽然新文档用了 init_chat_model，但为了连接 DeepSeek (非标准 OpenAI)，
# 我们直接实例化 ChatOpenAI 对象传进去最稳妥。
model = ChatOpenAI(
    model=os.getenv("LLM_MODEL_ID", "deepseek-chat"),
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL"),
    temperature=0
)

# --- 4. 配置记忆 (Checkpointer) ---
# LangGraph 用 "Checkpointer" 来管理记忆，这比以前的 Memory 更先进
checkpointer = InMemorySaver()

# --- 5. 创建新版 Agent ---
# 注意：这里不再用 AgentExecutor 了！
agent = create_agent(
    model=model,
    tools=tools,
    system_prompt="你是一个聪明的助手。如果需要获取信息，请使用工具。",
    checkpointer=checkpointer
)

# --- 6. 运行 Agent ---
print("----- 测试 LangChain v1 Agent (DeepSeek) -----")

# 配置线程 ID (Thread ID)，这代表一段对话的“身份证”
# 只要 ID 一样，Agent 就能记得之前的聊天内容
config = {"configurable": {"thread_id": "test_thread_1"}}

query = "请帮我计算 192837465 加上 918273678978978979879845 是多少？"

print(f"\nUser: {query}")
response = agent.invoke(
    {"messages": [{"role": "user", "content": query}]},
    config=config
)

print(f"Agent: {response['messages'][-1].content}")