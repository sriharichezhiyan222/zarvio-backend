import json
import os
from typing import Any, AsyncGenerator, Dict, List, Optional
from openai import AsyncOpenAI
from fastapi.responses import StreamingResponse

def get_nim_client(key_name: str = "NVIDIA_API_KEY") -> AsyncOpenAI:
    # Try the specific key first, fallback to the generic NVIDIA base key
    # It assumes the user has set either NVIDIA_API_KEY_DEEPSEEK or NVIDIA_API_KEY
    api_key = os.getenv(key_name) or os.getenv("NVIDIA_API_KEY") or os.getenv("OPENAI_API_KEY") or "sk-dummy"
    return AsyncOpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=api_key
    )

async def check_safety(content: str) -> bool:
    """Run Llama 3.2 Safety check on content."""
    # Assuming llama-3.2-safety as requested, fallback meta/llama-guard-3-8b
    client = get_nim_client("NVIDIA_API_KEY_LLAMA_SAFETY")
    try:
        response = await client.chat.completions.create(
            model="meta/llama-guard-3-8b", 
            messages=[{"role": "user", "content": content}],
            max_tokens=20
        )
        judgement = response.choices[0].message.content.lower()
        if "unsafe" in judgement:
            return False
    except Exception as e:
        print(f"Safety check failed: {e}")
    return True

async def generate_json(model: str, prompt: str, system: str = "") -> Dict[str, Any]:
    key_name = "NVIDIA_API_KEY_DEEPSEEK" if "deepseek" in model.lower() else "NVIDIA_API_KEY_QWEN"
    client = get_nim_client(key_name)
    
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        res = await client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"}
        )
        content = res.choices[0].message.content or "{}"
    except Exception as e:
        print(f"JSON Generation failed: {e}")
        return {"error": str(e)}
    
    # Run safety check on the output
    is_safe = await check_safety(content)
    if not is_safe:
        return {"error": "Content was flagged as unsafe by the safety guardrail."}
        
    try:
        return json.loads(content)
    except:
        return {"raw_content": content}

async def generate_embedding(text: str) -> List[float]:
    """Generate embedding using nv-embed-v1."""
    client = get_nim_client("NVIDIA_API_KEY_NVEMBED")
    try:
        res = await client.embeddings.create(
            input=[text],
            model="nvidia/nv-embed-v1",
            encoding_format="float",
            extra_body={"input_type": "query"}
        )
        return res.data[0].embedding
    except Exception as e:
        print(f"Embedding generation failed: {e}")
        return []

async def stream_chat(model: str, messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
    """Stream chat response token by token."""
    key_name = "NVIDIA_API_KEY_DEEPSEEK" if "deepseek" in model.lower() else "NVIDIA_API_KEY_QWEN"
    client = get_nim_client(key_name)
    
    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True
        )
        async for chunk in stream:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
    except Exception as e:
        yield f"Error generating stream: {e}"
