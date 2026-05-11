"""Shared pytest configuration — sets dummy env vars so no real API keys are needed."""

import os

# Set these before any app code imports (which triggers pydantic-settings validation)
os.environ.setdefault("OPENAI_API_KEY", "sk-test-openai")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-anthropic")
os.environ.setdefault("PINECONE_API_KEY", "pcsk-test-pinecone")
os.environ.setdefault("LANGSMITH_API_KEY", "lsv2-test-langsmith")
os.environ.setdefault("PINECONE_INDEX_NAME", "cancards-index")
os.environ.setdefault("LANGSMITH_TRACING", "false")
