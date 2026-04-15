import logging
import os
from typing import Dict, List, Optional

try:
    import chromadb  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    chromadb = None

logger = logging.getLogger(__name__)


class ChromaLegalClient:
    """Lightweight Chroma wrapper for legal retrieval."""

    def __init__(self, persist_directory: Optional[str] = None, embedding_model: Optional[str] = None):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        default_dir = os.path.join(base_dir, "data", "legal_chroma")
        self.persist_directory = persist_directory or os.getenv("AGENT_CHROMA_PATH", default_dir)
        self.embedding_model = embedding_model or os.getenv(
            "AGENT_EMBEDDING_MODEL",
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        )
        os.makedirs(self.persist_directory, exist_ok=True)

        self.client = None
        self.embedding_function = None
        self.available = False

        if chromadb is None:
            logger.warning("chromadb is not installed. vector retrieval will fallback to keyword search.")
            return

        try:
            try:
                from chromadb.config import Settings

                self.client = chromadb.PersistentClient(
                    path=self.persist_directory,
                    settings=Settings(anonymized_telemetry=False, allow_reset=True),
                )
            except Exception:
                self.client = chromadb.PersistentClient(path=self.persist_directory)
            self.embedding_function = self._build_embedding_function()
            self.available = True
        except Exception as exc:
            logger.warning("Failed to initialize chromadb client, fallback enabled. error=%s", exc)
            self.client = None
            self.embedding_function = None
            self.available = False

    def _build_embedding_function(self):
        try:
            import sentence_transformers  # noqa: F401
        except Exception as exc:
            logger.warning(
                "sentence-transformers import failed, fallback to Chroma default embedding. error=%s",
                exc,
            )
            return None

        try:
            from chromadb.utils import embedding_functions

            return embedding_functions.SentenceTransformerEmbeddingFunction(model_name=self.embedding_model)
        except Exception as exc:
            logger.warning(
                "Failed to create SentenceTransformer embedding function, fallback to Chroma default. error=%s",
                exc,
            )
            return None

    def is_available(self) -> bool:
        return self.available and self.client is not None

    def get_or_create_collection(self, name: str):
        if not self.is_available():
            return None
        if self.embedding_function is not None:
            return self.client.get_or_create_collection(name=name, embedding_function=self.embedding_function)
        return self.client.get_or_create_collection(name=name)

    def collection_count(self, name: str) -> int:
        collection = self.get_or_create_collection(name)
        if collection is None:
            return 0
        try:
            return collection.count()
        except Exception:
            return 0

    def upsert_documents(self, collection_name: str, documents: List[Dict[str, str]]) -> None:
        if not documents or not self.is_available():
            return

        collection = self.get_or_create_collection(collection_name)
        if collection is None:
            return
        ids = [item["id"] for item in documents]
        texts = [item["text"] for item in documents]
        metadatas = [item["metadata"] for item in documents]
        collection.upsert(ids=ids, documents=texts, metadatas=metadatas)

    def query(self, collection_name: str, query_text: str, top_k: int = 5) -> List[Dict[str, object]]:
        if not self.is_available():
            return []

        collection = self.get_or_create_collection(collection_name)
        if collection is None:
            return []
        result = collection.query(query_texts=[query_text], n_results=max(1, top_k))

        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        items: List[Dict[str, object]] = []
        for index, doc_id in enumerate(ids):
            distance = float(distances[index]) if index < len(distances) else 1.0
            score = max(0.0, 1.0 - distance)
            items.append(
                {
                    "id": doc_id,
                    "content": documents[index] if index < len(documents) else "",
                    "metadata": metadatas[index] if index < len(metadatas) else {},
                    "score": round(score, 4),
                }
            )

        return items


chroma_legal_client = ChromaLegalClient()
