# agent/nodes.py
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_community.tools.tavily_search import TavilySearchResults
import os
from pydantic import BaseModel, Field 

from agent.state import GraphState 
from langchain_core.output_parsers import PydanticOutputParser
from agent.tools import search_knowledge_base, get_retriever, perform_web_search
# 🔴 关键：从隔壁文件导入数据结构
from agent.state import GraphState 
from agent.tools import search_knowledge_base,get_retriever
from agent.tools import perform_web_search # 用于 web_search_node
# 定义 LLM (可以在这里初始化，也可以单独放配置)
llm = ChatOpenAI(
    model="deepseek-chat",
    temperature=0,
    # 👇 必须加上这两行，告诉它去哪里找 DeepSeek 的 Key 和地址
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL")
)


class GradeDocuments(BaseModel):
    """对检索到的文档与问题的相关性进行二元评分。"""
    binary_score: str = Field(description="文档是否与问题相关，'yes' 或 'no'")

# 2. 创建解析器 (Parser)
# 它的作用是：生成一段提示词告诉模型“怎么输出JSON”，并在模型输出后自动转成对象
parser = PydanticOutputParser(pydantic_object=GradeDocuments)

# 3. 定义 Prompt
# 关键点：我们在 system prompt 里挖了一个坑 {format_instructions}
# 解析器会自动把 "请输出 JSON，格式如下..." 填进去
system_prompt = """你是一个评分员，负责评估检索到的文档是否与用户的问题相关。
如果是相关的，binary_score 为 'yes'，否则为 'no'。

{format_instructions}
"""

grade_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system_prompt),
        ("human", "检索文档: \n\n {document} \n\n 用户问题: {question}"),
    ]
)

# 4. 自动注入格式说明
# 这一步会把 JSON 格式要求填入 Prompt
grade_prompt_with_format = grade_prompt.partial(format_instructions=parser.get_format_instructions())

# 5. 组装链
# Prompt -> LLM -> Parser (自动转回对象)
retrieval_grader = grade_prompt_with_format | llm | parser

def decide_to_generate(state: GraphState) -> str:
    """
    路由函数：检测 State 中的标记，决定下一步去哪。
    返回的是下一个节点的【字符串名称】。
    """
    print("--- [Edge] 路由判断 ---")
    web_search = state["web_search"]
    
    if web_search == "yes":
        print("  -> 路由指向: web_search_node")
        return "web_search_node" # 注意：这里要返回你在 graph.py 里注册的节点名
    else:
        print("  -> 路由指向: generate_node")
        return "generate_node"

def retrieve_node(state: GraphState):
    print("--- [Node] 检索阶段 ---")
    question = state["question"]
    
    try:
        # 1. 获取检索器对象
        retriever = get_retriever()
        
        # 2. 执行检索
        # retriever.invoke(question) 会返回 List[Document]
        documents = retriever.invoke(question)
        print(f"  -> 成功检索到 {len(documents)} 条文档")
        
        # 3. 更新 State
        return {"context": documents}
        
    except Exception as e:
        print(f"❌ 检索失败: {e}")
        return {"context": []}

def generate_node(state: GraphState):
    print("--- [Node] 生成阶段 ---")
    question = state["question"]
    context = state["context"]
    
    # 纯手动构建 RAG Prompt，不依赖 Agent 的黑盒工具调用
    # 这样你能完全控制 Prompt 的结构
    template = """你是一个智能问答助手。请根据提供的【上下文信息】回答用户的问题。

    【上下文信息】（可能来源于公司内部知识库或互联网搜索结果）:
    {context}
    
    【用户问题】: 
    {question}

    要求：
    1. 如果上下文中有答案，请根据上下文回答。
    2. 如果上下文是空的或者完全不相关，请回答“我不知道”。
    3. 回答要简洁、准确。
    """
    
    prompt = ChatPromptTemplate.from_template(template)
    
    
    # 这是一个标准的 Chain: Prompt -> LLM -> StringOutput
    chain = prompt | llm
    
    # 拼接 context 内容
    context_str = "\n\n".join([doc.page_content for doc in context])
    
    response = chain.invoke({"question": question, "context": context_str})
    
    # 更新 State 中的 answer 字段
    return {"answer": response.content}

def grade_documents_node(state: GraphState):
    print("--- [Node] 文档评分阶段 ---")
    question = state["question"]
    documents = state["context"]
    
    filtered_docs = []
    web_search = "no"
    
    for d in documents:
        # 调用上面定义的评分链
        score = retrieval_grader.invoke({"question": question, "document": d.page_content})
        grade = score.binary_score
        
        if grade == "yes":
            print("  -> 文档相关，保留")
            filtered_docs.append(d)
        else:
            print("  -> 文档不相关，丢弃")
            
    # 如果过滤后没有文档了，说明本地库里没货，需要联网
    if not filtered_docs:
        print("  -> (!) 本地文档均不相关，激活联网搜索标记")
        web_search = "yes"
        
    return {"context": filtered_docs, "web_search": web_search}

def format_output_node(state: GraphState):
    print("--- [Node]  格式化阶段 ---")
    answer = state["answer"]
    template = """你是一个专业的格式处理大师，把下面的内容改为 json 格式以方便反序列化，并在最后加上“huangjimi 的回答未必正确无误，请注意核查”
    内容:
    {content}
    """

    prompt = ChatPromptTemplate.from_template(template)

    chain = prompt | llm
    
    response = chain.invoke({"content": answer})
    
    # 更新 State 中的 answer 字段
    return {"answer": response.content}

def web_search_node(state: GraphState):
    """
    联网搜索节点：只负责从 State 取问题，调用工具，更新 State。
    """
    print("--- [Node] 联网搜索阶段 ---")
    
    # 1. 获取输入
    question = state["question"]
    
    # 2. 调用封装好的工具 (解耦的关键！)
    # node 不需要知道底层用的是 Tavily 还是 Google，也不需要知道怎么解析 JSON
    web_documents = perform_web_search(question)
    
    # 3. 更新状态
    # 直接把洗好的 Document 列表塞回去
    return {"context": web_documents}
