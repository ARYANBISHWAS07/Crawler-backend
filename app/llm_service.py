"""
LLM Service using LangChain with Ollama (Local Llama).
Handles chat responses, streaming, summarization, and questionnaire generation.
"""

from typing import List, Dict, Any, Optional, Generator
import os
from dotenv import load_dotenv

load_dotenv()

# LangChain Ollama import
from langchain_community.chat_models import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.callbacks import StreamingStdOutCallbackHandler


# ==============================
# Configuration
# ==============================

DEFAULT_MODEL = os.getenv("LLM_MODEL", "llama3:8b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


def get_llm(
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = 1000,
    streaming: bool = False
) -> ChatOllama:
    """
    Get configured Ollama LLM instance.
    """

    callbacks = [StreamingStdOutCallbackHandler()] if streaming else None

    return ChatOllama(
        model=model or DEFAULT_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=temperature,
        streaming=streaming,
        callbacks=callbacks,
    )


# ==============================
# Default System Prompt
# ==============================

DEFAULT_SYSTEM_PROMPT = """You are an intelligent AI assistant. Your role is to provide helpful, accurate, and well-organized answers based on the provided context.

Response Style:
- Give direct, clear answers without unnecessary filler
- Structure your response logically with clear sections when needed
- Be conversational yet professional
- Keep responses focused and relevant to the question
- If the context lacks sufficient information, clearly state what you can and cannot answer

Formatting Rules:
- For regular text: Use plain text without markdown symbols
- For code examples: ALWAYS wrap code in triple backticks with language name
- Keep code blocks clean and properly indented

Important:
- Base your answer strictly on the provided context
"""


# ==============================
# Chat Response
# ==============================

def generate_chat_response(
    question: str,
    context: str,
    model: str = None,
    system_prompt: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 1000
) -> str:

    chat_llm = get_llm(model, temperature, max_tokens)

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt or DEFAULT_SYSTEM_PROMPT),
        ("human", """Context:
{context}

Question: {question}

Provide a refined, well-organized answer based on the context above.""")
    ])

    chain = prompt | chat_llm | StrOutputParser()

    return chain.invoke({
        "context": context,
        "question": question
    })


# ==============================
# Streaming Response
# ==============================

def generate_chat_response_stream(
    question: str,
    context: str,
    model: str = None,
    system_prompt: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 1000
) -> Generator[str, None, None]:

    chat_llm = get_llm(model, temperature, max_tokens, streaming=True)

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt or DEFAULT_SYSTEM_PROMPT),
        ("human", """Context:
{context}

Question: {question}

Provide a refined, well-organized answer based on the context above.""")
    ])

    chain = prompt | chat_llm | StrOutputParser()

    for chunk in chain.stream({
        "context": context,
        "question": question
    }):
        yield chunk


# ==============================
# Chat With History
# ==============================

def chat_with_history(
    messages: List[Dict[str, str]],
    context: str,
    model: str = None,
    system_prompt: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 1000
) -> str:

    chat_llm = get_llm(model, temperature, max_tokens)

    full_system_prompt = f"""{system_prompt or DEFAULT_SYSTEM_PROMPT}

Context:
{context}"""

    langchain_messages = [SystemMessage(content=full_system_prompt)]

    for msg in messages:
        if msg["role"] == "user":
            langchain_messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            langchain_messages.append(AIMessage(content=msg["content"]))

    response = chat_llm.invoke(langchain_messages)

    return response.content


# ==============================
# Summarization
# ==============================

def summarize_content(
    content: str,
    model: str = None,
    max_tokens: int = 500
) -> str:

    chat_llm = get_llm(model, temperature=0.5, max_tokens=max_tokens)

    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful assistant that creates concise summaries."),
        ("human", "Summarize the following content clearly:\n\n{content}")
    ])

    chain = prompt | chat_llm | StrOutputParser()

    return chain.invoke({"content": content})


# ==============================
# Questionnaire From Summary
# ==============================

def generate_questionnaire_from_summary(
    summary: str,
    model: str = None,
    max_tokens: int = 800
) -> str:

    chat_llm = get_llm(model=model, temperature=0.6, max_tokens=max_tokens)

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are an expert educational content designer."
        ),
        ("human",
         """Based on the summary below, create 5-10 well-structured questions.

Summary:
{summary}

Rules:
- Do not include answers
- Number questions clearly
""")
    ])

    chain = prompt | chat_llm | StrOutputParser()

    return chain.invoke({"summary": summary})


# ==============================
# Questionnaire From Chunk
# ==============================

def generate_questionnaire_from_chunk(
    chunk: str,
    model: str = None,
    max_tokens: int = 600
) -> str:

    chat_llm = get_llm(model=model, temperature=0.6, max_tokens=max_tokens)

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are an expert instructional designer."
        ),
        ("human",
        """Generate exactly 5 high-quality questions based ONLY on this content.

Return strictly valid JSON:

{{
  "questions": [
    {{"id": 1, "question": "..."}},
    {{"id": 2, "question": "..."}},
    {{"id": 3, "question": "..."}},
    {{"id": 4, "question": "..."}},
    {{"id": 5, "question": "..."}}
  ]
}}

Content:
{chunk}

Rules:
- No answers
- No extra text
- Output JSON only
"""
        )
    ])

    chain = prompt | chat_llm | StrOutputParser()

    return chain.invoke({"chunk": chunk})