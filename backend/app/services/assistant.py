"""
FinScope Assistant — RAG chatbot service (Phase 9).

Architecture:
  1. On transaction ingest/feature refresh → embed transaction summaries
     into ChromaDB (vector store)
  2. On user question → embed query → retrieve top-k relevant chunks
  3. Augment LLM prompt with retrieved context → OpenAI GPT response

Why RAG vs fine-tuning?
  - User data changes daily (new transactions) — fine-tuning can't adapt
  - RAG retrieves the most recent data at query time
  - Much cheaper: no model training cost, just embedding + inference
  - Data isolation: each user's vectors are namespaced by user_id
"""

from __future__ import annotations

import json
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

SYSTEM_PROMPT = """You are FinScope Assistant, a personal finance AI advisor.
You have access to the user's actual transaction data and financial analytics.
Answer questions about their spending, savings, goals, and financial health.
Be specific, cite amounts and categories from the context provided.
If information is not in the context, say so clearly.
Never make up financial data. Keep responses concise and actionable.
"""


class FinScopeAssistant:
    """
    RAG-based financial Q&A assistant.

    Uses ChromaDB for vector storage and OpenAI for embeddings + generation.
    """

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self.collection_name = f"user_{user_id.replace('-', '_')}"

    def index_user_data(self, summaries: list[dict[str, Any]]) -> int:
        """
        Embed and store transaction summaries for a user.

        Args:
            summaries: List of {id, text, metadata} dicts

        Returns:
            Number of chunks indexed.
        """
        try:
            import chromadb
            from app.core.config import settings

            client = chromadb.Client()
            collection = client.get_or_create_collection(
                name=self.collection_name,
                metadata={"user_id": self.user_id},
            )

            ids = [s["id"] for s in summaries]
            documents = [s["text"] for s in summaries]
            metadatas = [s.get("metadata", {}) for s in summaries]

            collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
            logger.info("rag_indexed", user_id=self.user_id, chunks=len(summaries))
            return len(summaries)
        except Exception as exc:
            logger.error("rag_index_failed", error=str(exc))
            return 0

    def query(self, question: str, n_results: int = 5) -> dict[str, Any]:
        """
        Answer a financial question using RAG.

        Returns:
            {answer: str, sources: list[str], context_used: bool}
        """
        from app.core.config import settings

        if not settings.OPENAI_API_KEY:
            return self._fallback_response(question)

        # Step 1: Retrieve relevant context
        context = self._retrieve_context(question, n_results)

        # Step 2: Build augmented prompt
        messages = self._build_messages(question, context)

        # Step 3: Generate response
        try:
            from openai import OpenAI

            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            response = client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=500,
                temperature=0.3,  # lower temp = more factual
            )
            answer = response.choices[0].message.content or "I couldn't generate a response."

            return {
                "answer": answer,
                "sources": [c["text"][:100] for c in context],
                "context_used": len(context) > 0,
            }
        except Exception as exc:
            logger.error("openai_query_failed", error=str(exc))
            return self._fallback_response(question)

    def _retrieve_context(self, question: str, n_results: int) -> list[dict[str, Any]]:
        """Retrieve top-k relevant chunks from ChromaDB."""
        try:
            import chromadb

            client = chromadb.Client()
            collection = client.get_or_create_collection(self.collection_name)

            if collection.count() == 0:
                return []

            results = collection.query(
                query_texts=[question],
                n_results=min(n_results, collection.count()),
            )

            chunks = []
            if results["documents"]:
                for i, doc in enumerate(results["documents"][0]):
                    chunks.append({
                        "text": doc,
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    })
            return chunks
        except Exception as exc:
            logger.warning("rag_retrieve_failed", error=str(exc))
            return []

    def _build_messages(self, question: str, context: list[dict]) -> list[dict[str, str]]:
        """Build the LLM message array with RAG context."""
        context_text = "\n\n".join([f"[Data] {c['text']}" for c in context])
        if context_text:
            user_message = (
                f"Based on the following financial data:\n\n{context_text}\n\n"
                f"Question: {question}"
            )
        else:
            user_message = f"Question: {question}\n\n(Note: No transaction data is indexed yet.)"

        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

    def _fallback_response(self, question: str) -> dict[str, Any]:
        """Return a helpful fallback when OpenAI is not configured."""
        return {
            "answer": (
                "FinScope Assistant requires an OpenAI API key to answer questions. "
                "Please configure OPENAI_API_KEY in your .env file. "
                f"Your question was: '{question}'"
            ),
            "sources": [],
            "context_used": False,
        }

    @staticmethod
    def build_transaction_summaries(transactions: list[Any]) -> list[dict[str, Any]]:
        """
        Convert transaction ORM objects to embeddable text chunks.

        Each chunk = one month of spending by category (not individual transactions)
        to keep context concise and under token limits.
        """
        import pandas as pd

        if not transactions:
            return []

        records = [
            {
                "date": str(tx.transaction_date)[:7],  # YYYY-MM
                "amount": float(tx.amount_usd or tx.amount_raw),
                "category": tx.category.value if tx.category else "other",
                "type": tx.transaction_type.value,
            }
            for tx in transactions
        ]
        df = pd.DataFrame(records)
        summaries = []

        for period, group in df.groupby("date"):
            debits = group[group["type"] == "debit"]
            credits = group[group["type"] == "credit"]
            by_cat = debits.groupby("category")["amount"].sum().to_dict()
            cat_str = ", ".join([f"{k}: ${v:.0f}" for k, v in sorted(by_cat.items(), key=lambda x: -x[1])])

            text = (
                f"{period}: Total spend ${debits['amount'].sum():.0f}, "
                f"income ${credits['amount'].sum():.0f}. "
                f"By category: {cat_str}."
            )
            summaries.append({
                "id": f"monthly_{period}",
                "text": text,
                "metadata": {"period": str(period), "type": "monthly_summary"},
            })

        return summaries
