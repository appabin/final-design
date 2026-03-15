import os
from dotenv import load_dotenv

# --- LangChain & RAG 相关的库 ---
from langchain_core.tools import tool
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import CharacterTextSplitter
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.documents import Document
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.documents import Document
from typing import List


# 加载环境变量 (确保被其他文件导入时也能读到 API Key)
load_dotenv()

# ==========================================
# 第一部分：RAG 知识库构建逻辑 (私有方法)
# ==========================================

# 定义全局变量，充当缓存，避免每次调用工具都重新构建数据库
_GLOBAL_VECTOR_DB = None

def _get_or_create_vector_db():
    """
    获取向量数据库实例。如果不存在，则初始化构建。
    """
    global _GLOBAL_VECTOR_DB
    
    # 如果已经构建过，直接返回，不再重新切分文件
    if _GLOBAL_VECTOR_DB is not None:
        return _GLOBAL_VECTOR_DB
        
    print("--- [System] 正在初始化本地知识库 (RAG) ...")
    
    file_path = "TEST.txt"
    if not os.path.exists(file_path):
        # 容错处理：如果文件不存在，返回 None，防止程序崩溃
        print(f"⚠️ 警告: 未找到 {file_path} 文件，RAG 工具将无法使用。")
        return None

    try:
        # 1. 读取本地文件
        loader = TextLoader(file_path, encoding="utf-8")
        documents = loader.load()
        
        # 2. 切分文本
        text_splitter = CharacterTextSplitter(chunk_size=200, chunk_overlap=50)
        texts = text_splitter.split_documents(documents)
        
        # 3. 初始化 Embedding (Qwen v4)
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            raise ValueError("未找到 DASHSCOPE_API_KEY，请检查 .env 文件")
            
        embeddings = DashScopeEmbeddings(
            model="text-embedding-v4",
            dashscope_api_key=api_key
        )
        
        # 4. 存入 FAISS
        db = FAISS.from_documents(texts, embeddings)
        print("✅ 知识库构建完成！")
        
        _GLOBAL_VECTOR_DB = db
        return db
        
    except Exception as e:
        print(f"❌ 知识库构建失败: {e}")
        return None

# ==========================================
# 第二部分：定义工具 (Public Tools)
# ==========================================

#
def get_retriever():
    """
    这是一个工厂函数，用于获取 retriever 对象。
    供 nodes.py 中的 retrieve_node 使用。
    """
    # 1. 获取数据库实例 (复用之前的逻辑)
    db = _get_or_create_vector_db()
    
    if db is None:
        # 如果数据库挂了，返回一个假的 retriever 或者抛出错误
        raise ValueError("无法初始化检索器，因为知识库构建失败。")
        
    # 2. 将数据库转换为检索器
    # search_kwargs={"k": 2} 表示每次只找最相关的 2 条
    retriever = db.as_retriever(search_kwargs={"k": 2})
    
    return retriever

# ... 之前的 tools_list 导出 ...
@tool
def search_knowledge_base(query: str) -> str:
    """
    当用户询问关于公司政策、请假、报销、等内部规定时，必须使用此工具。
    输入用户的具体问题，工具会返回相关的文档片段。
    """
    # 1. 获取数据库实例
    db = _get_or_create_vector_db()
    
    if db is None:
        return "抱歉，本地知识库未初始化或文件不存在，无法查询。"

    print(f"\n[RAG 搜索] 正在检索: {query} ...")
    
    try:
        # 2. 搜索相似片段 (k=2)
        results = db.similarity_search(query, k=2)
        
        # 3. 格式化返回
        if not results:
            return "知识库中未找到相关内容。"
            
        context = "\n\n".join([doc.page_content for doc in results])
        return f"检索到的相关文档内容：\n{context}"
        
    except Exception as e:
        return f"检索过程发生错误: {e}"

# --- 我们也把你需要的 Tavily 工具封装在这里，方便统一管理 ---

# agent/tools.py

def perform_web_search(query: str) -> List[Document]:
    """
    执行联网搜索，并将结果清洗为 Document 对象列表。
    如果搜索失败，返回包含错误信息的 Document，保证程序不崩。
    """
    try:
        # 1. 初始化工具
        search_tool = TavilySearchResults(k=3)
        
        # 2. 执行搜索
        print(f"  -> [Tool] 正在调用 Tavily 搜索: {query}")
        search_results = search_tool.invoke({"query": query})
        
        # 3. 数据清洗 (把字典转为 Document)
        web_documents = []
        
        if isinstance(search_results, list):
            for result in search_results:
                content = result.get("content", "")
                url = result.get("url", "")
                
                # 封装成统一格式
                doc = Document(
                    page_content=content,
                    metadata={"source": url}
                )
                web_documents.append(doc)
        else:
            # Tavily 偶尔会返回字符串类型的错误信息
            print(f"  -> [Tool] Tavily 返回格式异常: {search_results}")
            return [Document(page_content=f"搜索异常: {str(search_results)}")]
            
        print(f"  -> [Tool] 搜索完成，获取 {len(web_documents)} 条结果")
        return web_documents

    except Exception as e:
        print(f"❌ [Tool] 联网搜索发生严重错误: {e}")
        # 兜底返回
        return [Document(page_content="抱歉，网络搜索暂时不可用。")]

# ==========================================
# 第三部分：导出工具列表
# ==========================================

# 这里的 tools 列表可以被 Graph 或 Agent 直接导入使用
# 注意：Tavily 是一个类实例，而 search_knowledge_base 是一个被 @tool 装饰的函数
# 它们都可以放入这个列表