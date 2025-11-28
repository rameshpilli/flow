
All code
151.33 KB •3,622 lines
•
Formatting may be inconsistent from source

---

# FlowForge: Client Meeting Prep Chain Server Architecture

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                    Aiden Banker (UI)                                │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         User Request                                                │
│  • Who are we meeting with?                                                         │
│  • When is the Meeting?                                                             │
│  • Who are attending?                                                               │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                           │
                                           ▼ (1)
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                     CLIENT MEETING PREP CHAIN SERVER                                │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  ┌──────────────────────┐    ┌─────────────────────────┐    ┌────────────────────┐  │
│  │   CONTEXT BUILDER    │    │CONTENT PRIORITIZATION   │    │ RESPONSE BUILDER & │  │
│  │                      │    │       ENGINE            │    │    GENERATOR       │  │
│  │                      │    │                         │    │                    │  │
│  │ • Customer Firm      │    │ • Temporal Source       │    │ • Agent Execution  │  │
│  │   Extractor          │    │   Prioritizer           │    │                    │  │
│  │                      │(2) │                         │(3) │ • Prompt Cache     │  │
│  │ • RBC Persona        │───▶│ • Subquery Engine       │───▶│   (deferred)       │  │
│  │   Extractor(deferred)│    │                         │    │                    │  │
│  │                      │    │ • Topic Ranker          │    │ • Prompt Builder   │  │
│  │ • Temporal Context   │    │   (deferred)            │    │                    │  │
│  │   Extractor          │    │                         │    │ • Response Builder │  │
│  │                      │    │ • Grid Config           │    │                    │  │
│  │ • Customer Persona   │    │                         │    │                    │  │
│  │   Extractor(deferred)│    │                         │    │                    │  │
│  └──────────────────────┘    └─────────────────────────┘    └─────────┬──────────┘  │
│                                                                        │ (5)        │
└────────────────────────────────────────────────────────────────────────┼────────────┘
                                                                         │
                         ┌───────────────────────────────────────────────┘
                         │ (4)
                         ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                  DATA AGENTS                                        │
├────────────────────┬─────────────────────┬──────────────────────────────────────────┤
│    SEC Filing      │       News          │              Earnings                    │
│                    │                     │                                          │
│   >> RavenPack     │    >> RavenPack     │              FACTSET                     │
│                    │                     │                                          │
│ Last 8 quarters    │ 1 year (market cap) │              Latest                      │
│ (revenue),         │ 30 days (others)    │                                          │
│ Latest (Others)    │                     │                                          │
└────────────────────┴─────────────────────┴──────────────────────────────────────────┘
                                           │
                                           ▼ (6)
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                    Response                                         │
│                                  CMPT Content                                       │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow Sequence

1. **User Request → Context Builder**: User provides meeting details (client, date, attendees)
2. **Context Builder → Content Prioritization**: Extracted context flows to prioritization engine
3. **Content Prioritization → Response Builder**: Prioritized content with subqueries flows to generator
4. **Response Builder → Data Agents**: Agent execution queries external data sources
5. **Data Agents → Response Builder**: Retrieved data flows back for response building
6. **Response Builder → Response**: Final CMPT content returned to user

## Core Framework Requirements (FlowForge)

### 1. Agent Registration System
- Decorator-based registration (`@flowforge.agent`)
- Auto-discovery of agents
- Version management
- Health checks

### 2. DAG-Based Chain Orchestration
- Decorator-based flow definition (`@flowforge.chain`, `@flowforge.step`)
- Dependency resolution
- Parallel execution where possible
- Error propagation and handling

### 3. Context Management
- Shared context across chain steps
- Memory management for large outputs
- Summarization middleware (Phase 2)
- Token-aware context windowing

### 4. Data Source Connectors
- SEC Filing (RavenPack)
- News (RavenPack)
- Earnings (FACTSET)
- Extensible connector interface

### 5. Middleware Support
- Pre/Post processing hooks
- Logging and monitoring
- Rate limiting
- Caching

---

## FlowForge Framework Implementation

The FlowForge framework has been implemented with the following structure:

```
flowforge/
├── __init__.py              # Main exports
├── README.md                # Documentation
├── setup.py                 # Package setup
├── core/
│   ├── __init__.py
│   ├── forge.py             # Main FlowForge class
│   ├── decorators.py        # @agent, @step, @chain decorators
│   ├── context.py           # ChainContext & ContextManager
│   ├── registry.py          # Agent/Step/Chain registries
│   └── dag.py               # DAG execution engine
├── middleware/
│   ├── __init__.py
│   ├── base.py              # Middleware base class
│   ├── logger.py            # Logging middleware
│   ├── cache.py             # Caching middleware
│   ├── summarizer.py        # Context summarization (Phase 2)
│   └── token_manager.py     # Token budget management
├── agents/
│   ├── __init__.py
│   ├── base.py              # BaseAgent class
│   └── data_agents.py       # Pre-built SEC/News/Earnings agents
├── connectors/
│   ├── __init__.py
│   ├── base.py              # BaseConnector & HTTPConnector
│   └── mcp.py               # MCP server integration
└── utils/
    ├── __init__.py
    ├── timing.py            # Timing decorators
    └── retry.py             # Retry logic
```

### Quick Example - User Perspective

```python
from flowforge import FlowForge, ChainContext
from flowforge.middleware import LoggerMiddleware, CacheMiddleware
from flowforge.agents import BaseAgent, AgentResult

# Initialize FlowForge
forge = FlowForge(name="meeting_prep")
forge.use_middleware(LoggerMiddleware())
forge.use_middleware(CacheMiddleware(ttl_seconds=300))

# Register a custom agent
@forge.agent(name="my_data_source")
class MyDataAgent(BaseAgent):
    async def fetch(self, query: str, **kwargs) -> AgentResult:
        data = await my_api_call(query)
        return AgentResult(data=data, source="my_source", query=query)

# Register chain steps
@forge.step(name="extract_context", produces=["context"])
async def extract_context(ctx: ChainContext):
    ctx.set("context", {"company": ctx.get("company_name")})
    return {"context": ctx.get("context")}

@forge.step(name="fetch_data", dependencies=["extract_context"])
async def fetch_data(ctx: ChainContext):
    agent = forge.get_agent("my_data_source")
    result = await agent.fetch(ctx.get("context", {}).get("company", ""))
    ctx.set("data", result.data)
    return {"data": result.data}

@forge.step(name="build_response", dependencies=["fetch_data"])
async def build_response(ctx: ChainContext):
    return {"response": f"Data for {ctx.get('context')}"}

# Define and run chain
@forge.chain(name="my_pipeline")
class MyPipeline:
    steps = ["extract_context", "fetch_data", "build_response"]

# Execute
result = await forge.run("my_pipeline", initial_data={"company_name": "Apple"})
```

### Key Features Implemented

1. **Decorator-Based API**: Clean `@forge.agent()`, `@forge.step()`, `@forge.chain()` syntax
2. **Automatic DAG Resolution**: Dependencies are resolved and parallel execution happens automatically
3. **Context Management**: Scoped storage (step/chain/global), token tracking
4. **Middleware Pipeline**: Extensible hooks for logging, caching, summarization
5. **MCP Integration**: Connect external MCP servers as agents
6. **Extensibility**: Register custom agents, connectors, and middleware

### Examples Available

- `examples/quickstart.py` - Minimal getting started
- `examples/meeting_prep_chain.py` - Full CMPT chain implementation
- `examples/custom_agent_example.py` - Custom agent & MCP integration

---

src/api/endpoints/chain_server.py
"""
Chain Server Endpoint
Single unified endpoint that orchestrates all chain modules.
"""

import traceback
import os
import hashlib
from fastapi import APIRouter, HTTPException

from src.api.models.chain_models import (
    ChainServerRequest, ChainServerResponse

)
from typing import Dict, Any
from src.services.data_models.models  import ContextBuilderOutput, ContentPrioritizationOutput , ResponseBuilderOutput
from src.services.data_models.llm_schemas import FinancialMetricsResponse, StrategicAnalysisResponse
from src.services.context_builder_service import ContextBuilderService
from src.services.content_prioritization_service import ContentPrioritizationService
from src.services.response_builder_and_generator import ResponseBuilderAndGenerator
from src.services.chain_orchestrator import ChainOrchestrator



router = APIRouter()



@router.post("/chain-server", response_model=ChainServerResponse)
async def chain_server(request: ChainServerRequest) -> ChainServerResponse:
    """
    Unified chain server endpoint that orchestrates all modules based on the request.
    ...
    """
    try:
        response_dict_with_metadata = await ChainOrchestrator().execute_chain(request)
        return response_dict_with_metadata

    except Exception as e:
        tb = traceback.format_exc()
        print(f"Chain execution failed: {e}\n{tb}")
        raise HTTPException(
            status_code=500,
            detail=f"Chain execution failed: {e}\nTraceback:\n{tb}"
        )

@router.post("/context-builder", response_model=ContextBuilderOutput)
async def context_builder_test(request: ChainServerRequest):
    """
    Endpoint to test individual steps of ContextBuilderService.
    """

    context_builder_output = await ContextBuilderService.execute(request)

    return context_builder_output

@router.post("/content-prioritization", response_model=ContentPrioritizationOutput)
async def content_prioritization_test(request: ChainServerRequest):
    """
    Endpoint to test individual steps of ContentPrioritizationService.
    """
    context_builder_output = await ContextBuilderService.execute(request)
    
    content_prioritization_output = await ContentPrioritizationService.execute(context_builder_output) 

    return content_prioritization_output

@router.post("/response-builder", response_model=ResponseBuilderOutput)
async def response_builder_test(request: ChainServerRequest):
    
    
    context_builder_output = await ContextBuilderService.execute(request)
    
    content_prioritization_output = await ContentPrioritizationService.execute(context_builder_output)
    
    response_builder_output = await ResponseBuilderAndGenerator.execute(context_builder_output,content_prioritization_output)

    return response_builder_output

@router.post("/agent-subqueries", response_model=Dict[str, Any])
async def get_agent_subqueries(request: ChainServerRequest):
    context_builder_output = await ContextBuilderService.execute(request)
    content_prioritization_output = await ContentPrioritizationService.execute(context_builder_output)
    return content_prioritization_output.get('subqueries_from_engine')



src/api/models/chain_models.py

from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

class ChainServerRequest(BaseModel):
    """Unified request model for the chain-server endpoint"""
    
    corporate_client_email: Optional[str] = None
    corporate_client_names: Optional[str] = None
    rbc_employee_email: Optional[str] = None
    meeting_datetime: Optional[str] = None
    corporate_company_name: Optional[str] = None
    verbose: Optional[bool] = False




class ChainServerResponse(BaseModel):
    context_builder: Optional[Dict[str, Any]] = None
    content_prioritization: Optional[Dict[str, Any]] = None
    response_builder_and_generator: Optional[Dict[str, Any]] = None
    timings: Optional[Dict[str, float]] = None




src/config/configuration.py
"""The definition of the application configuration."""

import os
import logging
from typing import List

from src.config.configuration_wizard import ConfigWizard, configclass, configfield

_LOGGER = logging.getLogger(__name__)


@configclass
class GeneralConfig(ConfigWizard):
    name: str = configfield(
        "name",
        help_txt="The name of the application.",
    )
    description: str = configfield(
        "description",
        help_txt="A description of the application.",
    )
    mcp_name: str = configfield(
        "mcp_name",
        help_txt="The name of the MCP Server.",
    )

@configclass
class AgentConfig(ConfigWizard):
    """Configuration class for individual agent settings.

    :cvar agent_name: The name of the agent.
    :cvar agent_type: The type of the agent.
    :cvar agent_description: A description of the agent.
    :cvar agent_version: The version of the agent.
    :cvar agent_language: The language supported by the agent.
    """

    agent_name: str = configfield(
        "agent_name",
        help_txt="The name of the agent.",
    )
    agent_type: str = configfield(
        "agent_type",
        help_txt="The type of the agent.",
    )
    agent_description: str = configfield(
        "agent_description",
        help_txt="A description of the agent.",
    )
    agent_version: str = configfield(
        "agent_version",
        help_txt="The version of the agent.",
    )
    agent_language: str = configfield(
        "agent_language",
        help_txt="The language supported by the agent.",
    )
    compass_index_name: str = configfield(
        "compass_index_name",
        help_txt="The name of the Compass index.",
    )
    compass_index_prefix: str = configfield(
        "compass_index_prefix",
        help_txt="The prefix for the Compass index.",
    )
    compass_index_suffix: str = configfield(
        "compass_index_suffix",
        help_txt="The suffix for the Compass index.",
    )


@configclass
class AgentsConfig(ConfigWizard):
    """Configuration class for the agents.

    :cvar agents: A list of agent configurations.
    """

    agents: List[AgentConfig] = configfield(
        "agents", help_txt="A list of agent configurations.", default=""
    )


@configclass
class DatabricksConfig(ConfigWizard):
    """Configuration class for Databricks connection.

    :cvar host: The host URL of the Databricks workspace.
    :cvar token: The personal access token for authentication.
    :cvar cluster_id: The ID of the Databricks cluster.
    :cvar catalog_name: The name of the catalog in Databricks.
    :cvar schema_name: The name of the schema in Databricks.
    :cvar table_name: The name of the table in Databricks.
    :cvar volume_name: The name of the volume in Databricks.
    :cvar local_folder: The local folder path for temporary storage.
    """

    host: str = configfield(
        "host",
        help_txt="The host URL of the Databricks workspace.",
    )
    token: str = configfield(
        "token",
        help_txt="The personal access token for authentication.",
    )
    cluster_id: str = configfield(
        "cluster_id",
        help_txt="The ID of the Databricks cluster.",
    )
    catalog_name: str = configfield(
        "catalog_name",
        help_txt="The name of the catalog in Databricks.",
    )
    schema_name: str = configfield(
        "schema_name",
        help_txt="The name of the schema in Databricks.",
    )
    table_name: str = configfield(
        "table_name",
        help_txt="The name of the table in Databricks.",
    )
    table_prefix: str = configfield(
        "table_name",
        help_txt="The name of the table in Databricks.",
    )

    volume_name: str = configfield(
        "volume_name",
        help_txt="The name of the volume in Databricks.",
    )
    local_folder: str = configfield(
        "local_folder",
        help_txt="The local folder path for temporary storage.",
    )
    meta_file_name: str = configfield(
        "meta_file_name",
        help_txt="The metadata file name.",
    )
    http_path: str = configfield(
        "http_path",
        help_txt="The HTTP path for the Databricks SQL endpoint.",
    )



@configclass
class LLMChatModelConfig(ConfigWizard):
    """Configuration class for the model.

    :cvar model_name: The name of the huggingface model.
    :cvar model_engine: The server type of the hosted model.
    """

    model_name: str = configfield(
        "model_name",
        help_txt="The name of huggingface model.",
    )
    model_engine: str = configfield(
        "model_engine",
        help_txt="The server type of the hosted model. Allowed values are hugginface",
    )
    server_url: str = configfield(
        "server_url",
        help_txt="The url of the server hosting  model",
    )
    max_tokens: int = configfield(
        "max_tokens",
        help_txt="The max_tokens for model",
    )
    oauth_endpoint: str = configfield(
        "oauth_endpoint",
        help_txt="The url of the server oauth token genration",
    )
    client_id: str = configfield(
        "client_id",
        help_txt="The url of the server oauth client_id",
    )
    client_secret: str = configfield(
        "client_id",
        help_txt="The url of the server oauth client_secret",
    )
    temperature: float = configfield(
        "temperature",
        help_txt="The LLM Chat model temperature",
    )
    top_p: float = configfield(
        "top_p",
        help_txt="The LLM Chat model temperature",
    )


@configclass
class CohereConfig(ConfigWizard):
    model_engine: str = configfield(
        "model_engine",
        help_txt="The engine type for the Cohere model.",
    )
    api_url: str = configfield(
        "api_url",
        help_txt="The API URL for accessing the Cohere service.",
    )
    parser_url: str = configfield(
        "parser_url",
        help_txt="The URL for the Cohere parser service.",
    )
    user_token: str = configfield(
        "user_token",
        help_txt="The user token for authenticating with the Cohere service.",
    )
    parser_token: str = configfield(
        "parser_token",
        help_txt="The parser token for authenticating with the Cohere parser service.",
    )
    idx_prefix: str = configfield(
        "idx_prefix",
        help_txt="The prefix for the index.",
    )
    idx_sufix: str = configfield(
        "idx_sufix",
        help_txt="The sufix for the index.",
    )


@configclass
class DatabaseConfig(ConfigWizard):
    database: str = configfield(
        "database",
        help_txt="The database to connect to the Snowflake database.",
    )
    schema: str = configfield(
        "schema",
        help_txt="The database to connect to the Snowflake schema.",
    )
    query: str = configfield(
        "query",
        help_txt="The database to connect to the Snowflake query.",
    )
    chunking_column: str = configfield(
        "chunking_column",
        help_txt="The database to connect to the Snowflake query.",
    )


@configclass
class ChunkingConfig(ConfigWizard):
    chunk_engine: str = configfield(
        "chunk_engine",
        default="default_engine",
        help_txt="The engine to use for chunking.",
    )
    chunk_size: int = configfield(
        "chunk_size",
        default=1024,
        help_txt="Size of each chunk in bytes.",
    )
    chunk_overlap: int = configfield(
        "chunk_overlap",
        default=0,
        help_txt="Number of bytes to overlap between chunks.",
    )


@configclass
class SnowflakeConfig(ConfigWizard):
    """Configuration class for the Snowflake database.
    :cvar user: The username to connect to the Snowflake database.
    :cvar password: The password to connect to the Snowflake database.
    :cvar account: The account to connect to the Snowflake database.
    :cvar host: The host to connect to the Snowflake database.
    :cvar warehouse: The warehouse to connect to the Snowflake database.
    :cvar database: The database to connect to the Snowflake database.
    :cvar schema: The schema to connect to the Snowflake database.
    """

    account: str = configfield(
        "account",
        help_txt="The account to connect to the Snowflake database.",
    )
    host: str = configfield(
        "host",
        help_txt="The host to connect to the Snowflake database.",
    )
    warehouse: str = configfield(
        "warehouse",
        help_txt="The warehouse to connect to the Snowflake database.",
    )
    user: str = configfield(
        "user",
        help_txt="The username to connect to the Snowflake database.",
    )
    password: str = configfield(
        "password",
        help_txt="The password to connect to the Snowflake database.",
    )

    role: str = configfield(
        "role",
        help_txt="The role to connect to the Snowflake database.",
    )

    database: str = configfield(
        "database",
        help_txt="The database to connect to the Snowflake database.",
    )

    schema: str = configfield(
        "schema",
        help_txt="The schema to connect to the Snowflake database.",
    )

    tables: List[str] = configfield(
        "tables",
        help_txt="A list of tables to include in the connection.",
    )

@configclass
class Auth(ConfigWizard):
    mcp_server_secret: str = configfield(
        "mcp_server_secret",
        help_txt="The secret key for the MCP server.",
    )


@configclass
class AppConfig(ConfigWizard):
    """Configuration class for the application.

    :cvar triton: The configuration of the chat
    :type triton: ChatConfig
    :cvar model: The configuration of the model
    :type triton: ModelConfig
    """

    app: GeneralConfig = configfield(
        "app",
        env=False,
        help_txt="The general configuration."
    )
    snowflake: SnowflakeConfig = configfield(
        "snowflake",
        env=False,
        help_txt="The configuration of snowflake."
    )
    llm_chat_model: LLMChatModelConfig = configfield(
        "llm_chat_model",
        env=False,
        help_txt="The configuration of the model.",
    )
    cohere_compass: CohereConfig = configfield(
        "cohere_compass",
        env=False,
        help_txt="The configuration of the cohere compass.",
    )
    databricks: DatabricksConfig = configfield(
        "databricks",
        env=False,
        help_txt="The configuration of the Databricks connection.",
    )
    auth: Auth = configfield(
        "auth",
        env=False,
        help_txt="The configuration of the authentication.",
    )
    rag_agents: AgentsConfig = configfield(
        "rag_agents",
        env=False,
        help_txt="The configuration of the agents.",
        default=AgentsConfig(),
    )
    chunking: ChunkingConfig = configfield(
        "chunking",
        env=False,
        help_txt="The configuration of the chunking engine.",
        default=ChunkingConfig(),
    )
    


# Test the above code
def get_config() -> AppConfig:
    """Parse the application configuration."""
    # _LOGGER.info("config working dir", str(os.getcwd()))
    config_file = os.environ.get("APP_CONFIG_FILE", "")
    assert config_file is not None, "APP_CONFIG_FILE environment variable is not set."
    assert os.path.exists(config_file), (
        f"Configuration file {config_file} does not exist."
    )
    config = AppConfig.from_file(config_file)
    _LOGGER.debug("config file read successfull", config)
    if config:
        return config
    raise RuntimeError("Unable to find configuration.")


# Create a config variable for easy access
app_config = get_config()

## Test the above code
if __name__ == "__main__":
    print(app_config.auth.envvars())
    logging.basicConfig(level=logging.INFO)
    # Example usage
    try:
        app_config = get_config()
        print(app_config.chunking)
    except Exception as e:
        logging.error(f"An error occurred: {e}")


src/config/configuration_wizard.py

"""A module containing utilities for defining application configuration.

This module provides a configuration wizard class that can read configuration data from YAML, JSON, and environment
variables. The configuration wizard is based heavily off of the JSON and YAML wizards from the `dataclass-wizard`
Python package. That package is in-turn based heavily off of the built-in `dataclass` module.

This module adds Environment Variable parsing to config file reading.
"""
# pylint: disable=too-many-lines; this file is meant to be portable between projects so everything is put into one file
import json
import logging
import os
from dataclasses import _MISSING_TYPE, dataclass
from typing import Any, Callable, Dict, List, Optional, TextIO, Tuple, Union

import yaml
from dataclass_wizard import (
    JSONWizard,
    LoadMeta,
    YAMLWizard,
    errors,
    fromdict,
    json_field,
)
from dataclass_wizard.models import JSONField
from dataclass_wizard.utils.string_conv import to_camel_case

configclass = dataclass(frozen=True)
ENV_BASE = "APP"
_LOGGER = logging.getLogger(__name__)


def configfield(name: str, *, env: bool = True, help_txt: str = "", **kwargs: Any) -> JSONField:
    """Create a data class field with the specified name in JSON format.

    :param name: The name of the field.
    :type name: str
    :param env: Whether this field should be configurable from an environment variable.
    :type env: bool
    :param help_txt: The description of this field that is used in help docs.
    :type help_txt: str
    :param kwargs: Optional keyword arguments to customize the JSON field. More information here:
                     https://dataclass-wizard.readthedocs.io/en/latest/dataclass_wizard.html#dataclass_wizard.json_field
    :type kwargs: Any
    :returns: A JSONField instance with the specified name and optional parameters.
    :rtype: JSONField

    :raises TypeError: If the provided name is not a string.
    """
    # sanitize specified name
    if not isinstance(name, str):
        raise TypeError("Provided name must be a string.")
    json_name = to_camel_case(name)

    # update metadata
    meta = kwargs.get("metadata", {})
    meta["env"] = env
    meta["help"] = help_txt
    kwargs["metadata"] = meta

    # create the data class field
    field = json_field(json_name, **kwargs)
    return field


class _Color:
    """A collection of colors used when writing output to the shell."""

    # pylint: disable=too-few-public-methods; this class does not require methods.

    PURPLE = "\033[95m"
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    END = "\033[0m"


class ConfigWizard(JSONWizard, YAMLWizard):  # type: ignore[misc] # dataclass-wizard doesn't provide stubs
    """A configuration wizard class that can read configuration data from YAML, JSON, and environment variables."""

    # pylint: disable=arguments-differ,arguments-renamed; this class intentionally reduces arguments for some methods.

    @classmethod
    def print_help(
        cls,
        help_printer: Callable[[str], Any],
        *,
        env_parent: Optional[str] = None,
        json_parent: Optional[Tuple[str, ...]] = None,
    ) -> None:
        """Print the help documentation for the application configuration with the provided `write` function.

        :param help_printer: The `write` function that will be used to output the data.
        :param help_printer: Callable[[str], None]
        :param env_parent: The name of the parent environment variable. Leave blank, used for recursion.
        :type env_parent: Optional[str]
        :param json_parent: The name of the parent JSON key. Leave blank, used for recursion.
        :type json_parent: Optional[Tuple[str, ...]]
        """
        if not env_parent:
            env_parent = ""
            help_printer("---\n")
        if not json_parent:
            json_parent = ()

        for (
                _,
                val,
        ) in (cls.__dataclass_fields__.items()  # pylint: disable=no-member; false positive
              ):  # pylint: disable=no-member; member is added by dataclass.
            jsonname = val.json.keys[0]
            envname = jsonname.upper()
            full_envname = f"{ENV_BASE}{env_parent}_{envname}"
            is_embedded_config = hasattr(val.type, "envvars")

            # print the help data
            indent = len(json_parent) * 2
            if is_embedded_config:
                default = ""
            elif not isinstance(val.default_factory, _MISSING_TYPE):
                default = val.default_factory()
            elif isinstance(val.default, _MISSING_TYPE):
                default = "NO-DEFAULT-VALUE"
            else:
                default = val.default
            help_printer(f"{_Color.BOLD}{' ' * indent}{jsonname}:{_Color.END} {default}\n")

            # print comments
            if is_embedded_config:
                indent += 2
            if val.metadata.get("help"):
                help_printer(f"{' ' * indent}# {val.metadata['help']}\n")
            if not is_embedded_config:
                typestr = getattr(val.type, "__name__", None) or str(val.type).replace("typing.", "")
                help_printer(f"{' ' * indent}# Type: {typestr}\n")
            if val.metadata.get("env", True):
                help_printer(f"{' ' * indent}# ENV Variable: {full_envname}\n")
            # if not is_embedded_config:
            help_printer("\n")

            if is_embedded_config:
                new_env_parent = f"{env_parent}_{envname}"
                new_json_parent = json_parent + (jsonname, )
                val.type.print_help(help_printer, env_parent=new_env_parent, json_parent=new_json_parent)

        help_printer("\n")

    @classmethod
    def envvars(
        cls,
        env_parent: Optional[str] = None,
        json_parent: Optional[Tuple[str, ...]] = None,
    ) -> List[Tuple[str, Tuple[str, ...], type]]:
        """Calculate valid environment variables and their config structure location.

        :param env_parent: The name of the parent environment variable.
        :type env_parent: Optional[str]
        :param json_parent: The name of the parent JSON key.
        :type json_parent: Optional[Tuple[str, ...]]
        :returns: A list of tuples with one item per configuration value. Each item will have the environment variable,
                  a tuple to the path in configuration, and they type of the value.
        :rtype: List[Tuple[str, Tuple[str, ...], type]]
        """
        if not env_parent:
            env_parent = ""
        if not json_parent:
            json_parent = ()
        output = []

        for (
                _,
                val,
        ) in (cls.__dataclass_fields__.items()  # pylint: disable=no-member; false positive
              ):  # pylint: disable=no-member; member is added by dataclass.
            jsonname = val.json.keys[0]
            envname = jsonname.upper()
            full_envname = f"{ENV_BASE}{env_parent}_{envname}"
            is_embedded_config = hasattr(val.type, "envvars")

            # add entry to output list
            if is_embedded_config:
                new_env_parent = f"{env_parent}_{envname}"
                new_json_parent = json_parent + (jsonname, )
                output += val.type.envvars(env_parent=new_env_parent, json_parent=new_json_parent)
            elif val.metadata.get("env", True):
                output += [(full_envname, json_parent + (jsonname, ), val.type)]

        return output

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConfigWizard":
        """Create a ConfigWizard instance from a dictionary.

        :param data: The dictionary containing the configuration data.
        :type data: Dict[str, Any]
        :returns: A ConfigWizard instance created from the input dictionary.
        :rtype: ConfigWizard

        :raises RuntimeError: If the configuration data is not a dictionary.
        """
        # sanitize data
        if not data:
            data = {}
        if not isinstance(data, dict):
            raise RuntimeError("Configuration data is not a dictionary.")

        # parse env variables
        for envvar in cls.envvars():
            var_name, conf_path, var_type = envvar
            var_value = os.environ.get(var_name)
            if var_value:
                var_value = try_json_load(var_value)
                update_dict(data, conf_path, var_value)
                _LOGGER.debug(
                    "Found EnvVar Config - %s:%s = %s",
                    var_name,
                    str(var_type),
                    repr(var_value),
                )

        LoadMeta(key_transform="CAMEL").bind_to(cls)
        return fromdict(cls, data)  # type: ignore[no-any-return] # dataclass-wizard doesn't provide stubs

    @classmethod
    def from_file(cls, filepath: str) -> Optional["ConfigWizard"]:
        """Load the application configuration from the specified file.

        The file must be either in JSON or YAML format.

        :returns: The fully processed configuration file contents. If the file was unreadable, None will be returned.
        :rtype: Optional["ConfigWizard"]
        """
        # open the file
        try:
            # pylint: disable-next=consider-using-with; using a with would make exception handling even more ugly
            file = open(filepath, encoding="utf-8")
        except FileNotFoundError:
            _LOGGER.error("The configuration file cannot be found.")
            file = None
        except PermissionError:
            _LOGGER.error("Permission denied when trying to read the configuration file.")
            file = None
        if not file:
            return None

        # read the file
        try:
            data = read_json_or_yaml(file)
        except ValueError as err:
            _LOGGER.error(
                "Configuration file must be valid JSON or YAML. The following errors occured:\n%s",
                str(err),
            )
            data = None
            config = None
        finally:
            file.close()

        # parse the file
        if data:
            try:
                config = cls.from_dict(data)
            except errors.MissingFields as err:
                _LOGGER.error("Configuration is missing required fields: \n%s", str(err))
                config = None
            except errors.ParseError as err:
                _LOGGER.error("Invalid configuration value provided:\n%s", str(err))
                config = None
        else:
            config = cls.from_dict({})

        return config


def read_json_or_yaml(stream: TextIO) -> Dict[str, Any]:
    """Read a file without knowing if it is JSON or YAML formatted.

    The file will first be assumed to be JSON formatted. If this fails, an attempt to parse the file with the YAML
    parser will be made. If both of these fail, an exception will be raised that contains the exception strings returned
    by both the parsers.

    :param stream: An IO stream that allows seeking.
    :type stream: typing.TextIO
    :returns: The parsed file contents.
    :rtype: typing.Dict[str, typing.Any]:
    :raises ValueError: If the IO stream is not seekable or if the file doesn't appear to be JSON or YAML formatted.
    """
    exceptions: Dict[str, Union[None, ValueError, yaml.error.YAMLError]] = {
        "JSON": None,
        "YAML": None,
    }
    data: Dict[str, Any]

    # ensure we can rewind the file
    if not stream.seekable():
        raise ValueError("The provided stream must be seekable.")

    # attempt to read json
    try:
        data = json.loads(stream.read())
    except ValueError as err:
        exceptions["JSON"] = err
    else:
        return data
    finally:
        stream.seek(0)

    # attempt to read yaml
    try:
        data = yaml.safe_load(stream.read())
    except (yaml.error.YAMLError, ValueError) as err:
        exceptions["YAML"] = err
    else:
        return data

    # neither json nor yaml
    err_msg = "\n\n".join([key + " Parser Errors:\n" + str(val) for key, val in exceptions.items()])
    raise ValueError(err_msg)


def try_json_load(value: str) -> Any:
    """Try parsing the value as JSON and silently ignore errors.

    :param value: The value on which a JSON load should be attempted.
    :type value: str
    :returns: Either the parsed JSON or the provided value.
    :rtype: typing.Any
    """
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def update_dict(
    data: Dict[str, Any],
    path: Tuple[str, ...],
    value: Any,
    overwrite: bool = False,
) -> None:
    """Update a dictionary with a new value at a given path.

    :param data: The dictionary to be updated.
    :type data: Dict[str, Any]
    :param path: The path to the key that should be updated.
    :type path: Tuple[str, ...]
    :param value: The new value to be set at the specified path.
    :type value: Any
    :param overwrite: If True, overwrite the existing value. Otherwise, don't update if the key already exists.
    :type overwrite: bool
    """
    end = len(path)
    target = data
    for idx, key in enumerate(path, 1):
        # on the last field in path, update the dict if necessary
        if idx == end:
            if overwrite or not target.get(key):
                target[key] = value
            return

        # verify the next hop exists
        if not target.get(key):
            target[key] = {}

        # if the next hop is not a dict, exit
        if not isinstance(target.get(key), dict):
            return

        # get next hop
        target = target.get(key)  # type: ignore[assignment] # type has already been enforced.


src/utils/utils.py
import datetime
import logging
import os
import time
from functools import lru_cache, wraps


import functools
import time
import logging


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def timed_lru_cache(seconds:int ,maxsize:int =1):
    def wrapped_cache(func):
        func = lru_cache(maxsize=maxsize)(func)
        func.lifetime=datetime.timedelta(seconds=seconds)
        func.expiration = datetime.datetime.now() + func.lifetime

        @wraps(func)
        def wrapped_func(*args, **kwargs):
            if datetime.datetime.now() > func.expiration:
                logger.info(
                    "Cache expired for function '%s'. Clearing cache. New expiration: %s",
                    func.__name__,
                    (datetime.datetime.now() + func.lifetime).strftime("%Y-%m-%d %H:%M:%S")
                )
                func.cache_clear()
                func.expiration = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
            return func(*args, **kwargs)
        return wrapped_func

    return wrapped_cache

def time_it(func):
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        start_datetime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start_time))
        end_datetime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(end_time))
        logger.info(
            f"Execution time for {func.__name__}: {end_time - start_time:.2f} seconds"
        )
        logger.info(f"Start time: {start_datetime}, End time: {end_datetime}")
        return result

    return wrapper



logger = logging.getLogger(__name__)

def async_time_it(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = await func(*args, **kwargs)
        elapsed = time.perf_counter() - start_time
        logger.info(f"Execution time for {func.__name__}: {elapsed:.2f} seconds")
        return result, elapsed
    return wrapper


src/utils/validation_utils.py
"""
Validation utilities for LLM-extracted financial metrics.
Provides functions to verify that extracted data is grounded in source documents.
"""
import re
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class MetricsValidator:
    """Validates extracted financial metrics against source chunks"""
    
    @staticmethod
    def validate_financial_metrics(
        metrics: Any,  # FinancialMetricsResponse object
        source_chunks: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Validate extracted financial metrics against source chunks.
        
        Args:
            metrics: FinancialMetricsResponse object with extracted data
            source_chunks: Dictionary with agent names as keys and combined content as values
                          e.g., {"news_tool": "...", "earnings_tool": "...", "sec_tool": "..."}
        
        Returns:
            Dictionary with validation results including:
            - validation_summary: Overall stats
            - field_validations: Per-field validation results
            - warnings: List of validation warnings
        """
        validation_results = {
            "validation_summary": {
                "total_fields_checked": 0,
                "fields_with_values": 0,
                "fields_with_sources": 0,
                "sources_verified": 0,
                "sources_not_found": 0,
                "warnings_count": 0
            },
            "field_validations": {},
            "warnings": []
        }
        
        # Combine all source chunks into one searchable text
        all_sources = "\n\n".join(source_chunks.values())
        
        # Critical fields that require source validation
        critical_fields = [
            ("current_annual_revenue", "current_annual_revenue_citation"),
            ("current_annual_revenue_yoy_change", "current_annual_revenue_yoy_change_citation"),
            ("estimated_annual_revenue_next_year", "estimated_annual_revenue_next_year_citation"),
            ("ebitda_margin", "ebitda_margin_citation"),
            ("ebitda_margin_yoy_change", "ebitda_margin_yoy_change_citation"),
            ("stock_price", "stock_price_citation"),
            ("stock_price_yoy_change", "stock_price_yoy_change_citation"),
            ("market_cap", "market_cap_citation"),
            ("revenue_growth_trajectory", "revenue_growth_trajectory_citation")
        ]
        
        for value_field, citation_field in critical_fields:
            validation_results["validation_summary"]["total_fields_checked"] += 1
            
            field_value = getattr(metrics, value_field, None)
            citation = getattr(metrics, citation_field, None)
            
            field_validation = {
                "has_value": field_value is not None,
                "has_citation": citation is not None,
                "citation_verified": False,
                "extracted_numbers": [],
                "issues": []
            }
            
            # Check if field has a value
            if field_value is not None:
                validation_results["validation_summary"]["fields_with_values"] += 1
            
            # Check if citation dictionary is provided
            if citation is not None:
                validation_results["validation_summary"]["fields_with_sources"] += 1
                
                # Handle both dict and Pydantic model
                if isinstance(citation, dict):
                    source_agents = citation.get('source_agent', [])
                    source_contents = citation.get('source_content', [])
                    reasoning = citation.get('reasoning', '')
                elif hasattr(citation, 'source_agent'):  # Pydantic model
                    source_agents = citation.source_agent
                    source_contents = citation.source_content
                    reasoning = citation.reasoning
                else:
                    warning = f"{value_field}: Citation is not a dictionary or valid object"
                    validation_results["warnings"].append(warning)
                    field_validation["issues"].append("Citation is not a dictionary or valid object")
                    logger.warning(warning)
                    validation_results["field_validations"][value_field] = field_validation
                    continue
                
                # Validate citation has required fields
                if not source_agents or not source_contents or not reasoning:
                    warning = f"{value_field}: Citation missing required fields (source_agent, source_content, reasoning)"
                    validation_results["warnings"].append(warning)
                    field_validation["issues"].append("Citation missing required fields")
                    logger.warning(warning)
                else:
                    # Validate source_agent references
                    verified_agents = 0
                    for agent in source_agents:
                        if agent in source_chunks:
                            verified_agents += 1
                        else:
                            warning = f"{value_field}: Referenced agent '{agent}' not in source_chunks"
                            validation_results["warnings"].append(warning)
                            field_validation["issues"].append(f"Agent '{agent}' not found")
                            logger.warning(warning)
                    
                    # Validate source_content quotes
                    verified_quotes = 0
                    
                    for i, quote in enumerate(source_contents):
                        # Determine which agent to check
                        agent_name = source_agents[i] if i < len(source_agents) else (source_agents[0] if source_agents else None)
                        
                        if agent_name and agent_name in source_chunks:
                            agent_content = source_chunks[agent_name]
                            
                            # Check if quote exists in agent content
                            if MetricsValidator._verify_citation_in_sources(quote, agent_content):
                                verified_quotes += 1
                            else:
                                warning = f"{value_field}: Quote #{i+1} not found in {agent_name} content"
                                validation_results["warnings"].append(warning)
                                field_validation["issues"].append(f"Quote #{i+1} not found in {agent_name}")
                                logger.warning(warning)
                        else:
                            warning = f"{value_field}: No agent specified for quote #{i+1}"
                            validation_results["warnings"].append(warning)
                            field_validation["issues"].append(f"No agent for quote #{i+1}")
                            logger.warning(warning)
                    
                    # Mark as verified if all agents and quotes are valid
                    if verified_agents == len(source_agents) and verified_quotes == len(source_contents) and verified_quotes > 0:
                        validation_results["validation_summary"]["sources_verified"] += 1
                        field_validation["citation_verified"] = True
                    else:
                        validation_results["validation_summary"]["sources_not_found"] += 1
                    
                    # Extract numbers from reasoning and source content
                    all_citation_text = reasoning + ' ' + ' '.join(source_contents)
                    numbers = MetricsValidator._extract_numbers_from_text(all_citation_text)
                    field_validation["extracted_numbers"] = numbers
                    
                    # For calculated fields, verify value appears in reasoning
                    if field_value is not None and reasoning:
                        # Handle both float values and dictionary values (like revenue_growth_trajectory)
                        if isinstance(field_value, dict):
                            # For dictionaries, check if any of the values appear in reasoning
                            dict_values = [str(v) for v in field_value.values() if v is not None]
                            reasoning_contains_value = any(val in reasoning for val in dict_values)
                            
                            if not reasoning_contains_value and dict_values:
                                warning = f"{value_field}: Dictionary values {dict_values[:3]} not found in citation reasoning"
                                validation_results["warnings"].append(warning)
                                field_validation["issues"].append(f"Dictionary values not in reasoning")
                                logger.warning(warning)
                        
                        elif isinstance(field_value, (int, float)):
                            # For numeric values, check various formatting variations
                            value_str = f"{field_value:.1f}" if isinstance(field_value, float) else str(field_value)
                            value_variations = [
                                value_str,
                                f"{field_value:.2f}" if isinstance(field_value, float) else str(field_value),
                                f"{field_value:.3f}" if isinstance(field_value, float) else str(field_value),
                                f"{field_value:,.1f}" if isinstance(field_value, float) else str(field_value),  # With commas: 1,114.4
                                f"${value_str}",
                                f"${field_value:,.1f}B" if isinstance(field_value, float) else f"${field_value}B",  # $1,114.4B
                                str(field_value)
                            ]
                            
                            reasoning_contains_value = any(var in reasoning for var in value_variations)
                            if not reasoning_contains_value:
                                warning = f"{value_field}: Value {field_value} not found in citation reasoning"
                                validation_results["warnings"].append(warning)
                                field_validation["issues"].append(f"Value {field_value} not in reasoning")
                                logger.warning(warning)
            else:
                # Has value but no citation
                if field_value is not None:
                    warning = f"{value_field}: Has value ({field_value}) but missing citation"
                    validation_results["warnings"].append(warning)
                    field_validation["issues"].append("Missing citation for non-null value")
                    logger.warning(warning)
            
            validation_results["field_validations"][value_field] = field_validation
        
        # Additional sanity checks
        validation_results["sanity_checks"] = MetricsValidator._run_sanity_checks(metrics)
        
        # Update warnings count
        validation_results["validation_summary"]["warnings_count"] = len(validation_results["warnings"])
        
        return validation_results
    
    @staticmethod
    def _verify_citation_in_sources(citation: str, sources: str) -> bool:
        """Check if citation exists in sources with fuzzy matching AND exact number matching"""
        if not citation or not sources:
            return False
        
        # Step 1: Extract all numbers from citation and sources
        citation_numbers = MetricsValidator._extract_numbers_from_text(citation)
        sources_numbers = MetricsValidator._extract_numbers_from_text(sources)
        
        # Step 2: If citation has numbers, ALL must exist in sources
        if citation_numbers:
            for num in citation_numbers:
                # Check if this exact number exists in sources (with small tolerance for floats)
                number_found = any(abs(num - src_num) < 0.01 for src_num in sources_numbers)
                
                if not number_found:
                    logger.warning(f"Number {num} from citation not found in sources")
                    return False
        
        # Step 3: Normalize whitespace and case
        citation_clean = ' '.join(citation.lower().strip().split())
        sources_clean = ' '.join(sources.lower().split())
        
        # Step 4: Try exact substring match (70% threshold)
        min_match_length = int(len(citation_clean) * 0.70)
        
        for i in range(len(citation_clean) - min_match_length + 1):
            substring = citation_clean[i:i + min_match_length]
            if substring in sources_clean:
                return True
        
        # Step 5: Fallback to word overlap (75% threshold)
        citation_words = set(citation_clean.split())
        sources_words = set(sources_clean.split())
        
        if len(citation_words) > 0:
            overlap = len(citation_words & sources_words) / len(citation_words)
            if overlap >= 0.75:
                return True  
        
        return False 
    
    @staticmethod
    def _extract_numbers_from_text(text: str) -> List[float]:
        """Extract all numbers from text (useful for debugging)"""
        # Pattern to match numbers with optional dollar signs, commas, and decimal points
        pattern = r'\$?\d+(?:,\d{3})*(?:\.\d+)?'
        matches = re.findall(pattern, text)
        
        numbers = []
        for match in matches:
            try:
                # Remove dollar signs and commas
                clean_number = match.replace('$', '').replace(',', '')
                numbers.append(float(clean_number))
            except ValueError:
                continue
        
        return numbers
    
    @staticmethod
    def _run_sanity_checks(metrics: Any) -> Dict[str, Any]:
        """Run sanity checks on extracted metrics"""
        checks = {
            "passed": [],
            "failed": [],
            "warnings": []
        }
        
        # Check 1: Revenue should be positive
        if metrics.current_annual_revenue is not None:
            if metrics.current_annual_revenue > 0:
                checks["passed"].append("Revenue is positive")
            else:
                checks["failed"].append(f"Revenue is non-positive: {metrics.current_annual_revenue}")
        
        # Check 2: EBITDA margin should be between -100 and 100
        if metrics.ebitda_margin is not None:
            if -100 <= metrics.ebitda_margin <= 100:
                checks["passed"].append("EBITDA margin in reasonable range (-100% to 100%)")
            else:
                checks["failed"].append(f"EBITDA margin out of range: {metrics.ebitda_margin}%")
        
        # Check 3: Stock price should be positive
        if metrics.stock_price is not None:
            if metrics.stock_price > 0:
                checks["passed"].append("Stock price is positive")
            else:
                checks["failed"].append(f"Stock price is non-positive: {metrics.stock_price}")
        
        # Check 5: Date fields should be valid dates
        date_fields = ["current_annual_revenue_date", "estimated_annual_revenue_next_year_date", "market_cap_date"]
        for field_name in date_fields:
            date_value = getattr(metrics, field_name, None)
            if date_value:
                try:
                    datetime.strptime(date_value, "%Y-%m-%d")
                    checks["passed"].append(f"{field_name} is valid date format")
                except ValueError:
                    checks["failed"].append(f"{field_name} has invalid date format: {date_value}")
        
        return checks
    
    @staticmethod
    def print_validation_report(validation_results: Dict[str, Any]) -> None:
        """Pretty print validation results"""
        print("\n" + "="*80)
        print("FINANCIAL METRICS VALIDATION REPORT")
        print("="*80)
        
        summary = validation_results["validation_summary"]
        print(f"\n SUMMARY:")
        print(f"  Total fields checked: {summary['total_fields_checked']}")
        print(f"  Fields with values: {summary['fields_with_values']}")
        print(f"  Fields with source citations: {summary['fields_with_sources']}")
        print(f"  Citations verified in sources: {summary['sources_verified']}")
        print(f"  Citations NOT found: {summary['sources_not_found']}")
        print(f"  Total warnings: {summary['warnings_count']}")
        
        if validation_results["warnings"]:
            print(f"\n WARNINGS ({len(validation_results['warnings'])}):")
            for warning in validation_results["warnings"]:
                print(f"  - {warning}")
        
        print(f"\n🔍 FIELD-BY-FIELD VALIDATION:")
        for field_name, field_data in validation_results["field_validations"].items():
            status = "✓ Passed" if field_data["citation_verified"] else "✗ Failed"
            print(f"\n  {status} {field_name}:")
            print(f"      Has value: {field_data['has_value']}")
            print(f"      Has citation: {field_data['has_citation']}")
            print(f"      Citation verified: {field_data['citation_verified']}")
            if field_data["extracted_numbers"]:
                print(f"      Numbers in citation: {field_data['extracted_numbers'][:5]}")  # First 5
            if field_data["issues"]:
                print(f"      Issues: {', '.join(field_data['issues'])}")
        
        sanity = validation_results["sanity_checks"]
        print(f"\n✓ SANITY CHECKS:")
        print(f"  Passed: {len(sanity['passed'])}")
        print(f"  Failed: {len(sanity['failed'])}")
        print(f"  Warnings: {len(sanity['warnings'])}")
        
        if sanity["failed"]:
            print(f"\n  Failed checks:")
            for fail in sanity["failed"]:
                print(f"    - {fail}")
        
        if sanity["warnings"]:
            print(f"\n  Sanity warnings:")
            for warn in sanity["warnings"]:
                print(f"    - {warn}")
        
        print("\n" + "="*80 + "\n")


src/services/chain_orchestrator.py

import asyncio

from src.api.models.chain_models import (
    ChainServerRequest, 
    ChainServerResponse
)
from src.services.context_builder_service import ContextBuilderService
from src.services.content_prioritization_service import ContentPrioritizationService
from src.services.response_builder_and_generator import ResponseBuilderAndGenerator


import time
import logging
logger = logging.getLogger("chain_orchestrator")

class ChainOrchestrator:
    """Orchestrates the execution of all chain modules"""


    async def execute_chain(self, request: ChainServerRequest) -> ChainServerResponse:
        total_start = time.perf_counter()
        try:
            # Step 1: Execute Context Builder
            logger.info("Executing Context Builder...")
            context_builder_output = await ContextBuilderService.execute(request)
            if context_builder_output.get("errors"):
                logger.warning(f"Context Builder errors: {context_builder_output['errors']}")

            # Step 2: Execute Content Prioritization
            logger.info("Executing Content Prioritization...")
            content_prioritization_output = await ContentPrioritizationService.execute(context_builder_output)
            if content_prioritization_output.get("errors"):
                logger.warning(f"\n\n Content Prioritization errors: {content_prioritization_output['errors']} \n\n")

            # Step 3: Execute Response Builder and Generator
            logger.info("Executing Response Builder and Generator...")
            response_builder_output = await ResponseBuilderAndGenerator.execute(context_builder_output, content_prioritization_output)
            if response_builder_output.get("errors"):
                logger.warning(f"Response Builder errors: {response_builder_output['errors']}")

            total_time = time.perf_counter() - total_start

            # Build final response
            response_dic = {
                "context_builder": {
                    "corporate_client_firm_response_raw": context_builder_output.get("corporate_client_firm_response_raw"),
                    "corporate_client_firm_response": context_builder_output.get("corporate_client_firm_response"),
                    "temporal_content_response_raw": context_builder_output.get("temporal_content_response_raw"),
                    "temporal_content_response": context_builder_output.get("temporal_content_response"),
                    "rbc_persona": context_builder_output.get("rbc_persona"),
                    "corporate_client_persona": context_builder_output.get("corporate_client_persona"),
                    "timings": context_builder_output.get("timings", {}),
                    "errors": context_builder_output.get("errors", {}),
                },
                "content_prioritization": {
                    "temporal_source_prioritizer": content_prioritization_output.get("temporal_source_prioritizer"),
                    "subqueries_from_engine": content_prioritization_output.get("subqueries_from_engine"),
                    "topic_ranker_result": content_prioritization_output.get("topic_ranker_result"),
                    "timings": content_prioritization_output.get("timings", {}),
                    "errors": content_prioritization_output.get("errors", {}),
                },
                "response_builder_and_generator": {
                    "financial_metrics_result": response_builder_output.get("financial_metrics_result"),
                    "strategic_analysis_result": response_builder_output.get("strategic_analysis_result"),
                    "validation_results": response_builder_output.get("validation_results"),
                    "parsed_data_agent_chunks": response_builder_output.get("parsed_data_agent_chunks"),
                    "company_name": response_builder_output.get("company_name"),
                    "timings": response_builder_output.get("timings", {}),
                    "errors": response_builder_output.get("errors", {}),
                },
                "timings": {
                    "total_time": total_time
                }
            }

            return response_dic

        except Exception as e:
            logger.error(f"Chain execution failed: {e}", exc_info=True)
            raise

if __name__ == "__main__":
    request = ChainServerRequest(
            corporate_client_email="akinahan@k1ops.com",
            corporate_client_names="Allison Kinahan",
            rbc_employee_email="saqlain.shaik@sterbc.com",
            meeting_datetime="2025-10-30",
            corporate_company_name="BlackRock Inc.",
            #corporate_company_name="Tesla"
        )
    asyncio.run(ChainOrchestrator().execute_chain(request))


src/services/content_prioritization_service.py
"""
Content Prioritization Engine Service Module
Contains all the business logic from the content prioritization engine endpoints converted to service functions.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import json
from src.services.grid_config import GRID

from src.services.llm.client import get_openai_client
from src.utils.utils import async_time_it
from src.services.static_subquery_engine import StaticSubqueryEngine
from src.services.data_models.models  import ContextBuilderOutput, ContentPrioritizationOutput
from src.api.models.chain_models import ChainServerRequest
from src.utils.utils import async_time_it

import logging

logger = logging.getLogger(__name__)


class ContentPrioritizationService:
    """Service class containing all content prioritization functionality"""

    @staticmethod
    async def temporal_source_prioritizer(
        company_type: str,
        meeting_date: str, 
        max_earnings_event_date: Optional[str] = None
    ) -> tuple:
        error = None
        result = None
        rule_errors = []
        try:
            config = GRID
            earnings_proximity_weeks = config.get("earnings_proximity_weeks")
            window = earnings_proximity_weeks * 7  # days

            meeting_datetime = datetime.strptime(meeting_date, "%Y-%m-%d")
            max_earnings_event_datetime = None
            if max_earnings_event_date:
                max_earnings_event_datetime = datetime.strptime(max_earnings_event_date, "%Y-%m-%d")

            context = {
                "company_type": company_type,
                "meeting_date": meeting_datetime,
                "max_earnings_event_date": max_earnings_event_datetime,
                "window": window
            }
            
            prioritizer_config = config["temporal_source_prioritizer"]
            rules = prioritizer_config["rules"]
            priority_profiles = config["priority_profiles"]
            default_profile = prioritizer_config["default_profile"]
            result = priority_profiles[default_profile]
            
            for rule in rules:
                try:
                    condition = rule["condition"]
                    if callable(condition) and condition(context):
                        profile_name = rule["priority_profile"]
                        result = priority_profiles[profile_name]
                        return result, None
                except Exception as e:
                    msg = f"Error evaluating rule '{rule.get('name')}': {e}"
                    logger.warning(msg)
                    rule_errors.append(msg)
            
        except Exception as e:
            error = str(e)
            logger.error(f"Error in temporal_source_prioritizer: {error}", exc_info=True)
        
        # If there were rule errors, include them in the error output
        if rule_errors:
            error = {"rule_errors": rule_errors, "final_error": error}
        
        return result, error
    
    @staticmethod
    async def subquery_engine(company_name: str, fiscal_year: str, fiscal_quarter: str) -> tuple:
        """
        Generate subqueries for data agents.
        Returns (result, error) tuple.
        """
        error = None
        result = None
        try:
            result = StaticSubqueryEngine.get_subquery_arguments(company_name, fiscal_year, fiscal_quarter)
        except Exception as e:
            error = str(e)
            logger.error(f"Error in subquery_engine: {error}", exc_info=True)
            result = None
        
        return result, error

    @staticmethod
    async def topic_ranker(subqueries):
        """
        Given the content from various data agents that each of the above sub-queries would generate, 
        rank them based on topics of interest as defined in the grid
        """
        return {"content_prioritization_topics": GRID["content_prioritization_topics"]}
    
    @staticmethod
    async def execute(
        context_builder_output: ContextBuilderOutput
    ) -> ContentPrioritizationOutput:
        """
        Execute the full content prioritization pipeline.
        """
        timings = {}
        result = {}
        errors = {}

        meeting_date = context_builder_output["request_meeting_date"]
        
        corporate_client_firm_response = context_builder_output["corporate_client_firm_response"]
        if corporate_client_firm_response:
            company_type = corporate_client_firm_response.get("company_type")
            company_name = corporate_client_firm_response.get("company_name")
        else:
            company_type = "PUB"
            company_name = context_builder_output["request_company_name"]

        temporal_content_response = context_builder_output["temporal_content_response"]
        if temporal_content_response:
            event_dt = temporal_content_response["event_dt"]
            fiscal_year = temporal_content_response.get("fiscal_year")
            fiscal_quarter = temporal_content_response.get("fiscal_period")
        else:
            event_dt = meeting_date
            fiscal_year = str(int(meeting_date[:4]))
            month = int(meeting_date[5:7])
            fiscal_quarter = str((month - 1) // 3 + 1)
        
        # Step 1: Temporal source prioritizer
        (temporal_source_prioritizer, temporal_source_error), timings["temporal_source_prioritizer"] = await async_time_it(
            ContentPrioritizationService.temporal_source_prioritizer
        )(
            company_type=company_type,
            meeting_date=meeting_date,
            max_earnings_event_date=event_dt
        )
        if temporal_source_error:
            errors["temporal_source_prioritizer"] = temporal_source_error
        
        # Step 2: Subquery engine
        (subqueries_from_engine, subquery_engine_error), timings["subquery_engine"] = await async_time_it(
            ContentPrioritizationService.subquery_engine
        )(
            company_name=company_name,
            fiscal_year=fiscal_year,
            fiscal_quarter=fiscal_quarter
        )
        if subquery_engine_error:
            errors["subquery_engine"] = subquery_engine_error
        
        result["topic_ranker_result"] = None
        result["temporal_source_prioritizer"] = temporal_source_prioritizer
        result["subqueries_from_engine"] = subqueries_from_engine
        result["timings"] = timings
        result["errors"] = errors
        
        return result

if __name__ == "__main__":
    import asyncio

    async def main():
        print("Testing temporal_source_prioritizer V2...")
        try:
            # Test case 1: Public company with earnings in proximity
            raw = await ContentPrioritizationService.temporal_source_prioritizer(
                company_type="PUB",
                meeting_date="2025-11-01",
                max_earnings_event_date="2025-10-25"
            )
            print("Public with earnings nearby:", raw)
            
            # Test case 2: Public company without earnings in proximity
            raw = await ContentPrioritizationService.temporal_source_prioritizer(
                company_type="PUB",
                meeting_date="2025-11-01",
                max_earnings_event_date="2025-08-15"
            )
            print("Public without earnings nearby:", raw)
            
            # Test case 3: Private company
            raw = await ContentPrioritizationService.temporal_source_prioritizer(
                company_type="PRIV",
                meeting_date="2025-11-01",
                max_earnings_event_date=None
            )
            print("Private company:", raw)
            
        except Exception as e:
            print("Error:", e)

        print("\nTesting subquery_engine...")
        try:
            raw = await ContentPrioritizationService.subquery_engine(
                company_name="Tesla",
                meeting_date="2025-11-01"
            )
            print("RAW:", raw)
        except Exception as e:
            print("Error:", e)

    asyncio.run(main())


src/services/context_builder_service.py
"""
Context Builder Service Module
Contains all the business logic from the context builder endpoints converted to service functions.
"""

import httpx
from typing import Dict, Any, Optional
import logging
from datetime import datetime, timezone
from difflib import SequenceMatcher
import os 
from src.utils.utils import async_time_it
from src.services.ldap_service.lookup_service_interface import LookupServiceInterface
from src.services.ldap_service.ldap_search_strategy.ldap_email_strategy import LDAPEmailStrategy
from src.services.ldap_service.ldap_service import LDAPService
from src.services.ldap_service.zoom_info_service import ZoomInfoService
from src.services.grid_config import GRID
from src.services.data_models.models  import ContextBuilderOutput
from src.api.models.chain_models import ChainServerRequest
from src.utils.utils import async_time_it
import asyncio

logger = logging.getLogger(__name__)


class ContextBuilderService:
    """Service class containing all context builder functionality"""
    
    # Add timeout configuration
    HTTP_TIMEOUT = 20.0  # 20 seconds

    @staticmethod
    def rank_profiles_by_company(profiles: list, user_company: str) -> list:
        """
        Rank profiles by similarity to user's company name using simple text matching
        """
        if not profiles or not user_company:
            return profiles
            
        logger.info(f"Ranking {len(profiles)} profiles by similarity to company: {user_company}")
        
        for profile in profiles:
            company_from_profile = profile.get('company', '') or profile.get('department', '')
            
            if company_from_profile:
                # Simple text similarity using SequenceMatcher
                similarity = SequenceMatcher(None, user_company.lower(), company_from_profile.lower()).ratio()
                profile['company_similarity_score'] = similarity
                logger.debug(f"Profile {profile.get('name', 'N/A')}: '{company_from_profile}' vs '{user_company}' = {similarity:.3f}")
            else:
                profile['company_similarity_score'] = 0.0
                logger.debug(f"Profile {profile.get('name', 'N/A')}: No company info available")
        
        # Sort by similarity score (highest first)
        ranked_profiles = sorted(profiles, key=lambda x: x.get('company_similarity_score', 0), reverse=True)
        
        logger.info("Ranking results:")
        for i, profile in enumerate(ranked_profiles[:5]):  # Log top 5
            score = profile.get('company_similarity_score', 0)
            company = profile.get('company', '') or profile.get('department', '')
            logger.info(f"  {i+1}. {profile.get('name', 'N/A')} at {company} (score: {score:.3f})")
        
        return ranked_profiles


    @staticmethod
    def parse_temporal_content_extractor_response(response) -> tuple:
        """
        Parses the raw response from temporal_content_extractor.
        Returns (result, error) tuple.
        """
        error = None
        result = None

        if not response: return response, error
        try:
            if response and "result" in response:
                matches = response["result"]
                if matches and len(matches) > 0:
                    # Parse event_dt and find the latest
                    latest = None
                    latest_date = None
                    for match in matches:
                        event_dt_str = match.get("event_dt")
                        if event_dt_str:
                            try:
                                event_date = datetime.strptime(event_dt_str, "%Y-%m-%d").date()
                                if latest_date is None or event_date > latest_date:
                                    latest_date = event_date
                                    latest = match
                            except Exception:
                                continue
                    result = latest if latest else {}
                else:
                    result = {}
            else:
                result = {}
        except Exception as e:
            error = str(e)
            logger.error(f"Error in parse_temporal_content_extractor_response: {error}", exc_info=True)
            result = None
        return result, error
        

    @staticmethod
    async def temporal_content_extractor(
        company_name: Optional[str] = None, 
        ticker_symbol: Optional[str] = None
    ) -> tuple:
        """
        Accepts company name and ticker, sends a POST request to /company_earnings_calendar, and returns the response.
        Returns (result, error) tuple.
        """
        error = None
        result = None
        try:
            top_n = GRID.get("earnings_proximity_weeks")
            if not company_name and not ticker_symbol:
                raise ValueError("Either company_name or ticker_symbol must be provided.")
            
            url = os.environ.get('FOUNDATION_EARNING_CALENDAR_URL')
            payload = {"top_n": top_n}
            
            if company_name is not None:
                payload["company_name"] = company_name
            elif ticker_symbol is not None:
                payload["ticker_symbol"] = ticker_symbol
            
            headers = {"Content-Type": "application/json"}

            async with httpx.AsyncClient(verify=False, timeout=ContextBuilderService.HTTP_TIMEOUT) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                result = response.json()
        except Exception as e:
            error = str(e)
            logger.error(f"temporal_content_extractor error: {error}", exc_info=True)
            result = None

        return result, error

    @staticmethod
    async def rbc_persona_extractor(email: str) -> Dict[str, Any]:
        """
        Accepts an email ID, performs LDAP lookup using the local service, and returns the response.
        """
        try:
            # Initialize LDAP service with email strategy
            ldap_service: LookupServiceInterface = LDAPService(LDAPEmailStrategy())
            
            # Perform LDAP lookup
            ldap_info = ldap_service.lookup([email])
            
            if not ldap_info:
                raise ValueError(f"No LDAP info found for email: {email}")
            
            # Return the first result (since we're looking up a single email)
            return ldap_info[0]
            
        except Exception as e:
            raise ValueError(f"Error during LDAP lookup: {str(e)}")
        
    @staticmethod
    def parse_corporate_client_firm_extractor_response(response) -> tuple:
        """
        Parses the raw response from corporate_client_firm_extractor.
        Returns (result, error) tuple.
        """
        error = None
        result = None
        if not response: return response, error
        try:
            if response and "result" in response and "matches" in response["result"]:
                matches = response["result"]["matches"]
                if matches and len(matches) > 0:
                    result = matches[0]
                else:
                    result = {}
            else:
                result = {}
        except Exception as e:
            error = str(e)
            logger.error(f"Error in parse_corporate_client_firm_extractor_response: {error}", exc_info=True)
            result = {}
        return result, error
        
    @staticmethod
    async def corporate_client_firm_extractor(
        company_name: Optional[str] = None, 
        ticker_symbol: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Accepts a company name or ticker symbol, sends a POST request to /find_company_matches, and returns the response.
        Either company_name or ticker_symbol must be provided.
        Returns a dict with 'result' and 'error' keys.
        """
        error = None
        result = None
        try:
            if not company_name and not ticker_symbol:
                raise ValueError("Either company_name or ticker_symbol must be provided.")

            url = os.environ.get('FOUNDATION_COMPANY_MATCHES')
            payload = {}
            if company_name:
                payload["company_name"] = company_name
            if ticker_symbol:
                payload["ticker_symbol"] = ticker_symbol

            headers = {"Content-Type": "application/json"}

            async with httpx.AsyncClient(verify=False, timeout=ContextBuilderService.HTTP_TIMEOUT) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                result = response.json()
        except Exception as e:
            error = str(e)
            logger.error(f"corporate_client_firm_extractor error: {error}", exc_info=True)
            result = None

        return  result, error

    @staticmethod
    async def corporate_client_persona_extractor(email: str = None, names: str = None, company_name: str = None) -> Dict[str, Any]:
        """
        Extracts corporate client persona using ZoomInfo service.
        - Email search: Returns single result (no ranking needed)
        - Name search: Requires company_name, returns only the best match
        """
        if not email and not names:
            return {
                "data": {},
                "success": False,
                "message": "Either email or names must be provided"
            }
        
        # For name search, company_name is required
        if names and not company_name:
            return {
                "data": {},
                "success": False,
                "message": "Company name is required when searching by names"
            }
        
        zoom_service = ZoomInfoService()
        
        if email:
            # Email-based search - simple, single result expected
            try:
                profile_response = zoom_service.get_user_details_from_zoominfo(email=email)
                
                if profile_response.status_code != 200:
                    logger.warning(f"ZoomInfo API error for email {email}: {profile_response.status_code}")
                    return {
                        "data": {},
                        "success": False,
                        "message": f"ZoomInfo API error: {profile_response.status_code}"
                    }
                
                # Process the response
                response_data = profile_response.json()
                profiles = []
                
                if 'data' in response_data and isinstance(response_data['data'], list):
                    for raw_profile in response_data['data']:
                        # Convert to UserProfile format
                        processed_profile = {
                            'id': raw_profile.get('id', ''),
                            'name': f"{raw_profile.get('firstName', '')} {raw_profile.get('lastName', '')}".strip(),
                            'first_name': raw_profile.get('firstName', ''),
                            'last_name': raw_profile.get('lastName', ''),
                            'email': email,
                            'employeeId': '',
                            'intraId': str(raw_profile.get('id', '')),
                            'internal_flag': False,
                            'department': '',  # Keep empty - no department info from ZoomInfo
                            'division': '',
                            'role': raw_profile.get('jobTitle', ''),
                            'last_update_time': str(datetime.now(timezone.utc)),
                            'middle_name': raw_profile.get('middleName', ''),
                            'company': raw_profile.get('company', {}).get('name', '') if 'company' in raw_profile else '',  # Use company field
                            'company_id': raw_profile.get('company', {}).get('id', '') if 'company' in raw_profile else '',
                            'zoominfo_id': raw_profile.get('id', '')
                        }
                        profiles.append(processed_profile)
                
                return {
                    "data": profiles,
                    "success": True,
                    "search_type": "email_based",
                    "total_results": len(profiles),
                    "message": f"Found {len(profiles)} profile(s)" if profiles else "No profiles found"
                }
                
            except Exception as e:
                logger.error(f"Error during email-based ZoomInfo lookup: {str(e)}")
                return {
                    "data": {},
                    "success": False,
                    "message": f"Error during ZoomInfo lookup: {str(e)}"
                }
        
        elif names:
            # Name-based search - rank by company and return only the best match
            try:
                profile_data = zoom_service.lookup_by_names(names_string=names)
                
                if not profile_data or len(profile_data) == 0:
                    logger.warning(f"No ZoomInfo data found for names: {names}")
                    return {
                        "data": {},
                        "success": False,
                        "search_type": "name_based",
                        "company_filter": company_name,
                        "total_results": 0,
                        "message": f"No ZoomInfo data found for names: {names}"
                    }
                
                # Rank profiles by company similarity and get the best match
                logger.info(f"Ranking {len(profile_data)} profiles by company similarity to: {company_name}")
                ranked_profiles = ContextBuilderService.rank_profiles_by_company(profile_data, company_name)
                
                # Return only the top match
                best_match = ranked_profiles[0] if ranked_profiles else None
                
                if best_match:
                    logger.info(f"Best match: {best_match.get('name', 'N/A')} at {best_match.get('department', 'N/A')} (score: {best_match.get('company_similarity_score', 0):.3f})")
                
                return {
                    "data": best_match,
                    "search_type": "name_based",
                    "company_filter": company_name,
                    "best_match_score": best_match.get('company_similarity_score', 0) if best_match else 0,
                    "message": f"Found best match with similarity score {best_match.get('company_similarity_score', 0):.3f}" if best_match else "No suitable match found"
                }
                
            except Exception as e:
                logger.error(f"Error during name-based ZoomInfo lookup: {str(e)}")
                return {
                    "data": {},
                    "search_type": "name_based",
                    "company_filter": company_name,
                    "total_results": 0,
                    "message": f"Error during ZoomInfo lookup: {str(e)}"
    
                }

    @staticmethod
    async def execute(request: ChainServerRequest) -> ContextBuilderOutput:
        """
        Execute the full context builder pipeline.
        """
        timings = {}
        errors = {}

        # Step 1: Corporate client firm extractor
        (corporate_client_firm_response_raw, corporate_client_firm_error), timings["corporate_client_firm_extractor"] = await async_time_it(
            ContextBuilderService.corporate_client_firm_extractor
        )(company_name=request.corporate_company_name)
        if corporate_client_firm_error:
            errors["corporate_client_firm_extractor"] = corporate_client_firm_error

        # Step 2: Parse corporate client firm response
        corporate_client_firm_response, parse_corporate_client_firm_error = ContextBuilderService.parse_corporate_client_firm_extractor_response(
            corporate_client_firm_response_raw
        )
        if parse_corporate_client_firm_error:
            errors["parse_corporate_client_firm_extractor_response"] = parse_corporate_client_firm_error

        logger.info(f"\n\n\n Corporate Client Firm Response: {corporate_client_firm_response} \n\n\n")

        # Step 3: Temporal content extractor
        (temporal_content_response_raw, temporal_content_error), timings["temporal_content_extractor"] = await async_time_it(
            ContextBuilderService.temporal_content_extractor
        )(
            company_name=corporate_client_firm_response.get("company_name") if corporate_client_firm_response else None,
            ticker_symbol=corporate_client_firm_response.get("ticker_symbol") if corporate_client_firm_response else None
        )
        if temporal_content_error:
            errors["temporal_content_extractor"] = temporal_content_error

        # Step 4: Parse temporal content response
        t0 = asyncio.get_event_loop().time()
        temporal_content_response, parse_temporal_content_error = ContextBuilderService.parse_temporal_content_extractor_response(
            temporal_content_response_raw
        )
        timings["parse_temporal_content_extractor_response"] = asyncio.get_event_loop().time() - t0
        if parse_temporal_content_error:
            errors["parse_temporal_content_extractor_response"] = parse_temporal_content_error

        logger.info(f"\n\n\n Temporal Content Response: {temporal_content_response} \n\n\n")

        # Placeholder for persona extractors
        rbc_persona = False
        corporate_client_persona = False

        # Set result at the end
        result = {
            "corporate_client_firm_response_raw": corporate_client_firm_response_raw,
            "corporate_client_firm_response": corporate_client_firm_response,
            "temporal_content_response_raw": temporal_content_response_raw,
            "temporal_content_response": temporal_content_response,
            "rbc_persona": rbc_persona,
            "corporate_client_persona": corporate_client_persona,
            "request_meeting_date": request.meeting_datetime,
            "request_company_name": request.corporate_company_name,
            "timings": timings,
            "errors": errors,
        }

        return result

if __name__ == "__main__":
    import asyncio
    import os

    async def main():
        print("\n\nTesting corporate_client_firm_extractor...")
        try:
            raw = await ContextBuilderService.corporate_client_firm_extractor(
                company_name="Microsoft"
            )
            parsed = ContextBuilderService.parse_corporate_client_firm_extractor_response(raw)
            print("RAW:", raw)
            print("PARSED:", parsed)
        except Exception as e:
            print("Error:", e)

        print("\n\n Testing temporal_content_extractor...")
        try:
            raw = await ContextBuilderService.temporal_content_extractor(
                company_name="Microsoft Corp.",
                ticker_symbol="MSFT"
            )
            parsed = ContextBuilderService.parse_temporal_content_extractor_response(raw)
            print("RAW:", raw)
            print("PARSED:", parsed)
        except Exception as e:
            print("Error:", e)

    asyncio.run(main())

src/services/enums.py
from enum import Enum

class ToolName(Enum):
    EARNINGS_TOOL = "earnings_agent"
    NEWS_TOOL = "news_agent"
    SEC_TOOL = "SEC_agent"


src/services/grid_config.py
from src.services.enums import ToolName

GRID = {
    "earnings_proximity_weeks": 1,
    
    # Define priority profiles to avoid repetition
    "priority_profiles": {
        "earnings_dominant": {
            ToolName.EARNINGS_TOOL.value: 50,
            ToolName.NEWS_TOOL.value: 30,
            ToolName.SEC_TOOL.value: 20
        },
        "news_dominant": {
            ToolName.EARNINGS_TOOL.value: 20,
            ToolName.NEWS_TOOL.value: 60,
            ToolName.SEC_TOOL.value: 20
        }
    },
    
    # Rules reference the profiles
    "temporal_source_prioritizer": {
        "rules": [
            {
                "name": "non_public_company",
                "condition": lambda ctx: ctx["company_type"] not in ["PUB", "SUB"],
                "priority_profile": "news_dominant"
            },
            {
                "name": "earnings_proximity",
                "condition": lambda ctx: (
                    ctx["company_type"] in ["PUB", "SUB"] and
                    ctx.get("max_earnings_event_date") and
                    abs((ctx["max_earnings_event_date"] - ctx["meeting_date"]).days) <= ctx["window"]
                ),
                "priority_profile": "earnings_dominant"
            }
        ],
        "default_profile": "news_dominant"
    }
}



src/services/llm_prompts.py
DATA_FOR_FINANCIAL_METRICS_PROMPT = """
[SEC_AGENT]
Agent Guidance:
- Primary source for all financial metrics
- Extract precise numbers from financial statements
- Look for year-over-year comparisons in financial statements
{SEC_AGENT_CONTENT}

[EARNINGS_AGENT]
Agent Guidance:
- Use for forward guidance and quarterly commentary
- Extract YoY growth rates mentioned in management discussion
{EARNINGS_AGENT_CONTENT}

[NEWS_AGENT]
Agent Guidance:
- Extract current stock price and today's price movement if mentioned in recent articles
- Look for daily price changes (e.g., "stock up $1.39 or 0.56% today")
{NEWS_AGENT_CONTENT}
"""

DATA_FOR_STRATEGIC_ANALYSIS_PROMPT = """
[NEWS_AGENT]
Agent Guidance:
- Include {NEWS_percentage}% of the response from this agent chunks
- Extract date, category, and source URL for each development
{NEWS_AGENT_CONTENT}

[EARNINGS_AGENT]
Agent Guidance:
- Include {EARNINGS_percentage}% of the response from this agent chunks
{EARNINGS_AGENT_CONTENT}

[SEC_AGENT]
Agent Guidance:
- Include {SEC_percentage}% of the response from this agent chunks
"""

FINANCIAL_METRICS_PROMPT = """
## Task: Extract Financial Metrics

You are analyzing financial data for {COMPANY_NAME}. Extract precise financial metrics from SEC filings and earnings reports.

{DATA_FOR_FINANCIAL_METRICS}

## CRITICAL JSON FORMAT REQUIREMENT:
**For ALL numeric fields (float type):**
- Return actual numbers (e.g., 96.773, 25.5, 1.39) OR the JSON null value
- NEVER return strings like "<UNKNOWN>", "N/A", "null", "None", or any text placeholders
- If data is genuinely missing after exhausting all sources, return null (JSON null, not the string "null")

**Example - CORRECT:**
```json
{{
  "current_annual_revenue": 96.773,
  "ebitda_margin": null,
  "stock_price": 251.72
}}
```

**Example - WRONG (will cause errors):**
```json
{{
  "current_annual_revenue": "<UNKNOWN>",
  "ebitda_margin": "N/A",
  "stock_price": "null"
}}
```

## CRITICAL: Source Attribution (REQUIRED FOR VERIFICATION)
For ALL numeric fields, you MUST provide citations as dictionaries with these keys:
- **source_agent**: List of agent names (e.g., ["SEC_agent", "earnings_agent"])
- **source_content**: List of VERBATIM quotes from those agents (COPY-PASTE EXACTLY - DO NOT PARAPHRASE)
- **reasoning**: String explaining your extraction/calculation logic

**CRITICAL RULE FOR NULL VALUES:**
- If you return null for ANY numeric field, you MUST still provide a citation dictionary
- The citation MUST explain: (1) which specific sources you searched, (2) what keywords/sections you looked for, and (3) why data was unavailable
- Be SPECIFIC about what you searched: "Searched SEC 10-K 'Management Discussion' and 'Forward-Looking Statements' sections, earnings call transcript Q&A (pages 15-23), and 15 news articles from past 90 days. Found qualitative growth statements but no specific numerical revenue guidance for FY2026."
- DO NOT return citation as null - always provide a dictionary explaining your search process



**IMPORTANT CITATION RULES:**
1. **VERBATIM QUOTES ONLY**: Copy-paste the EXACT text from the source documents into source_content
   - CORRECT: "Total revenues were $25,182 million for the three months ended September 30, 2025"
   - WRONG: "Revenue was about $25 billion in Q3 2025" (paraphrased)
   
2. **QUOTE LENGTH**: Each quote should be 20-100 words (enough context to verify)
   - Too short: "Revenue: $25B" (not enough context)
   - Good: "During the three months ended September 30, 2025, total revenues were $25,182 million, compared to $23,350 million for the same period in 2024."

3. **SHOW YOUR WORK**: For calculated metrics (like EBITDA margin), include the actual calculation in reasoning
   - Must show: Formula + Numbers + Final result
   - Example: "EBITDA Margin = ($25.5B operating income + $2.1B D&A) / $96.8B revenue = 28.5%"
   - The final value MUST appear in the reasoning string

4. **STOCK PRICE**: Always include the date/timestamp in the quote
   - Correct: "On November 15, 2024, shares closed at $350.00"
   - Wrong:  "Stock price is $350" (no date)

**REQUIRED citation fields:**
- current_annual_revenue_citation
- current_annual_revenue_yoy_change_citation
- estimated_annual_revenue_next_year_citation
- ebitda_margin_citation
- ebitda_margin_yoy_change_citation
- stock_price_citation
- stock_price_yoy_change_citation
- market_cap_citation
- revenue_growth_trajectory_citation

**Format Example:**
```json
{{
  "current_annual_revenue": 96.773,
  "current_annual_revenue_citation": {{
    "source_agent": ["SEC_agent"],
    "source_content": [
      "Total revenues were $96,773 million for the twelve months ended September 30, 2025, compared to $81,462 million for the same period in 2024."
    ],
    "reasoning": "Extracted annual revenue from SEC 10-Q filing (Form 10-Q filed 2025-10-20). Used trailing twelve month (TTM) revenue of $96.773 billion."
  }},
  
  "ebitda_margin": 28.5,
  "ebitda_margin_citation": {{
    "source_agent": ["SEC_agent", "SEC_agent", "SEC_agent"],
    "source_content": [
      "Operating income was $25,500 million for the twelve months ended September 30, 2025.",
      "Depreciation and amortization expense was $2,100 million for the twelve months ended September 30, 2025.",
      "Total revenues were $96,773 million for the twelve months ended September 30, 2025."
    ],
    "reasoning": "Calculated EBITDA margin = ($25,500M operating income + $2,100M D&A) / $96,773M revenue = 28.5%. All components extracted from Form 10-Q Consolidated Statements."
  }},
  
  "stock_price": 350.0,
  "stock_price_citation": {{
    "source_agent": ["news_agent"],
    "source_content": [
      "Tesla shares closed at $350.00 on November 15, 2024, up $5.20 or 1.5% on the day, according to Bloomberg data."
    ],
    "reasoning": "Current stock price of $350.0 extracted from Bloomberg article dated November 15, 2024."
  }},
  
  "market_cap": 1114.4,
  "market_cap_citation": {{
    "source_agent": ["SEC_agent", "news_agent"],
    "source_content": [
      "Common stock outstanding: 3,183,666,092 shares as of September 30, 2025.",
      "Tesla shares closed at $350.00 on November 15, 2024."
    ],
    "reasoning": "Market cap = 3.184 billion shares × $350.00 per share = $1,114.4 billion."
  }}
}}
```

**IMPORTANT**: 
- source_agent: Use exact agent names from the data sources: "SEC_agent", "earnings_agent", "news_agent"
- source_content: Must be verbatim quotes (copy-paste) from agent content, not paraphrased
- reasoning: Explain where you found it and any calculations performed
- Each quote in source_content should map to the corresponding agent in source_agent (same index)
- If calculation spans multiple quotes, include all relevant quotes
- If you cannot find data in the provided documents, return null for BOTH the value AND the citation

## Extraction Guidelines:

**Revenue Metrics (REQUIRED - DO NOT SKIP):**
- Current annual revenue: Most recent 10-K or annualized 10-Q
- Next year estimate: Company guidance or extrapolate from growth trends
- **Year-over-year change**: Calculate or extract YoY % change in revenue (e.g., "+9% YoY")
  - Search for: "compared to prior year", "year-over-year", "% increase from"
  - Formula: ((Current Year Revenue - Prior Year Revenue) / Prior Year Revenue) × 100
  - **MUST provide current_annual_revenue_yoy_change_citation with BOTH current and prior year revenue quotes AND calculation**
- Always include exact source dates
- **MUST provide current_annual_revenue_citation with VERBATIM quotes and detailed reasoning**

**EBITDA Margin (REQUIRED - CALCULATE IF NEEDED):**
- First, search for explicit "EBITDA" in SEC_AGENT
- If not found, calculate: (Operating Income + Depreciation + Amortization) / Revenue × 100
- Search for "Operating Income", "D&A", "Depreciation", "Amortization" in financial statements
- **Year-over-year change**: Calculate YoY change in margin percentage points (e.g., "+1% YoY")
  - Formula: Current Period EBITDA Margin - Prior Period EBITDA Margin
  - **MUST provide ebitda_margin_yoy_change_citation with BOTH periods' calculations AND comparison**
- If components scattered across tables, extract and calculate manually
- **MUST provide ebitda_margin_citation showing calculation with all component VERBATIM quotes**
- **In reasoning, MUST show: EBITDA Margin = (Operating Income $X + D&A $Y) / Revenue $Z = [final value]%**
- **DO NOT return null unless absolutely no financial data exists**

**Stock Price (REQUIRED - MULTIPLE SOURCES):**
1. Check NEWS_AGENT for recent price mentions
2. Check SEC filing cover pages for "Class A Common Stock" price
3. Check EARNINGS_AGENT transcript for price references
4. **Today's price movement**: Extract daily change in both dollars and percentage
   - Look for: "stock up/down $X.XX", "gained/lost X%", "closed at $XXX, up $X.XX (X%)"
   - Example: "$251.72, up $1.39 (0.56%) today"
   - Extract both absolute dollar change AND percentage change
5. **Year-over-year change (stock_price_yoy_change)**: Compare to price from one year ago
   - **PRIORITY 1 (PREFERRED)**: Find explicit "stock price on [date one year ago] was $XXX"
   - **PRIORITY 2 (ACCEPTABLE)**: Use Year-to-Date (YTD) performance as YoY proxy
     - If article states "YTD +29.10%" and today is Nov 19, 2024, this compares Jan 1, 2024 to Nov 19, 2024
     - For practical purposes, YTD ≈ YoY when comparing similar dates (late in calendar year)
     - Formula: stock_price_yoy_change = YTD percentage (e.g., 29.10 for +29.10%)
     - In reasoning: "Used YTD performance (+29.10%) as YoY proxy. YTD compares Jan 1, 2024 to Nov 19, 2024, which approximates YoY comparison for late-year dates."
   - **PRIORITY 3 (FALLBACK)**: Calculate backwards from current price and YTD
     - Prior year price ≈ Current price / (1 + YTD%/100)
     - Example: $338.74 / 1.291 = $262.43 (approx price on Jan 1, 2024)
     - YoY ≈ YTD for practical purposes
   - **MUST provide stock_price_yoy_change_citation** explaining which method you used
   - **DO NOT return null if you have YTD data** - use it as a reasonable approximation
6. **MUST provide stock_price_citation with VERBATIM quote including date/timestamp**
7. **In reasoning, MUST include the exact date of the stock price (e.g., "Stock price of $350.0 as of November 15, 2024")**
8. **DO NOT return null for stock_price - extract from ANY available source**

**Market Cap (CALCULATE IF NEEDED):**
- Formula: Stock Price × Outstanding Shares
- Find "Outstanding Shares" in SEC_AGENT (search: "shares outstanding", "common stock outstanding")
- If you have stock price but not shares, search harder in SEC balance sheet
- **MUST provide market_cap_citation with quotes for BOTH stock price AND share count AND calculation**
- **DO NOT return null if you have either component**

## Revenue Growth Trajectory (REQUIRED)

**GOAL**: Build a dictionary of the last 7 quarterly revenues using fiscal quarter notation (e.g., "Q1 FY2026", "Q3 FY2025").

**DATA SOURCES**:
- 10-Q filings contain Q1, Q2, Q3 data (look for "Three Months Ended [Date]")
- 10-K annual reports contain full fiscal year data
- Q4 is NOT in 10-Q filings - must be calculated from 10-K

**EXTRACTION STEPS**:
1. **Scan all SEC chunks** for 10-Q filings - look for "FORM 10-Q for Q[X], FY [YYYY]" in metadata
2. **Extract quarterly revenue** from financial tables with "Three Months Ended" column headers
   - Search for tables/sections with: "SUMMARY RESULTS OF OPERATIONS", "INCOME STATEMENTS", or similar financial statement headers
   - Look for the "Revenue" line item in these tables
   - Revenue may appear in columns formatted as: "| |$|XX,XXX| |" or "Revenue $ XX,XXX"
3. **Use the exact fiscal quarter label from the filing title** as your dictionary key
4. For Q4 quarters: Calculate Q4 = Annual (from 10-K) - Nine Months Ended (from Q3 10-Q)
   - Locate both values in financial statement tables, even if presented in multi-year or multi-column format
   - Match the correct fiscal year column for both annual and nine-month values
   - Only calculate Q4 if BOTH values are explicitly present for the same fiscal year
   - Show calculation: "Q4 FY[YEAR] = $XXXM annual - $XXXM nine months = $XXXM"
   - In your citation, include the full table row and specify which columns were used for each value

**Q4 CALCULATION TRIGGERS**:
- Any Q4 that falls within the last 7 quarters
- You have the annual 10-K AND the Q3 10-Q "Nine Months Ended" for that fiscal year

**CRITICAL RULES**:
- Use fiscal quarter format: "Q1 FY2026", "Q3 FY2025" (copy from filing titles)
- DO NOT duplicate quarters or copy values between quarters
- DO NOT estimate components - only calculate Q4 if you have exact figures
- Include ALL calculation steps in citation with verbatim quotes, including the full table row/context
- Return null for quarters where data is genuinely unavailable

**EXCEPTION**: If you cannot find "Nine Months Ended" data for Q4 calculation, return null for that Q4 and note in citation why calculation was not possible.


## CRITICAL INSTRUCTIONS:
1. **EXHAUST ALL SOURCES** before returning null
2. **CALCULATE** when direct values unavailable
3. **SEARCH MULTIPLE KEYWORDS** for each metric
4. **PROVIDE VERBATIM CITATIONS** for all critical metrics - NO PARAPHRASING
5. **SHOW YOUR CALCULATIONS** in reasoning with actual numbers and formulas
6. **EXTRACT YoY CHANGES**: Always look for year-over-year comparisons in financial statements
7. **EXTRACT DAILY CHANGES**: For stock price, get today's movement ($ and %)
8. For optional fields: null is acceptable ONLY if you've tried calculation/extraction from all sources
9. For EBITDA, stock price, revenue trajectory: **These are effectively required - try harder**

## Data Source Strategy:
- SEC_AGENT: Financial statements, balance sheet, cash flow (look in ALL sections for YoY comparisons)
- EARNINGS_AGENT: Management commentary, guidance, Q&A mentions, growth rate discussions
- NEWS_AGENT: Recent price action, market cap references, daily stock movements

**Your goal: Maximize data extraction with VERBATIM, VERIFIABLE citations. Every null is a failure. Every paraphrased quote is a validation error.**
"""

STRATEGIC_ANALYSIS_PROMPT = """
## Task: Strategic Analysis for Client Meeting

You are preparing a strategic briefing for {COMPANY_NAME} for an RBC Capital Markets client meeting.

{DATA_FOR_STRATEGIC_ANALYSIS}

**CRITICAL: You must fill ALL fields in the response schema. Do not skip any fields.**

## Required Output Structure (ALL FIELDS MANDATORY):

### 1. SWOT Analysis (strength, weakness, opportunity, threat)
- 4-6 bullets each
- Each bullet: 15-25 words, specific, data-backed

### 2. Investment Thesis (investment_thesis field - REQUIRED)
**Format**: List of 3-4 dictionaries, each with:
- Key: One subheading (e.g., "Growth Drivers", "Competitive Moat")
- Value: List of 2-4 bullet points (15-30 words each)

**Example**:
```json
[
  {{"Growth Drivers": ["Bullet 1...", "Bullet 2..."]}},
  {{"Competitive Moat": ["Bullet 1...", "Bullet 2..."]}}
]
```

### 3. Key Risk Highlights (key_risk_highlights field)
- 5-7 critical risks
- Each bullet: 15-30 words with impact and timeline

### 4. Strategic Opportunities (strategic_opportunities field - REQUIRED)
**Format**: List of 3-4 dictionaries with:
- Key: Category (e.g., "M&A Advisory", "Capital Raising")
- Value: List of 2-3 specific opportunities (15-30 words each)

### 5. Recent Developments (recent_developments field - REQUIRED)
**NEW FORMAT**: List of 4-6 dictionaries, each with these exact keys:
- **category**: ONE of: "News", "M&A", "Management", "Company", or "Industry"
- **header**: 5-10 word title/summary of the development (e.g., "Battery Tech Acquisition", "New CFO Appointed")
- **date**: Date in format "MMM DD YYYY" (e.g., "Sept 11 2025")
- **description**: 20-40 words describing what happened, including key figures/names
- **source_url**: Full URL to the source article/document

**Example**:
```json
[
  {{
    "category": "M&A",
    "header": "Battery Tech Startup Acquisition",
    "date": "Sept 11 2025",
    "description": "Acquired battery tech startup for $2B to expand EV supply chain capabilities. Deal expected to close Q4 2025.",
    "source_url": "https://..."
  }},
  {{
    "category": "Management",
    "header": "New CFO Appointed",
    "date": "Aug 15 2025",
    "description": "Appointed Jane Doe as new CFO. She brings 20 years of experience from Fortune 500 companies.",
    "source_url": "https://..."
  }}
]
```

**IMPORTANT**: 
- Each development MUST include category, header, date, description, and source_url
- Use exact date from news article (extract from NEWS_AGENT)
- Categories must be one of the 5 specified options
- Maximum 4-6 total developments

### 6. Sources (sources field)
- 8-12 minimum
- Format: "Source Name - URL - Date Accessed (YYYY-MM-DD)"

## Data Sources:
- **NEWS_AGENT**: Recent developments, strategic moves, M&A - **EXTRACT dates and URLs**
- **EARNINGS_AGENT**: Management commentary, guidance, risks

## Compliance Check:
Before submitting, verify you have filled:
✓ strength (4-6 items)
✓ weakness (4-6 items)
✓ opportunity (4-6 items)
✓ threat (4-6 items)
✓ investment_thesis (3-4 dictionaries)
✓ key_risk_highlights (5-7 items)
✓ strategic_opportunities (3-4 dictionaries)
✓ recent_developments (4-6 dictionaries with category, date, description, source_url)
✓ sources (8-12 items)

**DO NOT skip any field. If data is limited, synthesize from available information.**
"""

# System prompts remain the same
FINANCIAL_METRICS_SYSTEM_PROMPT = """
You are a financial data extraction specialist. Your task is to extract precise financial metrics from SEC filings and financial documents with 100% accuracy. Always cite your sources and use exact figures from the documents provided. If you need to calculate a metric, show your work. Never estimate or guess - use only data present in the documents.
"""

STRATEGIC_ANALYSIS_SYSTEM_PROMPT = """
You are an expert investment banking analyst preparing strategic briefings for client meetings. Your analysis must be concise, data-driven, and actionable. Focus on insights that help bankers engage effectively with clients. Eliminate generic observations - every point should be specific to this company and backed by evidence from the provided documents. Prioritize material information that impacts business decisions.
"""



src/services/response_builder_and_generator.py
"""
Response Builder and Generator Service Module
Contains all the business logic for response building and generation.
"""
from src.utils.utils import async_time_it
import json
from typing import Dict, Any, List
from typing import Optional
from pydantic import BaseModel, Field
import ast
import re
import os 
import asyncio
import time
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from src.services.enums import ToolName
from rbc_security import enable_certs
enable_certs()


from src.services.llm.client import call_llm_raw, get_oauth_token
from src.services.data_models.models  import ContextBuilderOutput, ContentPrioritizationOutput, ResponseBuilderOutput

from src.utils.utils import async_time_it
from src.services.llm_prompts import (
            DATA_FOR_FINANCIAL_METRICS_PROMPT,
            DATA_FOR_STRATEGIC_ANALYSIS_PROMPT,
            FINANCIAL_METRICS_PROMPT,
            STRATEGIC_ANALYSIS_PROMPT,
            FINANCIAL_METRICS_SYSTEM_PROMPT,
            STRATEGIC_ANALYSIS_SYSTEM_PROMPT
        )
from src.services.data_models.llm_schemas import (
            FinancialMetricsResponse,
            StrategicAnalysisResponse
        )
from src.utils.validation_utils import MetricsValidator


import logging

logger = logging.getLogger(__name__)


class ResponseBuilderAndGenerator:
    """Service class containing all response builder and generator functionality"""


    @staticmethod
    def sanitize_prompt_for_guardrails(text: str) -> str:
        """Remove patterns that trigger false positive guardrail blocks"""
        # Remove chunk IDs that look like crypto addresses
        text = re.sub(r'chunk_id:\s*[A-Z0-9]{20,}', 'chunk_id: REDACTED', text)
        text = re.sub(r"chunk_id=['\"][A-Z0-9]{20,}['\"]", "chunk_id='REDACTED'", text)
        
        # Remove document IDs
        text = re.sub(r'document_id:\s*[A-Z0-9]{15,}', 'document_id: REDACTED', text)
        
        # Shorten URLs (keep domain but remove paths/parameters)
        text = re.sub(r'(https?://[^/\s]+)/[^\s]*', r'\1', text)
        
        # Remove long alphanumeric strings that look like account numbers
        text = re.sub(r'\b[A-Z0-9]{15,}\b', 'REDACTED', text)
        
        return text
      

    @staticmethod
    async def execute_subqueries_on_data_agents(subqueries_by_agent: dict):
        """
        Reuse a single MCP session per agent for all subqueries.
        Returns both data_agent_chunks and errors.
        """
        data_agent_chunks = {ToolName.NEWS_TOOL.value: [], ToolName.EARNINGS_TOOL.value: [], ToolName.SEC_TOOL.value: []}
        errors = {}

        for agent_name, subqueries in subqueries_by_agent.items():
            parsed_agent_name = agent_name.upper().split("_")[0]
            bearer_token = os.getenv(f"{parsed_agent_name}_AGENT_MCP_BEARER_TOKEN")
            server_url = os.getenv(f"{parsed_agent_name}_AGENT_MCP_URL")
            tool_name = os.getenv(f"{parsed_agent_name}_AGENT_MCP_TOOL")
            headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}

            try:
                # Create one MCP session per agent
                async with streamablehttp_client(server_url, headers=headers) as (read_stream, write_stream, _):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()

                        for subquery in subqueries:
                            try:
                                chunks_for_subquery = await session.call_tool(
                                    name=tool_name,
                                    arguments=subquery
                                )
                                content = chunks_for_subquery.model_dump()["content"] if chunks_for_subquery else None
                                if content:
                                    data_agent_chunks[agent_name].extend(content)
                                else:
                                    error_msg = f"Failed to retrieve data for {agent_name} subquery: {subquery}"
                                    errors.setdefault(agent_name, []).append(error_msg)
                                    logger.error(error_msg)
                            except Exception as e:
                                error_msg = f"Error for {agent_name} subquery {subquery}: {e}"
                                errors.setdefault(agent_name, []).append(error_msg)
                                logger.error(error_msg, exc_info=True)
            except Exception as e:
                error_msg = f"Error initializing MCP session for {agent_name}: {e}"
                errors.setdefault(agent_name, []).append(error_msg)
                logger.error(error_msg, exc_info=True)

        return data_agent_chunks, errors
    
    @staticmethod
    async def parse_earnings_agent_response(text_field):
        chunks = []
    
        # Split by RetrievedChunkExtended and process each
        chunk_strings = re.split(r'RetrievedChunkExtended\(', text_field)
        
        for chunk_str in chunk_strings:
            try:
                # Extract key fields using regex
                chunk_id_match = re.search(r"chunk_id='([^']*)'", chunk_str)
                score_match = re.search(r"score=([\d.]+)", chunk_str)
                
                # Extract the content dict text
                text_match = re.search(r"'text':\s*'((?:[^'\\]|\\.)*)'", chunk_str, re.DOTALL)
                if not text_match:
                    text_match = re.search(r"'text':\s*\"((?:[^\"\\]|\\.)*?)\"", chunk_str, re.DOTALL)
                
                # Extract metadata
                ticker_match = re.search(r"'TICKER':\s*'([^']*)'", chunk_str)
                date_match = re.search(r"'EVENT_DT':\s*'([^']*)'", chunk_str)
                title_match = re.search(r"'TITLE':\s*'([^']*)'", chunk_str)
                
                chunk_data = {
                    'chunk_id': chunk_id_match.group(1) if chunk_id_match else None,
                    'score': float(score_match.group(1)) if score_match else None,
                    'text': text_match.group(1) if text_match else None,
                    'ticker': ticker_match.group(1) if ticker_match else None,
                    'event_date': date_match.group(1) if date_match else None,
                    'title': title_match.group(1) if title_match else None
                }
                
                chunks.append(chunk_data)
            except Exception as e:
                print(f"Error parsing chunk: {e}")
                continue
        
        return chunks

    @staticmethod
    async def context_parser(data_agent_chunks: Dict[str, Any]) -> tuple:
        """
        Parses and processes the content prioritization data to extract relevant context.
        Returns (parsed_result, errors) tuple.
        """
        resp = {}
        errors = {}

        for agent, agent_mcp_chunks_raw in data_agent_chunks.items():
            try:
                if agent == ToolName.EARNINGS_TOOL.value:
                    agent_chunks = []
                    text_field = chunk.get("text", "")

                    chunks = await ResponseBuilderAndGenerator.parse_earnings_agent_response(text_field)
                    formatted_output = []
    
                    for idx, chunk in enumerate(chunks, 1):
                        # Skip chunks without text
                        if not chunk.get('text'):
                            continue
                        
                        # Build the chunk header
                        chunk_header = f"CHUNK-{idx}\n\n"
                        
                        # Build metadata section
                        metadata_lines = ["METADATA"]
                        if chunk.get('title'):
                            metadata_lines.append(f"title: {chunk['title']}")
                        if chunk.get('ticker'):
                            metadata_lines.append(f"ticker: {chunk['ticker']}")
                        if chunk.get('event_date'):
                            metadata_lines.append(f"event_date: {chunk['event_date']}")
                        if chunk.get('score') is not None:
                            metadata_lines.append(f"relevancy: {chunk['score']:.5f}")
                        if chunk.get('chunk_id'):
                            metadata_lines.append(f"chunk_id: {chunk['chunk_id']}")
                        
                        metadata_section = "\n".join(metadata_lines) + "\n\n\n"
                        
                        # Build content section
                        content_section = f"CHUNK-CONTENT\n{chunk['text']}\n\n\n"
                        
                        # Combine all parts
                        formatted_chunk = chunk_header + metadata_section + content_section
                        formatted_output.append(formatted_chunk)
                            
                    resp[agent] = "".join(formatted_output)

                elif agent == ToolName.NEWS_TOOL.value or agent == ToolName.SEC_TOOL.value:
                    agent_chunks = []
                    for chunk in agent_mcp_chunks_raw:
                        text_field = chunk.get("text", "")
                        
                        # Skip JSON parsing if already formatted text
                        # if text_field.startswith("CHUNK-"):
                        #     agent_chunks.append(text_field)
                        #     continue
                        
                        try:
                            parsed = json.loads(text_field)
                        except Exception:
                            try:
                                parsed = ast.literal_eval(text_field)
                            except Exception as e:
                                errors.setdefault(agent, []).append(f"Parsing failed: {e}")
                                parsed = []
                        if isinstance(parsed, list):
                            for idx, article in enumerate(parsed):
                                if not isinstance(article, dict):
                                    continue
                                main_text = article.get("text", "")
                                metadata = {k: v for k, v in article.items() if k != "text"}
                                if "_north_metadata" in metadata and isinstance(metadata["_north_metadata"], dict):
                                    for mk, mv in metadata["_north_metadata"].items():
                                        metadata[mk] = mv
                                    del metadata["_north_metadata"]
                                chunk_number = str(idx + 1)
                                metadata_lines = [f"{k}: {v}" for k, v in metadata.items()]
                                chunk_str = f"CHUNK-{chunk_number}\n\n"
                                chunk_str += "METADATA\n"
                                if metadata_lines:
                                    chunk_str += "\n".join(metadata_lines) + "\n"
                                chunk_str += "\n\nCHUNK-CONTENT\n"
                                chunk_str += main_text if isinstance(main_text, str) else str(main_text)
                                agent_chunks.append(chunk_str)
                        elif isinstance(parsed, dict):
                            main_text = parsed.get("text", "")
                            metadata = {k: v for k, v in parsed.items() if k != "text"}
                            if "_north_metadata" in metadata and isinstance(metadata["_north_metadata"], dict):
                                for mk, mv in metadata["_north_metadata"].items():
                                    metadata[mk] = mv
                                del metadata["_north_metadata"]
                            chunk_number = "1"
                            metadata_lines = [f"{k}: {v}" for k, v in metadata.items()]
                            chunk_str = f"CHUNK-{chunk_number}\n\n"
                            chunk_str += "METADATA\n"
                            if metadata_lines:
                                chunk_str += "\n".join(metadata_lines) + "\n"
                            chunk_str += "\n\nCHUNK-CONTENT\n"
                            chunk_str += main_text if isinstance(main_text, str) else str(main_text)
                            agent_chunks.append(chunk_str)
                    resp[agent] = "\n\n\n".join(agent_chunks)
            except Exception as e:
                errors.setdefault(agent, []).append(f"Agent-level parsing failed: {e}")

        return resp, errors

       

    @staticmethod
    async def prompt_builder(
        
        parsed_data_agent_chunks,
        company_name, 
        FINANCIAL_METRICS_PROMPT,
        STRATEGIC_ANALYSIS_PROMPT,
        DATA_FOR_FINANCIAL_METRICS_PROMPT,
        DATA_FOR_STRATEGIC_ANALYSIS_PROMPT,
        content_prioritization_data_distribution
    ):
        """
        Builds prompts based on the content prioritization data.
        """

        parsed_DATA_FOR_FINANCIAL_METRICS_PROMPT = DATA_FOR_FINANCIAL_METRICS_PROMPT.format(
        EARNINGS_AGENT_CONTENT=parsed_data_agent_chunks.get(ToolName.EARNINGS_TOOL.value),
        SEC_AGENT_CONTENT=parsed_data_agent_chunks.get(ToolName.SEC_TOOL.value),
        NEWS_AGENT_CONTENT=parsed_data_agent_chunks.get(ToolName.NEWS_TOOL.value)
        )

        parsed_DATA_FOR_STRATEGIC_ANALYSIS_PROMPT = DATA_FOR_STRATEGIC_ANALYSIS_PROMPT.format(
            NEWS_AGENT_CONTENT=parsed_data_agent_chunks.get(ToolName.NEWS_TOOL.value),
            EARNINGS_AGENT_CONTENT=parsed_data_agent_chunks.get(ToolName.EARNINGS_TOOL.value),
            SEC_AGENT_CONTENT=parsed_data_agent_chunks.get(ToolName.SEC_TOOL.value),
            NEWS_percentage=content_prioritization_data_distribution[ToolName.NEWS_TOOL.value],
            EARNINGS_percentage=content_prioritization_data_distribution[ToolName.EARNINGS_TOOL.value],
            SEC_percentage=content_prioritization_data_distribution[ToolName.SEC_TOOL.value]
        )

        parsed_FINANCIAL_METRICS_PROMPT = FINANCIAL_METRICS_PROMPT.format(
            DATA_FOR_FINANCIAL_METRICS=parsed_DATA_FOR_FINANCIAL_METRICS_PROMPT,
            COMPANY_NAME=company_name
        )

        parsed_STRATEGIC_ANALYSIS_PROMPT = STRATEGIC_ANALYSIS_PROMPT.format(
            DATA_FOR_STRATEGIC_ANALYSIS=parsed_DATA_FOR_STRATEGIC_ANALYSIS_PROMPT,
            COMPANY_NAME=company_name
        )

        # Sanitize ONLY strategic analysis (it's longer and triggers guardrails)
        parsed_STRATEGIC_ANALYSIS_PROMPT = ResponseBuilderAndGenerator.sanitize_prompt_for_guardrails(
            parsed_STRATEGIC_ANALYSIS_PROMPT
        )

        return parsed_FINANCIAL_METRICS_PROMPT, parsed_STRATEGIC_ANALYSIS_PROMPT
    

    @staticmethod
    async def get_structured_response(
        user_prompt, 
        system_prompt, 
        response_obj, 
        name, 
        description
    ):
        """Extract financial metrics using structured output. Returns (result, error) tuple."""
        error = None
        result = None
        try:
            schema = response_obj.model_json_schema()
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            tools = [{
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": schema
                }
            }]
            response = await call_llm_raw(
                messages=messages,
                tools=tools,
                tool_choice={"type": "function", "function": {"name": name}}
            )

            

            try:
                tool_call = response["choices"][0]["message"]["tool_calls"][0]
            
            except Exception as e:
                # DEBUG: Print full response structure
                print(f"\n\n=== FULL LLM RESPONSE for {name} ===")
                print(json.dumps(response, indent=2, default=str))
                print("=== END ===\n\n")

            arguments = json.loads(tool_call["function"]["arguments"])

            # DEBUG: Print what LLM returned
            print("\n\n=== LLM RESPONSE ===")
            print(json.dumps(arguments, indent=2))
            print("\n=== MISSING/NULL FIELDS ===")
            required_fields = response_obj.model_fields.keys()
            for field in required_fields:
                if field not in arguments:
                    print(f"MISSING: {field}")
                elif arguments[field] is None:
                    print(f"NULL: {field}")
            print("=== END ===\n\n")


            # Clean up string placeholders for numeric fields
            for k, v in arguments.items():
                if isinstance(v, str) and v.strip().upper() in {"<UNKNOWN>", "N/A", "NULL", "NONE"}:
                    arguments[k] = None

            result = response_obj(**arguments)
        except Exception as e:
            error = str(e)
            logger.error(f"Error in get_structured_response: {error}", exc_info=True)
            result = None
        return result, error
    

    @staticmethod
    async def response_builder(
        financial_metrics_prompt,
        strategic_analysis_prompt,
        financial_metrics_system_prompt,
        strategic_analysis_system_prompt,
        FinancialMetricsResponse,
        StrategicAnalysisResponse
    ):
        financial_metrics_response_name = "extract_financial_metrics"
        financial_metrics_response_description = "Extract precise financial metrics from SEC filings and earnings reports"

        strategic_analysis_response_name = "generate_strategic_analysis"
        strategic_analysis_response_description = "Generate comprehensive strategic analysis for investment banking client meeting"

        # Start BOTH calls concurrently using asyncio.gather
        fm_tuple, sa_tuple = await asyncio.gather(
            ResponseBuilderAndGenerator.get_structured_response(
                user_prompt=financial_metrics_prompt,
                system_prompt=financial_metrics_system_prompt,
                response_obj=FinancialMetricsResponse,
                name=financial_metrics_response_name,
                description=financial_metrics_response_description
            ),
            ResponseBuilderAndGenerator.get_structured_response(
                user_prompt=strategic_analysis_prompt,
                system_prompt=strategic_analysis_system_prompt,
                response_obj=StrategicAnalysisResponse,
                name=strategic_analysis_response_name,
                description=strategic_analysis_response_description
            )
        )

        financial_metrics_result, financial_metrics_error = fm_tuple
        strategic_analysis_result, strategic_analysis_error = sa_tuple

        return (
            (financial_metrics_result, financial_metrics_error),
            (strategic_analysis_result, strategic_analysis_error)
        )
    

    @staticmethod
    async def execute(
        context_builder_output: ContextBuilderOutput,
        content_prioritization_output: ContentPrioritizationOutput
    ) -> ResponseBuilderOutput:
        """
        Execute the full response builder and generator pipeline.
        """
        timings = {}
        errors = {}

        corporate_client_firm_response = context_builder_output["corporate_client_firm_response"]
        if corporate_client_firm_response:
            company_name = corporate_client_firm_response.get("company_name")
        else:
            company_name = context_builder_output["request_company_name"]

        temporal_source_prioritizer = content_prioritization_output["temporal_source_prioritizer"]
        subqueries_from_engine = content_prioritization_output["subqueries_from_engine"]

        # Step 1: Execute subqueries on data agents
        (data_agent_chunks, data_agent_errors), timings["execute_subqueries_on_data_agents"] = await async_time_it(
            ResponseBuilderAndGenerator.execute_subqueries_on_data_agents
        )(subqueries_by_agent=subqueries_from_engine)
        if data_agent_errors:
            errors["execute_subqueries_on_data_agents"] = data_agent_errors

        # Step 2: Context parser
        (parsed_data_agent_chunks, context_parser_errors), timings["context_parser"] = await async_time_it(
            ResponseBuilderAndGenerator.context_parser
        )(data_agent_chunks=data_agent_chunks)
        if context_parser_errors:
            errors["context_parser"] = context_parser_errors

        logger.info(f"\n\n\n Parsed Data Agent Chunks Character Lengths: {[(agent, len(content)) for agent, content in parsed_data_agent_chunks.items()]} \n\n\n")

        # Check if all data agent chunks are empty
        total_content_length = sum(len(content) for content in parsed_data_agent_chunks.values())
        if total_content_length == 0:
            logger.warning("All data agent chunks are empty - skipping LLM calls")
            errors["data_agents"] = "All data agents returned empty results"
            result = {
                "financial_metrics_result": None,
                "strategic_analysis_result": None,
                "timings": timings,
                "errors": errors,
                "parsed_data_agent_chunks": parsed_data_agent_chunks,
                "company_name": company_name,
            }
            return result

        # Step 3: Prompt builder
        (parsed_FINANCIAL_METRICS_PROMPT, parsed_STRATEGIC_ANALYSIS_PROMPT), timings["prompt_builder"] = await async_time_it(
            ResponseBuilderAndGenerator.prompt_builder
        )(
            parsed_data_agent_chunks=parsed_data_agent_chunks,
            company_name=company_name,
            FINANCIAL_METRICS_PROMPT=FINANCIAL_METRICS_PROMPT,
            STRATEGIC_ANALYSIS_PROMPT=STRATEGIC_ANALYSIS_PROMPT,
            DATA_FOR_FINANCIAL_METRICS_PROMPT=DATA_FOR_FINANCIAL_METRICS_PROMPT,
            DATA_FOR_STRATEGIC_ANALYSIS_PROMPT=DATA_FOR_STRATEGIC_ANALYSIS_PROMPT,
            content_prioritization_data_distribution=temporal_source_prioritizer
        )

        # Step 4: Response builder
        (financial_metrics_tuple, strategic_analysis_tuple), timings["response_builder"] = await async_time_it(
            ResponseBuilderAndGenerator.response_builder
        )(
            financial_metrics_prompt=parsed_FINANCIAL_METRICS_PROMPT,
            strategic_analysis_prompt=parsed_STRATEGIC_ANALYSIS_PROMPT,
            financial_metrics_system_prompt=FINANCIAL_METRICS_SYSTEM_PROMPT,
            strategic_analysis_system_prompt=STRATEGIC_ANALYSIS_SYSTEM_PROMPT,
            FinancialMetricsResponse=FinancialMetricsResponse,
            StrategicAnalysisResponse=StrategicAnalysisResponse
        )

        financial_metrics_result, financial_metrics_error = financial_metrics_tuple
        strategic_analysis_result, strategic_analysis_error = strategic_analysis_tuple

        if financial_metrics_error:
            errors["financial_metrics_response"] = financial_metrics_error
        if strategic_analysis_error:
            errors["strategic_analysis_response"] = strategic_analysis_error

        # Step 5: Validate financial metrics extraction
        validation_results = None
        if financial_metrics_result:
            try:
                start_time = time.perf_counter()
                validation_results = MetricsValidator.validate_financial_metrics(
                    metrics=financial_metrics_result,
                    source_chunks=parsed_data_agent_chunks
                )
                timings["validate_financial_metrics"] = time.perf_counter() - start_time
                logger.info(f"Execution time for validate_financial_metrics: {timings['validate_financial_metrics']:.2f} seconds")
                
                # Log validation summary
                logger.info(f"Validation Summary: {validation_results['validation_summary']}")
                
                # Print detailed validation report (optional - can be controlled by config)
                if logger.isEnabledFor(logging.DEBUG):
                    MetricsValidator.print_validation_report(validation_results)
                
                # Add warnings to errors dict if any validation issues found
                if validation_results["warnings"]:
                    errors["validation_warnings"] = validation_results["warnings"]
                    
            except Exception as e:
                logger.error(f"Error during metrics validation: {e}", exc_info=True)
                errors["validation_error"] = str(e)

        result = {
            "financial_metrics_result": financial_metrics_result,
            "strategic_analysis_result": strategic_analysis_result,
            "validation_results": validation_results,
            "timings": timings,
            "errors": errors,
            "parsed_data_agent_chunks": parsed_data_agent_chunks,
            "company_name": company_name,
        }

        return result

    
async def main(user_prompt, system_prompt,FinancialMetricsResponse, tool_name, tool_description):
        result, error = await ResponseBuilderAndGenerator.get_structured_response(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            response_obj=FinancialMetricsResponse,
            name=tool_name,
            description=tool_description
        )
        if error:
            print("Error:", error)
        else:
            print("Result:", result)


src/services/static_subquery_engine.py
from datetime import datetime, timedelta
from src.services.enums import ToolName
    

class StaticSubqueryEngine:

    @staticmethod
    def get_SEC_agent_query_argument(company_name) -> dict:
        """
        Args:
            meeting_date: Optional date string in 'YYYY-MM-DD' format. 
                        If None, uses today's date.
        """
        
        return [
                
    
                {
        "reporting_entity": f"{company_name}",
        "search_queries": [
            "consolidated statements of operations","statements of income","total revenue"
        ],
        "keywords": [
            "net sales",
            "total revenue",
            "net product sales",
            "net service sales",
            "three months ended",
            "quarterly revenue",
            "consolidated statements of operations",
            "total net sales",
            "revenue",
        ],
        "get_latest": 8,
                },
                {
                "reporting_entity": f"{company_name}",
      "search_queries": [
        "consolidated balance sheets",
        "stockholders equity",
        "common stock outstanding shares"
      ],
      "keywords": [
        "outstanding shares",
        "common stock",
        "shares outstanding",
        "issued shares",
        "share capital",
        "stockholders equity",
        "equity structure",
        "shares issued",
        "capital stock",
        "basic shares"
      ],
      "get_latest": 1
                } 


        ]

    @staticmethod
    def get_earnings_agent_query_argument(company_name: str, fiscal_year: str, fiscal_quarter: str) -> dict:
        return [
            {
                "query": f"Give me the earnings transcript for {company_name} for fiscal year: {fiscal_year} and quarter: {fiscal_quarter}.",
            }
        ]
    

    @staticmethod
    def get_news_agent_query_argument(company_name: str) -> list[dict]:
        end_date = datetime.now().strftime('%Y-%m-%d')
        once_month_ago = (datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=31)).strftime('%Y-%m-%d')
        five_days_ago = (datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=5)).strftime('%Y-%m-%d')
        absolute_date_range = {"start_date": once_month_ago, "end_date": end_date}
        one_year_and_five_days_ago = (datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=365+5)).strftime('%Y-%m-%d')
        one_year_ago = (datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=365)).strftime('%Y-%m-%d')
        return [
            # Executive changes & leadership
            {
                "search_query": f"{company_name} executive leadership changes appointments departures CEO CFO senior management hires",
                "topics": ["executive", "CEO", "CFO", "leadership", "appointment", "hire", "departure"],
                "absolute_date_range": absolute_date_range
            },
            # M&A and strategic transactions
            {
                "search_query": f"{company_name} mergers acquisitions M&A strategic transactions deal announced acquired acquiring",
                "topics": ["merger", "acquisition", "M&A", "deal", "transaction"],
                "absolute_date_range": absolute_date_range
            },
            # Regulatory, legal, and controversies
            {
                "search_query": f"{company_name} regulatory issues lawsuit litigation investigation antitrust compliance controversy",
                "topics": ["regulatory", "lawsuit", "litigation", "investigation", "compliance"],
                "absolute_date_range": absolute_date_range
            },
            # Strategic initiatives and restructuring
            {
                "search_query": f"{company_name} strategic pivot restructuring expansion office opening closing organizational changes credit rating investor relations",
                "topics": ["restructuring", "expansion", "strategic pivot", "office", "credit rating", "investor relations", "AGM"],
                "absolute_date_range": absolute_date_range
            },
            # Market capitalization and stock price
            {
                "search_query": f"{company_name} market capitalization and stock price",
                "topics": ["market capitalization", "market cap", "valuation", "company worth", "enterprise value", "stock price"],
                "absolute_date_range": {"start_date": five_days_ago, "end_date": end_date}
            },
            # Market capitalization and stock price (1 year and 5 days ago to 1 year ago) 
            {
                "search_query": f"{company_name} market capitalization and stock price",
                "topics": ["market capitalization", "market cap", "valuation", "company worth", "enterprise value", "stock price"],
                "absolute_date_range": {"start_date": one_year_and_five_days_ago, "end_date": one_year_ago}
            },
            
        ]
    @staticmethod
    def get_subquery_arguments(company_name: str, fiscal_year: str, fiscal_quarter: str):
        return  {
            ToolName.EARNINGS_TOOL.value: StaticSubqueryEngine.get_earnings_agent_query_argument(company_name, fiscal_year, fiscal_quarter),
            ToolName.NEWS_TOOL.value: StaticSubqueryEngine.get_news_agent_query_argument(company_name),
             ToolName.SEC_TOOL.value: StaticSubqueryEngine.get_SEC_agent_query_argument(company_name),
        }


if __name__=="__main__":
    import os 
    import asyncio
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    from rbc_security import enable_certs
    enable_certs()

    async def make_tool_call():
        server_url = os.environ["NEWS_AGENT_MCP_URL"]
        bearer_token = os.environ["NEWS_AGENT_MCP_BEARER_TOKEN"]
        headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}
        print(server_url)
        async with streamablehttp_client(server_url, headers=headers) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                print(f"Available tools: {[tool.name for tool in tools.tools]}")

                news_args = StaticSubqueryEngine.get_news_agent_query_argument("BlackRock, Inc.", "2025-11-29")
                for idx, arg in enumerate(news_args):
                    print(f"\nCalling tool with news argument {idx+1}: {arg}\n")
                    result = await session.call_tool(
                        name=os.environ["NEWS_AGENT_MCP_TOOL"], 
                        arguments=arg
                    )
                    response_text = "".join([doc.text for doc in result.content])
                    print(response_text)
                    print(f"Response length for argument {idx+1}: {len(response_text)} \n\n\n")

    asyncio.run(make_tool_call())



src/services/llm/client.py
"""
LLM Client for reference_mcp_client - loads config from .env using os.getenv.
"""

# --- REFACTORED TO USE oauth_client.py LOGIC ---
import os
import json
from typing import Dict, Any, List
from dotenv import load_dotenv
import asyncio
from .oauth_client import get_env, get_oauth_token
import httpx
from src.config.configuration import get_config
from llama_index.llms.openai import OpenAI

from rbc_security import enable_certs
enable_certs()
load_dotenv()

async def call_llm(messages: List[Dict[str, str]], tools: List[Dict[str, Any]] = None) -> str:
    """
    Call the LLM using the new company-standard approach (see llm_call.py).
    Accepts OpenAI-style messages and optional tools.
    Returns the main content string or tool call summary.
    """
    token = await get_oauth_token()
    config = get_config().llm_chat_model
    llm_model = config.model_name
    llm_base_url = config.server_url
    supports_temperature = hasattr(config, "temperature") and config.temperature is not None

    payload = {
        "model": llm_model,
        "messages": messages,
        "max_tokens": getattr(config, "max_tokens", 4000)
    }
    if supports_temperature:
        payload["temperature"] = config.temperature
    if tools:
        payload["tools"] = tools

    async with httpx.AsyncClient(verify=False, timeout=60.0) as client:
        response = await client.post(
            llm_base_url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            }
        )
        response.raise_for_status()
        data = response.json()
        try:
            choice = data["choices"][0]
            # OpenAI format: either {"message": {"content": ...}} or {"content": ...}
            if "message" in choice and "content" in choice["message"]:
                return choice["message"]["content"]
            elif "content" in choice:
                return choice["content"]
            elif "message" in choice and "tool_calls" in choice["message"]:
                tool_calls = choice["message"]["tool_calls"]
                tool_call_strs = []
                for tc in tool_calls:
                    name = tc.get("function", {}).get("name", tc.get("name", "<unknown>"))
                    args = tc.get("function", {}).get("arguments", tc.get("arguments", ""))
                    tool_call_strs.append(f"Tool call: {name} with arguments {args}")
                return "\n".join(tool_call_strs)
            else:
                return f"LLM response did not contain content or tool_calls. Raw: {json.dumps(choice)}"
        except Exception as e:
            return f"Error parsing LLM response: {e}. Raw: {json.dumps(data)}"

async def call_llm_raw(
    messages: List[Dict[str, str]], 
    tools: List[Dict[str, Any]] = None,
    tool_choice: Dict[str, Any] = None  # Add this parameter
) -> dict:
    """
    Same as call_llm, but returns the full LLM response dict for advanced routing.
    """
    token = await get_oauth_token()
    config = get_config().llm_chat_model
    llm_model = config.model_name
    llm_base_url = config.server_url
    supports_temperature = config.temperature

    payload = {
        "model": llm_model,
        "messages": messages,
        "max_tokens": config.max_tokens
    }
    if supports_temperature:
        payload["temperature"] = supports_temperature
    if tools:
        payload["tools"] = tools
    if tool_choice:  # Add this
        payload["tool_choice"] = tool_choice

    async with httpx.AsyncClient(verify=False, timeout=180) as client:
        response = await client.post(
            llm_base_url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            }
        )
        response.raise_for_status()
        return response.json()

async def get_openai_client():
    token = await get_oauth_token()
    config = get_config().llm_chat_model
    llm_model = config.model_name
    llm_base_url = (config.server_url).split("/chat")[0]
    temperature = config.temperature

    return OpenAI(model=llm_model, 
                 api_base=llm_base_url,
                 api_key=token,
                 temperature=temperature)
    


src/services/llm/oauth_client.py
import os
import httpx
import asyncio
from dotenv import load_dotenv
from src.config.configuration import get_config

load_dotenv()

def get_env(key, default=None, required=False):
    """Get environment variable with optional default and required validation"""
    value = os.getenv(key, default)
    if required and value is None:
        raise ValueError(f"Missing required environment variable: {key}")
    return value

async def get_oauth_token():
    """Get OAuth token for LLM API authentication"""
    config = get_config().llm_chat_model
    oauth_endpoint = config.oauth_endpoint
    client_id = config.client_id
    client_secret = os.getenv('LLM_CLIENT_SECRET')
    grant_type = "client_credentials"
    scope = "read"

    data = {
        "grant_type": grant_type,
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": scope
    }
    async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
        response = await client.post(
            oauth_endpoint,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        response.raise_for_status()
        result = response.json()
        return result["access_token"]
    
if __name__=="__main__":
    token = asyncio.run(get_oauth_token()   )
    print("\n\n\n\n\n\n")

    print(token)


src/services/data_models/llm_schemas.py
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field

class CitationDict(BaseModel):
    """Structured citation with source tracking and reasoning"""
    source_agent: List[str] = Field(
        description="List of data agents used. Valid values: 'SEC_agent', 'earnings_agent', 'news_agent'. Example: ['SEC_agent'] or ['SEC_agent', 'earnings_agent']"
    )
    source_content: List[str] = Field(
        description="List of verbatim quotes/phrases from source chunks. Each quote should be 10-200 words, directly copy-pasted from agent content. DO NOT paraphrase."
    )
    reasoning: str = Field(
        description="Explanation of how you derived this metric. For extracted values: 'Extracted from [document] [section]'. For calculated values: show step-by-step math with actual numbers. Example: 'Calculated EBITDA: (Operating Income $1.6B + D&A $1.0B) / Revenue $28.1B = 9.25%'"
    )

class StrategicAnalysisResponse(BaseModel):
    strength: List[str] = Field(
        description="List of 4-6 key competitive strengths from SWOT analysis. Each bullet should be specific, data-backed, and 15-25 words. Focus on: market position, financial health, operational advantages, brand strength, or proprietary capabilities. Cite metrics where possible."
    )
    weakness: List[str] = Field(
        description="List of 4-6 key vulnerabilities from SWOT analysis. Each bullet should be specific, data-backed, and 15-25 words. Focus on: competitive disadvantages, financial constraints, operational challenges, regulatory risks, or market exposure issues."
    )
    opportunity: List[str] = Field(
        description="List of 4-6 growth opportunities from SWOT analysis. Each bullet should be specific, actionable, and 15-25 words. Focus on: market expansion, new products/services, M&A targets, regulatory changes, or emerging trends that benefit the company."
    )
    threat: List[str] = Field(
        description="List of 4-6 external threats from SWOT analysis. Each bullet should be specific, data-backed, and 15-25 words. Focus on: competitive pressures, regulatory headwinds, market disruption, economic conditions, or technological changes threatening the business."
    )
    
    investment_thesis: List[Dict[str, List[str]]] = Field(
        description="Investment thesis structured as a list of dictionaries. Each dictionary has ONE subheading as key (e.g., 'Growth Drivers', 'Competitive Moat', 'Valuation Opportunity') and a list of 2-4 supporting bullet points as value. Each bullet should be 15-30 words. Total: 3-4 subheadings maximum."
    )
    
    key_risk_highlights: List[str] = Field(
        description="List of 5-7 critical risks that could impact investment thesis or business operations. Each bullet should be 15-30 words and include: specific risk factor, potential impact magnitude, and timeline if relevant. Prioritize material risks from SEC filings and recent news."
    )
    
    strategic_opportunities: List[Dict[str, List[str]]] = Field(
        description="Strategic opportunities for the company AND for RBC Capital Markets engagement, structured as list of dictionaries. Each dictionary has ONE subheading as key (e.g., 'M&A Advisory', 'Capital Raising', 'Strategic Repositioning') and 2-3 specific opportunity bullets as value. Each bullet: 15-30 words. Total: 3-4 subheadings maximum."
    )
    
    recent_developments: List[Dict[str, Any]] = Field(
        description="Recent FIRM-LEVEL developments (last 12 months) structured as list of dictionaries. Each dictionary must have: 'category' (one of: 'News', 'M&A', 'Management', 'Company', 'Industry'), 'header' (5-10 word title/summary of the development), 'date' (format: 'MMM DD YYYY' e.g., 'Sept 11 2025'), 'description' (20-40 words including what happened, key figures/names), and 'source_url' (hyperlink). Maximum 4-6 total developments. EXCLUDE portfolio company news unless it signals major strategic shift."
    )
    
    sources: List[str] = Field(
        description="Comprehensive list of all sources cited in the analysis. Format each as: 'Source Name - URL - Date Accessed (YYYY-MM-DD)'. Include: SEC filings, news articles, earnings transcripts, press releases. Minimum 8-12 sources for thorough analysis."
    )

class FinancialMetricsResponse(BaseModel):
    # REQUIRED fields
    current_annual_revenue: Optional[float] = Field(
        description="Current annual revenue of the company in billions USD, extracted from most recent SEC filing (10-K or 10-Q). This should be the total revenue/sales figure from the income statement."
    )
    current_annual_revenue_date: Optional[str] = Field(
        description="Date of the SEC filing from which current annual revenue was extracted (format: YYYY-MM-DD). Use the filing date, not the period end date."
    )
    current_annual_revenue_citation: Optional[CitationDict] = Field(
        default=None,
        description="Citation for current annual revenue including source agents, verbatim quotes, and extraction reasoning."
    )
    current_annual_revenue_yoy_change: Optional[float] = Field(
        default=None,
        description="Year-over-year percentage change in annual revenue (e.g., 9.0 for +9% YoY). Compare current period revenue to same period prior year. Return null if insufficient data."
    )
    current_annual_revenue_yoy_change_citation: Optional[CitationDict] = Field(
        default=None,
        description="Citation for YoY revenue change including source agents, verbatim quotes showing both current and prior year revenue figures, and calculation formula with actual numbers."
    )
    estimated_annual_revenue_next_year: Optional[float] = Field(
        description="Projected annual revenue for next fiscal year in billions USD, based on company guidance from SEC filings, earnings calls, or analyst estimates mentioned in the documents. If unavailable, extrapolate from current growth trends."
    )
    estimated_annual_revenue_next_year_date: Optional[str] = Field(
        description="Date of the source document (SEC filing or earnings report) from which the revenue estimate was derived (format: YYYY-MM-DD)."
    )
    estimated_annual_revenue_next_year_citation: Optional[CitationDict] = Field(
        default=None,
        description="Citation for estimated annual revenue including source agents, verbatim quotes, and reasoning/calculation method. REQUIRED even if value is null - explain which sources were checked (SEC forward guidance, earnings outlook, analyst estimates) and why no data was found."
    )
    
    ebitda_margin: Optional[float] = Field(
        default=None,
        description="EBITDA margin as a percentage (e.g., 25.5 for 25.5%), calculated from most recent SEC filing. If EBITDA is not directly stated, calculate as (Operating Income + Depreciation + Amortization) / Revenue * 100. Return null if insufficient data."
    )
    ebitda_margin_citation: Optional[CitationDict] = Field(
        default=None,
        description="Citation for EBITDA margin including source agents, verbatim quotes of calculation components (Operating Income, D&A, Revenue), and step-by-step calculation reasoning."
    )
    ebitda_margin_yoy_change: Optional[float] = Field(
        default=None,
        description="Year-over-year change in EBITDA margin as percentage points (e.g., 1.0 for +1% YoY). Compare current period margin to same period prior year. Return null if insufficient data."
    )
    ebitda_margin_yoy_change_citation: Optional[CitationDict] = Field(
        default=None,
        description="Citation for YoY EBITDA margin change including source agents, verbatim quotes showing both current and prior period margin calculations, and step-by-step comparison."
    )
    stock_price: Optional[float] = Field(
        default=None,
        description="Most recent stock price in USD from news articles or market data. Use the latest available closing price mentioned in the documents. Return null if not available."
    )
    stock_price_citation: Optional[CitationDict] = Field(
        default=None,
        description="Citation for stock price including source agents, verbatim quote with price and date/time context, and extraction reasoning."
    )
    stock_price_daily_change: Optional[float] = Field(
        default=None,
        description="Today's stock price change in USD (e.g., 1.39 for +$1.39 today). This is the absolute dollar change from previous close to current price. Return null if not available."
    )
    stock_price_daily_change_percent: Optional[float] = Field(
        default=None,
        description="Today's stock price percentage change (e.g., 0.56 for +0.56% today). This is the percentage change from previous close to current price. Return null if not available."
    )
    stock_price_yoy_change: Optional[float] = Field(
        default=None,
        description="Year-over-year percentage change in stock price (e.g., 15.5 for +15.5%, -8.2 for -8.2%). PREFERRED: Compare current price to price from same date one year prior. ACCEPTABLE: Use Year-to-Date (YTD) performance as proxy when exact YoY unavailable (e.g., if YTD = +29.10%, use 29.10 as approximate YoY). Return null only if no YoY or YTD data available."
    )
    stock_price_yoy_change_citation: Optional[CitationDict] = Field(
        default=None,
        description="Citation for YoY stock price change including source agents, verbatim quotes showing both current and prior year prices with dates (if available), and calculation formula. If using YTD as proxy, explain in reasoning: 'Used YTD performance as YoY approximation' and include verbatim YTD quote. REQUIRED even if value is null - explain what sources were checked."
    )
    market_cap: Optional[float] = Field(
        default=None,
        description="Current market capitalization in billions USD, calculated as stock price × outstanding shares. Use most recent figures from SEC filings or news articles. Return null if insufficient data."
    )
    market_cap_citation: Optional[CitationDict] = Field(
        default=None,
        description="Citation for market cap including source agents, verbatim quotes showing stock price and outstanding shares, and calculation formula (price × shares = market cap)."
    )
    market_cap_date: Optional[str] = Field(
        default=None,
        description="Date when market cap was calculated or reported (format: YYYY-MM-DD). Should match the stock price date. Return null if not available."
    )
    revenue_growth_trajectory: Optional[Dict[str, Optional[float]]] = Field(
    default=None,
    description="""

    Quarterly revenue in billions USD for the last 7 quarters, using fiscal quarter notation.

**EXTRACTION APPROACH**:
- Scan SEC chunks for 10-Q filings (contain Q1, Q2, Q3 data)
- Look for "FORM 10-Q for Q[X], FY [YYYY]" in chunk metadata
- Extract revenue from financial statement tables with "Three Months Ended [Date]" column headers
- Search for: "SUMMARY RESULTS OF OPERATIONS", "INCOME STATEMENTS", or similar headers
- Find "Revenue" line item in these tables (may appear as: "| |$|XX,XXX| |" or "Revenue $ XX,XXX")
- Use fiscal quarter label from filing title as dictionary key (e.g., "Q1 FY2026")

**Q4 CALCULATION**:
- Formula: Q4 = Annual Revenue (10-K) - Nine Months Ended (Q3 10-Q)
- Only calculate if BOTH components are explicitly present in the documents
- When extracting annual and nine-month values, match the correct fiscal year column in multi-year tables
- In your citation, specify the table row and the exact columns used for each value
- Do NOT estimate any missing components
- Show full calculation in citation with verbatim quotes from both sources

**KEY FORMAT**: "Q[1-4] FY[YYYY]" matching the fiscal year from SEC filing titles

**QUALITY RULES**:
- Each quarter should appear ONCE (no duplicates)
- Only use quarters with actual filing data or valid Q4 calculations
- Use null for individual quarters where data is unavailable
- Do NOT return null for the entire field if any quarterly data exists

Example: {"Q1 FY2026": 77.673, "Q4 FY2025": 76.441, "Q3 FY2025": 70.066, "Q2 FY2025": 64.727, ...}
"""
    )
    revenue_growth_trajectory_citation: Optional[CitationDict] = Field(
        default=None,
        description="Citation for quarterly revenue including verbatim quotes with EXACT filing references (e.g., '10-Q for Q3 FY2025 filed Apr 30, 2025') and explanation of fiscal quarter mapping."
    )


src/services/data_models/models.py
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field


class ContextBuilderOutput(BaseModel):
    corporate_client_firm_response_raw: Optional[Dict[str, Any]] = None
    corporate_client_firm_response: Optional[Dict[str, Any]] = None
    temporal_content_response_raw: Optional[Dict[str, Any]] = None
    temporal_content_response: Optional[Dict[str, Any]] = None
    rbc_persona: Optional[Any] = None
    corporate_client_persona: Optional[Any] = None
    meeting_date: Optional[str] = None
    corporate_company_name: Optional[str] = None
    request_meeting_date: Optional[str] = None
    request_company_name: Optional[str] = None
    timings: Optional[Dict[str, float]] = None
    errors: Optional[Dict[str, Any]] = None

class ContentPrioritizationOutput(BaseModel):
    temporal_source_prioritizer: Optional[Dict[str, Any]] = None
    subqueries_from_engine: Optional[Dict[str, Any]] = None
    topic_ranker_result: Optional[Any] = None
    timings: Optional[Dict[str, float]] = None
    errors: Optional[Dict[str, Any]] = None

class ResponseBuilderOutput(BaseModel):
    financial_metrics_result: Optional[Any] = None
    strategic_analysis_result: Optional[Any] = None
    parsed_data_agent_chunks: Optional[Dict[str, Any]] = None
    company_name: Optional[str] = None
    timings: Optional[Dict[str, float]] = None
    errors: Optional[Dict[str, Any]] = None