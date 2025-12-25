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
    ChainServerRequest, ChainServerResponse, ChatRequest

)
from typing import Dict, Any
from src.services.data_models.models  import ContextBuilderOutput, ContentPrioritizationOutput , ResponseBuilderOutput
from src.services.data_models.llm_schemas import StrategicAnalysisResponse
from src.services.context_builder_service import ContextBuilderService
from src.services.content_prioritization_service import ContentPrioritizationService
from src.services.response_builder_and_generator import ResponseBuilderAndGenerator
from src.services.chain_orchestrator import ChainOrchestrator
from src.services.chat_service import ChatService



router = APIRouter()



@router.post("/chain-server")
async def chain_server(request: ChainServerRequest) -> Dict[str, Any]:
    """
    Unified chain server endpoint that orchestrates all modules based on the request.
    Returns full response when verbose=True, filtered response when verbose=False.
    """
    try:
        response_dict_with_metadata = await ChainOrchestrator().execute_chain(request)

        if not request.verbose:
            rbg = response_dict_with_metadata.get("response_builder_and_generator", {})
            filtered_rbg = {
                k: v for k, v in rbg.items()
                if k in ("financial_metrics_result", "strategic_analysis_result")
            }
            return {"response_builder_and_generator": filtered_rbg}

        return response_dict_with_metadata

    except Exception as e:
        tb = traceback.format_exc()
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

@router.post("/chain-server-chat", response_model=Dict[str, Any])
async def chain_server_chat(request: ChatRequest):
    """
    Chat endpoint that answers user queries using cached agent content.
    """
    try:
        
        chain_request = ChainServerRequest(
            meeting_datetime=request.meeting_datetime,
            corporate_company_name=request.corporate_company_name
        )
        

        context_builder_output = await ContextBuilderService.execute(chain_request)
        content_prioritization_output = await ContentPrioritizationService.execute(context_builder_output)
        
        subqueries_by_agent = content_prioritization_output.get('subqueries_from_engine')
        

        chat_response = await ChatService.chat(
            user_query=request.user_query,
            company_name=request.corporate_company_name,
            subqueries_by_agent=subqueries_by_agent
        )
        
        return chat_response
        
    except Exception as e:
        tb = traceback.format_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Chat execution failed: {e}\nTraceback:\n{tb}"
        )   


src/api/models/chain_models.py
from pydantic import BaseModel, field_validator
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from datetime import datetime

class ChainServerRequest(BaseModel):
    """Unified request model for the chain-server endpoint"""
    
    corporate_client_email: Optional[str] = None
    corporate_client_names: Optional[str] = None
    rbc_employee_email: Optional[str] = None
    meeting_datetime: str = Field(..., description="Meeting date and time (required)")
    corporate_company_name: str = Field(..., description="Corporate company name (required)")
    verbose: Optional[bool] = False
    @field_validator('meeting_datetime')
    @classmethod
    def validate_meeting_datetime(cls, v):
        if not v or not v.strip():
            raise ValueError('meeting_datetime cannot be empty')
        
        # Validate date format (YYYY-MM-DD)
        try:
            datetime.strptime(v.strip(), '%Y-%m-%d')
        except ValueError:
            raise ValueError('meeting_datetime must be in YYYY-MM-DD format (e.g., 2025-01-12)')
        
        return v
    

    @field_validator('corporate_company_name')
    @classmethod
    def validate_company_name(cls, v):
        if not v or not v.strip():
            raise ValueError('corporate_company_name cannot be empty')
        return v




class ChatRequest(BaseModel):
    """Request model for the chain-server-chat endpoint"""
    meeting_datetime: str = Field(..., description="Meeting date and time (required)")
    corporate_company_name: str = Field(..., description="Corporate company name (required)")
    user_query: str = Field(..., description="User question/query (required)")

    @field_validator('meeting_datetime')
    @classmethod
    def validate_meeting_datetime(cls, v):
        if not v or not v.strip():
            raise ValueError('meeting_datetime cannot be empty')
        
        try:
            datetime.strptime(v.strip(), '%Y-%m-%d')
        except ValueError:
            raise ValueError('meeting_datetime must be in YYYY-MM-DD format (e.g., 2025-01-12)')
        
        return v

    @field_validator('corporate_company_name')
    @classmethod
    def validate_company_name(cls, v):
        if not v or not v.strip():
            raise ValueError('corporate_company_name cannot be empty')
        return v

    @field_validator('user_query')
    @classmethod
    def validate_user_query(cls, v):
        if not v or not v.strip():
            raise ValueError('user_query cannot be empty')
        return v


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
import asyncio
from base64 import b64encode
import json
from pydantic import BaseModel, Field, ValidationError
import jwt
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def timed_lru_cache(seconds: int, maxsize: int = 1):
    def wrapped_cache(func):
        func = lru_cache(maxsize=maxsize)(func)
        func.lifetime = datetime.timedelta(seconds=seconds)
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


def async_timed_lru_cache(seconds: int, maxsize: int = 128):
    """
    Async LRU cache with TTL support.
    Returns (result, was_cached) tuple to track cache hits/misses.
    """
    def decorator(func):
        # Store cache and metadata
        cache = {}
        cache_times = {}
        cache_order = []  # For LRU tracking
        lifetime = datetime.timedelta(seconds=seconds)
        
        @wraps(func)
        async def wrapper(*args, **kwargs):
            nonlocal cache, cache_times, cache_order
            
            # Create cache key from args and kwargs
            key = str(args) + str(sorted(kwargs.items()))
            
            # Check if key exists and is not expired
            now = datetime.datetime.now()
            if key in cache:
                cache_time = cache_times.get(key)
                if cache_time and (now - cache_time) < lifetime:
                    # Move to end (most recently used)
                    if key in cache_order:
                        cache_order.remove(key)
                    cache_order.append(key)
                    logger.info(f"Cache HIT for {func.__name__} with key: {key[:50]}...")
                    return cache[key], True
                else:
                    # Expired, remove from cache
                    logger.info(f"Cache EXPIRED for {func.__name__} with key: {key[:50]}...")
                    del cache[key]
                    del cache_times[key]
                    if key in cache_order:
                        cache_order.remove(key)
            
            # Cache miss - execute function
            logger.info(f"Cache MISS for {func.__name__} with key: {key[:50]}...")
            result = await func(*args, **kwargs)
            
            # Store in cache
            cache[key] = result
            cache_times[key] = now
            cache_order.append(key)
            
            # Enforce maxsize (LRU eviction)
            while len(cache) > maxsize:
                oldest_key = cache_order.pop(0)
                del cache[oldest_key]
                del cache_times[oldest_key]
                logger.info(f"Cache EVICTED oldest entry for {func.__name__}")
            
            return result, False
        
        # Add cache_clear method for manual clearing
        def cache_clear():
            nonlocal cache, cache_times, cache_order
            cache.clear()
            cache_times.clear()
            cache_order.clear()
            logger.info(f"Cache CLEARED for {func.__name__}")
        
        wrapper.cache_clear = cache_clear
        
        return wrapper
    
    return decorator


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


def async_time_it(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = await func(*args, **kwargs)
        elapsed = time.perf_counter() - start_time
        logger.info(f"Execution time for {func.__name__}: {elapsed:.2f} seconds")
        return result, elapsed
    return wrapper

class AuthHeaderTokens(BaseModel):
    server_secret: str | None
    user_id_token: str | None
    connector_access_tokens: dict[str, str] = Field(default_factory=dict)

def create_bearer_token( server_secret:str, email=''):
    user_id_token = jwt.encode(payload={"email": email}, key="does-not-matter")
    header = AuthHeaderTokens(
        server_secret=server_secret,
        user_id_token=user_id_token,
        connector_access_tokens={"google": "abc"},
    )
    header_as_json = json.dumps(header.model_dump())
    header_as_b64 = b64encode(header_as_json.encode()).decode()
    return header_as_b64


def create_dynamic_token_factory(server_token: str, server_secret: str):
    def dynamic_token(**kwargs):
        user_token = create_bearer_token(server_secret)
        token = user_token if user_token else server_token
        print(
            f"Final token being used: {'user_token' if user_token else 'server_token'}"
        )

        if token:
            return httpx.AsyncClient(
                headers={"Authorization": f"Bearer {token}"},
                timeout=120.0,
                follow_redirects=True,
            )
        else:
            # Fallback for when no token is available
            return httpx.AsyncClient(timeout=120.0, follow_redirects=True)

    return dynamic_token



src/main.py
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from src.config.configuration import get_config
from src.api.endpoints.chain_server import router as chain_server_router

from typing import Optional

app = FastAPI(
    title="ISA0 Aiden Chain Server",
    description="Unified API service that orchestrates all chain modules through a single endpoint",
    version="2.0.0"
)

# Add CORS middleware (customize origins as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the unified chain server router
app.include_router(
    chain_server_router,
    prefix="/api",
    tags=["Chain Server"]
)


# Root endpoint for health check
@app.get("/")
async def root():
    return {"message": "ISA0 Aiden Chain Server is running", "status": "healthy"}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "isa0-aiden-chain-server"}


if __name__ == "__main__":
    import os
    import uvicorn
    import asyncio
    


    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", "8081"))
    uvicorn.run(app, host=host, port=port)


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
                    "corporate_client_firm_response": context_builder_output.get("corporate_client_firm_response"),
                    "temporal_content_response": context_builder_output.get("temporal_content_response"),
                    "rbc_persona": context_builder_output.get("rbc_persona"),
                    "corporate_client_persona": context_builder_output.get("corporate_client_persona"),
                    "timings": context_builder_output.get("timings", {}),
                    "cached": context_builder_output.get("cached"),
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
                    "cached": response_builder_output.get("cached"),
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


src/services/chat_service.py
"""
Chat Service Module
Handles chat queries by retrieving agent content and making LLM calls.
"""

import logging
import json
from typing import Dict, Any
from src.services.response_builder_and_generator import ResponseBuilderAndGenerator
from src.services.llm.client import call_llm_raw
from src.services.enums import ToolName
from src.utils.utils import async_time_it
from src.services.llm_prompts import CHAT_SYSTEM_PROMPT, CHAT_USER_PROMPT
from src.services.data_models.llm_schemas import ChatResponse

logger = logging.getLogger(__name__)


class ChatService:
    """Service class for handling chat queries with agent content context"""

    @staticmethod
    async def chat(
        user_query: str,
        company_name: str,
        subqueries_by_agent: dict
    ) -> Dict[str, Any]:
        """
        Handle chat queries by retrieving agent content and making LLM call.
        Returns chat response with agent content context.
        """
        errors = {}
        
        # Execute subqueries on data agents (will use cached results)
        (data_agent_chunks, agent_errors, cache_info), timing = await async_time_it(
            ResponseBuilderAndGenerator.execute_subqueries_on_data_agents
        )(subqueries_by_agent)
        
        if agent_errors:
            errors["data_agents"] = agent_errors
        
        # Parse agent responses
        (parsed_data_agent_chunks, parse_errors), parse_timing = await async_time_it(
            ResponseBuilderAndGenerator.context_parser
        )(data_agent_chunks)
        
        if parse_errors:
            errors["parsing"] = parse_errors
        
        # Build chat prompt using template
        chat_prompt = CHAT_USER_PROMPT.format(
            COMPANY_NAME=company_name,
            NEWS_AGENT_CONTENT=parsed_data_agent_chunks.get(ToolName.NEWS_TOOL.value),
            EARNINGS_AGENT_CONTENT=parsed_data_agent_chunks.get(ToolName.EARNINGS_TOOL.value),
            SEC_AGENT_CONTENT=parsed_data_agent_chunks.get(ToolName.SEC_TOOL.value),
            USER_QUERY=user_query
        )
        
        # Sanitize prompt
        chat_prompt = ResponseBuilderAndGenerator.sanitize_prompt_for_guardrails(chat_prompt)
        
        # Make LLM call with structured output
        try:
            schema = ChatResponse.model_json_schema()
            messages = [
                {"role": "system", "content": CHAT_SYSTEM_PROMPT},
                {"role": "user", "content": chat_prompt}
            ]
            tools = [{
                "type": "function",
                "function": {
                    "name": "generate_chat_response",
                    "description": "Generate chat response with citations and confidence assessment",
                    "parameters": schema
                }
            }]
            
            llm_response, llm_timing = await async_time_it(
                call_llm_raw
            )(
                messages=messages,
                tools=tools,
                tool_choice={"type": "function", "function": {"name": "generate_chat_response"}}
            )
            
            # Extract structured response
            try:
                tool_call = llm_response["choices"][0]["message"]["tool_calls"][0]
                arguments = json.loads(tool_call["function"]["arguments"])
                chat_response = ChatResponse(**arguments)
                
                return {
                    "answer": chat_response.answer,
                    "citations": [c.model_dump() for c in chat_response.citations],
                    "company_name": company_name,
                    "user_query": user_query,
                    "cache_info": cache_info,
                    "errors": errors if errors else None,
                    "timings": {
                        "data_agents": timing,
                        "parsing": parse_timing,
                        "llm": llm_timing
                    }
                }
            except Exception as parse_error:
                logger.error(f"Failed to parse structured response: {parse_error}", exc_info=True)
                errors["llm_parse"] = str(parse_error)
                # Fallback to basic response
                return {
                    "answer": "Sorry, I encountered an error parsing the response.",
                    "citations": [],
                    "company_name": company_name,
                    "user_query": user_query,
                    "cache_info": cache_info,
                    "errors": errors,
                    "timings": {
                        "data_agents": timing,
                        "parsing": parse_timing,
                        "llm": llm_timing if 'llm_timing' in locals() else 0
                    }
                }
                
        except Exception as e:
            logger.error(f"LLM call failed in chat: {e}", exc_info=True)
            errors["llm"] = str(e)
            return {
                "answer": "Sorry, I encountered an error processing your question.",
                "citations": [],
                "company_name": company_name,
                "user_query": user_query,
                "cache_info": cache_info,
                "errors": errors,
                "timings": {
                    "data_agents": timing,
                    "parsing": parse_timing,
                    "llm": 0
                }
            }

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
import time
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
from src.utils.utils import async_timed_lru_cache

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

            async with httpx.AsyncClient(timeout=ContextBuilderService.HTTP_TIMEOUT) as client:
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

            async with httpx.AsyncClient(timeout=ContextBuilderService.HTTP_TIMEOUT) as client:
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
    @async_timed_lru_cache(
        seconds=int(os.getenv("CONTEXT_BUILDER_CACHE_SECONDS", "3600")), 
        maxsize=int(os.getenv("CONTEXT_BUILDER_CACHE_SIZE", "128"))
    )
    async def _execute_cached(corporate_company_name):
        """Cached implementation - caches data AND timings"""
        timings = {}
        errors = {}

        # Step 1: Corporate client firm extractor
        (corporate_client_firm_response_raw, corporate_client_firm_error), timings["corporate_client_firm_extractor"] = await async_time_it(
            ContextBuilderService.corporate_client_firm_extractor
        )(company_name=corporate_company_name)
        if corporate_client_firm_error:
            errors["corporate_client_firm_extractor"] = corporate_client_firm_error

        # Step 2: Parse corporate client firm response
        t0 = asyncio.get_event_loop().time()
        corporate_client_firm_response, parse_corporate_client_firm_error = ContextBuilderService.parse_corporate_client_firm_extractor_response(
            corporate_client_firm_response_raw
        )
        timings["parse_corporate_client_firm_extractor_response"] = asyncio.get_event_loop().time() - t0
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

     
        if errors:
            logger.warning(f"Errors encountered for company '{corporate_company_name}': {errors}")
            raise ValueError(f"Pipeline execution failed with errors: {errors}")

        
        return corporate_client_firm_response, temporal_content_response, timings


    @staticmethod
    async def execute(request: ChainServerRequest) -> ContextBuilderOutput:
        """
        Execute the full context builder pipeline.
        """
        
        start_time = time.perf_counter()
        
        try:
       
            (corporate_client_firm_response, temporal_content_response, internal_timings), was_cached = await ContextBuilderService._execute_cached(request.corporate_company_name)
            
   
            cache_lookup_time = time.perf_counter() - start_time
            
        
            if was_cached:
            
                timings = {
                    "cache_lookup": cache_lookup_time,  
                    "corporate_client_firm_extractor": 0.0,
                    "parse_corporate_client_firm_extractor_response": 0.0,
                    "temporal_content_extractor": 0.0,
                    "parse_temporal_content_extractor_response": 0.0
                }
                logger.info(f"Cache HIT for '{request.corporate_company_name}' (lookup: {cache_lookup_time:.4f}s)")
            else:
           
                timings = {
                    "total_execution": cache_lookup_time,  
                    **internal_timings  
                }
                logger.info(f"Cache MISS for '{request.corporate_company_name}' (execution: {cache_lookup_time:.4f}s)")
            
            errors = {}
            
        except Exception as e:
            logger.error(f"Error executing context builder for {request.corporate_company_name}: {str(e)}")
            return {
                "corporate_client_firm_response": {},
                "temporal_content_response": {},
                "rbc_persona": False,
                "corporate_client_persona": False,
                "request_meeting_date": request.meeting_datetime,
                "request_company_name": request.corporate_company_name,
                "timings": {"error_time": time.perf_counter() - start_time},
                "cached": False,
                "errors": {"execution_error": str(e)},
            }

        # Placeholder for persona extractors
        rbc_persona = False
        corporate_client_persona = False

        # Set result at the end
        result = {
            "corporate_client_firm_response": corporate_client_firm_response,
            "temporal_content_response": temporal_content_response,
            "rbc_persona": rbc_persona,
            "corporate_client_persona": corporate_client_persona,
            "request_meeting_date": request.meeting_datetime,
            "request_company_name": request.corporate_company_name,
            "timings": timings,
            "cached": was_cached,
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
# ===== CHAT PROMPTS =====
CHAT_USER_PROMPT = """
You are an AI assistant helping answer questions about {COMPANY_NAME}.

Below is contextual information from multiple data sources:

## News Content (source_agent: 'news_agent')
{NEWS_AGENT_CONTENT}

## Earnings Content (source_agent: 'earnings_agent')
{EARNINGS_AGENT_CONTENT}

## SEC Filing Content (source_agent: 'sec_agent')
{SEC_AGENT_CONTENT}

## User Question
{USER_QUERY}

## CRITICAL INSTRUCTIONS

### Answer Requirements:
1. **Answer ONLY from provided context** - Do NOT use external knowledge
2. **Be specific and precise** - Include numbers, dates, names where available
3. **If context is insufficient**, clearly state what's missing in your answer (e.g., "I don't have Q3 2024 earnings data in the provided context")
4. **Be concise** - Direct answers, no unnecessary elaboration

### Citation Requirements (MANDATORY):
1. **Every factual claim must be cited** - No unsupported statements
2. **Use verbatim quotes** (10-200 words) - Copy exact text from context
3. **Specify source_agent** - Which agent: 'news_agent', 'earnings_agent', or 'sec_agent'
4. **Explain reasoning** - How the quote supports your claim
5. **Provide 2-5 citations minimum** - More for complex answers

## Anti-Hallucination Rules:
- ❌ Do NOT fabricate numbers, dates, or facts
- ❌ Do NOT paraphrase - use exact quotes in citations
- ❌ Do NOT assume information not explicitly stated
- ✅ Say "I don't know" if context lacks information
- ✅ State clearly in your answer what information is unavailable
"""

CHAT_SYSTEM_PROMPT = """
You are an expert financial analyst assistant with strict source attribution requirements. Your responses must be:
1. Grounded exclusively in provided context
2. Supported by verbatim citations with source tracking
3. Honest about missing information - state clearly in your answer what you don't know
4. Precise with numbers, dates, and facts
5. Conservative - prefer "I don't know" over speculation

NEVER make up information. ALWAYS cite sources with verbatim quotes.
"""

# ===== NEWS SUMMARY PROMPT (LLM Call 1) =====
NEWS_SUMMARY_PROMPT = """
## Task: News Summary for {COMPANY_NAME}

You are preparing a news summary for {COMPANY_NAME} for an RBC Capital Markets client meeting.

## Data Source:

[NEWS_AGENT - 100% of content]
{NEWS_AGENT_CONTENT}

---

## Required Output: News Summary (3-5 thematic categories)

**Source: 100% from NEWS_AGENT**

**If NEWS_AGENT content is empty/unavailable, return empty list: `[]`**

### Filtering Rules (FIRM-LEVEL ONLY):
**INCLUDE:**
- Executive hires/departures (names, titles, previous roles)
- Fund closes, strategic pivots, geographic expansion
- Regulatory issues, lawsuits, controversies affecting the firm
- Product launches, partnerships, strategic initiatives
- Major organizational restructuring or M&A (firm acquiring or being acquired)
- Market expansion, competitive positioning changes

**STRICTLY EXCLUDE:**
- Individual portfolio company acquisitions/exits
- Portfolio company operational updates
- General market commentary or industry trends (unless directly affecting firm)

### Required Format:
List of dictionaries, each with:
- **Key**: Thematic heading (e.g., "Product Launches", "Market Expansion", "Regulatory Updates", "Leadership Changes", "Strategic Partnerships")
- **Value**: List of 2-4 news bullets (15-30 words each)

**Example**:
```json
[
  {{"Product Launches": ["Launched new AI chip series with 50% performance improvement over previous generation", "Announced partnership with major cloud provider for next-gen data centers"]}},
  {{"Market Expansion": ["Expanded operations into Southeast Asia with new manufacturing facility in Vietnam", "Secured $5B contract with European automotive consortium"]}}
]
```

Group related news items under logical themes. Focus on material news from last 6-12 months. Prioritize news impacting:
1. Company strategy/operations (highest priority)
2. Sector dynamics
3. Broader market context (lowest priority)

**Each bullet should be concise but informative with specific details (names, figures, dates where available).**
"""

NEWS_SUMMARY_SYSTEM_PROMPT = """
You are an expert investment banking analyst preparing news summaries for client meetings. Focus on firm-level developments only. Extract specific details (names, figures, dates) from the news content. Group related news under logical themes. Eliminate generic observations - every point should be specific to this company and backed by the provided news articles.
"""

# ===== EARNINGS SUMMARY PROMPT (LLM Call 2) =====
EARNINGS_SUMMARY_PROMPT = """
## Task: Earnings Summary for {COMPANY_NAME}

You are providing a high-impact and concise earnings call summary for {COMPANY_NAME}'s latest earnings call to be used by bulge bracket investment bankers. 300 words max total.

## Data Source:

[EARNINGS_AGENT - 100% of content]
{EARNINGS_AGENT_CONTENT}

---

## Required Output: Earnings Summary (3-4 thematic categories)

**Source: 100% from EARNINGS_AGENT**

**If EARNINGS_AGENT content is empty/unavailable, return empty list: `[]`**

### Required Format:
**[Company Name] Q[Quarter] [Year] Earnings Summary (Call Date: [insert date of call in month day, year format])**

### Required Themes (as dictionary keys):

1. **Financial Highlights**
   - Revenue of $[X]B, up/down [Y]% YoY, driven by [key segment]. [Metric] margin at [Z]%, [vs. guidance/expectations]. EPS of $[X] vs. consensus of $[Y].

2. **Forward Guidance & Outlook**
   - Management guides [key metric] to $[X]–$[Y] [period], reflecting [primary driver]. Demand trends [positive/challenged] due to [macro factors: inflation, FX, rates, etc.]. Key growth levers include [1–2 initiatives].

3. **Segment Performance**
   - [Segment 1]: $[X]B revenue, [+/– Y]% growth, [Z]% margin. [Segment 2]: $[X]B revenue, [+/– Y]% growth, [Z]% margin. Performance driven by [pricing/volume/mix shifts].

4. **Key Q&A Takeaways**
   - [Topic 1]: Management addressed [specific concern regarding market dynamics, competition, or execution]. [Supporting data point or strategic rationale].
   - [Topic 2]: [Key insight on guidance, margin trajectory, or business momentum]. [Relevant context or management commentary on outlook].
   - [Topic 3]: [Strategic response to sector headwinds or growth opportunity]. [Action plan or expected impact].

### Additional Themes (include if relevant):

5. **Market Trends & Competitive Positioning**
   - [Industry trend impacting sector]. Competitive environment [stable/intensifying]; company's market position [stable/gaining/losing share] due to [key factor].

6. **Margin & Cost Drivers**
   - [Primary cost pressure: labor, commodities, logistics]. Margin performance [improved/pressured] by [pricing realization vs. cost inflation]. Management targeting [efficiency initiatives/pricing actions].

7. **Capital Allocation**
   - Capex: $[X]B ([maintenance/growth] focused). Shareholder returns: [dividend/buyback updates]. Net debt: $[X]B; liquidity position [strong/tight].

**Output as list of dictionaries**: Each dictionary has ONE theme as key and list of 2-4 bullets (15-30 words each) as value.

**Example**:
```json
[
  {{"Financial Highlights": ["Revenue of $28.1B, up 12% YoY, driven by Cloud Services growth. Operating margin at 35%, exceeding guidance. EPS of $2.15 vs. consensus of $2.08."]}},
  {{"Forward Guidance & Outlook": ["Management guides Q4 revenue to $29-30B, reflecting strong cloud demand. Demand trends positive due to AI infrastructure buildout. Key growth levers include enterprise AI adoption."]}}
]
```
"""

EARNINGS_SUMMARY_SYSTEM_PROMPT = """
You are an expert investment banking analyst preparing earnings summaries for client meetings. Extract specific financial metrics, guidance figures, and management commentary from the earnings call transcript. Focus on material information that impacts investment decisions. Be precise with numbers and dates. Eliminate generic observations.
"""

# ===== RECENT DEVELOPMENTS PROMPT (LLM Call 3) =====
RECENT_DEVELOPMENTS_PROMPT = """
## Task: Recent Developments for {COMPANY_NAME}

You are preparing a recent developments summary for {COMPANY_NAME} for an RBC Capital Markets client meeting.

## Data Sources:

[NEWS_AGENT]
Agent Guidance:
- Include {NEWS_percentage}% of insights from this agent
- Extract dates and source URLs for recent developments
{NEWS_AGENT_CONTENT}

[EARNINGS_AGENT]
Agent Guidance:
- Include {EARNINGS_percentage}% of insights from this agent
{EARNINGS_AGENT_CONTENT}

---

## Required Output: Recent Developments (4-6 items)

**Source Distribution (SEC excluded):**
- **{NEWS_percentage}%** from NEWS_AGENT
- **{EARNINGS_percentage}%** from EARNINGS_AGENT

**If both NEWS and EARNINGS are empty, return empty list: `[]`. If only one has data, use 100% from available source.**

### Filtering Rules (FIRM-LEVEL ONLY):
**INCLUDE:**
- Executive hires/departures (names, titles, previous roles)
- Fund closes, strategic pivots, geographic expansion
- Regulatory issues, lawsuits, controversies affecting the firm
- Earnings beats/misses and guidance changes
- Major organizational restructuring or M&A (firm acquiring or being acquired)
- Credit rating changes, investor relations events

**STRICTLY EXCLUDE:**
- Individual portfolio company acquisitions/exits
- Portfolio company operational updates
- General market commentary or industry trends (unless directly affecting firm)

### Required Format:
Each development must be a dictionary with:
- **category**: ONE of: "News", "M&A", "Management", "Company", "Industry"
- **header**: 5-10 word title (e.g., "New CFO Appointed", "Q3 Earnings Beat Expectations")
- **date**: Extract from chunk metadata 'timestamp' field (format: YYYY-MM-DD). Convert to "MMM DD YYYY" (e.g., "Dec 11 2025"). If timestamp unavailable, use `null`.
- **description**: 20-40 words with specific details (names, figures, outcomes)
- **source_url**: **COMPLETE URL from chunk metadata including full path** (e.g., "https://finance.yahoo.com/news/article-title-123456.html"). **Do NOT use base URLs** - include the entire URL path with article slug. Use `null` if unavailable.

**Example**:
```json
[
  {{
    "category": "Management",
    "header": "Cybertruck and Model Y Chiefs Depart",
    "date": "Nov 11 2025",
    "description": "Two Tesla executives announced departures within 24 hours: Cybertruck program manager and Emmanuel Lamacchia, Model Y program head for four years.",
    "source_url": "https://finance.yahoo.com/news/tesla-cybertruck-model-y-program-172900044.html"
  }},
  {{
    "category": "Company",
    "header": "Q3 Revenue Hits Record High",
    "date": null,
    "description": "Company reported Q3 revenue of $28.1B, up 12% YoY, exceeding analyst expectations. Operating margin expanded to 35% from 32% in prior quarter.",
    "source_url": null
  }}
]
```

**URL Extraction Rules**:
1. Look for 'url:' field in chunk metadata
2. Copy the ENTIRE URL including protocol (https://), domain, path, and parameters
3. Example: `url: https://finance.yahoo.com/news/tesla-cybertruck-model-y-program-172900044.html` → use complete string
4. **NEVER truncate to base domain** (e.g., don't use "https://finance.yahoo.com" when full path is available)
5. If no URL in metadata, use `null`

**Date Extraction Note**: Look for 'timestamp:' in chunk metadata (e.g., `timestamp: 2025-11-11T17:44:27+00:00`). Extract the date portion (2025-11-11) and convert to "Nov 11 2025" format. If timestamp is missing from a chunk, use `null` for that item's date field.
"""

RECENT_DEVELOPMENTS_SYSTEM_PROMPT = """
You are an expert investment banking analyst preparing recent developments summaries for client meetings. Focus on firm-level developments only. Extract COMPLETE URLs from chunk metadata 'url:' fields - never truncate to base domains. Extract dates from chunk metadata 'timestamp' fields - convert YYYY-MM-DD format to "MMM DD YYYY" (e.g., 2025-11-11 → Nov 11 2025). If a chunk lacks timestamp or URL, use null. Filter out portfolio company updates and generic market commentary. Every development should be material and specific to this company.
"""

# ===== CORE STRATEGIC ANALYSIS PROMPT (LLM Call 4) =====
CORE_STRATEGIC_ANALYSIS_PROMPT = """
## Task: Core Strategic Analysis for {COMPANY_NAME}

You are preparing a strategic briefing for {COMPANY_NAME} for an RBC Capital Markets client meeting.

## Data Sources:

[NEWS_AGENT]
Agent Guidance:
- Include {NEWS_percentage}% of insights from this agent
- Extract dates and source URLs for recent developments
{NEWS_AGENT_CONTENT}

[EARNINGS_AGENT]
Agent Guidance:
- Include {EARNINGS_percentage}% of insights from this agent
{EARNINGS_AGENT_CONTENT}

[SEC_AGENT]
Agent Guidance:
- Include {SEC_percentage}% of insights from this agent
{SEC_AGENT_CONTENT}

---

## CRITICAL INSTRUCTIONS:

**Data Availability Handling:**
- If an agent's content is empty/unavailable, adapt accordingly
- For fields sourced from **multiple agents** (SWOT, investment_thesis, etc.): Use available agents and adjust distribution proportionally

**You must fill ALL fields in the response schema. Use empty structures (`[]`) only when source data is completely unavailable.**

---

## 1. SWOT Analysis

### Source Distribution Requirements:
- **{NEWS_percentage}%** of insights from NEWS_AGENT
- **{EARNINGS_percentage}%** of insights from EARNINGS_AGENT  
- **{SEC_percentage}%** of insights from SEC_AGENT

### Strength (4-6 bullets, 15-25 words each)
Identify competitive advantages:
- Market position and brand strength
- Financial health and operational advantages
- Proprietary capabilities and technology
- Management quality and track record

**Cite specific metrics from agent content. Distribute insights according to percentage requirements.**

### Weakness (4-6 bullets, 15-25 words each)
Identify vulnerabilities:
- Competitive disadvantages or market share erosion
- Financial constraints or margin pressures
- Operational challenges or execution risks
- Regulatory compliance issues

**Be specific and data-backed. Distribute insights according to percentage requirements.**

### Opportunity (4-6 bullets, 15-25 words each)
Identify growth vectors:
- Market expansion or geographic growth
- New products, services, or business lines
- M&A targets or partnership opportunities
- Regulatory tailwinds or emerging trends

**Focus on actionable opportunities. Distribute insights according to percentage requirements.**

### Threat (4-6 bullets, 15-25 words each)
Identify external risks:
- Competitive pressures or market disruption
- Regulatory headwinds or policy changes
- Economic conditions or macro pressures
- Technological obsolescence or industry shifts

**Prioritize material threats. Distribute insights according to percentage requirements.**

---

## 2. Investment Thesis (3-4 subheadings)

### Source Distribution:
- **{NEWS_percentage}%** from NEWS_AGENT
- **{EARNINGS_percentage}%** from EARNINGS_AGENT
- **{SEC_percentage}%** from SEC_AGENT

### Required Format:
List of dictionaries with:
- **Key**: Subheading (e.g., "Growth Drivers", "Competitive Moat", "Valuation Opportunity", "Management Quality")
- **Value**: List of 2-4 supporting bullets (15-30 words each)

**Focus on**: Why invest now? What makes this company compelling? What are the key value drivers?

---

## 3. Key Risk Highlights (5-7 critical risks)

### Source Distribution:
- **{NEWS_percentage}%** from NEWS_AGENT
- **{EARNINGS_percentage}%** from EARNINGS_AGENT
- **{SEC_percentage}%** from SEC_AGENT

Each bullet (15-30 words) must include:
- Specific risk factor
- Potential impact magnitude
- Timeline if relevant

Prioritize material risks from SEC filings, earnings calls, and recent news.

---

## 4. Strategic Opportunities (3-4 subheadings)

### Source Distribution:
- **{NEWS_percentage}%** from NEWS_AGENT
- **{EARNINGS_percentage}%** from EARNINGS_AGENT
- **{SEC_percentage}%** from SEC_AGENT

### Required Format:
List of dictionaries with:
- **Key**: Opportunity category (e.g., "M&A Advisory", "Capital Raising", "Strategic Repositioning", "Equity/Debt Offerings")
- **Value**: List of 2-3 specific opportunities (15-30 words each)

**Focus on**: Actionable opportunities for BOTH the company AND RBC Capital Markets engagement.

---

## 5. Sources (8-12 minimum)

Extract COMPLETE source URLs from chunk metadata for ALL agents used.

### Required Format:
"Source Name - Complete URL - Date (YYYY-MM-DD)"

**URL Extraction Rules**:
- Look for 'url:' field in chunk metadata
- Copy ENTIRE URL including full path (e.g., "https://finance.yahoo.com/news/article-title-123456.html")
- **NEVER truncate to base domain** - include complete article path
- For chunks without URLs, use source name only

**Example**:
```
"Yahoo Finance - https://finance.yahoo.com/news/tesla-cybertruck-model-y-program-172900044.html - 2025-11-11"
"BNN Bloomberg - https://www.bnnbloomberg.ca/business/company-news/2025/12/05/tesla-launches-low-cost-model-3-variant-in-europe/ - 2025-12-05"
"Tesla Q3 2025 Earnings Call - SEC Filing - 2025-10-22"
```

Include: SEC filings, earnings transcripts, news articles with complete URLs, press releases.

---

## Compliance Checklist:
Before finalizing, verify ALL fields are filled:
✓ strength (4-6, percentages enforced)
✓ weakness (4-6, percentages enforced)
✓ opportunity (4-6, percentages enforced)
✓ threat (4-6, percentages enforced)
✓ investment_thesis (3-4 subheadings, percentages enforced)
✓ key_risk_highlights (5-7, percentages enforced)
✓ strategic_opportunities (3-4 subheadings, percentages enforced)
✓ sources (8-12 with URLs from metadata)
"""

CORE_STRATEGIC_ANALYSIS_SYSTEM_PROMPT = """
You are an expert investment banking analyst preparing strategic briefings for client meetings. Your analysis must be concise, data-driven, and actionable. Focus on insights that help bankers engage effectively with clients. Eliminate generic observations - every point should be specific to this company and backed by evidence from the provided documents. Prioritize material information that impacts business decisions.
"""

# ===== LEGACY COMBINED PROMPT (kept for reference) =====
STRATEGIC_ANALYSIS_PROMPT = """
## Task: Strategic Analysis for Client Meeting

You are preparing a strategic briefing for {COMPANY_NAME} for an RBC Capital Markets client meeting.

## Data Sources:

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
{SEC_AGENT_CONTENT}

---

## CRITICAL INSTRUCTIONS:

**Data Availability Handling:**
- If an agent's content is empty/unavailable, adapt accordingly:
  - For fields that are **100% sourced from one agent** (news_summary, earnings_summary, recent_developments): Return empty list `[]` if that agent has no data
  - For fields sourced from **multiple agents** (SWOT, investment_thesis, etc.): Use available agents and adjust distribution proportionally

**You must fill ALL fields in the response schema. Use empty structures (`[]`) only when source data is completely unavailable.**

---

## 1. SWOT Analysis

### Source Distribution Requirements:
- **{NEWS_percentage}%** of insights from NEWS_AGENT
- **{EARNINGS_percentage}%** of insights from EARNINGS_AGENT  
- **{SEC_percentage}%** of insights from SEC_AGENT

### Strength (4-6 bullets, 15-25 words each)
Identify competitive advantages:
- Market position and brand strength
- Financial health and operational advantages
- Proprietary capabilities and technology
- Management quality and track record

**Cite specific metrics from agent content. Distribute insights according to percentage requirements.**

### Weakness (4-6 bullets, 15-25 words each)
Identify vulnerabilities:
- Competitive disadvantages or market share erosion
- Financial constraints or margin pressures
- Operational challenges or execution risks
- Regulatory compliance issues

**Be specific and data-backed. Distribute insights according to percentage requirements.**

### Opportunity (4-6 bullets, 15-25 words each)
Identify growth vectors:
- Market expansion or geographic growth
- New products, services, or business lines
- M&A targets or partnership opportunities
- Regulatory tailwinds or emerging trends

**Focus on actionable opportunities. Distribute insights according to percentage requirements.**

### Threat (4-6 bullets, 15-25 words each)
Identify external risks:
- Competitive pressures or market disruption
- Regulatory headwinds or policy changes
- Economic conditions or macro pressures
- Technological obsolescence or industry shifts

**Prioritize material threats. Distribute insights according to percentage requirements.**

---

## 2. News Summary (3-5 thematic categories)

**Source: 100% from NEWS_AGENT**

**If NEWS_AGENT content is empty/unavailable, return empty list: `[]`**

### Filtering Rules:
Apply the same firm-level filtering as Recent Developments. Focus on material news from last 6-12 months.

### Required Format:
List of dictionaries, each with:
- **Key**: Thematic heading (e.g., "Product Launches", "Market Expansion", "Regulatory Updates")
- **Value**: List of 2-4 news bullets (15-30 words each)

Group related news items under logical themes. Prioritize news impacting:
1. Company strategy/operations (highest priority)
2. Sector dynamics
3. Broader market context (lowest priority)

---

## 3. Earnings Summary (3-4 thematic categories)

**Source: 100% from EARNINGS_AGENT**

**If EARNINGS_AGENT content is empty/unavailable, return empty list: `[]`**

You are providing a high impact and concise earnings call summary using the provided format for {COMPANY_NAME}'s latest earnings call to be used by bulge bracket investment bankers. 300 words max.

### Required Format:
**[Company Name] Q[Quarter] [Year] Earnings Summary (Call Date: [insert date of call in month day, year format])**

### Required Themes (as dictionary keys):

1. **Financial Highlights**
   - Revenue of $[X]B, up/down [Y]% YoY, driven by [key segment]. [Metric] margin at [Z]%, [vs. guidance/expectations]. EPS of $[X] vs. consensus of $[Y].

2. **Forward Guidance & Outlook**
   - Management guides [key metric] to $[X]–$[Y] [period], reflecting [primary driver]. Demand trends [positive/challenged] due to [macro factors: inflation, FX, rates, etc.]. Key growth levers include [1–2 initiatives].

3. **Segment Performance**
   - [Segment 1]: $[X]B revenue, [+/– Y]% growth, [Z]% margin. [Segment 2]: $[X]B revenue, [+/– Y]% growth, [Z]% margin. Performance driven by [pricing/volume/mix shifts].

4. **Key Q&A Takeaways**
   - [Topic 1]: Management addressed [specific concern regarding market dynamics, competition, or execution]. [Supporting data point or strategic rationale].
   - [Topic 2]: [Key insight on guidance, margin trajectory, or business momentum]. [Relevant context or management commentary on outlook].
   - [Topic 3]: [Strategic response to sector headwinds or growth opportunity]. [Action plan or expected impact].

### Additional Themes (include if relevant):

5. **Market Trends & Competitive Positioning**
   - [Industry trend impacting sector]. Competitive environment [stable/intensifying]; company's market position [stable/gaining/losing share] due to [key factor].

6. **Margin & Cost Drivers**
   - [Primary cost pressure: labor, commodities, logistics]. Margin performance [improved/pressured] by [pricing realization vs. cost inflation]. Management targeting [efficiency initiatives/pricing actions].

7. **Capital Allocation**
   - Capex: $[X]B ([maintenance/growth] focused). Shareholder returns: [dividend/buyback updates]. Net debt: $[X]B; liquidity position [strong/tight].

**Output as list of dictionaries**: Each dictionary has ONE theme as key and list of 2-4 bullets (15-30 words each) as value.

---

## 4. Recent Developments (4-6 items)

**Source: NEWS_AGENT + EARNINGS_AGENT (SEC excluded)**

**If both NEWS and EARNINGS are empty, return empty list: `[]`. If only one has data, use 100% from available source.**

See RECENT_DEVELOPMENTS_PROMPT for detailed instructions on filtering rules and required format.

---

## 5. Investment Thesis (3-4 subheadings)

### Source Distribution:
- **{NEWS_percentage}%** from NEWS_AGENT
- **{EARNINGS_percentage}%** from EARNINGS_AGENT
- **{SEC_percentage}%** from SEC_AGENT

### Required Format:
List of dictionaries with:
- **Key**: Subheading (e.g., "Growth Drivers", "Competitive Moat", "Valuation Opportunity", "Management Quality")
- **Value**: List of 2-4 supporting bullets (15-30 words each)

**Focus on**: Why invest now? What makes this company compelling? What are the key value drivers?

---

## 6. Key Risk Highlights (5-7 critical risks)

### Source Distribution:
- **{NEWS_percentage}%** from NEWS_AGENT
- **{EARNINGS_percentage}%** from EARNINGS_AGENT
- **{SEC_percentage}%** from SEC_AGENT

Each bullet (15-30 words) must include:
- Specific risk factor
- Potential impact magnitude
- Timeline if relevant

Prioritize material risks from SEC filings, earnings calls, and recent news.

---

## 7. Strategic Opportunities (3-4 subheadings)

### Source Distribution:
- **{NEWS_percentage}%** from NEWS_AGENT
- **{EARNINGS_percentage}%** from EARNINGS_AGENT
- **{SEC_percentage}%** from SEC_AGENT

### Required Format:
List of dictionaries with:
- **Key**: Opportunity category (e.g., "M&A Advisory", "Capital Raising", "Strategic Repositioning", "Equity/Debt Offerings")
- **Value**: List of 2-3 specific opportunities (15-30 words each)

**Focus on**: Actionable opportunities for BOTH the company AND RBC Capital Markets engagement.

---

## 8. Sources (8-12 minimum)

Extract source URLs from chunk metadata for ALL agents used.

### Required Format:
"Source Name - URL - Date Accessed (YYYY-MM-DD)"

Include: SEC filings, earnings transcripts, news articles, press releases.

---

## Compliance Checklist:
Before finalizing, verify ALL fields are filled:
✓ strength (4-6, percentages enforced)
✓ weakness (4-6, percentages enforced)
✓ opportunity (4-6, percentages enforced)
✓ threat (4-6, percentages enforced)
✓ news_summary (3-5 themes, 100% news)
✓ earnings_summary (3-4 themes, 100% earnings)
✓ recent_developments (4-6, 100% from news/earnings)
✓ investment_thesis (3-4 subheadings, percentages enforced)
✓ key_risk_highlights (5-7, percentages enforced)
✓ strategic_opportunities (3-4 subheadings, percentages enforced)
✓ sources (8-12 with URLs from metadata)
"""









STRATEGIC_ANALYSIS_SYSTEM_PROMPT = """
You are an expert investment banking analyst preparing strategic briefings for client meetings. Your analysis must be concise, data-driven, and actionable. Focus on insights that help bankers engage effectively with clients. Eliminate generic observations - every point should be specific to this company and backed by evidence from the provided documents. Prioritize material information that impacts business decisions.
"""

src/services/new_tool_call.py
import os 
import time 
from src.services.response_builder_and_generator import ResponseBuilderAndGenerator
from src.services.enums import ToolName
from src.utils.utils import async_timed_lru_cache
from rbc_security import enable_certs
from src.utils.utils import create_bearer_token, create_dynamic_token_factory
from langchain_mcp_adapters.client import MultiServerMCPClient
enable_certs()



# @async_timed_lru_cache(seconds=int(os.getenv("OAUTH_TOKEN_EXPIRATION")), maxsize=128)
async def get_client():
    multi_mcp_client_config = {}

    for tool in ToolName:
        parsed_agent_name = tool.value.upper().split("_")[0]
        server_secret = os.getenv(f"{parsed_agent_name}_AGENT_MCP_SECRET")
        bearer_token = create_bearer_token(server_secret)
        server_url = os.getenv(f"{parsed_agent_name}_AGENT_MCP_URL")
        multi_mcp_client_config[tool.value] = {
             "url": server_url,
                    "transport": "streamable_http",
                    "httpx_client_factory": create_dynamic_token_factory(
                        bearer_token, server_secret
                    )
        }
    
    client = MultiServerMCPClient(
            multi_mcp_client_config
        )
    
    return client
    

# @async_timed_lru_cache(seconds=int(os.getenv("OAUTH_TOKEN_EXPIRATION")), maxsize=128)
async def get_agent_tool(tool_name):
    client = await get_client()
    tools = await client.get_tools()

    
    for tool in tools:
        if tool.name == tool_name:
            return tool



if __name__ == "__main__":
    import asyncio

    async def main():
        agent_name = "earnings_agent"
        parsed_agent_name = agent_name.upper().split("_")[0]

        tool_name = os.getenv(f"{parsed_agent_name}_AGENT_MCP_TOOL")
        company_name = "Microsoft"


        from src.services.static_subquery_engine import StaticSubqueryEngine
        tool_arguments = StaticSubqueryEngine.get_earnings_agent_query_argument(company_name, fiscal_year="2025", fiscal_quarter="1")

        
        
        tool = await get_agent_tool(tool_name)

        for id, tool_argument in enumerate(tool_arguments):
            try:
                result = await tool.ainvoke(tool_argument)

                print(type(result))
                print("############ PARSED ##############################")

                chunks = await ResponseBuilderAndGenerator.parse_earnings_agent_response(result)

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

                print("#"*10)
                print(f"Succesfully Parsed: {id}")
                print("#"*10)

            except Exception as e:
                print("#"*10)
                print(f"Error invoking tool for argument set {id}: {e}")
                print("#"*10)
                continue



        # result_list = eval(result)

        # for chunk in result_list:
        #     print("\n\n\n")
        #     for key, item in chunk.items():
        #         print("#"*10)
        #         print(key)
        #         print("#"*10)
        #         print(item)


        # content = "\n\n".join([chunk.get("text") for chunk in result_list])
        # print(content)

    for _ in range(1):
        asyncio.run(main())
        time.sleep(1)


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
from src.utils.utils import async_timed_lru_cache
from rbc_security import enable_certs
from src.utils.utils import create_bearer_token, create_dynamic_token_factory
from langchain_mcp_adapters.client import MultiServerMCPClient
enable_certs()


from src.services.llm.client import call_llm_raw
from src.services.data_models.models  import ContextBuilderOutput, ContentPrioritizationOutput, ResponseBuilderOutput

from src.utils.utils import async_time_it
from src.services.llm_prompts import (
            NEWS_SUMMARY_PROMPT,
            NEWS_SUMMARY_SYSTEM_PROMPT,
            EARNINGS_SUMMARY_PROMPT,
            EARNINGS_SUMMARY_SYSTEM_PROMPT,
            RECENT_DEVELOPMENTS_PROMPT,
            RECENT_DEVELOPMENTS_SYSTEM_PROMPT,
            CORE_STRATEGIC_ANALYSIS_PROMPT,
            CORE_STRATEGIC_ANALYSIS_SYSTEM_PROMPT
        )
from src.services.data_models.llm_schemas import (
            NewsSummaryResponse,
            EarningsSummaryResponse,
            RecentDevelopmentsResponse,
            CoreStrategicAnalysisResponse,
            StrategicAnalysisResponse
        )



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
    @async_timed_lru_cache(
        seconds=int(os.getenv("DATA_AGENT_CACHE_SECONDS")),
        maxsize=int(os.getenv("DATA_AGENT_CACHE_SIZE"))
    )
    async def _execute_agent_subqueries_cached(agent_name: str, subqueries: tuple):
        """Cached version - used for agents with caching enabled."""
        result = await ResponseBuilderAndGenerator._execute_agent_subqueries_impl(agent_name, subqueries)
        return result
    

    @async_timed_lru_cache(seconds=int(os.getenv("MULTI_MCP_AGENT_CLIENT_CACHE_SECONDS")), maxsize=1)
    async def get_multi_mcp_agent_client():
        multi_mcp_client_config = {}

        for tool in ToolName:
            parsed_agent_name = tool.value.upper().split("_")[0]
            server_secret = os.getenv(f"{parsed_agent_name}_AGENT_MCP_SECRET")
            bearer_token = create_bearer_token(server_secret)
            server_url = os.getenv(f"{parsed_agent_name}_AGENT_MCP_URL")
            multi_mcp_client_config[tool.value] = {
                "url": server_url,
                        "transport": "streamable_http",
                        "httpx_client_factory": create_dynamic_token_factory(
                            bearer_token, server_secret
                        )
            }
        
        client = MultiServerMCPClient(
                multi_mcp_client_config
            )
        
        return client
    
    @async_timed_lru_cache(seconds=int(os.getenv("AGENT_TOOL_CACHE_SECONDS")), maxsize=int(os.getenv("AGENT_TOOL_CACHE_SIZE")))
    async def get_agent_tool(tool_name):
        client, _ = await ResponseBuilderAndGenerator.get_multi_mcp_agent_client()
        tools = await client.get_tools()

        
        for tool in tools:
            if tool.name == tool_name:
                return tool
        

    

    @staticmethod
    async def _execute_agent_subqueries_impl(agent_name: str, subqueries: tuple):
        """
        Core implementation of agent subquery execution (no caching).
        Executes all subqueries for this agent in parallel.
        """
        parsed_agent_name = agent_name.upper().split("_")[0]
        tool_name = os.getenv(f"{parsed_agent_name}_AGENT_MCP_TOOL")

        agent_chunks = []
        subquery_errors = []
        tool,_ = await ResponseBuilderAndGenerator.get_agent_tool(tool_name)
        
        async def execute_single_subquery(subquery_tuple):
            """Execute a single subquery and return (result, error) tuple"""
            try:
                subquery_dict = dict(subquery_tuple)
                
                # Get result from tool
                result = await tool.ainvoke(subquery_dict)
                
                # Parse IMMEDIATELY (like in new_tool_call.py)
                if result:
                    if agent_name == ToolName.EARNINGS_TOOL.value:
                        parsed_result = await ResponseBuilderAndGenerator.parse_earnings_agent_response(result)
                        return (parsed_result, None)
                    else:
                        try:
                            parsed_result = ast.literal_eval(result)
                            return (parsed_result, None)
                        except Exception as parse_error:
                            error_msg = f"Failed to parse result for subquery {subquery_dict}: {parse_error}"
                            logger.error(f"{agent_name}: {error_msg}")
                            return (None, error_msg)
                else:
                    error_msg = f"No content returned for subquery: {subquery_dict}"
                    logger.warning(f"{agent_name}: {error_msg}")
                    return (None, error_msg)
            except Exception as e:
                error_msg = f"Error for subquery {subquery_dict if 'subquery_dict' in locals() else subquery_tuple}: {e}"
                logger.error(f"{agent_name}: {error_msg}", exc_info=True)
                return (None, error_msg)
        
        try:
            # Execute all subqueries in parallel
            tasks = [execute_single_subquery(subquery_tuple) for subquery_tuple in subqueries]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for result in results:
                if isinstance(result, Exception):
                    error_msg = f"Unexpected exception: {result}"
                    logger.error(f"{agent_name}: {error_msg}")
                    subquery_errors.append(error_msg)
                else:
                    parsed_result, error = result
                    if error:
                        subquery_errors.append(error)
                    elif parsed_result:
                        agent_chunks.append(parsed_result)
                    
        except Exception as e:
            error_msg = f"Error initializing MCP session for {agent_name}: {e}"
            logger.error(error_msg, exc_info=True)
            raise ValueError(error_msg)
        
        if subquery_errors:
            error_summary = f"{agent_name} had {len(subquery_errors)} subquery error(s): {subquery_errors}"
            logger.warning(error_summary)
            raise ValueError(error_summary)
        
        if not agent_chunks:
            raise ValueError(f"No chunks retrieved for agent {agent_name} with subqueries {subqueries}")
        
        return agent_chunks

    @staticmethod
    async def _execute_agent_subqueries(agent_name: str, subqueries: tuple):
        cache_enabled = os.getenv(f"{agent_name}_CACHE").lower() == "true"
        
        if cache_enabled:
            result, was_cached = await ResponseBuilderAndGenerator._execute_agent_subqueries_cached(agent_name, subqueries)
            
            # Return immediately on cache hit (no timing overhead)
            if was_cached:
                logger.info(f"{agent_name}: Cache HIT")
                return result, True
            
            logger.info(f"{agent_name}: Cache MISS - fetching fresh")
            return result, False
        else:
            result = await ResponseBuilderAndGenerator._execute_agent_subqueries_impl(agent_name, subqueries)
            return result, False

    @staticmethod
    async def execute_subqueries_on_data_agents(subqueries_by_agent: dict):
        """
        Execute subqueries on data agents with caching per agent.
        Returns data_agent_chunks, errors, and cache_info.
        
        Uses cached _execute_agent_subqueries for each agent to avoid redundant API calls.
        """
        data_agent_chunks = {
            ToolName.NEWS_TOOL.value: [], 
            ToolName.EARNINGS_TOOL.value: [], 
            ToolName.SEC_TOOL.value: []
        }
        errors = {}
        cache_info = {}

        # Create tasks for all agents to run concurrently
        agent_tasks = []
        agent_names = []
        
        for agent_name, subqueries in subqueries_by_agent.items():
            # Convert subqueries list to tuple for hashability (required for cache key)
            subqueries_tuple = tuple(
                tuple(sorted(sq.items())) if isinstance(sq, dict) else sq 
                for sq in subqueries
            )
            
            # Create task for this agent
            task = ResponseBuilderAndGenerator._execute_agent_subqueries(
                agent_name=agent_name,
                subqueries=subqueries_tuple
            )
            agent_tasks.append(task)
            agent_names.append(agent_name)
        
        # Execute all agents concurrently
        results = await asyncio.gather(*agent_tasks, return_exceptions=True)
        
        # Process results
        for agent_name, result in zip(agent_names, results):
            if isinstance(result, Exception):
                # Agent failed - log error but don't cache
                error_msg = str(result)
                errors[agent_name] = [error_msg]
                cache_info[agent_name] = False
                logger.error(f"Agent {agent_name} failed: {error_msg}")
            else:
                # Agent succeeded - unpack (chunks, was_cached) tuple
                chunks, was_cached = result
                data_agent_chunks[agent_name] = chunks
                cache_info[agent_name] = was_cached
                logger.info(f"Agent {agent_name} returned {len(chunks)} chunks (cached: {was_cached})")

        return data_agent_chunks, errors, cache_info
    
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
                    for chunks in agent_mcp_chunks_raw:

                       
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
                            
                    resp[agent] = "\n\n\n".join(formatted_output)

                elif agent == ToolName.NEWS_TOOL.value or agent == ToolName.SEC_TOOL.value:
                    agent_chunks = []
                    for parsed in agent_mcp_chunks_raw:
                        for idx, article in enumerate(parsed):
                            if not isinstance(article, dict):
                                continue
                            main_text = article.get("text", "")
                            metadata = {k: v for k, v in article.items() if k != "text"}
                           
                            chunk_number = str(idx + 1)
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
        content_prioritization_data_distribution
    ):
        """
        Builds four separate prompts for parallel LLM calls:
        1. News summary prompt (NEWS_AGENT only)
        2. Earnings summary prompt (EARNINGS_AGENT only)
        3. Recent developments prompt (NEWS_AGENT + EARNINGS_AGENT)
        4. Core strategic analysis prompt (all three agents)
        """

        # Extract percentages
        news_pct = content_prioritization_data_distribution[ToolName.NEWS_TOOL.value]
        earnings_pct = content_prioritization_data_distribution[ToolName.EARNINGS_TOOL.value]
        sec_pct = content_prioritization_data_distribution[ToolName.SEC_TOOL.value]

        # 1. News Summary Prompt (only NEWS_AGENT content)
        news_summary_prompt = NEWS_SUMMARY_PROMPT.format(
            COMPANY_NAME=company_name,
            NEWS_AGENT_CONTENT=parsed_data_agent_chunks.get(ToolName.NEWS_TOOL.value, "")
        )

        # 2. Earnings Summary Prompt (only EARNINGS_AGENT content)
        earnings_summary_prompt = EARNINGS_SUMMARY_PROMPT.format(
            COMPANY_NAME=company_name,
            EARNINGS_AGENT_CONTENT=parsed_data_agent_chunks.get(ToolName.EARNINGS_TOOL.value, "")
        )

        # 3. Recent Developments Prompt (NEWS_AGENT + EARNINGS_AGENT, SEC excluded)
        recent_developments_prompt = RECENT_DEVELOPMENTS_PROMPT.format(
            COMPANY_NAME=company_name,
            NEWS_AGENT_CONTENT=parsed_data_agent_chunks.get(ToolName.NEWS_TOOL.value, ""),
            EARNINGS_AGENT_CONTENT=parsed_data_agent_chunks.get(ToolName.EARNINGS_TOOL.value, ""),
            NEWS_percentage=news_pct,
            EARNINGS_percentage=earnings_pct
        )

        # 4. Core Strategic Analysis Prompt (all three agents)
        core_strategic_prompt = CORE_STRATEGIC_ANALYSIS_PROMPT.format(
            COMPANY_NAME=company_name,
            NEWS_AGENT_CONTENT=parsed_data_agent_chunks.get(ToolName.NEWS_TOOL.value, ""),
            EARNINGS_AGENT_CONTENT=parsed_data_agent_chunks.get(ToolName.EARNINGS_TOOL.value, ""),
            SEC_AGENT_CONTENT=parsed_data_agent_chunks.get(ToolName.SEC_TOOL.value, ""),
            NEWS_percentage=news_pct,
            EARNINGS_percentage=earnings_pct,
            SEC_percentage=sec_pct
        )

        # Sanitize prompts to avoid guardrail false positives
        news_summary_prompt = ResponseBuilderAndGenerator.sanitize_prompt_for_guardrails(news_summary_prompt)
        earnings_summary_prompt = ResponseBuilderAndGenerator.sanitize_prompt_for_guardrails(earnings_summary_prompt)
        recent_developments_prompt = ResponseBuilderAndGenerator.sanitize_prompt_for_guardrails(recent_developments_prompt)
        core_strategic_prompt = ResponseBuilderAndGenerator.sanitize_prompt_for_guardrails(core_strategic_prompt)

        return {
            "news_summary": news_summary_prompt,
            "earnings_summary": earnings_summary_prompt,
            "recent_developments": recent_developments_prompt,
            "core_strategic": core_strategic_prompt
        }
    

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
        prompts: dict
    ):
        """
        Execute four parallel LLM calls:
        1. News summary (NewsSummaryResponse)
        2. Earnings summary (EarningsSummaryResponse)
        3. Recent developments (RecentDevelopmentsResponse)
        4. Core strategic analysis (CoreStrategicAnalysisResponse)
        
        Then merge results into final StrategicAnalysisResponse.
        """
        
        # Execute all four LLM calls in parallel
        results = await asyncio.gather(
            # 1. News Summary
            ResponseBuilderAndGenerator.get_structured_response(
                user_prompt=prompts["news_summary"],
                system_prompt=NEWS_SUMMARY_SYSTEM_PROMPT,
                response_obj=NewsSummaryResponse,
                name="generate_news_summary",
                description="Generate news summary for investment banking client meeting"
            ),
            # 2. Earnings Summary
            ResponseBuilderAndGenerator.get_structured_response(
                user_prompt=prompts["earnings_summary"],
                system_prompt=EARNINGS_SUMMARY_SYSTEM_PROMPT,
                response_obj=EarningsSummaryResponse,
                name="generate_earnings_summary",
                description="Generate earnings summary for investment banking client meeting"
            ),
            # 3. Recent Developments
            ResponseBuilderAndGenerator.get_structured_response(
                user_prompt=prompts["recent_developments"],
                system_prompt=RECENT_DEVELOPMENTS_SYSTEM_PROMPT,
                response_obj=RecentDevelopmentsResponse,
                name="generate_recent_developments",
                description="Generate recent developments summary for investment banking client meeting"
            ),
            # 4. Core Strategic Analysis
            ResponseBuilderAndGenerator.get_structured_response(
                user_prompt=prompts["core_strategic"],
                system_prompt=CORE_STRATEGIC_ANALYSIS_SYSTEM_PROMPT,
                response_obj=CoreStrategicAnalysisResponse,
                name="generate_core_strategic_analysis",
                description="Generate core strategic analysis for investment banking client meeting"
            )
        )
        
        # Unpack results
        news_result, news_error = results[0]
        earnings_result, earnings_error = results[1]
        recent_devs_result, recent_devs_error = results[2]
        core_result, core_error = results[3]
        
        # Combine errors
        combined_error = None
        if news_error or earnings_error or recent_devs_error or core_error:
            errors = []
            if news_error:
                errors.append(f"News: {news_error}")
            if earnings_error:
                errors.append(f"Earnings: {earnings_error}")
            if recent_devs_error:
                errors.append(f"Recent Developments: {recent_devs_error}")
            if core_error:
                errors.append(f"Core: {core_error}")
            combined_error = "; ".join(errors)
        
        # Merge all results into StrategicAnalysisResponse
        if core_result and not core_error:
            strategic_analysis_result = StrategicAnalysisResponse(
                strength=core_result.strength,
                weakness=core_result.weakness,
                opportunity=core_result.opportunity,
                threat=core_result.threat,
                investment_thesis=core_result.investment_thesis,
                key_risk_highlights=core_result.key_risk_highlights,
                strategic_opportunities=core_result.strategic_opportunities,
                sources=core_result.sources,
                news_summary=news_result.news_summary if news_result else [],
                earnings_summary=earnings_result.earnings_summary if earnings_result else [],
                recent_developments=recent_devs_result.recent_developments if recent_devs_result else []
            )
        else:
            strategic_analysis_result = None
        
        return (strategic_analysis_result, combined_error)
    

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
        (data_agent_chunks, data_agent_errors, agent_cache_info), timings["execute_subqueries_on_data_agents"] = await async_time_it(
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
                "cached": {"data_agents": agent_cache_info},
                "errors": errors,
                "parsed_data_agent_chunks": parsed_data_agent_chunks,
                "company_name": company_name,
            }
            return result

        # Step 3: Prompt builder (creates 3 prompts)
        (prompts), timings["prompt_builder"] = await async_time_it(
            ResponseBuilderAndGenerator.prompt_builder
        )(
            parsed_data_agent_chunks=parsed_data_agent_chunks,
            company_name=company_name,
            content_prioritization_data_distribution=temporal_source_prioritizer
        )

        # Step 4: Response builder (3 parallel LLM calls)
        (strategic_analysis_result, strategic_analysis_error), timings["response_builder"] = await async_time_it(
            ResponseBuilderAndGenerator.response_builder
        )(prompts=prompts)

        if strategic_analysis_error:
            errors["strategic_analysis_response"] = strategic_analysis_error

       

        result = {
            "strategic_analysis_result": strategic_analysis_result,
            "timings": timings,
            "cached": {"data_agents": agent_cache_info},
            "errors": errors,
            "parsed_data_agent_chunks": parsed_data_agent_chunks,
            "company_name": company_name,
        }

        return result


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
      "retrieve": 1
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
        one_year_and_a_day_ago = (datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=366)).strftime('%Y-%m-%d')
        return [

    {
        "relative_date_range": "last_thirty_days",
        "entities": [f"{company_name}"],
        "topics": [
            "merger", "acquisition", "restructuring", "investor relation", "shareholder", "market expansion", "partnership"
        ]
    },
    {
        "relative_date_range": "last_thirty_days",
        "entities": [f"{company_name}"],
        "topics": [
            "product launch", "changes to leadership", "headcount", "hiring", "legal", "regulatory", "controlversies", "investigation", "executive", "appointments", "departures"
        ]
    } 


            
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

class ChatCitation(BaseModel):
    """Citation for chat responses with source tracking"""
    source_agent: str = Field(
        description="Data agent source. ONE of: 'news_agent', 'earnings_agent', 'sec_agent'"
    )
    quote: str = Field(
        description="Verbatim quote from agent content (10-200 words). Must be exact text from context. DO NOT paraphrase."
    )
    reasoning: str = Field(
        description="How this quote supports your answer. Be specific about what claim it backs up."
    )

class ChatResponse(BaseModel):
    """Structured chat response with citations"""
    answer: str = Field(
        description="Direct answer to user's question. Be concise and specific. If context is insufficient, clearly state what information is missing directly in your answer."
    )
    citations: List[ChatCitation] = Field(
        description="List of 2-5 citations supporting your answer. Each citation must include: source_agent (which agent), quote (verbatim text from context), reasoning (how it supports the answer). REQUIRED: Every factual claim in your answer must have a corresponding citation."
    )

class NewsSummaryResponse(BaseModel):
    """News-focused analysis using NEWS_AGENT data"""
    news_summary: List[Dict[str, List[str]]] = Field(
        description="Summary of recent firm-level news organized by 3-5 thematic categories. Each dictionary: ONE thematic heading as key (e.g., 'Product Launches', 'Market Expansion', 'Regulatory Updates') and 2-4 news bullets as value (15-30 words each). Source: 100% from NEWS_AGENT. Apply firm-level filtering. Focus on material news from last 6-12 months. Prioritize: (1) company strategy/operations, (2) sector dynamics, (3) broader market context."
    )

class EarningsSummaryResponse(BaseModel):
    """Earnings-focused analysis using EARNINGS_AGENT data"""
    earnings_summary: List[Dict[str, List[str]]] = Field(
        description="High-impact summary of LATEST earnings call (300 words max total). List of 3-4 dictionaries. Required themes as keys: 'Financial Highlights' (revenue, margins, EPS vs. consensus), 'Forward Guidance & Outlook' (management guidance, demand trends, growth levers), 'Segment Performance' (performance by business segment with metrics), 'Key Q&A Takeaways' (critical insights from Q&A). Optional themes: 'Market Trends & Competitive Positioning', 'Margin & Cost Drivers', 'Capital Allocation'. Each bullet: 15-30 words with specific metrics and dates. Source: 100% from EARNINGS_AGENT."
    )

class RecentDevelopmentsResponse(BaseModel):
    """Recent developments using NEWS_AGENT and EARNINGS_AGENT data"""
    recent_developments: List[Dict[str, Any]] = Field(
        description="List of 4-6 FIRM-LEVEL recent developments. Each dictionary must have: 'category' (ONE of: 'News', 'M&A', 'Management', 'Company', 'Industry'), 'header' (5-10 word title), 'date' (format: 'MMM DD YYYY'), 'description' (20-40 words with specific details, names, figures, outcomes), 'source_url' (full URL from chunk metadata, or null if unavailable - do NOT use '<UNKNOWN>' or empty string). EXCLUDE: portfolio company acquisitions/exits, portfolio company operational updates, general market commentary. Source distribution (SEC excluded): NEWS_percentage% from NEWS_AGENT, EARNINGS_percentage% from EARNINGS_AGENT."
    )

class CoreStrategicAnalysisResponse(BaseModel):
    """Core strategic analysis using all three agents"""
    strength: List[str] = Field(
        description="List of 4-6 competitive strengths from SWOT analysis. Each bullet: 15-25 words, specific, data-backed. Focus on: market position, brand strength, financial health, operational advantages, proprietary capabilities, technology, management quality. Cite specific metrics. Source distribution: NEWS_percentage% from NEWS_AGENT, EARNINGS_percentage% from EARNINGS_AGENT, SEC_percentage% from SEC_AGENT."
    )
    weakness: List[str] = Field(
        description="List of 4-6 vulnerabilities from SWOT analysis. Each bullet: 15-25 words, specific, data-backed. Focus on: competitive disadvantages, market share erosion, financial constraints, margin pressures, operational challenges, execution risks, regulatory compliance issues. Source distribution: NEWS_percentage% from NEWS_AGENT, EARNINGS_percentage% from EARNINGS_AGENT, SEC_percentage% from SEC_AGENT."
    )
    opportunity: List[str] = Field(
        description="List of 4-6 growth opportunities from SWOT analysis. Each bullet: 15-25 words, actionable. Focus on: market expansion, geographic growth, new products/services/business lines, M&A targets, partnership opportunities, regulatory tailwinds, emerging trends. Source distribution: NEWS_percentage% from NEWS_AGENT, EARNINGS_percentage% from EARNINGS_AGENT, SEC_percentage% from SEC_AGENT."
    )
    threat: List[str] = Field(
        description="List of 4-6 external threats from SWOT analysis. Each bullet: 15-25 words, specific. Focus on: competitive pressures, market disruption, regulatory headwinds, policy changes, economic/macro conditions, technological obsolescence, industry shifts. Prioritize material threats. Source distribution: NEWS_percentage% from NEWS_AGENT, EARNINGS_percentage% from EARNINGS_AGENT, SEC_percentage% from SEC_AGENT."
    )
    
    investment_thesis: List[Dict[str, List[str]]] = Field(
        description="Investment thesis structured as list of 3-4 dictionaries. Each dictionary: ONE subheading as key (e.g., 'Growth Drivers', 'Competitive Moat', 'Valuation Opportunity', 'Management Quality') and 2-4 supporting bullets as value (15-30 words each). Focus on: Why invest now? What makes this company compelling? What are key value drivers? Source distribution: NEWS_percentage% from NEWS_AGENT, EARNINGS_percentage% from EARNINGS_AGENT, SEC_percentage% from SEC_AGENT."
    )
    
    key_risk_highlights: List[str] = Field(
        description="List of 5-7 critical risks. Each bullet: 15-30 words including specific risk factor, potential impact magnitude, and timeline if relevant. Prioritize material risks from SEC filings, earnings calls, and recent news. Source distribution: NEWS_percentage% from NEWS_AGENT, EARNINGS_percentage% from EARNINGS_AGENT, SEC_percentage% from SEC_AGENT."
    )
    
    strategic_opportunities: List[Dict[str, List[str]]] = Field(
        description="Strategic opportunities for the company AND RBC Capital Markets engagement. List of 3-4 dictionaries. Each dictionary: ONE subheading as key (e.g., 'M&A Advisory', 'Capital Raising', 'Strategic Repositioning', 'Equity/Debt Offerings') and 2-3 specific opportunity bullets as value (15-30 words each). Focus on actionable opportunities. Source distribution: NEWS_percentage% from NEWS_AGENT, EARNINGS_percentage% from EARNINGS_AGENT, SEC_percentage% from SEC_AGENT."
    )

    sources: List[str] = Field(
        description="Comprehensive list of 8-12 sources cited. Format: 'Source Name - URL - Date Accessed (YYYY-MM-DD)'. Extract URLs from chunk metadata for ALL agents. Include: SEC filings, earnings transcripts, news articles, press releases."
    )

class StrategicAnalysisResponse(BaseModel):
    """Combined response merging all four analysis types"""
    strength: List[str] = Field(
        description="List of 4-6 competitive strengths from SWOT analysis. Each bullet: 15-25 words, specific, data-backed. Focus on: market position, brand strength, financial health, operational advantages, proprietary capabilities, technology, management quality. Cite specific metrics. Source distribution: NEWS_percentage% from NEWS_AGENT, EARNINGS_percentage% from EARNINGS_AGENT, SEC_percentage% from SEC_AGENT."
    )
    weakness: List[str] = Field(
        description="List of 4-6 vulnerabilities from SWOT analysis. Each bullet: 15-25 words, specific, data-backed. Focus on: competitive disadvantages, market share erosion, financial constraints, margin pressures, operational challenges, execution risks, regulatory compliance issues. Source distribution: NEWS_percentage% from NEWS_AGENT, EARNINGS_percentage% from EARNINGS_AGENT, SEC_percentage% from SEC_AGENT."
    )
    opportunity: List[str] = Field(
        description="List of 4-6 growth opportunities from SWOT analysis. Each bullet: 15-25 words, actionable. Focus on: market expansion, geographic growth, new products/services/business lines, M&A targets, partnership opportunities, regulatory tailwinds, emerging trends. Source distribution: NEWS_percentage% from NEWS_AGENT, EARNINGS_percentage% from EARNINGS_AGENT, SEC_percentage% from SEC_AGENT."
    )
    threat: List[str] = Field(
        description="List of 4-6 external threats from SWOT analysis. Each bullet: 15-25 words, specific. Focus on: competitive pressures, market disruption, regulatory headwinds, policy changes, economic/macro conditions, technological obsolescence, industry shifts. Prioritize material threats. Source distribution: NEWS_percentage% from NEWS_AGENT, EARNINGS_percentage% from EARNINGS_AGENT, SEC_percentage% from SEC_AGENT."
    )
    
    investment_thesis: List[Dict[str, List[str]]] = Field(
        description="Investment thesis structured as list of 3-4 dictionaries. Each dictionary: ONE subheading as key (e.g., 'Growth Drivers', 'Competitive Moat', 'Valuation Opportunity', 'Management Quality') and 2-4 supporting bullets as value (15-30 words each). Focus on: Why invest now? What makes this company compelling? What are key value drivers? Source distribution: NEWS_percentage% from NEWS_AGENT, EARNINGS_percentage% from EARNINGS_AGENT, SEC_percentage% from SEC_AGENT."
    )
    
    key_risk_highlights: List[str] = Field(
        description="List of 5-7 critical risks. Each bullet: 15-30 words including specific risk factor, potential impact magnitude, and timeline if relevant. Prioritize material risks from SEC filings, earnings calls, and recent news. Source distribution: NEWS_percentage% from NEWS_AGENT, EARNINGS_percentage% from EARNINGS_AGENT, SEC_percentage% from SEC_AGENT."
    )
    
    strategic_opportunities: List[Dict[str, List[str]]] = Field(
        description="Strategic opportunities for the company AND RBC Capital Markets engagement. List of 3-4 dictionaries. Each dictionary: ONE subheading as key (e.g., 'M&A Advisory', 'Capital Raising', 'Strategic Repositioning', 'Equity/Debt Offerings') and 2-3 specific opportunity bullets as value (15-30 words each). Focus on actionable opportunities. Source distribution: NEWS_percentage% from NEWS_AGENT, EARNINGS_percentage% from EARNINGS_AGENT, SEC_percentage% from SEC_AGENT."
    )

    news_summary: List[Dict[str, List[str]]] = Field(
        description="Summary of recent firm-level news organized by 3-5 thematic categories. Each dictionary: ONE thematic heading as key (e.g., 'Product Launches', 'Market Expansion', 'Regulatory Updates') and 2-4 news bullets as value (15-30 words each). Source: 100% from NEWS_AGENT. Apply firm-level filtering (same as recent_developments). Focus on material news from last 6-12 months. Prioritize: (1) company strategy/operations, (2) sector dynamics, (3) broader market context."
    )

    earnings_summary: List[Dict[str, List[str]]] = Field(
        description="High-impact summary of LATEST earnings call (300 words max total). List of 3-4 dictionaries. Required themes as keys: 'Financial Highlights' (revenue, margins, EPS vs. consensus), 'Forward Guidance & Outlook' (management guidance, demand trends, growth levers), 'Segment Performance' (performance by business segment with metrics), 'Key Q&A Takeaways' (critical insights from Q&A). Optional themes: 'Market Trends & Competitive Positioning', 'Margin & Cost Drivers', 'Capital Allocation'. Each bullet: 15-30 words with specific metrics and dates. Source: 100% from EARNINGS_AGENT."
    )

    recent_developments: List[Dict[str, Any]] = Field(
        description="List of 4-6 FIRM-LEVEL recent developments. Each dictionary must have: 'category' (ONE of: 'News', 'M&A', 'Management', 'Company', 'Industry'), 'header' (5-10 word title), 'date' (format: 'MMM DD YYYY'), 'description' (20-40 words with specific details, names, figures, outcomes), 'source_url' (full URL from chunk metadata, or null if unavailable - do NOT use '<UNKNOWN>' or empty string). EXCLUDE: portfolio company acquisitions/exits, portfolio company operational updates, general market commentary. Source distribution (SEC excluded): NEWS_percentage% from NEWS_AGENT, EARNINGS_percentage% from EARNINGS_AGENT."
    )

    sources: List[str] = Field(
        description="Comprehensive list of 8-12 sources cited. Format: 'Source Name - URL - Date Accessed (YYYY-MM-DD)'. Extract URLs from chunk metadata for ALL agents. Include: SEC filings, earnings transcripts, news articles, press releases."
    )

src/services/data_models/models.py
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field


class ContextBuilderOutput(BaseModel):
    corporate_client_firm_response: Optional[Dict[str, Any]] = None
    temporal_content_response: Optional[Dict[str, Any]] = None
    rbc_persona: Optional[Any] = None
    corporate_client_persona: Optional[Any] = None
    request_meeting_date: Optional[str] = None
    request_company_name: Optional[str] = None
    timings: Optional[Dict[str, float]] = None
    cached: Optional[bool] = None
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
    cached: Optional[Dict[str, Any]] = None
    errors: Optional[Dict[str, Any]] = None

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
from src.services.llm.oauth_client import  get_oauth_token
import httpx
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
    token, _ = await get_oauth_token()
    llm_model = os.getenv('LLM_MODEL_NAME')
    llm_base_url = os.getenv('LLM_SERVER_URL')
    max_tokens = int(os.getenv('LLM_MAX_TOKENS'))
    temperature = os.getenv('LLM_TEMPERATURE')
    supports_temperature = temperature is not None

    payload = {
        "model": llm_model,
        "messages": messages,
        "max_tokens": max_tokens
    }
    if supports_temperature:
        payload["temperature"] = float(temperature)
    if tools:
        payload["tools"] = tools

    async with httpx.AsyncClient( timeout=60.0) as client:
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

async def call_llm_raw(messages: List[Dict[str, str]], tools: List[Dict[str, Any]] = None, tool_choice: Dict[str, Any] = None) -> dict:
    """
    Same as call_llm, but returns the full LLM response dict for advanced routing.
    """
    token, _ = await get_oauth_token()
    llm_model = os.getenv('LLM_MODEL_NAME')
    llm_base_url = os.getenv('LLM_SERVER_URL')
    max_tokens = int(os.getenv('LLM_MAX_TOKENS'))
    temperature = os.getenv('LLM_TEMPERATURE')
    supports_temperature = temperature is not None

    payload = {
        "model": llm_model,
        "messages": messages,
        "max_tokens": max_tokens
    }
    if supports_temperature:
        payload["temperature"] = float(temperature)
    if tools:
        payload["tools"] = tools
    if tool_choice:  # Add this
        payload["tool_choice"] = tool_choice

    async with httpx.AsyncClient( timeout=120.0) as client:
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
    token, _ = await get_oauth_token()

    llm_model = os.getenv('LLM_MODEL_NAME')
    llm_base_url = os.getenv('LLM_SERVER_URL')
    temperature = os.getenv('LLM_TEMPERATURE')


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
from src.utils.utils import async_timed_lru_cache
load_dotenv()

def get_env(key, default=None, required=False):
    """Get environment variable with optional default and required validation"""
    value = os.getenv(key, default)
    if required and value is None:
        raise ValueError(f"Missing required environment variable: {key}")
    return value


@async_timed_lru_cache(seconds=int(os.getenv("OAUTH_TOKEN_EXPIRATION")), maxsize=1)
async def get_oauth_token():
    """Get OAuth token for LLM API authentication"""
    config = get_config().llm_chat_model
    oauth_endpoint = os.getenv('LLM_OAUTH_ENDPOINT')
    client_id = os.getenv('LLM_CLIENT_ID')
    client_secret = os.getenv('LLM_CLIENT_SECRET')
    grant_type = "client_credentials"
    scope = "read"

    data = {
        "grant_type": grant_type,
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": scope
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            oauth_endpoint,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        response.raise_for_status()
        result = response.json()
        return result["access_token"]


src/services/ldap_service/ldap_service.py
import logging
import os
import datetime

from ldap3 import Server, Connection, ALL, NTLM

from src.services.ldap_service.lookup_service_interface import LookupServiceInterface
from src.services.ldap_service.ldap_search_strategy.ldap_search_strategy_Interface import LDAPSearchStrategyInterface
from src.services.ldap_service.user_profile import UserProfile
from src.utils.utils import timed_lru_cache

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s -[%(funcName)s:%(lineno)d] - %(message)s"
)

logger = logging.getLogger(__name__)

class LDAPService(LookupServiceInterface):
    def __init__(self, ldap_search_strategy: LDAPSearchStrategyInterface):
        self.ldap_search_strategy = ldap_search_strategy

    @staticmethod
    @timed_lru_cache(seconds=60, maxsize=1)
    def build_ldap_connection():
        logger.info("Building LDAP connection")
        ldap_user = os.getenv("LDAP_USERNAME")
        ldap_password = os.getenv("LDAP_PASSWORD")
        logger.info(f"LDAP user: {ldap_user}")
        # logger.info(f"LDAP password: {ldap_password}")

        server = Server("ldaps://" + os.getenv("LDAP_SERVER"), get_info=ALL)
        conn = Connection(
            server, user=ldap_user, password=ldap_password, authentication=NTLM
        )
        return conn

    @staticmethod
    def parse_user_entry( user_entry):
        logger.info(f"Parsing user entry with username: {user_entry.name.values[0]} ")
        first_last_name=user_entry.name.values[0].split(" ",1)
        if len(first_last_name) == 1:
            first_name=first_last_name[0]
            last_name=first_last_name[0]
        else:
            first_name, last_name= first_last_name

        # first_name, last_name = user_entry.name.values[0].split(" ",1)
        first_name, last_name = first_name.strip(" ,"), last_name.strip(" ,")
        user_profile = UserProfile(
            id=user_entry.sAMAccountName.values[0],
            name=f"{first_name} {last_name}",
            first_name=first_name,
            last_name=last_name,
            email=user_entry.mail.values[0] if 'mail' in user_entry else '',
            employeeId=user_entry.employeeID.values[0] if 'employeeID' in user_entry else '',
            intraId=user_entry.sAMAccountName.values[0],
            internal_flag=True,
            department=user_entry.department.values[0] if 'department' in user_entry else '',
            division=user_entry.division.value if 'division' in user_entry else '',
            role=user_entry.title.values[0] if 'title' in user_entry else '',
            last_update_time=str(datetime.datetime.now(datetime.timezone.utc)),
        )
        return user_profile.__dict__


    def lookup(self,values: list[str])->list:
        logger.info(f"Looking up {len(values)} LDAP entries")
        profiles = []
        conn = self.build_ldap_connection()
        for val in values:
            try:
                user_profile_entries=self.ldap_search_strategy.run(conn,val)
                if user_profile_entries and len(user_profile_entries)>0:
                    for profile in user_profile_entries:
                        user_profile=self.parse_user_entry(profile)
                        profiles.append(user_profile)
            except Exception as e:
                logger.error(f"LDAP profile lookup failed: {e}")

        return profiles

src/services/ldap_service/lookup_service_interface.py
import abc


class LookupServiceInterface(metaclass=abc.ABCMeta):

    @classmethod
    def __subclasshook__(cls, subclass):
        return (
            hasattr(subclass, "lookup") and
            callable(subclass.lookup) or
            NotImplemented
        )

    @abc.abstractmethod
    def lookup(self, emails:list[str])-> list:
        raise NotImplementedError()

src/services/ldap_service/user_profile.py

from dataclasses import dataclass


@dataclass
class UserProfile:
    id: str
    name: str
    first_name: str
    last_name: str
    email: str
    employeeId: str
    intraId: str
    internal_flag: bool
    department: str
    division: str
    role: str
    last_update_time: str
    company: str = ""  # Add company field for ZoomInfo company data


src/services/ldap_service/zoom_info_service.py
import datetime
import json
import logging
import os
import jwt
from datetime import datetime, timedelta, timezone
import requests
import json

import requests

from rbc_security import enable_certs


from src.services.ldap_service.user_profile import UserProfile

from src.utils.utils import timed_lru_cache, time_it

enable_certs()

from src.services.ldap_service.lookup_service_interface import LookupServiceInterface
from src.config.configuration import app_config

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s -[%(funcName)s:%(lineno)d] - %(message)s"
)
logger = logging.getLogger(__name__)

class ZoomInfoService(LookupServiceInterface):

    def __init__(self):
        self.user_name = os.environ.get("ZOOM_INFO_USERNAME")
        self.audience = 'enterprise_api'
        self.issuer = 'api-client@zoominfo.com'
        self.authenticate_url = "https://api.zoominfo.com/authenticate"
        self.expiry_time_in_seconds = 300
        self.hashing_algorithm = 'RS256'

    def user_name_pwd_authentication(self, password):
        headers = {'Accept': "application/json", 'user-agent': ""}
        request_body = {'username': self.user_name, 'password': password}
        response = requests.post(self.authenticate_url, headers=headers, data=request_body)
        if not response.ok:
            response.reason = response.text
            return response.raise_for_status()
        return self._extract_jwt_from_text(response.text)

    def pki_authentication(self, client_id, private_key):
        return self._post_and_get_jwt(client_id, private_key)

    def _post_and_get_jwt(self, client_id, private_key):
        client_jwt = self._get_client_jwt(client_id, private_key)
        headers = {'Authorization': f"Bearer {client_jwt}", 'Accept': "application/json", 'user-agent': ""}
        response = requests.post(self.authenticate_url, headers=headers)
        if not response.ok:
            response.reason = response.text
            return response.raise_for_status()
        return self._extract_jwt_from_text(response.text)

    def _get_client_jwt(self, client_id, private_key):
        current_time = datetime.utcnow()
        claims = {
            'aud': self.audience,
            'iss': self.issuer,
            'iat': current_time,
            'exp': current_time + timedelta(seconds=self.expiry_time_in_seconds),
            'client_id': client_id,
            'username': self.user_name
        }
        encoded_jwt = jwt.encode(claims, private_key, algorithm=self.hashing_algorithm)
        # `PyJWT` switched to returning a string in v2.0.0
        return encoded_jwt.decode("utf-8") if isinstance(encoded_jwt, bytes) else encoded_jwt

    def _extract_jwt_from_text(self, text_input):
        json_response = json.loads(text_input)
        return json_response["jwt"]

    @time_it
    @timed_lru_cache(seconds=5 * 60, maxsize=1)
    def _get_jwt_token(self):
        password=os.environ.get("ZOOM_INFO_PASSWORD")
        return self.user_name_pwd_authentication(password)


    def parse_response(self,email,zoom_info_response):
        logger.debug("Parsing Zoom Info response")
        if(zoom_info_response.ok):
            data_json = zoom_info_response.json()
            data=data_json['data'][0]
            try:
                user_profile = UserProfile(
                    id=data['id'],
                    name=f"{data['firstName']} {data['lastName']}".strip(),
                    first_name=data['firstName'],
                    last_name=data['lastName'],
                    email=email,
                    employeeId='',
                    intraId=data['id'],
                    internal_flag=False,
                    department='',  # Keep empty - no department info from ZoomInfo
                    division='',
                    role=data['jobTitle'],
                    last_update_time=str(datetime.now(timezone.utc)),
                    company=data['company']['name'],  # Use the new company field
                )
                return user_profile.__dict__
            except Exception as e:
                logger.error(f"Failed to parse zoom user response: {e}")
                raise
        else:
            return None

    def parse_response_for_name(self, name_info: dict, zoom_info_response):
        """Enhanced response parsing that returns ALL matches, not just the first one"""
        logger.debug("Parsing Zoom Info response for name search")
        
        if not zoom_info_response.ok:
            logger.error(f"ZoomInfo API error {zoom_info_response.status_code}: {zoom_info_response.text}")
            return []
        
        try:
            data_json = zoom_info_response.json()
            results = []
            
            if 'data' in data_json and len(data_json['data']) > 0:
                # Process ALL results, not just the first one
                for data in data_json['data']:
                    # Handle company info - might be in 'company' object or 'companyName' field
                    company_name = ''
                    company_id = ''
                    
                    if 'company' in data and isinstance(data['company'], dict):
                        company_name = data['company'].get('name', '')
                        company_id = data['company'].get('id', '')
                    elif 'companyName' in data:
                        company_name = data.get('companyName', '')
                    
                    user_profile = UserProfile(
                        id=data.get('id', ''),
                        name=f"{data.get('firstName', '')} {data.get('lastName', '')}".strip(),
                        first_name=data.get('firstName', name_info['first_name']),
                        last_name=data.get('lastName', name_info['last_name']),
                        email='',  # Not available in name-based search
                        employeeId='',
                        intraId=str(data.get('id', '')),
                        internal_flag=False,
                        department='',  # Keep empty - no department info from ZoomInfo
                        division='',
                        role=data.get('jobTitle', ''),
                        last_update_time=str(datetime.now(timezone.utc)),
                        company=company_name,  # Use the new company field
                    )
                    
                    profile_dict = user_profile.__dict__
                    
                    # Add additional fields
                    profile_dict['middle_name'] = data.get('middleName', '')
                    profile_dict['company_id'] = company_id
                    profile_dict['zoominfo_id'] = data.get('id', '')
                    
                    results.append(profile_dict)
                
                logger.info(f"Found {len(results)} matches for {name_info['full_name']}")
                return results
                    
            else:
                logger.info(f"No data found in ZoomInfo response for {name_info['full_name']}")
                return []
                    
        except Exception as e:
            logger.error(f"Failed to parse ZoomInfo response for {name_info['full_name']}: {e}")
            return []

    def parse_names_string(self, names_string: str) -> list[dict]:
        """
        Simple robust name parsing - just clean and split names
        """
        names = []
        individual_names = [name.strip() for name in names_string.split(',')]
        
        for name in individual_names:
            # Remove anything in parentheses (company info, titles, etc.)
            clean_name = name.split('(')[0].strip()
            
            # Remove common prefixes/suffixes that might interfere
            clean_name = clean_name.replace('Mr.', '').replace('Ms.', '').replace('Dr.', '').strip()
            
            # Split into parts
            name_parts = clean_name.split()
            
            if len(name_parts) >= 2:
                first_name = name_parts[0]
                last_name = ' '.join(name_parts[1:])  # Everything after first name
                
                names.append({
                    'first_name': first_name,
                    'last_name': last_name,
                    'full_name': clean_name,
                    'original': name.strip()
                })
            elif len(name_parts) == 1:
                # Single name - could be first or last
                names.append({
                    'first_name': name_parts[0],
                    'last_name': '',
                    'full_name': clean_name,
                    'original': name.strip()
                })
        
        return names

    @time_it
    def get_user_details_from_zoominfo(self, email: str):
        zoom_info_url=os.environ.get("ZOOM_INFO_URL")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._get_jwt_token()}"
        }

        # data = {
        #     "emailAddress": "akinahan@k1ops.com"
        # }

        data = {
                "emailAddress": email ,
            "outputFields": [
                "id", "firstName", "middleName", "lastName", "jobTitle", "companyName"]
        }



        response = requests.post(zoom_info_url, headers=headers, json=data)
        # print(response.status_code)
        # print(response.json())
        return response

    @time_it
    def get_user_details_from_zoominfo_by_name(self, first_name: str, last_name: str = None, full_name: str = None):
        """
        Name search without company filtering - get ALL matches for the name
        """
        zoom_info_url = os.environ.get("ZOOM_INFO_URL")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._get_jwt_token()}"
        }

        # Remove company filtering - get all matches for the name
        data = {
            "outputFields": [
                "id", "firstName", "middleName", "lastName", "jobTitle", "companyName"
            ]
        }
        
        # Add search criteria (no company filter)
        if first_name and last_name:
            data["firstName"] = first_name
            data["lastName"] = last_name
        elif full_name:
            name_parts = full_name.split()
            if len(name_parts) >= 2:
                data["firstName"] = name_parts[0]
                data["lastName"] = " ".join(name_parts[1:])
            else:
                data["firstName"] = full_name
        elif first_name:
            data["firstName"] = first_name
        
        logger.debug(f"ZoomInfo API payload: {data}")
        
        response = requests.post(zoom_info_url, headers=headers, json=data)
        
        if response.status_code != 200:
            logger.error(f"ZoomInfo API error {response.status_code}: {response.text}")
        
        return response



    def lookup(self, emails:list[str]) -> list:
        # Implement Zoom lookup logic here
        logger.info(f"Looking up {len(emails)} Zoom entries")
        result = []
        for email in emails:
            try:
                zoom_user_response = self.get_user_details_from_zoominfo(email)
                user_details = self.parse_response(email,zoom_user_response)
                if user_details and len(user_details) > 0:
                    result.append(user_details)
            except Exception as e:
                logger.error(f"Failed to get user details: {e}")

        return result

    def lookup_by_names(self, names_string: str) -> list:
        """
        Simplified name lookup - just get ALL matches for each name
        """
        logger.info(f"Looking up ZoomInfo entries for names: {names_string}")
        
        result = []
        
        try:
            parsed_names = self.parse_names_string(names_string)
            
            for name_info in parsed_names:
                try:
                    logger.debug(f"Searching for all matches: {name_info['full_name']}")
                    zoom_user_response = self.get_user_details_from_zoominfo_by_name(
                        first_name=name_info['first_name'],
                        last_name=name_info['last_name']
                    )
                    
                    all_matches = self.parse_response_for_name(name_info, zoom_user_response)
                    
                    if all_matches:
                        logger.info(f"Found {len(all_matches)} total matches for {name_info['full_name']}")
                        result.extend(all_matches)
                    else:
                        logger.warning(f"No results found for: {name_info['original']}")
                            
                except Exception as e:
                    logger.error(f"Failed to process {name_info['full_name']}: {e}")
                    continue
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to parse names string '{names_string}': {e}")
            return []


if __name__ == "__main__":

    from dotenv import load_dotenv
    load_dotenv()

    async def debug_field_comparison():
        """
        Experiment to compare email vs name search API responses
        """
        zoom_service = ZoomInfoService()
        
        print("=== EXPERIMENT: EMAIL vs NAME SEARCH COMPARISON ===\n")
        
        # Test 1: Email search for Allison Kinahan
        print("1. EMAIL SEARCH for akinahan@k1ops.com")
        print("-" * 50)
        try:
            email_response = zoom_service.get_user_details_from_zoominfo("akinahan@k1ops.com")
            print(f"Status: {email_response.status_code}")
            if email_response.ok:
                email_data = email_response.json()
                if 'data' in email_data and email_data['data']:
                    person = email_data['data'][0]
                    print(f"ID: {person.get('id', 'N/A')}")
                    print(f"Name: {person.get('firstName', '')} {person.get('lastName', '')}")
                    print(f"Job Title: {person.get('jobTitle', 'N/A')}")
                    print(f"Company: {person.get('company', {}).get('name', 'N/A') if 'company' in person else person.get('companyName', 'N/A')}")
                    print(f"All available fields: {list(person.keys())}")
                else:
                    print("No data in response")
            else:
                print(f"Error: {email_response.text}")
        except Exception as e:
            print(f"Exception: {e}")
        
        print("\n" + "="*60 + "\n")
        
        # Test 2: Name search for the same person
        print("2. NAME SEARCH for Allison Kinahan")
        print("-" * 50)
        try:
            name_response = zoom_service.get_user_details_from_zoominfo_by_name("Allison", "Kinahan")
            print(f"Status: {name_response.status_code}")
            if name_response.ok:
                name_data = name_response.json()
                if 'data' in name_data and name_data['data']:
                    person = name_data['data'][0]
                    print(f"ID: {person.get('id', 'N/A')}")
                    print(f"Name: {person.get('firstName', '')} {person.get('lastName', '')}")
                    print(f"Job Title: {person.get('jobTitle', 'N/A')}")
                    print(f"Company: {person.get('company', {}).get('name', 'N/A') if 'company' in person else person.get('companyName', 'N/A')}")
                    print(f"All available fields: {list(person.keys())}")
                else:
                    print("No data in response")
            else:
                print(f"Error: {name_response.text}")
        except Exception as e:
            print(f"Exception: {e}")
        
        print("\n" + "="*60 + "\n")
        
        # Test 3: Compare the output fields being requested
        print("3. COMPARING API PAYLOADS")
        print("-" * 50)
        
        # Email search payload
        email_payload = {
            "emailAddress": "akinahan@k1ops.com",
            "outputFields": ["id", "firstName", "middleName", "lastName", "jobTitle", "companyName"]
        }
        print(f"Email search requests fields: {email_payload['outputFields']}")
        
        # Name search payload  
        name_payload = {
            "firstName": "Allison",
            "lastName": "Kinahan",
            "outputFields": ["id", "firstName", "middleName", "lastName", "jobTitle", "companyName"]
        }
        print(f"Name search requests fields: {name_payload['outputFields']}")
        
        print(f"Fields are identical: {email_payload['outputFields'] == name_payload['outputFields']}")
        
        print("\n" + "="*60 + "\n")
        print("CONCLUSION:")
        print("- If IDs are the same but jobTitle differs: Same person, different data sources")
        print("- If fields are identical but responses differ: API endpoint behavior difference")
        print("- If fields differ: Request payload issue")

    import asyncio
    asyncio.run(debug_field_comparison())


src/services/ldap_service/ldap_search_strategy/ldap_email_strategy.py
import logging
import os

from ldap3 import SUBTREE, ALL_ATTRIBUTES

from src.services.ldap_service.ldap_search_strategy.ldap_search_strategy_Interface import LDAPSearchStrategyInterface


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s -[%(funcName)s:%(lineno)d] - %(message)s"
)

logger = logging.getLogger(__name__)


class LDAPEmailStrategy(LDAPSearchStrategyInterface):

    def run(self, conn, value: str):
        logger.info(f"Authenticating email via LDAP: {value}")
        # conn = self.build_ldap_connection()
        if not conn.bind():
            logger.error(f"LDAP server bind failed")
            return {}

        user_dn = os.getenv("LDAP_USER_DN")
        rsp = conn.search(
            user_dn,
            f"(mail={value})",
            search_scope=SUBTREE,
            # attributes=["name", "mail", "sAMAccountName", "department","title"],
            attributes=ALL_ATTRIBUTES,
        )
        logger.info(f"LDAP search response: {rsp}")
        if rsp and conn.entries:
            user_entry = conn.entries
            return user_entry

        else:
            if not rsp:
                logger.info(f"LDAP profile lookup returned false for user : {value}")
            if not conn.entries:
                logger.info(f"No LDAP profile entries for user  : {value}")
            return {}

src/services/ldap_service/ldap_search_strategy/ldap_search_strategy_Interface.py
from abc import ABC, abstractclassmethod, abstractmethod
from typing import List


class LDAPSearchStrategyInterface(ABC):

    @abstractmethod
    def run(self, conn, value: str):
        pass


src/services/ldap_service/ldap_search_strategy/ldap_username_strategy.py
import logging
import os

from ldap3 import SUBTREE, ALL_ATTRIBUTES

from src.services.ldap_service.ldap_search_strategy.ldap_search_strategy_Interface import LDAPSearchStrategyInterface


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s -[%(funcName)s:%(lineno)d] - %(message)s"
)

logger = logging.getLogger(__name__)


class LDAPUsernameStrategy(LDAPSearchStrategyInterface):

    def run(self, conn, value: str):
        logger.info(f"Authenticating name via LDAP: {value}")
        # conn = self.build_ldap_connection()
        if not conn.bind():
            logger.error(f"LDAP server bind failed")
            return {}

        user_dn = os.getenv("LDAP_USER_DN")
        rsp = conn.search(
            user_dn,
            f"(cn={value})",
            search_scope=SUBTREE,
            # attributes=["name", "mail", "sAMAccountName", "department","title"],
            attributes=ALL_ATTRIBUTES,
        )
        if rsp and conn.entries:
            user_entry = conn.entries
            return user_entry

        else:
            if not rsp:
                logger.info(f"LDAP profile lookup returned false for user : {value}")
            if not conn.entries:
                logger.info(f"No LDAP profile entries for user  : {value}")
            return {}




# Python/FastAPI starter kit


# Chain Server Response Structure

**ACTUAL OUTPUT SCHEMA** - Based on code analysis and real output from `response_new.json`

---

## Root Structure

```json
{
  "context_builder": { ... },
  "content_prioritization": { ... },
  "response_builder_and_generator": { ... },
  "timings": { ... }
}
```

---

## 1. context_builder

Extracts contextual information about the corporate client and meeting.

### Fields

#### `corporate_client_firm_response_raw` (Object | null)
Raw response from firm lookup API.

**Structure:**
```json
{
  "result": {
    "matches": [
      {
        "company_name": "Tesla, Inc.",
        "ticker_symbol": "TSLA",
        "industry": "Consumer Durables",
        "isin": "US88160R1014",
        "company_type": "PUB",             
        "company_type_desc": "Public Company",
        "iso_country": "US",
        "region": "US",
        "fsym_id": "WWDPYB-S"
      }
      // ... more matches
    ],
    "cache_time": 0.03313112258911133,
    "total_matches": 5
  }
}
```

#### `corporate_client_firm_response` (Object | null)
Selected company match from the raw response.

**Fields:**
- `company_name` (string): Official company name
- `ticker_symbol` (string): Stock ticker
- `industry` (string): Industry classification
- `isin` (string): International Securities Identification Number
- `company_type` (string): "PUB" (public) or "PRIV" (private)
- `company_type_desc` (string): "Public Company" or "Private Company"
- `iso_country` (string): Country code
- `region` (string): Region code (e.g., "US", "CA", "AR")
- `fsym_id` (string): FactSet Symbol ID

#### `temporal_content_response_raw` (Object | null)
Raw response from earnings/temporal data lookup.

**Structure:**
```json
{
  "result": [
    {
      "report_id": 3326653,
      "transcript_expected": "C",
      "transcript_completed": "C",
      "event_datetime_utc": "2025-10-22T21:30:00",
      "fiscal_period": "3",
      "fiscal_year": 2025.0,
      "title": "Q3 2025 EARNINGS CALL",
      "event_dt": "2025-10-22",
      "company_name": "Tesla, Inc.",
      "company_type_desc": "Public Company",
      "ticker_symbol": "TSLA",
      "region": "US"
    }
    // ... more results
  ]
}
```

#### `temporal_content_response` (Object | null)
Selected temporal data from raw response.

**Fields:**
- `report_id` (integer): Report identifier
- `transcript_expected` (string): Expected status code
- `transcript_completed` (string): Completion status code
- `event_datetime_utc` (string): UTC datetime of event (ISO format)
- `fiscal_period` (string): Fiscal quarter ("1", "2", "3", "4")
- `fiscal_year` (float): Fiscal year
- `title` (string): Event title (e.g., "Q3 2025 EARNINGS CALL")
- `event_dt` (string): Event date (YYYY-MM-DD)
- `company_name` (string): Company name
- `company_type_desc` (string): Company type description
- `ticker_symbol` (string): Stock ticker
- `region` (string): Region code

#### `rbc_persona` (boolean)
Whether RBC employee persona is active. Default: `false`

#### `corporate_client_persona` (boolean)
Whether corporate client persona is active. Default: `false`

#### `timings` (Object)
Performance metrics in seconds.

**Fields:**
- `corporate_client_firm_extractor` (float): Time to extract firm info (e.g., `0.157`)
- `temporal_content_extractor` (float): Time to extract temporal info (e.g., `0.091`)
- `parse_temporal_content_extractor_response` (float): Time to parse response (e.g., `0.003`)

#### `errors` (Object)
Error dictionary. Empty if no errors: `{}`

---

## 2. content_prioritization

Determines data source priorities and generates queries for data agents.

### Fields

#### `temporal_source_prioritizer` (Object)
Percentage distribution across data sources (must sum to 100).

**Fields:**
- `earnings_agent` (integer): 0-100
- `news_agent` (integer): 0-100
- `SEC_agent` (integer): 0-100

**Example:**
```json
{
  "earnings_agent": 20,
  "news_agent": 60,
  "SEC_agent": 20
}
```

#### `subqueries_from_engine` (Object)
Generated queries for each data agent.

**Structure:**
```json
{
  "earnings_agent": [...],
  "news_agent": [...],
  "SEC_agent": [...]
}
```

##### `earnings_agent` (Array)
```json
[
  {
    "query": "Give me the earnings transcript for Tesla, Inc. for fiscal year: 2025.0 and quarter: 3."
  }
]
```

##### `news_agent` (Array)
```json
[
  {
    "search_query": "Tesla, Inc. executive leadership changes",
    "topics": ["CEO", "CFO", "management"],
    "absolute_date_range": {
      "start_date": "2025-10-18",
      "end_date": "2025-11-18"
    }
  }
]
```

**Fields per query:**
- `search_query` (string): Search terms
- `topics` (array of strings): Topic keywords
- `absolute_date_range` (object):
  - `start_date` (string): YYYY-MM-DD
  - `end_date` (string): YYYY-MM-DD

##### `SEC_agent` (Array)
```json
[
  {
    "reporting_entity": "Tesla, Inc.",
    "search_queries": [
      "consolidated statements of operations total revenues",
      "total revenues annual fiscal year"
    ],
    "keywords": [
      "total revenues",
      "sales",
      "consolidated statements of operations"
    ],
    "get_latest": 8,
    "filing_type_filters": ["RNS-SEC-10-K"]  // optional
  }
]
```

**Fields per query:**
- `reporting_entity` (string): Company name
- `search_queries` (array of strings): Query phrases
- `keywords` (array of strings): Search keywords
- `get_latest` (integer): Number of latest filings to retrieve
- `filing_type_filters` (array of strings, optional): Specific filing types

#### `topic_ranker_result` (null)
Currently not implemented. Always `null`.

#### `timings` (Object)
**Fields:**
- `temporal_source_prioritizer` (float): Time in seconds (e.g., `0.000045`)
- `subquery_engine` (float): Time in seconds (e.g., `0.000111`)

#### `errors` (Object)
Empty if no errors: `{}`

---

## 3. response_builder_and_generator

Executes data agent queries and generates structured financial analysis.

### Fields

#### `financial_metrics_result` (Object | null)
Structured financial metrics extracted from data sources.

**ALL fields are Optional[type] - can be null if data unavailable**

##### Revenue Metrics

- **`current_annual_revenue`** (float | null)
  - Description: Current annual revenue in billions USD
  - Example: `69.926`

- **`current_annual_revenue_date`** (string | null)
  - Description: Date of SEC filing (YYYY-MM-DD)
  - Example: `"2025-10-23"`

- **`current_annual_revenue_citation`** (Object | null)
  - `source_agent` (array of strings): e.g., `["SEC_agent"]`
  - `source_content` (array of strings): Verbatim quotes from sources
  - `reasoning` (string): Explanation of extraction/calculation

- **`current_annual_revenue_yoy_change`** (float | null)
  - Description: Year-over-year % change
  - Example: `-2.86` (for -2.86%)

- **`current_annual_revenue_yoy_change_citation`** (Object | null)
  - Same structure as citation above

- **`estimated_annual_revenue_next_year`** (float | null)
  - Description: Projected revenue for next fiscal year (billions USD)
  - Example: `93.2`

- **`estimated_annual_revenue_next_year_date`** (string | null)
  - Description: Source document date (YYYY-MM-DD)
  - Example: `"2025-10-23"`

- **`estimated_annual_revenue_next_year_citation`** (Object | null)

##### Profitability Metrics

- **`ebitda_margin`** (float | null)
  - Description: EBITDA margin as percentage
  - Example: `4.21` (for 4.21%)

- **`ebitda_margin_citation`** (Object | null)

- **`ebitda_margin_yoy_change`** (float | null)
  - Description: YoY change in percentage points
  - Example: `-3.64` (for -3.64 percentage points)

- **`ebitda_margin_yoy_change_citation`** (Object | null)

##### Market Metrics

- **`stock_price`** (float | null)
  - Description: Most recent stock price in USD
  - Example: `406.98`

- **`stock_price_citation`** (Object | null)

- **`stock_price_daily_change`** (float | null)
  - Description: Daily absolute change in USD
  - Example: `2.62`

- **`stock_price_daily_change_percent`** (float | null)
  - Description: Daily percentage change
  - Example: `0.65` (for +0.65%)

- **`stock_price_yoy_change`** (float | null)
  - Description: Year-over-year % change
  - Example: `27.0` (for +27%)
  - **Can be null** if insufficient data

- **`stock_price_yoy_change_citation`** (Object | null)

- **`market_cap`** (float | null)
  - Description: Market capitalization in billions USD
  - Example: `1299.4`

- **`market_cap_citation`** (Object | null)

- **`market_cap_date`** (string | null)
  - Description: Date of market cap calculation (YYYY-MM-DD)
  - Example: `"2025-11-17"`

##### Growth Trajectory

- **`revenue_growth_trajectory`** (Object | null)
  - Description: Dictionary of quarterly revenues
  - Keys: Quarter labels (e.g., "Q1 2024", "Q2 2025")
  - Values: Revenue in billions USD (float | null)
  - Example (Note: Q4 2024 not present in actual output):
    ```json
    {
      "Q1 2024": 21.301,
      "Q2 2024": 25.5,
      "Q3 2024": 25.182,
      "Q1 2025": 19.335,
      "Q2 2025": 22.496,
      "Q3 2025": 28.095
    }
    ```

- **`revenue_growth_trajectory_citation`** (Object | null)

#### `strategic_analysis_result` (Object | null)
Strategic analysis output (based on `StrategicAnalysisResponse` schema).

**Structure:**

- **`strength`** (array of strings): 4-6 SWOT strengths (15-25 words each)
  - Example: `"Market leader in EV space with $1.34 trillion market cap and 42.1% annualized returns over 15 years"`

- **`weakness`** (array of strings): 4-6 SWOT weaknesses (15-25 words each)
  - Example: `"Shallow management bench following senior departures, with limited internal CEO succession options beyond CFO Taneja"`

- **`opportunity`** (array of strings): 4-6 SWOT opportunities (15-25 words each)
  - Example: `"Federal autonomous vehicle framework under Trump administration could accelerate robotaxi deployment and regulatory approvals"`

- **`threat`** (array of strings): 4-6 SWOT threats (15-25 words each)
  - Example: `"Intensifying regulatory pressure with $329 million jury award for Autopilot-related fatality and ongoing DMV lawsuits"`

- **`investment_thesis`** (array of objects): List of dictionaries, 3-4 total
  - Each dict has 1 subheading key → list of 2-4 bullet points (15-30 words each)
  - Example:
    ```json
    [
      {
        "Autonomous Vehicle Leadership": [
          "Tesla's FSD technology showing significant progress...",
          "Trump administration's potential federal framework...",
          "Target of 1 million robotaxis represents massive revenue opportunity..."
        ]
      },
      {
        "Diversified Technology Platform": [
          "Beyond EVs, Tesla operates in energy storage, AI...",
          "Potential Apple partnership for Grok integration..."
        ]
      }
    ]
    ```

- **`key_risk_highlights`** (array of strings): 5-7 critical risks (15-30 words each)
  - Example: `"Regulatory investigations into Autopilot and FSD systems could result in significant penalties, recalls, or operational restrictions within 12-18 months"`

- **`strategic_opportunities`** (array of objects): 3-4 dictionaries for RBC engagement opportunities
  - Each dict has 1 subheading key → list of 2-3 specific opportunities (15-30 words each)
  - Example:
    ```json
    [
      {
        "Capital Markets Advisory": [
          "Potential spin-off or IPO of xAI division to unlock AI valuation premium",
          "Strategic partnerships or joint ventures in autonomous vehicle technology"
        ]
      },
      {
        "M&A Advisory": [
          "Acquisition opportunities in battery technology, charging infrastructure",
          "Potential divestiture of non-core assets to focus on highest-growth initiatives"
        ]
      }
    ]
    ```

- **`recent_developments`** (array of objects): 4-6 recent firm-level developments
  - Each object contains:
    - `category` (string): "News" | "M&A" | "Management" | "Company" | "Industry"
    - `date` (string): "MMM DD YYYY" format (e.g., "Oct 29 2025")
    - `description` (string): 20-40 word description including key details and figures
    - `source_url` (string): URL to source article
  - Example:
    ```json
    {
      "category": "Management",
      "date": "Oct 29 2025",
      "description": "Tesla board evaluating internal CEO succession plans with CFO Vaibhav Taneja and SVP Tom Zhu as leading candidates if Musk steps down",
      "source_url": "https://finance.yahoo.com"
    }
    ```

- **`sources`** (array of strings): 8-12 source citations
  - Format: "Source Name - URL - Date Accessed (YYYY-MM-DD)"
  - Example: `"Yahoo! Finance - https://finance.yahoo.com - 2025-11-20"`

#### `validation_results` (Object | null)
Validation of extracted financial metrics against sources.

**Structure:**
```json
{
  "validation_summary": {
    "total_fields_checked": 9,
    "fields_with_values": 9,
    "fields_with_sources": 9,
    "sources_verified": 7,
    "sources_not_found": 2,
    "warnings_count": 4
  },
  "field_validations": {
    "current_annual_revenue": {
      "has_value": true,
      "has_citation": true,
      "citation_verified": true,
      "extracted_numbers": [69.926, 28.1, ...],
      "issues": []
    },
    "ebitda_margin_yoy_change": {
      "has_value": true,
      "has_citation": true,
      "citation_verified": false,
      "extracted_numbers": [2025.0, 2946.0, ...],
      "issues": ["Quote #1 not found in SEC_agent", "Value -3.64 not in reasoning"]
    },
    "stock_price_yoy_change": {
      "has_value": true,
      "has_citation": true,
      "citation_verified": true,
      "extracted_numbers": [406.98, 2025.0, 320.72, ...],
      "issues": ["Value 27.0 not in reasoning"]
    }
    // ... more field validations
  },
  "warnings": [
    "ebitda_margin: Quote #1 not found in SEC_agent content",
    "ebitda_margin_yoy_change: Quote #1 not found in SEC_agent content",
    "ebitda_margin_yoy_change: Value -3.64 not found in citation reasoning",
    "stock_price_yoy_change: Value 27.0 not found in citation reasoning"
  ],
  "sanity_checks": {
    "passed": [
      "Revenue is positive",
      "EBITDA margin in reasonable range (-100% to 100%)",
      "Stock price is positive"
    ],
    "failed": [],
    "warnings": []
  }
}
```

**Fields:**
- `validation_summary` (object): High-level stats
  - `total_fields_checked` (integer)
  - `fields_with_values` (integer)
  - `fields_with_sources` (integer)
  - `sources_verified` (integer)
  - `sources_not_found` (integer)
  - `warnings_count` (integer)
- `field_validations` (object): Per-field validation details
  - Key = field name (e.g., "current_annual_revenue")
  - Value = validation object:
    - `has_value` (boolean)
    - `has_citation` (boolean)
    - `citation_verified` (boolean)
    - `extracted_numbers` (array of numbers): Numbers found in citations
    - `issues` (array of strings): Validation issues
- `warnings` (array of strings): All validation warnings
- `sanity_checks` (object):
  - `passed` (array of strings): Passed checks
  - `failed` (array of strings): Failed checks
  - `warnings` (array of strings): Warning messages

#### `parsed_data_agent_chunks` (Object)
Formatted content from each data agent.

**Structure:**
```json
{
  "news_agent": "CHUNK-1\n\nMETADATA\ntitle: ...\nsource: ...\n\nCHUNK-CONTENT\n[Chunk #1]\n...",
  "earnings_agent": "CHUNK-1\n\nMETADATA\n...",
  "SEC_agent": "CHUNK-1\n\nMETADATA\n..."
}
```

**Format for each agent:**
- Multiple chunks separated by newlines
- Each chunk has:
  - `CHUNK-N` header
  - `METADATA` section (title, source, timestamp, relevancy, url, document_id, etc.)
  - `CHUNK-CONTENT` section (actual text)

#### `company_name` (string)
Company name used for analysis (e.g., "Tesla, Inc.")

#### `timings` (Object)
Performance metrics in seconds.

**Fields (all times in seconds):**
- `execute_subqueries_on_data_agents` (float): Time to fetch from MCP agents
- `context_parser` (float): Time to parse agent responses
- `prompt_builder` (float): Time to build LLM prompts
- `response_builder` (float): Time for LLM generation
- `validate_financial_metrics` (float): Time for validation (if present)

**Note:** Specific timing fields may vary by execution. Check actual output for available timing metrics.

#### `errors` (Object)
Error dictionary. Common keys:
- `execute_subqueries_on_data_agents`: Errors fetching data
- `context_parser`: Parsing errors
- `financial_metrics_response`: Extraction errors
- `strategic_analysis_response`: Generation errors
- `validation_error`: Validation errors
- `data_agents`: e.g., "All data agents returned empty results"

---

## 4. timings (Root Level)

Overall execution time.

### Fields

- **`total_time`** (float): Total end-to-end execution time in seconds

---

## Key Patterns & Notes

### Null Handling
- Almost all fields can be `null` if:
  - Data not available from sources
  - LLM extraction fails
  - Field not applicable to company
  - API/service errors

### Date Formats
- All dates: `YYYY-MM-DD`
- UTC datetimes: ISO 8601 format (e.g., `"2025-10-22T21:30:00"`)

### Financial Values
- Revenue/market cap: billions USD (float)
- Percentages: numeric (e.g., `4.21` for 4.21%)
- Stock prices: USD per share (float)

### Citation Structure
All financial metrics with citations follow this pattern:
```json
{
  "source_agent": ["SEC_agent", "news_agent"],
  "source_content": ["verbatim quote 1", "verbatim quote 2"],
  "reasoning": "Step-by-step explanation with calculations"
}
```

### Error Handling
- Errors captured but don't stop execution
- Partial results returned when possible
- Check `errors` objects at each level for issues
- Empty errors object: `{}`