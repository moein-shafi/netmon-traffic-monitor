"""
Multi-LLM Provider Support with Secure API Key Management
Supports both free and paid LLM services.
"""
from __future__ import annotations

import json
import os
import base64
from pathlib import Path
from typing import Dict, Optional, List, Any
from dataclasses import dataclass
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import requests

# Encryption key file
ENCRYPTION_KEY_FILE = Path("/var/netmon/config/.llm_encryption_key")
SECRETS_FILE = Path("/var/netmon/config/.llm_secrets.json")

# Free LLM providers (no API key required)
FREE_PROVIDERS = {
    "ollama": {
        "name": "Ollama (Local)",
        "type": "local",
        "requires_key": False,
        "default_url": "http://127.0.0.1:11434/api/generate",
        "models": [
            "smollm2:135m",
            "llama2",
            "mistral",
            "codellama",
            "phi",
        ],
    },
    "huggingface-free": {
        "name": "Hugging Face (Free Inference)",
        "type": "api",
        "requires_key": False,
        "default_url": "https://api-inference.huggingface.co/models",
        "models": [
            "microsoft/DialoGPT-medium",
            "gpt2",
            "distilgpt2",
        ],
        "note": "Rate limited, may require Hugging Face account",
    },
}

# Paid LLM providers (require API key)
PAID_PROVIDERS = {
    "openai": {
        "name": "OpenAI GPT",
        "type": "api",
        "requires_key": True,
        "key_name": "OPENAI_API_KEY",
        "default_url": "https://api.openai.com/v1/chat/completions",
        "models": [
            "gpt-4",
            "gpt-4-turbo",
            "gpt-3.5-turbo",
            "gpt-4o",
            "gpt-4o-mini",
        ],
    },
    "anthropic": {
        "name": "Anthropic Claude",
        "type": "api",
        "requires_key": True,
        "key_name": "ANTHROPIC_API_KEY",
        "default_url": "https://api.anthropic.com/v1/messages",
        "models": [
            "claude-3-5-sonnet-20241022",
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
        ],
    },
    "google": {
        "name": "Google Gemini",
        "type": "api",
        "requires_key": True,
        "key_name": "GOOGLE_API_KEY",
        "default_url": "https://generativelanguage.googleapis.com/v1beta/models",
        "models": [
            "gemini-pro",
            "gemini-pro-vision",
            "gemini-1.5-pro",
        ],
    },
    "cohere": {
        "name": "Cohere",
        "type": "api",
        "requires_key": True,
        "key_name": "COHERE_API_KEY",
        "default_url": "https://api.cohere.ai/v1/generate",
        "models": [
            "command",
            "command-light",
            "command-nightly",
        ],
    },
    "mistral-ai": {
        "name": "Mistral AI",
        "type": "api",
        "requires_key": True,
        "key_name": "MISTRAL_API_KEY",
        "default_url": "https://api.mistral.ai/v1/chat/completions",
        "models": [
            "mistral-large-latest",
            "mistral-medium-latest",
            "mistral-small-latest",
        ],
    },
    "groq": {
        "name": "Groq (Fast Inference)",
        "type": "api",
        "requires_key": True,
        "key_name": "GROQ_API_KEY",
        "default_url": "https://api.groq.com/openai/v1/chat/completions",
        "models": [
            "llama-3.1-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
        ],
    },
    "together-ai": {
        "name": "Together AI",
        "type": "api",
        "requires_key": True,
        "key_name": "TOGETHER_API_KEY",
        "default_url": "https://api.together.xyz/v1/chat/completions",
        "models": [
            "meta-llama/Llama-3-70b-chat-hf",
            "mistralai/Mixtral-8x7B-Instruct-v0.1",
        ],
    },
}

ALL_PROVIDERS = {**FREE_PROVIDERS, **PAID_PROVIDERS}


def get_or_create_encryption_key() -> bytes:
    """Get or create encryption key for API keys."""
    ENCRYPTION_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    if ENCRYPTION_KEY_FILE.exists():
        try:
            return ENCRYPTION_KEY_FILE.read_bytes()
        except Exception:
            pass
    
    # Generate a new key
    key = Fernet.generate_key()
    try:
        ENCRYPTION_KEY_FILE.write_bytes(key)
        # chmod only works on Unix-like systems
        import os
        if hasattr(os, 'chmod'):
            os.chmod(ENCRYPTION_KEY_FILE, 0o600)
    except Exception as e:
        print(f"[llm_providers] Warning: Could not set permissions on encryption key: {e}")
    return key


def encrypt_api_key(key: str, encryption_key: bytes) -> str:
    """Encrypt an API key."""
    f = Fernet(encryption_key)
    return f.encrypt(key.encode()).decode()


def decrypt_api_key(encrypted_key: str, encryption_key: bytes) -> str:
    """Decrypt an API key."""
    f = Fernet(encryption_key)
    return f.decrypt(encrypted_key.encode()).decode()


def save_api_key(provider: str, api_key: str) -> None:
    """Save an encrypted API key."""
    encryption_key = get_or_create_encryption_key()
    encrypted = encrypt_api_key(api_key, encryption_key)
    
    SECRETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    secrets = {}
    if SECRETS_FILE.exists():
        try:
            with SECRETS_FILE.open("r") as f:
                secrets = json.load(f)
        except Exception:
            pass
    
    secrets[provider] = encrypted
    secrets["_metadata"] = {
        "last_updated": json.dumps({"provider": provider}, default=str),
    }
    
    with SECRETS_FILE.open("w") as f:
        json.dump(secrets, f, indent=2)
    
    # chmod only works on Unix-like systems
    import os
    if hasattr(os, 'chmod'):
        try:
            os.chmod(SECRETS_FILE, 0o600)
        except Exception:
            pass


def get_api_key(provider: str) -> Optional[str]:
    """Get a decrypted API key."""
    if not SECRETS_FILE.exists():
        return None
    
    try:
        with SECRETS_FILE.open("r") as f:
            secrets = json.load(f)
        
        if provider not in secrets:
            return None
        
        encryption_key = get_or_create_encryption_key()
        return decrypt_api_key(secrets[provider], encryption_key)
    except Exception as e:
        print(f"[llm_providers] Error getting API key for {provider}: {e}")
        return None


def delete_api_key(provider: str) -> None:
    """Delete an API key."""
    if not SECRETS_FILE.exists():
        return
    
    try:
        with SECRETS_FILE.open("r") as f:
            secrets = json.load(f)
        
        if provider in secrets:
            del secrets[provider]
        
        with SECRETS_FILE.open("w") as f:
            json.dump(secrets, f, indent=2)
    except Exception:
        pass


def list_providers() -> Dict[str, Dict[str, Any]]:
    """List all available LLM providers with their status."""
    providers_info = {}
    
    for provider_id, provider_info in ALL_PROVIDERS.items():
        has_key = False
        if provider_info.get("requires_key", False):
            has_key = get_api_key(provider_id) is not None
        
        providers_info[provider_id] = {
            **provider_info,
            "has_api_key": has_key,
            "configured": not provider_info.get("requires_key", False) or has_key,
        }
    
    return providers_info


def generate_with_llm(
    provider: str,
    model: str,
    prompt: str,
    timeout: int = 60,
    **kwargs
) -> Optional[str]:
    """
    Generate text using the specified LLM provider.
    Returns the generated text or None on error.
    """
    if provider not in ALL_PROVIDERS:
        raise ValueError(f"Unknown provider: {provider}")
    
    provider_info = ALL_PROVIDERS[provider]
    
    if provider_info.get("requires_key", False):
        api_key = get_api_key(provider)
        if not api_key:
            raise ValueError(f"API key not configured for {provider}")
    
    try:
        if provider == "ollama":
            return _generate_ollama(model, prompt, timeout, **kwargs)
        elif provider == "openai":
            return _generate_openai(model, prompt, api_key, timeout, **kwargs)
        elif provider == "anthropic":
            return _generate_anthropic(model, prompt, api_key, timeout, **kwargs)
        elif provider == "google":
            return _generate_google(model, prompt, api_key, timeout, **kwargs)
        elif provider == "cohere":
            return _generate_cohere(model, prompt, api_key, timeout, **kwargs)
        elif provider == "mistral-ai":
            return _generate_mistral(model, prompt, api_key, timeout, **kwargs)
        elif provider == "groq":
            return _generate_groq(model, prompt, api_key, timeout, **kwargs)
        elif provider == "together-ai":
            return _generate_together(model, prompt, api_key, timeout, **kwargs)
        elif provider == "huggingface-free":
            return _generate_huggingface(model, prompt, timeout, **kwargs)
        else:
            raise ValueError(f"Provider {provider} not implemented")
    except Exception as e:
        print(f"[llm_providers] Error generating with {provider}: {e}")
        return None


def _generate_ollama(model: str, prompt: str, timeout: int, **kwargs) -> Optional[str]:
    """Generate using Ollama."""
    url = kwargs.get("url", "http://127.0.0.1:11434/api/generate")
    
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }
    
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return data.get("response", "").strip()


def _generate_openai(model: str, prompt: str, api_key: str, timeout: int, **kwargs) -> Optional[str]:
    """Generate using OpenAI."""
    url = kwargs.get("url", "https://api.openai.com/v1/chat/completions")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a senior network security engineer."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 1000,
    }
    
    resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def _generate_anthropic(model: str, prompt: str, api_key: str, timeout: int, **kwargs) -> Optional[str]:
    """Generate using Anthropic Claude."""
    url = kwargs.get("url", "https://api.anthropic.com/v1/messages")
    
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": model,
        "max_tokens": 1000,
        "messages": [
            {"role": "user", "content": prompt},
        ],
    }
    
    resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return data["content"][0]["text"].strip()


def _generate_google(model: str, prompt: str, api_key: str, timeout: int, **kwargs) -> Optional[str]:
    """Generate using Google Gemini."""
    url = f"{kwargs.get('url', 'https://generativelanguage.googleapis.com/v1beta/models')}/{model}:generateContent?key={api_key}"
    
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
    }
    
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def _generate_cohere(model: str, prompt: str, api_key: str, timeout: int, **kwargs) -> Optional[str]:
    """Generate using Cohere."""
    url = kwargs.get("url", "https://api.cohere.ai/v1/generate")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": model,
        "prompt": prompt,
        "max_tokens": 1000,
        "temperature": 0.7,
    }
    
    resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return data["generations"][0]["text"].strip()


def _generate_mistral(model: str, prompt: str, api_key: str, timeout: int, **kwargs) -> Optional[str]:
    """Generate using Mistral AI."""
    url = kwargs.get("url", "https://api.mistral.ai/v1/chat/completions")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 1000,
    }
    
    resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def _generate_groq(model: str, prompt: str, api_key: str, timeout: int, **kwargs) -> Optional[str]:
    """Generate using Groq."""
    url = kwargs.get("url", "https://api.groq.com/openai/v1/chat/completions")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 1000,
    }
    
    resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def _generate_together(model: str, prompt: str, api_key: str, timeout: int, **kwargs) -> Optional[str]:
    """Generate using Together AI."""
    url = kwargs.get("url", "https://api.together.xyz/v1/chat/completions")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 1000,
    }
    
    resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def _generate_huggingface(model: str, prompt: str, timeout: int, **kwargs) -> Optional[str]:
    """Generate using Hugging Face free inference."""
    url = f"https://api-inference.huggingface.co/models/{model}"
    
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": 200,
            "temperature": 0.7,
        },
    }
    
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    
    # Handle different response formats
    if isinstance(data, list) and len(data) > 0:
        return data[0].get("generated_text", "").strip()
    elif isinstance(data, dict):
        return data.get("generated_text", "").strip()
    return None

