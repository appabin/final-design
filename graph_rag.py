import os
from dotenv import load_dotenv
from typing import List, TypedDict

# LangGraph 核心组件
from langgraph.graph import StateGraph, END

# LangChain 组件
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import CharacterTextSplitter
from langchain_core.documents import Document

load_dotenv()

# --- 0. 准备向量数据库 (单例模式) ---
# 这是一个简单的帮助函数，模拟数据库连接
def get_vector_store():
    if not os.path.exists("TEST.txt"):
        raise FileNotFoundError("请确保 TEST.txt 存在")
        
    loader = TextLoader("TEST.txt", encoding="utf-8")
    docs = loader.load()
    text_splitter = CharacterTextSplitter(chunk_size=200, chunk_overlap=50)
    splits = text_splitter.split_documents(docs)
    
   
    embeddings = DashScopeEmbeddings(model="text-embedding-v4", dashscope_api_key=os.getenv("DASHSCOPE_API_KEY"))
    vectorstore = FAISS.from_documents(splits, embeddings)
    return vectorstore

vectorstore = get_vector_store()
retriever = vectorstore.as_retriever(search_kwargs={"k": 2})


# 定义 State 的 Schema
class GraphState(TypedDict):
    question: str      # 用户的问题
    context: List[Document] # 检索到的文档片段
    answer: str        # 最终生成的答案

# --- 节点 1: 检索 (Retrieve) ---
def retrieve(state: GraphState):
    print("--- [Node] 检索阶段 ---")
    question = state["question"]
    
    # 执行检索
    documents = retriever.invoke(question)
    print(f"检索到 {len(documents)} 条相关文档")
    
    # 更新 State 中的 context 字段
    return {"context": documents}

# --- 节点 2: 生成 (Generate) ---
def generate(state: GraphState):
    print("--- [Node] 生成阶段 ---")
    question = state["question"]
    context = state["context"]
    
    # 纯手动构建 RAG Prompt，不依赖 Agent 的黑盒工具调用
    # 这样你能完全控制 Prompt 的结构
    template = """你是一个专业的公司助手。请基于以下检索到的上下文回答问题。
    如果上下文中没有答案，请直接说不知道。
    
    上下文:
    {context}
    
    问题: {question}
    """
    prompt = ChatPromptTemplate.from_template(template)
    
    # 初始化 LLM
    llm = ChatOpenAI(
        model=os.getenv("LLM_MODEL_ID", "deepseek-chat"),
        api_key=os.getenv("LLM_API_KEY"),
        base_url=os.getenv("LLM_BASE_URL"),
        temperature=0
    )
    
    # 这是一个标准的 Chain: Prompt -> LLM -> StringOutput
    chain = prompt | llm
    
    # 拼接 context 内容
    context_str = "\n\n".join([doc.page_content for doc in context])
    
    response = chain.invoke({"question": question, "context": context_str})
    
    # 更新 State 中的 answer 字段
    return {"answer": response.content}








def format_output(state: GraphState):
    print("--- [Node]  格式化阶段 ---")
    answer = state["answer"]
    template = """你是一个专业的格式处理大师，把下面的内容改为 json 格式以方便反序列化，并在最后加上“huangjimi 的回答未必正确无误，请注意核查”
    内容:
    {content}
    """

    prompt = ChatPromptTemplate.from_template(template)
    llm = ChatOpenAI(
        model=os.getenv("LLM_MODEL_ID", "deepseek-chat"),
        api_key=os.getenv("LLM_API_KEY"),
        base_url=os.getenv("LLM_BASE_URL"),
        temperature=0
    )
    
    chain = prompt | llm
    
    response = chain.invoke({"content": answer})
    
    # 更新 State 中的 answer 字段
    return {"answer": response.content}

# 1. 初始化图
workflow = StateGraph(GraphState)

# 2. 添加节点
workflow.add_node("retrieve_node", retrieve)
workflow.add_node("generate_node", generate)
workflow.add_node("format",format_output)

# 3. 添加边 (逻辑流向)
# 入口 -> 检索
workflow.set_entry_point("retrieve_node")

# 检索 -> 生成
workflow.add_edge("retrieve_node", "generate_node")

workflow.add_edge("generate_node","format")

# 生成 -> 结束 (END 是一个特殊节点)
workflow.add_edge("format", END)

# 4. 编译图 (Compile)
# 这一步会把图变成一个可运行的 Runnable 对象
app = workflow.compile()

if __name__ == "__main__":
    print("----- 测试 LangGraph RAG -----")
    
    # 初始输入
    inputs = {"question": "马老师连续迟到三天会到扣钱吗？"}
    
    # 运行图
    # app.invoke 会自动从 entry_point 开始流转
    result = app.invoke(inputs)
    
    print("\n----- 最终结果 -----")
    print(result["answer"])