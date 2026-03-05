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


def generate_questionnaire_from_chunk(
    chunk: str,
    model: str = None,
    max_tokens: int = 600
) -> str:
    """
    Generate a questionnaire for a single chunk of crawled data.
    """

    chat_llm = get_llm(model=model, temperature=0.6, max_tokens=max_tokens)

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are an expert instructional designer. "
         "Create a focused questionnaire strictly based on the provided chunk of content."
        ),
        ("human",
        """Based on the following content chunk, generate exactly 5 high-quality questions.

Return the output strictly in this JSON format:

{{
  "questions": [
    {{"id": 1, "question": "First question here"}},
    {{"id": 2, "question": "Second question here"}},
    {{"id": 3, "question": "Third question here"}},
    {{"id": 4, "question": "Fourth question here"}},
    {{"id": 5, "question": "Fifth question here"}}
  ]
}}

Content Chunk:
{chunk}

Rules:
- Questions must be strictly based on this chunk only
- Do not assume missing information
- Do not provide answers
- Output must be valid JSON only
"""
        )
    ])

    chain = prompt | chat_llm | StrOutputParser()

    return chain.invoke({"chunk": chunk})


# Learning Path Generation Prompt
LEARNING_PATH_SYSTEM_PROMPT = """You are an expert curriculum architect and UI information designer.

Your task is to transform website documentation or sitemap URLs into a
professional learning roadmap graph suitable for a modern web application UI.

The output will be used to render an interactive learning graph similar to
professional learning platforms.

GOALS:
- Extract the most important learning topics
- Organize them into logical modules
- Build a prerequisite graph
- Generate UI metadata for visualization

RULES:
1. Topics must follow a logical learning progression
2. The graph must be a Directed Acyclic Graph (no circular dependencies)
3. Merge duplicate or similar topics
4. Prefer concise topic names (1–3 words)
5. Limit the roadmap to the most important concepts (max 15-20 nodes)
6. Organize topics into modules when possible
7. Difficulty must increase gradually
8. Use URL hierarchy to infer structure
9. Ignore irrelevant pages like login, privacy, terms, blog, or marketing pages

UI DESIGN REQUIREMENTS:
Return UI metadata for visualization:

difficulty colors:
- beginner → green
- intermediate → yellow  
- advanced → red

node types:
- core_topic (main concepts)
- sub_topic (supporting concepts)

layout style:
- top-to-bottom learning progression
- position.y should increase with difficulty (beginner=0, intermediate=200, advanced=400)
- position.x should spread nodes horizontally within same level

Return ONLY valid JSON in the following format (no explanations or markdown):

{{
  "modules": [
    {{
      "id": "module-id",
      "title": "Module Name",
      "description": "Short description"
    }}
  ],
  "nodes": [
    {{
      "id": "topic-id",
      "label": "Topic Name",
      "module": "module-id",
      "difficulty": "beginner | intermediate | advanced",
      "type": "core_topic | sub_topic",
      "position": {{"x": 0, "y": 0}}
    }}
  ],
  "edges": [
    {{
      "source": "topic-id",
      "target": "topic-id",
      "type": "prerequisite"
    }}
  ],
  "learning_path": [
    "Topic 1",
    "Topic 2",
    "Topic 3"
  ]
}}

IMPORTANT: Respond with ONLY the JSON object. No preamble, no markdown code fences, no explanation."""


def generate_learning_path(
    urls: List[str],
    model: str = None,
    max_tokens: int = 4000,
    temperature: float = 0.5
) -> Dict[str, Any]:
    """
    Generate a structured learning path from a list of URLs.
    
    Args:
        urls: List of URLs from a sitemap
        model: LLM model to use
        max_tokens: Maximum response length
        temperature: Response creativity (0-1)
        
    Returns:
        Dictionary containing modules, nodes, edges, and learning_path
    """
    import json
    
    chat_llm = get_llm(model, temperature, max_tokens)
    
    # Format URLs as a list
    urls_text = "\n".join(f"- {url}" for url in urls)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", LEARNING_PATH_SYSTEM_PROMPT),
        ("human", """CONTENT SOURCE (Sitemap URLs):
{urls}

Analyze these URLs and generate the learning roadmap JSON with modules, nodes, edges, and learning path.""")
    ])
    
    chain = prompt | chat_llm | StrOutputParser()
    
    try:
        print(f"[DEBUG] Sending {len(urls)} URLs to LLM for learning path generation...")
        response = chain.invoke({"urls": urls_text})
    except Exception as e:
        print(f"[ERROR] LLM API call failed: {type(e).__name__}: {e}")
        raise ValueError(f"LLM API call failed: {e}")
    
    # Debug: log the raw response
    print(f"[DEBUG] Raw LLM response length: {len(response) if response else 0}")
    print(f"[DEBUG] Raw LLM response (first 500 chars): {response[:500] if response else 'EMPTY'}")
    
    if not response or not response.strip():
        raise ValueError("LLM returned an empty response")
    
    # Clean up response - extract JSON if wrapped in markdown code blocks
    response = response.strip()
    if response.startswith("```json"):
        response = response[7:]
    if response.startswith("```"):
        response = response[3:]
    if response.endswith("```"):
        response = response[:-3]
    response = response.strip()
    
    # Try to find JSON object in the response if it contains extra text
    if not response.startswith("{"):
        # Try to find the first { and last }
        start_idx = response.find("{")
        end_idx = response.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            response = response[start_idx:end_idx + 1]
            print(f"[DEBUG] Extracted JSON from response")
    
    print(f"[DEBUG] Cleaned response (first 500 chars): {response[:500] if response else 'EMPTY'}")
    
    # Parse and validate JSON
    try:
        result = json.loads(response)
        
        # Validate structure
        if not isinstance(result.get("modules"), list):
            result["modules"] = []
        if not isinstance(result.get("nodes"), list):
            result["nodes"] = []
        if not isinstance(result.get("edges"), list):
            result["edges"] = []
        if not isinstance(result.get("learning_path"), list):
            result["learning_path"] = []
            
        # Validate and normalize node properties
        valid_difficulties = {"beginner", "intermediate", "advanced"}
        valid_types = {"core_topic", "sub_topic"}
        
        for i, node in enumerate(result["nodes"]):
            # Handle difficulty (new field) or level (old field)
            difficulty = node.get("difficulty") or node.get("level")
            if difficulty not in valid_difficulties:
                difficulty = "intermediate"
            node["difficulty"] = difficulty
            
            # Set level for backward compatibility
            node["level"] = difficulty
            
            # Validate type
            if node.get("type") not in valid_types:
                node["type"] = "core_topic"
                
            # Ensure position exists
            if not isinstance(node.get("position"), dict):
                # Auto-calculate position based on difficulty
                y_map = {"beginner": 0, "intermediate": 200, "advanced": 400}
                node["position"] = {
                    "x": (i % 4) * 200,
                    "y": y_map.get(difficulty, 200)
                }
            else:
                node["position"]["x"] = node["position"].get("x", 0)
                node["position"]["y"] = node["position"].get("y", 0)
                
        return result
        
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse learning path response as JSON: {e}")


def generate_learning_path_stream(
    urls: List[str],
    model: str = None,
    max_tokens: int = 4000,
    temperature: float = 0.5
) -> Generator[str, None, None]:
    """
    Generate a streaming learning path response.
    
    Yields:
        Response chunks as they are generated
    """
    chat_llm = get_llm(model, temperature, max_tokens, streaming=True)
    
    urls_text = "\n".join(f"- {url}" for url in urls)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", LEARNING_PATH_SYSTEM_PROMPT),
        ("human", """CONTENT SOURCE (Sitemap URLs):
{urls}

Analyze these URLs and generate the learning roadmap JSON with modules, nodes, edges, and learning path.""")
    ])
    
    chain = prompt | chat_llm | StrOutputParser()
    
    for chunk in chain.stream({"urls": urls_text}):
        yield chunk


