"""
CMPT Services - Client Meeting Prep Tool

3-Stage Pipeline:
  01_context_builder.py     → Extract company, temporal, persona info
  02_content_prioritization.py → Prioritize sources, generate subqueries
  03_response_builder.py    → Execute agents, build final response

Usage:
    from cmpt.services import (
        ContextBuilderService,        # Step 1
        ContentPrioritizationService, # Step 2
        ResponseBuilderService,       # Step 3
    )
"""

# ═══════════════════════════════════════════════════════════════════════════════
#                    FROM AGENTORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════════

from agentorchestrator.agents.base import (
    AgentResult, BaseAgent, CompositeAgent, ResilientAgent,
    ResilientAgentConfig, ResilientCompositeAgent,
)
from agentorchestrator.services.llm_gateway import (
    LLMGatewayClient, OAuthTokenManager, timed_lru_cache,
)

# ═══════════════════════════════════════════════════════════════════════════════
#                    CMPT SERVICES (Step 1, 2, 3)
# ═══════════════════════════════════════════════════════════════════════════════

from cmpt.services._01_context_builder import ContextBuilderService
from cmpt.services._02_content_prioritization import ContentPrioritizationService, ToolName
from cmpt.services._03_response_builder import ResponseBuilderService

# ═══════════════════════════════════════════════════════════════════════════════
#                    CMPT MODELS
# ═══════════════════════════════════════════════════════════════════════════════

from cmpt.services.models import (
    # Request/Response
    ChainRequest, ChainRequestOverrides, ChainResponse,
    # Context Builder
    CompanyInfo, TemporalContext, PersonaInfo, ContextBuilderInput, ContextBuilderOutput,
    # Content Prioritization
    DataSource, Priority, PrioritizedSource, Subquery, ContentPrioritizationInput, ContentPrioritizationOutput,
    # Response Builder
    ResponseBuilderInput, ResponseBuilderOutput,
    # LLM Schemas
    CitationDict, MetricWithCitation, FinancialMetricsResponse, StrategicAnalysisResponse,
)

# ═══════════════════════════════════════════════════════════════════════════════
#                    CMPT AGENTS
# ═══════════════════════════════════════════════════════════════════════════════

from cmpt.services.agents import (
    SECFilingAgent, EarningsAgent, NewsAgent,
    create_cmpt_agents, create_composite_agent,
)

# ═══════════════════════════════════════════════════════════════════════════════
#                    CMPT PROMPTS & UTILS
# ═══════════════════════════════════════════════════════════════════════════════

from cmpt.services.llm_prompts import (
    FINANCIAL_METRICS_PROMPT, FINANCIAL_METRICS_SYSTEM_PROMPT,
    STRATEGIC_ANALYSIS_PROMPT, STRATEGIC_ANALYSIS_SYSTEM_PROMPT,
    DATA_FOR_FINANCIAL_METRICS_PROMPT, DATA_FOR_STRATEGIC_ANALYSIS_PROMPT,
)
from cmpt.services.validation_utils import MetricsValidator


__all__ = [
    # From AgentOrchestrator
    "AgentResult", "BaseAgent", "CompositeAgent", "ResilientAgent",
    "ResilientAgentConfig", "ResilientCompositeAgent",
    "LLMGatewayClient", "OAuthTokenManager", "timed_lru_cache",
    # CMPT Services
    "ContextBuilderService", "ContentPrioritizationService", "ResponseBuilderService",
    # CMPT Agents
    "SECFilingAgent", "EarningsAgent", "NewsAgent", "create_cmpt_agents", "create_composite_agent",
    # CMPT Models
    "ChainRequest", "ChainRequestOverrides", "ChainResponse",
    "CompanyInfo", "TemporalContext", "PersonaInfo", "ContextBuilderInput", "ContextBuilderOutput",
    "DataSource", "Priority", "PrioritizedSource", "Subquery", "ContentPrioritizationInput", "ContentPrioritizationOutput",
    "ResponseBuilderInput", "ResponseBuilderOutput",
    "CitationDict", "MetricWithCitation", "FinancialMetricsResponse", "StrategicAnalysisResponse",
    # Config & Utils
    "ToolName", "MetricsValidator",
    # Prompts
    "FINANCIAL_METRICS_PROMPT", "FINANCIAL_METRICS_SYSTEM_PROMPT",
    "STRATEGIC_ANALYSIS_PROMPT", "STRATEGIC_ANALYSIS_SYSTEM_PROMPT",
    "DATA_FOR_FINANCIAL_METRICS_PROMPT", "DATA_FOR_STRATEGIC_ANALYSIS_PROMPT",
]
