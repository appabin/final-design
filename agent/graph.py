# agent/graph.py
from langgraph.graph import StateGraph, END

# 🔴 导入零件
from agent.state import GraphState
from agent.nodes import retrieve_node, generate_node, grade_documents_node,web_search_node,format_output_node,decide_to_generate


def build_agent_graph():
    """构建并编译图"""
    workflow = StateGraph(GraphState)


    # 添加节点
    workflow.add_node("retrieve_node", retrieve_node)
    workflow.add_node("grade_node", grade_documents_node) # 新增
    workflow.add_node("web_search_node", web_search_node) # 新增
    workflow.add_node("generate_node", generate_node)
    workflow.add_node("format_node", format_output_node) # 你写的格式化节点

    # 1. 入口 -> 检索
    workflow.set_entry_point("retrieve_node")

    # 2. 检索 -> 评分
    workflow.add_edge("retrieve_node", "grade_node")

    # 3. 评分 -> 条件路由 (关键！)
    # add_conditional_edges 接收三个参数：
    # (1) 上一个节点
    # (2) 路由逻辑函数 (decide_to_generate)
    # (3) 路径映射字典 {逻辑函数返回值: 下一个节点名}
    workflow.add_conditional_edges(
        "grade_node",
        decide_to_generate,
        {
            "web_search_node": "web_search_node", # 如果返回 'web_search'，去搜网
            "generate_node": "generate_node"      # 如果返回 'generate'，去生成
        }
    )

    # 4. 联网搜索 -> 生成 (搜完之后，还是要把资料给 LLM 整理回答)
    workflow.add_edge("web_search_node", "generate_node")

    # 5. 生成 -> 格式化 -> 结束
    workflow.add_edge("generate_node", "format_node")
    workflow.add_edge("format_node", END)

    app = workflow.compile()

    # 3. 编译
    return workflow.compile()
