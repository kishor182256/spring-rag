from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "GenAI FastAPI Service"
    api_v1_prefix: str = "/api/v1"
    upload_dir: str = "storage/uploads"
    chunk_size: int = 1000
    chunk_overlap: int = 150
    embedding_provider: str = "local"
    llm_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "llama3.1:8b"
    ollama_timeout_seconds: int = 25
    ollama_max_output_tokens: int = 140
    ollama_keep_alive: str = "30m"
    rag_answer_cache_ttl_seconds: int = 300
    llm_context_chunks: int = 3
    llm_chunk_char_limit: int = 700
    hf_api_token: str = ""
    hf_model: str = "mistralai/Mistral-7B-Instruct-v0.2"
    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-small"
    openai_chat_model: str = "gpt-4o-mini"
    openai_chat_enabled: bool = True
    llm_answer_required: bool = True
    retrieval_top_k: int = 4
    retrieval_candidate_multiplier: int = 2
    retrieval_semantic_pool: int = 60
    retrieval_min_semantic_score: float = 0.1
    retrieval_min_lexical_score: float = 0.15
    retrieval_max_jaccard_similarity: float = 0.8

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
UPLOAD_DIR_PATH = Path(settings.upload_dir)
