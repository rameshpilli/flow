"""
AgentOrchestrator RAG Agent Template
====================================

Provides a template for Retrieval-Augmented Generation (RAG) agents
that combine VectorStoreService for retrieval and LLMGatewayClient for generation.
"""

import logging
from typing import Optional, Any, AsyncIterable

from agentorchestrator.squad.agents.llm_gateway_agent import (
    LLMGatewayAgent,
    LLMGatewayAgentOptions,
)
from agentorchestrator.squad.types import (
    ConversationMessage,
    ParticipantRole,
    AgentStreamResponse,
)
from agentorchestrator.services.vector_store import VectorStoreService, VectorStoreConfig

logger = logging.getLogger(__name__)

class RAGAgentOptions(LLMGatewayAgentOptions):
    """
    Options for RAG Agent.
    
    Attributes:
        vector_store_config: Configuration for the vector store
        top_k: Number of documents to retrieve
        context_prompt_template: Template for injecting retrieved context
    """
    vector_store_config: Optional[VectorStoreConfig] = None
    top_k: int = 3
    context_prompt_template: str = (
        "Use the following pieces of retrieved context to answer the question. "
        "If you don't know the answer, just say that you don't know. "
        "\n\nContext:\n{context}\n\nQuestion: {query}"
    )

class RAGAgent(LLMGatewayAgent):
    """
    Agent that performs Retrieval-Augmented Generation.
    
    Combines vector search with LLM generation to provide grounded answers.
    """
    
    def __init__(self, options: RAGAgentOptions):
        super().__init__(options)
        self.rag_options = options
        self.vector_store = VectorStoreService(config=options.vector_store_config)

    async def process_request(
        self,
        input_text: str,
        user_id: str,
        session_id: str,
        chat_history: list[ConversationMessage],
        additional_params: Optional[dict[str, Any]] = None,
    ) -> ConversationMessage:
        """Process request with retrieval step."""
        
        # 1. Retrieve relevant documents
        try:
            matches = await self.vector_store.query(input_text, top_k=self.rag_options.top_k)
            context_text = "\n".join([f"- {m.text}" for m in matches])
        except Exception as e:
            logger.error(f"RAG Retrieval failed: {e}")
            context_text = "No context available (retrieval failed)."

        # 2. Build augmented prompt
        rag_prompt = self.rag_options.context_prompt_template.format(
            context=context_text,
            query=input_text
        )

        # 3. Generate response using base LLM agent logic
        # We pass the augmented prompt as the input to the base implementation
        return await super().process_request(
            rag_prompt, user_id, session_id, chat_history, additional_params
        )

    # Note: For streaming, we'd override process_request similarly 
    # but yielding from super().process_request if it returns a stream.