# agent/state.py
from typing import TypedDict, List
from langchain_core.documents import Document

class GraphState(TypedDict):
    """定义 Agent 运行时的状态"""
    question: str
    context: List[Document]
    answer: str
    web_search: str