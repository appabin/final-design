# main.py
import os
from dotenv import load_dotenv

# 🔴 从 agent 包中导入构建函数
from agent.graph import build_agent_graph

# 加载环境
load_dotenv()

if __name__ == "__main__":
    print("启动 Agent...")
    
    # 1. 获取编译好的图
    app = build_agent_graph()
    
    # 2. 运行
    inputs = {"question": "今天的时间是，我什么时候会有新的年假"}
    result = app.invoke(inputs)
    
    print(result["answer"])



