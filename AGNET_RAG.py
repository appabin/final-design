import os
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

# --- RAG 相关的库 ---
from langchain_community.embeddings import DashScopeEmbeddings # 用于连接 Qwen Embedding
from langchain_community.vectorstores import FAISS           # 向量数据库
from langchain_community.document_loaders import TextLoader  # 读取 txt
from langchain_text_splitters import CharacterTextSplitter   # 切分文本

load_dotenv()

# ==========================================
# 第一部分：构建知识库 (Build Vector DB)
# ==========================================

def build_vector_db():
    print("正在构建知识库...")
    
    # 1. 读取本地文件
    loader = TextLoader("TEST.txt", encoding="utf-8")
    documents = loader.load()
    
    # 2. 切分文本 (Chunking)
    # 把长文章切成小块，每块 200 字左右，重叠 50 字(防止上下文切断)
    text_splitter = CharacterTextSplitter(chunk_size=200, chunk_overlap=50)
    texts = text_splitter.split_documents(documents)
    
    # 3. 初始化 Embedding 模型 (Qwen)
    # 这一步会把文字变成向量
    embeddings = DashScopeEmbeddings(
        model="text-embedding-v4",  # Qwen 的新版 Embedding 模型
        dashscope_api_key=os.getenv("DASHSCOPE_API_KEY")
    )
    
    # 4. 存入向量数据库 (FAISS)
    # 这一步会真正调用 API，可能会花几秒钟
    db = FAISS.from_documents(texts, embeddings)
    print("知识库构建完成！")
    return db

# 初始化数据库 (在实际生产中，这一步通常是单独运行并保存到硬盘的，这里为了演示直接运行)
vector_db = build_vector_db()

# ==========================================
# 第二部分：定义搜索工具 (The Tool)
# ==========================================

@tool
def search_knowledge_base(query: str) -> str:
    """
    当用户询问关于公司政策、请假、报销等内部规定时，必须使用此工具。
    输入用户的具体问题，工具会返回相关的文档片段。
    """
    print(f"\n[RAG 搜索] 正在检索: {query} ...")
    
    # 在数据库中搜索最相似的 2 个片段 (k=2)
    results = vector_db.similarity_search(query, k=2)
    
    # 将找到的片段拼接成字符串返回
    context = "\n\n".join([doc.page_content for doc in results])
    return f"检索到的相关文档内容：\n{context}"

# ==========================================
# 第三部分：组装 Agent
# ==========================================

# 1. 工具列表
tools = [search_knowledge_base]

# 2. 初始化 LLM (DeepSeek)
model = ChatOpenAI(
    model=os.getenv("LLM_MODEL_ID", "deepseek-chat"),
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL"),
    temperature=0
)

# 3. 创建 Agent
checkpointer = InMemorySaver()

agent = create_agent(
    model=model,
    tools=tools,
    # System Prompt 极其重要：告诉它先查库，再回答
    system_prompt="你是一个行政助手。回答问题时，请优先使用 search_knowledge_base 工具查询公司文档，基于检索到的内容回答，不要瞎编。",
    checkpointer=checkpointer
)

# ==========================================
# 第四部分：运行测试
# ==========================================

print("\n----- 测试 RAG Agent -----")
config = {"configurable": {"thread_id": "rag_test_1"}}

# 问题涉及文档里的“特殊规定”
query = "我今年已经修了 4 天年假了，我的年假什么时候会增加"

print(f"User: {query}")
response = agent.invoke(
    {"messages": [{"role": "user", "content": query}]},
    config=config
)

print(f"Agent: {response['messages'][-1].content}")