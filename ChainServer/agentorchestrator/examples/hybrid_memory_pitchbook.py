"""
Hybrid Memory Architecture Example: Pitchbook Editor with Multi-Agent System

This example demonstrates a sophisticated multi-agent AI system that:
- Automatically extracts context from existing pitchbooks
- Enables intelligent text refinement through natural language instructions
- Employs a hybrid memory architecture combining:
  - Session Memory (Redis) - 24-hour retention for active editing
  - Long-term Memory (Mem0) - Persistent project/user knowledge
  - Reference Memory (Cohere Compass) - Semantic search across documents

Architecture:
    ┌─────────────────────────────────────────────────────────────────┐
    │                     ORCHESTRATOR AGENT                          │
    │         (Coordinates workflow, manages user interactions)        │
    └─────────────────────────────────────────────────────────────────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            ▼                       ▼                       ▼
    ┌───────────────┐      ┌───────────────┐      ┌───────────────┐
    │   Document    │      │   Context     │      │   Content     │
    │   Analyzer    │      │   Builder     │      │   Generator   │
    │   Agent       │      │   Agent       │      │   Agent       │
    └───────────────┘      └───────────────┘      └───────────────┘
            │                       │                       │
            ▼                       ▼                       ▼
    ┌───────────────┐      ┌───────────────┐      ┌───────────────┐
    │   Refinement  │      │   Compass     │      │   Memory      │
    │   Agent       │      │   Agent       │      │   Manager     │
    │ (Self-Critique)│      │ (References)  │      │   Agent       │
    └───────────────┘      └───────────────┘      └───────────────┘

Memory Architecture:
    ┌─────────────────────────────────────────────────────────────────┐
    │                      HYBRID MEMORY                               │
    ├─────────────────┬─────────────────┬─────────────────────────────┤
    │  Session Memory │  Long-term Mem  │  Reference Memory           │
    │  (Redis)        │  (Mem0)         │  (Cohere Compass)           │
    │  TTL: 24 hours  │  Permanent      │  Project lifetime           │
    │                 │                 │                             │
    │  - Current edits│  - User prefs   │  - Reference docs           │
    │  - Undo states  │  - Company ctx  │  - Research materials       │
    │  - Working draft│  - Patterns     │  - Source files             │
    └─────────────────┴─────────────────┴─────────────────────────────┘

Usage:
    # Set environment variables for your services
    export LLM_SERVER_URL="https://llm-gateway.corp.com/v1/chat/completions"
    export LLM_CLIENT_ID="your-client-id"
    export LLM_CLIENT_SECRET="your-client-secret"
    export COHERE_COMPASS_URL="https://compass.corp.com"
    export COHERE_COMPASS_API_KEY="your-api-key"

    # Run the example
    python -m agentorchestrator.examples.hybrid_memory_pitchbook

Requirements:
    pip install agentorchestrator[all]
    pip install python-pptx  # For PPTX parsing
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

# AgentOrchestrator imports
from agentorchestrator import AgentOrchestrator
from agentorchestrator.agents.base import AgentResult, BaseAgent
from agentorchestrator.middleware import (
    CitationMiddleware,
    LoggerMiddleware,
    MetricsMiddleware,
    ReflectionConfig,
    ReflectionMiddleware,
)
from agentorchestrator.services import (
    LLMGatewayClient,
    Mem0Memory,
    VectorStoreService,
)
from agentorchestrator.squad import (
    AggregationStrategy,
    ContextIsolationManager,
    IsolationLevel,
    LLMGatewayAgent,
    LLMGatewayAgentOptions,
    ResultAggregator,
    Squad,
    SquadOptions,
    SupervisorAgent,
    SupervisorAgentOptions,
)
from agentorchestrator.squad.storage import InMemoryChatStorage
from agentorchestrator.squad.storage.redis import RedisChatStorage

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
#                              CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class HybridMemoryConfig:
    """Configuration for the hybrid memory architecture."""

    # Session Memory (Redis)
    session_ttl_seconds: int = 86400  # 24 hours default
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: Optional[str] = None
    redis_ssl: bool = False

    # Long-term Memory (Mem0)
    mem0_api_key: Optional[str] = None
    mem0_host: Optional[str] = None

    # Reference Memory (Cohere Compass)
    compass_url: Optional[str] = None
    compass_api_key: Optional[str] = None
    compass_index_name: str = "pitchbook_references"

    # LLM Configuration
    llm_server_url: Optional[str] = None
    llm_client_id: Optional[str] = None
    llm_client_secret: Optional[str] = None
    llm_model: str = "gpt-4"

    @classmethod
    def from_env(cls) -> "HybridMemoryConfig":
        """Load configuration from environment variables."""
        return cls(
            # Session Memory
            session_ttl_seconds=int(os.getenv("SESSION_TTL_SECONDS", "86400")),
            redis_host=os.getenv("REDIS_HOST", "localhost"),
            redis_port=int(os.getenv("REDIS_PORT", "6379")),
            redis_password=os.getenv("REDIS_PASSWORD"),
            redis_ssl=os.getenv("REDIS_SSL", "false").lower() == "true",
            # Long-term Memory
            mem0_api_key=os.getenv("MEM0_API_KEY"),
            mem0_host=os.getenv("MEM0_HOST"),
            # Reference Memory
            compass_url=os.getenv("COHERE_COMPASS_URL"),
            compass_api_key=os.getenv("COHERE_COMPASS_API_KEY"),
            compass_index_name=os.getenv("COMPASS_INDEX_NAME", "pitchbook_references"),
            # LLM
            llm_server_url=os.getenv("LLM_SERVER_URL"),
            llm_client_id=os.getenv("LLM_CLIENT_ID"),
            llm_client_secret=os.getenv("LLM_CLIENT_SECRET"),
            llm_model=os.getenv("LLM_MODEL_NAME", "gpt-4"),
        )


@dataclass
class SlideContent:
    """Represents content extracted from a slide."""

    slide_number: int
    title: str = ""
    body_text: list[str] = field(default_factory=list)
    notes: str = ""
    shapes: list[dict] = field(default_factory=list)


@dataclass
class PitchbookContext:
    """Context extracted from a pitchbook."""

    company_name: str = ""
    industry: str = ""
    pitch_type: str = ""  # e.g., "Series A", "M&A", "IPO"
    slides: list[SlideContent] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════════════
#                         DOCUMENT PARSER AGENT
# ═══════════════════════════════════════════════════════════════════════════════


class DocumentParserAgent(BaseAgent):
    """
    Agent for parsing PPTX files and extracting structured content.

    This agent handles:
    - Text extraction from slides
    - Shape and layout detection
    - Speaker notes extraction
    - Metadata extraction

    Requires: pip install python-pptx
    """

    _ao_name = "DocumentParser"
    _ao_description = "Extract text and structure from PowerPoint files"

    def __init__(self):
        super().__init__()
        self._pptx_available = False
        try:
            from pptx import Presentation  # noqa: F401

            self._pptx_available = True
        except ImportError:
            logger.warning(
                "python-pptx not installed. Install with: pip install python-pptx"
            )

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        """
        Parse a PPTX file and extract content.

        Args:
            query: Path to the PPTX file
            **kwargs: Additional options (e.g., extract_images=True)

        Returns:
            AgentResult with extracted slide content
        """
        import time

        start = time.perf_counter()
        file_path = kwargs.get("file_path", query)

        if not self._pptx_available:
            return AgentResult(
                data=None,
                source=self._ao_name,
                query=query,
                duration_ms=(time.perf_counter() - start) * 1000,
                error="python-pptx not installed",
            )

        try:
            from pptx import Presentation

            prs = Presentation(file_path)
            slides = []

            for i, slide in enumerate(prs.slides, 1):
                slide_content = SlideContent(slide_number=i)

                # Extract text from shapes
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text.strip():
                        # Check if it's a title
                        if shape.is_placeholder and hasattr(shape, "placeholder_format"):
                            if shape.placeholder_format.type == 1:  # Title
                                slide_content.title = shape.text.strip()
                            else:
                                slide_content.body_text.append(shape.text.strip())
                        else:
                            slide_content.body_text.append(shape.text.strip())

                    # Store shape info for layout understanding
                    slide_content.shapes.append(
                        {
                            "type": type(shape).__name__,
                            "has_text": hasattr(shape, "text"),
                        }
                    )

                # Extract notes
                if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
                    slide_content.notes = slide.notes_slide.notes_text_frame.text

                slides.append(slide_content)

            # Extract presentation metadata
            metadata = {
                "slide_count": len(prs.slides),
                "slide_width": prs.slide_width,
                "slide_height": prs.slide_height,
            }

            duration = (time.perf_counter() - start) * 1000
            return AgentResult(
                data={
                    "slides": [
                        {
                            "number": s.slide_number,
                            "title": s.title,
                            "body": s.body_text,
                            "notes": s.notes,
                        }
                        for s in slides
                    ],
                    "metadata": metadata,
                },
                source=self._ao_name,
                query=file_path,
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.perf_counter() - start) * 1000
            return AgentResult(
                data=None,
                source=self._ao_name,
                query=file_path,
                duration_ms=duration,
                error=str(e),
            )


# ═══════════════════════════════════════════════════════════════════════════════
#                         MEMORY MANAGER AGENT
# ═══════════════════════════════════════════════════════════════════════════════


class MemoryManagerAgent(BaseAgent):
    """
    Agent that coordinates between different memory systems.

    Responsibilities:
    - Route queries to appropriate memory backends
    - Merge results from multiple sources
    - Handle memory promotion (session → long-term)
    - Manage memory lifecycle
    """

    _ao_name = "MemoryManager"
    _ao_description = "Coordinate between session, long-term, and reference memory"

    def __init__(
        self,
        session_storage: Optional[Any] = None,
        long_term_memory: Optional[Mem0Memory] = None,
        reference_memory: Optional[VectorStoreService] = None,
        importance_threshold: float = 0.8,
    ):
        super().__init__()
        self.session_storage = session_storage
        self.long_term_memory = long_term_memory
        self.reference_memory = reference_memory
        self.importance_threshold = importance_threshold

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        """
        Search across all memory systems and merge results.

        Args:
            query: Search query
            **kwargs:
                - user_id: User identifier
                - session_id: Session identifier
                - search_session: Include session memory (default: True)
                - search_longterm: Include long-term memory (default: True)
                - search_references: Include reference docs (default: True)

        Returns:
            AgentResult with merged memory results
        """
        import time

        start = time.perf_counter()
        results = {
            "session": [],
            "long_term": [],
            "references": [],
        }

        user_id = kwargs.get("user_id", "default")
        session_id = kwargs.get("session_id", "default")

        # Search session memory
        if kwargs.get("search_session", True) and self.session_storage:
            try:
                shared_memory = await self.session_storage.get_shared_memory(
                    user_id, session_id
                )
                if shared_memory:
                    results["session"] = [
                        {"key": k, "value": v} for k, v in shared_memory.items()
                    ]
            except Exception as e:
                logger.warning(f"Session memory search failed: {e}")

        # Search long-term memory
        if kwargs.get("search_longterm", True) and self.long_term_memory:
            try:
                memories = await self.long_term_memory.search(query, limit=5)
                results["long_term"] = [
                    {"content": m.content, "relevance": m.relevance_score}
                    for m in memories
                ]
            except Exception as e:
                logger.warning(f"Long-term memory search failed: {e}")

        # Search reference documents
        if kwargs.get("search_references", True) and self.reference_memory:
            try:
                matches = await self.reference_memory.search(query, top_k=5)
                results["references"] = [
                    {
                        "text": m.text,
                        "score": m.score,
                        "metadata": m.metadata,
                    }
                    for m in matches
                ]
            except Exception as e:
                logger.warning(f"Reference memory search failed: {e}")

        duration = (time.perf_counter() - start) * 1000
        return AgentResult(
            data=results,
            source=self._ao_name,
            query=query,
            duration_ms=duration,
        )

    async def promote_to_longterm(
        self,
        content: str,
        metadata: Optional[dict] = None,
        importance_score: float = 1.0,
    ) -> bool:
        """
        Promote content from session to long-term memory.

        Args:
            content: Content to store
            metadata: Optional metadata
            importance_score: Score indicating importance (0.0-1.0)

        Returns:
            True if successfully promoted
        """
        if importance_score < self.importance_threshold:
            logger.debug(
                f"Content below threshold ({importance_score} < {self.importance_threshold})"
            )
            return False

        if not self.long_term_memory:
            logger.warning("No long-term memory configured")
            return False

        try:
            await self.long_term_memory.add(content, metadata=metadata)
            logger.info(f"Promoted content to long-term memory: {content[:50]}...")
            return True
        except Exception as e:
            logger.error(f"Failed to promote to long-term memory: {e}")
            return False


# ═══════════════════════════════════════════════════════════════════════════════
#                       PITCHBOOK EDITOR SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════


class PitchbookEditor:
    """
    Main orchestrator for the pitchbook editing system.

    This class coordinates:
    - Memory architecture initialization
    - Agent team setup
    - Workflow execution
    - Context management
    """

    def __init__(self, config: HybridMemoryConfig):
        self.config = config
        self.ao = AgentOrchestrator(name="pitchbook_editor")

        # Memory systems (initialized lazily)
        self._session_storage: Optional[Any] = None
        self._long_term_memory: Optional[Mem0Memory] = None
        self._reference_memory: Optional[VectorStoreService] = None

        # LLM client
        self._llm_client: Optional[LLMGatewayClient] = None

        # Agents
        self._document_parser: Optional[DocumentParserAgent] = None
        self._memory_manager: Optional[MemoryManagerAgent] = None
        self._orchestrator: Optional[SupervisorAgent] = None

        # State
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize all components."""
        if self._initialized:
            return

        logger.info("Initializing PitchbookEditor...")

        # Initialize memory systems
        await self._init_memory_systems()

        # Initialize LLM client
        self._init_llm_client()

        # Initialize agents
        self._init_agents()

        # Add middleware
        self._init_middleware()

        self._initialized = True
        logger.info("PitchbookEditor initialized successfully")

    async def _init_memory_systems(self) -> None:
        """Initialize the three-layer memory architecture."""

        # 1. Session Memory (Redis with configurable TTL)
        try:
            from agentorchestrator.services.redis import init_redis_client

            init_redis_client(
                host=self.config.redis_host,
                port=self.config.redis_port,
                password=self.config.redis_password,
                ssl=self.config.redis_ssl,
            )
            self._session_storage = RedisChatStorage(
                ttl_seconds=self.config.session_ttl_seconds,  # User-configurable!
            )
            logger.info(
                f"Session memory initialized (TTL: {self.config.session_ttl_seconds}s)"
            )
        except Exception as e:
            logger.warning(f"Redis not available, using in-memory storage: {e}")
            self._session_storage = InMemoryChatStorage()

        # 2. Long-term Memory (Mem0)
        if self.config.mem0_api_key or self.config.mem0_host:
            try:
                # Note: You'd need to provide your Mem0 client implementation
                # This is a placeholder showing the pattern
                self._long_term_memory = Mem0Memory(
                    client=None,  # Your Mem0 client here
                    user_id="pitchbook_system",
                )
                logger.info("Long-term memory (Mem0) initialized")
            except Exception as e:
                logger.warning(f"Mem0 not available: {e}")

        # 3. Reference Memory (Cohere Compass)
        if self.config.compass_url:
            try:
                self._reference_memory = VectorStoreService(
                    provider="cohere_compass",
                    index_name=self.config.compass_index_name,
                )
                logger.info("Reference memory (Compass) initialized")
            except Exception as e:
                logger.warning(f"Cohere Compass not available: {e}")

    def _init_llm_client(self) -> None:
        """Initialize LLM client."""
        if self.config.llm_server_url:
            self._llm_client = LLMGatewayClient(
                server_url=self.config.llm_server_url,
                client_id=self.config.llm_client_id,
                client_secret=self.config.llm_client_secret,
                model_name=self.config.llm_model,
            )
        else:
            logger.warning("No LLM server configured, using mock responses")

    def _init_agents(self) -> None:
        """Initialize the agent team."""

        # Document Parser (no LLM needed)
        self._document_parser = DocumentParserAgent()

        # Memory Manager
        self._memory_manager = MemoryManagerAgent(
            session_storage=self._session_storage,
            long_term_memory=self._long_term_memory,
            reference_memory=self._reference_memory,
        )

        if not self._llm_client:
            logger.warning("LLM client not available, skipping LLM agents")
            return

        # Context Builder Agent
        context_builder = LLMGatewayAgent(
            LLMGatewayAgentOptions(
                name="ContextBuilder",
                description="Synthesize extracted information into comprehensive project context",
                llm_client=self._llm_client,
            )
        )

        # Content Generator Agent
        content_generator = LLMGatewayAgent(
            LLMGatewayAgentOptions(
                name="ContentGenerator",
                description="Generate and modify text based on user instructions",
                llm_client=self._llm_client,
            )
        )

        # Refinement Agent (with self-critique)
        refinement_agent = LLMGatewayAgent(
            LLMGatewayAgentOptions(
                name="RefinementAgent",
                description="Review and improve generated content through iterative refinement",
                llm_client=self._llm_client,
            )
        )

        # Compass Integration Agent
        compass_agent = LLMGatewayAgent(
            LLMGatewayAgentOptions(
                name="CompassAgent",
                description="Search reference documents and provide citations",
                llm_client=self._llm_client,
            )
        )

        # Main Orchestrator (Supervisor)
        self._orchestrator = SupervisorAgent(
            SupervisorAgentOptions(
                name="Orchestrator",
                description="Coordinate the pitchbook editing workflow",
                llm_client=self._llm_client,
                team=[
                    context_builder,
                    content_generator,
                    refinement_agent,
                    compass_agent,
                ],
                storage=self._session_storage,
                isolation_level=IsolationLevel.PARTIAL,
            )
        )

    def _init_middleware(self) -> None:
        """Configure middleware stack."""
        # Logging
        self.ao.use(LoggerMiddleware(level="INFO"))

        # Metrics collection
        self.ao.use(MetricsMiddleware())

        # Citation tracking for RAG
        self.ao.use(CitationMiddleware())

        # Self-critique for quality (applied to specific steps)
        self.ao.use(
            ReflectionMiddleware(
                config=ReflectionConfig(
                    quality_threshold=0.8,
                    max_revisions=2,
                    applies_to=["generate_content", "refine_content"],
                )
            )
        )

    async def parse_pitchbook(self, file_path: str) -> PitchbookContext:
        """
        Parse a pitchbook and extract context.

        Args:
            file_path: Path to the PPTX file

        Returns:
            PitchbookContext with extracted information
        """
        await self.initialize()

        result = await self._document_parser.fetch(file_path=file_path, query=file_path)

        if result.error:
            raise RuntimeError(f"Failed to parse pitchbook: {result.error}")

        data = result.data
        context = PitchbookContext(
            slides=[
                SlideContent(
                    slide_number=s["number"],
                    title=s["title"],
                    body_text=s["body"],
                    notes=s["notes"],
                )
                for s in data["slides"]
            ],
            metadata=data["metadata"],
        )

        # Store in session memory
        if self._session_storage:
            await self._session_storage.update_shared_memory(
                user_id="system",
                session_id="current",
                key="pitchbook_context",
                value={
                    "slide_count": len(context.slides),
                    "extracted_at": datetime.now().isoformat(),
                },
            )

        return context

    async def edit_slide(
        self,
        user_id: str,
        session_id: str,
        slide_number: int,
        instruction: str,
        context: Optional[PitchbookContext] = None,
    ) -> dict[str, Any]:
        """
        Edit a slide based on natural language instruction.

        Args:
            user_id: User identifier
            session_id: Session identifier
            slide_number: Slide to edit (1-indexed)
            instruction: Natural language edit instruction
            context: Optional pitchbook context

        Returns:
            Dict with edited content and metadata
        """
        await self.initialize()

        if not self._orchestrator:
            return {"error": "Orchestrator not initialized (LLM required)"}

        # 1. Gather context from all memory systems
        memory_result = await self._memory_manager.fetch(
            query=instruction,
            user_id=user_id,
            session_id=session_id,
        )

        # 2. Build the prompt with context
        prompt = f"""
Edit slide {slide_number} based on the following instruction:

INSTRUCTION: {instruction}

CONTEXT FROM MEMORY:
- Session: {json.dumps(memory_result.data.get('session', []), indent=2)}
- Long-term knowledge: {json.dumps(memory_result.data.get('long_term', []), indent=2)}
- Reference documents: {json.dumps(memory_result.data.get('references', []), indent=2)}

Please generate the edited content for this slide.
"""

        # 3. Run through the orchestrator
        result = await self._orchestrator.process(
            query=prompt,
            context={
                "user_id": user_id,
                "session_id": session_id,
                "slide_number": slide_number,
            },
        )

        # 4. Store the edit in session memory
        if self._session_storage:
            await self._session_storage.save_chat_message(
                user_id=user_id,
                session_id=session_id,
                agent_id="Orchestrator",
                new_message={
                    "role": "assistant",
                    "content": [{"text": result.content if hasattr(result, 'content') else str(result)}],
                },
            )

        # 5. Check if this edit should be promoted to long-term memory
        if hasattr(result, "metadata") and result.metadata.get("is_pattern", False):
            await self._memory_manager.promote_to_longterm(
                content=f"User editing pattern: {instruction}",
                metadata={
                    "user_id": user_id,
                    "type": "editing_pattern",
                },
                importance_score=0.9,
            )

        return {
            "slide_number": slide_number,
            "edited_content": result.content if hasattr(result, 'content') else str(result),
            "memory_context_used": {
                "session_items": len(memory_result.data.get("session", [])),
                "longterm_items": len(memory_result.data.get("long_term", [])),
                "reference_items": len(memory_result.data.get("references", [])),
            },
        }

    async def upload_reference(
        self,
        file_path: str,
        metadata: Optional[dict] = None,
    ) -> bool:
        """
        Upload a reference document to Compass.

        Args:
            file_path: Path to the document
            metadata: Optional metadata

        Returns:
            True if uploaded successfully
        """
        if not self._reference_memory:
            logger.warning("Reference memory not configured")
            return False

        try:
            # Read file content
            with open(file_path, "r") as f:
                content = f.read()

            # Add to vector store
            from agentorchestrator.services import VectorDocument

            doc = VectorDocument(
                id=f"ref_{datetime.now().timestamp()}",
                text=content,
                metadata=metadata or {"source": file_path},
            )
            await self._reference_memory.add_documents([doc])
            logger.info(f"Uploaded reference document: {file_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to upload reference: {e}")
            return False

    async def cleanup(self) -> None:
        """Cleanup resources."""
        logger.info("Cleaning up PitchbookEditor...")
        # Add any cleanup logic here


# ═══════════════════════════════════════════════════════════════════════════════
#                              EXAMPLE USAGE
# ═══════════════════════════════════════════════════════════════════════════════


async def main():
    """Demonstrate the hybrid memory pitchbook editor."""
    print("=" * 70)
    print("Hybrid Memory Architecture: Pitchbook Editor Demo")
    print("=" * 70)

    # Load configuration from environment
    config = HybridMemoryConfig.from_env()

    # Override with demo settings if not configured
    if not config.redis_host:
        config.redis_host = "localhost"
    if not config.session_ttl_seconds:
        config.session_ttl_seconds = 86400  # 24 hours

    print(f"\nConfiguration:")
    print(f"  Session TTL: {config.session_ttl_seconds} seconds ({config.session_ttl_seconds // 3600} hours)")
    print(f"  Redis: {config.redis_host}:{config.redis_port}")
    print(f"  Compass: {config.compass_url or 'Not configured'}")
    print(f"  Mem0: {config.mem0_host or 'Not configured'}")

    # Initialize the editor
    editor = PitchbookEditor(config)

    try:
        await editor.initialize()
        print("\n[OK] PitchbookEditor initialized")

        # Demo: Memory Manager search
        print("\n--- Memory Manager Demo ---")
        result = await editor._memory_manager.fetch(
            query="company financial performance",
            user_id="demo_user",
            session_id="demo_session",
        )
        print(f"Memory search completed in {result.duration_ms:.2f}ms")
        print(f"  Session items: {len(result.data.get('session', []))}")
        print(f"  Long-term items: {len(result.data.get('long_term', []))}")
        print(f"  Reference items: {len(result.data.get('references', []))}")

        # Demo: Document parsing (if PPTX file provided)
        demo_pptx = os.getenv("DEMO_PPTX_PATH")
        if demo_pptx and os.path.exists(demo_pptx):
            print(f"\n--- Document Parser Demo ---")
            context = await editor.parse_pitchbook(demo_pptx)
            print(f"Parsed {len(context.slides)} slides")
            for slide in context.slides[:3]:  # Show first 3
                print(f"  Slide {slide.slide_number}: {slide.title or '(no title)'}")

        print("\n" + "=" * 70)
        print("Demo complete! The system supports:")
        print("  1. Configurable session TTL (Redis)")
        print("  2. Long-term semantic memory (Mem0)")
        print("  3. Reference document search (Cohere Compass)")
        print("  4. Multi-agent coordination with context isolation")
        print("  5. Self-critique/reflection for quality")
        print("=" * 70)

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()

    finally:
        await editor.cleanup()


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Run the demo
    asyncio.run(main())
