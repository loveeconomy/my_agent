from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_deepseek import ChatDeepSeek
from dotenv import load_dotenv
import pandas as pd
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.checkpoint.memory import InMemorySaver
from sysengi_downloader import SysengiDownloader
import pdfplumber
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
import os
import asyncio
from pathlib import Path
from wechat.scripts.common import prepare_pyweixin
import json

os.environ["NO_PROXY"] = "localhost,127.0.0.1"
os.environ["no_proxy"] = "localhost,127.0.0.1"

load_dotenv()

embeddings = OllamaEmbeddings(
    model="embeddinggemma",
)

vector_store = Chroma(
    collection_name="first",
    embedding_function=embeddings,
    persist_directory="./my_knowledge",
)

@tool
def search_pdf_knowledge_base(query: str) -> str:
    """搜索本地 PDF 知识库，返回与问题最相关的文档片段。"""
    docs = vector_store.similarity_search(query, k=4)

    if not docs:
        return "知识库中没有找到相关内容。"

    return "\n\n".join(
        [
            f"来源: {doc.metadata}\n内容: {doc.page_content}"
            for doc in docs
        ]
    )

@tool
def send_message(friend: str,messages: str) -> None:
    """给用户的好友发送微信消息"""
    root = Path(r"C:\Users\j1383\Desktop\data_AI\my_agent\wechat")
    pyweixin = prepare_pyweixin(str(root))
    pyweixin.Messages.send_messages_to_friend(
        friend=friend,
        messages=[messages],
        close_weixin=False,
    )
    return (
        json.dumps(
            {
                "ok": True,
                "friend": friend,
                "message": [messages],
            },
            ensure_ascii=False,
        )
    )


@tool
def paper_download(title: str,output_dir: str) -> str:
    """用于下载系统工程理论与实践这个期刊中的论文的工具，并将用户想要下载的论文保存在用户指定的文件夹中"""
    downloader = SysengiDownloader(output_dir)
    downloader.download_by_title(title)
    return f"{title} download success"

@tool
def read_pdf_content(file_path: str) -> str:
    """
    读取PDF文件并返回全部文本内容。
    :param file_path: PDF文件路径
    :return: 文本内容字符串
    """
    try:
        with pdfplumber.open(file_path) as pdf:
            full_text = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text.append(text)
            return '\n'.join(full_text)
    except Exception as e:
        raise RuntimeError(f"读取PDF失败: {e}")

@tool
def read_excel(filename: str) -> str:
    """读取文档的全部内容"""
    data = pd.read_excel(filename)
    return f"{filename}文件的全部内容是：{data}"

client = MultiServerMCPClient(
    {
        "mine": {
            "transport": "http",
            "url": "http://localhost:8000/mcp",
        },

        "google-scholar": {
            "transport": "stdio",  # Local subprocess communication
            "command": "C:\\Users\j1383\Desktop\search\Google-Scholar-MCP-Server\\venv\Scripts\python.exe",
            "args": ["C:\\Users\j1383\Desktop\search\Google-Scholar-MCP-Server\google_scholar_server.py"],

        }
      }
)


SKILLS_DIR = Path("skills")

def list_skills() -> str:
    items = []
    for skill_md in SKILLS_DIR.glob("*/SKILL.md"):
        text = skill_md.read_text(encoding="utf-8")
        name = skill_md.parent.name

        description = ""
        for line in text.splitlines():
            if line.startswith("description:"):
                description = line.replace("description:", "").strip()
                break

        items.append(f"- {name}: {description}")

    return "\n".join(items)

@tool
def load_skill(skill_name: str) -> str:
    """Load a skill's full instructions by skill name."""
    skill_path = SKILLS_DIR / skill_name / "SKILL.md"

    if not skill_path.exists():
        return f"Skill not found: {skill_name}"

    return skill_path.read_text(encoding="utf-8")



SYSTEM_PROMPT = f"""你是一个中文AI助手。

## Capabilities

- 'read_excel': 读取用户提供给你的文件名的文档，根据文档的内容回答用户的问题.
- 'search_pdf_knowledge_base' 搜索本地 PDF 知识库，返回与问题最相关的文档片段。

"""

model = ChatDeepSeek(
    model="deepseek-v4-flash",
    temperature=0,
    extra_body={
        "thinking":{
            "type": "disabled"
        }
    }
)

checkpointer = InMemorySaver()


async def main():

    tools = await client.get_tools()
    print(f"已加载 MCP 工具：{len(tools)}个")

    agent = create_agent(
        model=model,
        tools=[read_excel, search_pdf_knowledge_base, *tools, send_message],
        system_prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,

    )
    for _ in range(100):
        content = input('请输入问题:')
        if content == 'q':
            break

        async for chunk in agent.astream(
                    {"messages": [{"role": "user", "content": content}]},
                    stream_mode="messages",
                    version="v2",
                    config={"configurable": {"thread_id": "session_1"}},
            ):
                if chunk["type"] == "messages":
                    token, metadata = chunk["data"]
                    if token.content_blocks:
                        for block in token.content_blocks:
                            if block.get("type") == "text":
                                print(block.get("text", ""), end="", flush=True)
        print('\n')

if __name__ == "__main__":
    asyncio.run(main())

'''        result2 = agent.invoke(
            {"messages": [{"role": "user", "content": content}]},
            config={"configurable": {"thread_id": "session_1"}},
        )


        print(result2["messages"][-1].content_blocks[0]['text'])'''