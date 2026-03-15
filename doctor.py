import os
import dashscope
from dotenv import load_dotenv
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import CharacterTextSplitter

# 1. 加载环境变量
load_dotenv()
api_key = os.getenv("DASHSCOPE_API_KEY")

print("========== 诊断开始 ==========")

# --- 检查 1: API Key 是否读取成功 ---
if not api_key:
    print("❌ 错误: .env 文件未读取到 DASHSCOPE_API_KEY")
    print("   -> 请检查 .env 格式，确保没有多余空格，且变量名拼写正确。")
    exit()
else:
    print(f"✅ 成功读取 API Key: {api_key[:6]}******")

# --- 检查 2: SDK 版本 ---

# --- 检查 3: 本地文件读取 ---
if not os.path.exists("TEST.txt"):
    print("❌ 错误: 找不到 company_policy.txt 文件")
    exit()

try:
    loader = TextLoader("TEST.txt", encoding="utf-8")
    documents = loader.load()
    print(f"✅ 成功读取文件，字符数: {len(documents[0].page_content)}")
    
    text_splitter = CharacterTextSplitter(chunk_size=200, chunk_overlap=50)
    texts = text_splitter.split_documents(documents)
    print(f"✅ 成功切分为 {len(texts)} 个片段")
    if len(texts) == 0:
        print("❌ 错误: 文件切分后为空，可能是文件内容太少或切分规则问题。")
        exit()
except Exception as e:
    print(f"❌ 文件读取/切分步骤报错: {e}")
    exit()

# --- 检查 4: 裸测 API (不经过 LangChain) ---
print("\n正在尝试直接调用阿里云 API (模型: text-embedding-v4)...")
try:
    resp = dashscope.TextEmbedding.call(
        model="text-embedding-v4",
        input=texts[0].page_content, # 只测第一段
        api_key=api_key
    )
    
    if resp.status_code == 200:
        print("✅ API 调用成功！")
        print(f"   -> 返回向量维度: {len(resp.output['embeddings'][0]['embedding'])}")
    else:
        print("❌ API 调用失败！")
        print(f"   -> 状态码: {resp.status_code}")
        print(f"   -> 错误码: {resp.code}")
        print(f"   -> 错误信息: {resp.message}")
        print("   -> 建议: 如果提示 InvalidApiKey，请检查 Key 是否正确。")
        print("   -> 建议: 如果提示 ModelNotFound，请尝试改回 text-embedding-v2。")
        exit()
except Exception as e:
    print(f"❌ API连接过程报错: {e}")
    exit()

print("\n========== 诊断通过 ==========")
print("既然 API 是通的，你的 AGNET_RAG.py 应该能运行。")
print("如果还报错，请升级库: pip install -U langchain-community dashscope")