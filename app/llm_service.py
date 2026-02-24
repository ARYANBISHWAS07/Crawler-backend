"""
LLM Service using LangChain with Groq provider.
Handles chat responses, streaming, and text processing.
"""
from typing import List, Dict, Any, Optional, Generator
import os
from dotenv import load_dotenv

load_dotenv()

# LangChain imports
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.callbacks import StreamingStdOutCallbackHandler

# Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DEFAULT_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")

# Initialize LangChain Groq LLM
llm = None
if GROQ_API_KEY:
    llm = ChatGroq(
        api_key=GROQ_API_KEY,
        model_name=DEFAULT_MODEL,
        temperature=0.7,
        max_tokens=1000,
    )


def get_llm(
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = 1000,
    streaming: bool = False
) -> ChatGroq:
    """Get configured LangChain LLM instance."""
    if not GROQ_API_KEY:
        raise ValueError(
            "Groq API key not configured. Set GROQ_API_KEY in .env file. "
            "Get free key at https://console.groq.com"
        )
    
    callbacks = [StreamingStdOutCallbackHandler()] if streaming else None
    
    return ChatGroq(
        api_key=GROQ_API_KEY,
        model_name=model or DEFAULT_MODEL,
        temperature=temperature,
        max_tokens=max_tokens,
        streaming=streaming,
        callbacks=callbacks,
    )


# Default system prompt for RAG
DEFAULT_SYSTEM_PROMPT = """You are an intelligent AI assistant. Your role is to provide helpful, accurate, and well-organized answers based on the provided context.

Response Style:
- Give direct, clear answers without unnecessary filler
- Structure your response logically with clear sections when needed
- Be conversational yet professional
- Keep responses focused and relevant to the question
- If the context lacks sufficient information, clearly state what you can and cannot answer

Formatting Rules:
- For regular text: Use plain text without markdown symbols like **, *, or #
- For code examples: ALWAYS wrap code in triple backticks with the language name, like:
  ```javascript
  const example = "code here";
  ```
- Use proper language identifiers: javascript, python, typescript, html, css, jsx, etc.
- Keep code blocks clean and properly indented
- Separate code blocks from text with blank lines

Important:
- Base your answer strictly on the provided context
- Present explanations naturally as if speaking to someone
- Cite sources by mentioning page names naturally in your response"""


def generate_chat_response(
    question: str,
    context: str,
    model: str = None,
    system_prompt: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 1000
) -> str:
    """
    Generate a chat response using LangChain with Groq.
    
    Args:
        question: The user's question
        context: Relevant context from the vector store
        model: LLM model to use
        system_prompt: Custom system prompt (optional)
        temperature: Response creativity (0-1)
        max_tokens: Maximum response length
        
    Returns:
        Generated response string
    """
    chat_llm = get_llm(model, temperature, max_tokens)
    
    # Create prompt template
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt or DEFAULT_SYSTEM_PROMPT),
        ("human", """Context:
{context}

Question: {question}

Provide a refined, well-organized answer based on the context above. Be direct and helpful.""")
    ])
    
    # Create chain
    chain = prompt | chat_llm | StrOutputParser()
    
    # Run chain
    response = chain.invoke({
        "context": context,
        "question": question
    })
    
    return response


def generate_chat_response_stream(
    question: str,
    context: str,
    model: str = None,
    system_prompt: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 1000
) -> Generator[str, None, None]:
    """
    Generate a streaming chat response using LangChain.
    
    Yields:
        Response chunks as they are generated
    """
    chat_llm = get_llm(model, temperature, max_tokens, streaming=True)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt or DEFAULT_SYSTEM_PROMPT),
        ("human", """Context:
{context}

Question: {question}

Provide a refined, well-organized answer based on the context above. Be direct and helpful.""")
    ])
    
    chain = prompt | chat_llm | StrOutputParser()
    
    # Stream response
    for chunk in chain.stream({
        "context": context,
        "question": question
    }):
        yield chunk


def chat_with_history(
    messages: List[Dict[str, str]],
    context: str,
    model: str = None,
    system_prompt: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 1000
) -> str:
    """
    Continue a conversation with chat history using LangChain.
    
    Args:
        messages: List of previous messages [{"role": "user/assistant", "content": "..."}]
        context: Relevant context from the vector store
        model: LLM model to use
        system_prompt: Custom system prompt (optional)
        temperature: Response creativity (0-1)
        max_tokens: Maximum response length
        
    Returns:
        Generated response string
    """
    chat_llm = get_llm(model, temperature, max_tokens)
    
    # Build system prompt with context
    full_system_prompt = f"""{system_prompt or DEFAULT_SYSTEM_PROMPT}

Context:
{context}"""
    
    # Convert messages to LangChain format
    langchain_messages = [SystemMessage(content=full_system_prompt)]
    
    for msg in messages:
        if msg["role"] == "user":
            langchain_messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            langchain_messages.append(AIMessage(content=msg["content"]))
    
    # Get response
    response = chat_llm.invoke(langchain_messages)
    
    return response.content


def summarize_content(
    content: str,
    model: str = None,
    max_tokens: int = 500
) -> str:
    """
    Summarize content using LangChain.
    
    Args:
        content: The content to summarize
        model: LLM model to use
        max_tokens: Maximum summary length
        
    Returns:
        Summary string
    """
    chat_llm = get_llm(model, temperature=0.5, max_tokens=max_tokens)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful assistant that creates concise, informative summaries."),
        ("human", "Please summarize the following content in a clear and concise way:\n\n{content}")
    ])
    
    chain = prompt | chat_llm | StrOutputParser()
    
    return chain.invoke({"content": content})

def generate_questionnaire_from_summary(
    summary: str,
    model: str = None,
    max_tokens: int = 800
) -> str:
    """
    Generate a structured questionnaire based on summarized content.
    
    Args:
        summary: The summarized content
        model: Optional model override
        max_tokens: Maximum length of output
        
    Returns:
        Questionnaire string
    """

    chat_llm = get_llm(model=model, temperature=0.6, max_tokens=max_tokens)

    prompt = ChatPromptTemplate.from_messages([
        ("system", 
         "You are an expert educational content designer. "
         "Your job is to generate a high-quality questionnaire "
         "based strictly on the provided summary."
        ),
        ("human",
         """Based on the following summarized content, create a well-structured questionnaire.

Summary:
{summary}

Instructions:
- Create 5-10 questions
- Include a mix of conceptual and analytical questions
- Keep questions clear and concise
- Do not include answers
- Number the questions clearly
"""
        )
    ])

    chain = prompt | chat_llm | StrOutputParser()

    return chain.invoke({"summary": summary})
   