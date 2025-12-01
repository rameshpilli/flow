```
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
```
```
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
```


