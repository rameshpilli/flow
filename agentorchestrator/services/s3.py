"""
AgentOrchestrator S3 Service
============================

This module provides an enterprise S3 connection service with support for
AWS S3 and S3-compatible storage backends, including health checks,
exception handling, and high-level operations for object storage.

Designed for corporate environments that require secure S3 connections with
proper authentication and connection pooling.

Classes:
    S3Config: Configuration dataclass for S3 connection settings.
    S3HealthStatus: Health check result dataclass.
    S3Service: Main S3 service class with async and sync operations.

Functions:
    get_s3_client: Get the default S3 service instance.
    init_s3_client: Initialize and set the default S3 service.
    set_s3_client: Set a custom S3 service as the default.

Exceptions:
    S3Error: Base exception for all S3 errors.
    S3ConnectionError: Connection to S3 endpoint failed.
    S3ConfigurationError: S3 configuration is invalid or incomplete.
    S3ObjectNotFoundError: Requested S3 object does not exist.
    S3UploadError: Failed to upload object to S3.
    S3DownloadError: Failed to download object from S3.
    S3AccessDeniedError: Access denied for S3 operation.
    S3BucketNotFoundError: Specified bucket does not exist.

Usage:
    from agentorchestrator.services import S3Service, get_s3_client

    # Option 1: Using configuration
    s3 = S3Service(
        bucket_name="my-bucket",
        aws_access_key_id="your_access_key",
        aws_secret_access_key="your_secret_key",
        region_name="us-west-2",
    )

    # Option 2: Using environment variables
    s3 = S3Service.from_env()

    # Connect and use
    await s3.connect()
    await s3.upload_file("local_file.txt", "remote_key.txt")
    content = await s3.download_file("remote_key.txt")

    # Health check
    status = await s3.health_check()

Example:
    >>> from agentorchestrator.services import S3Service
    >>>
    >>> # Create and connect
    >>> s3 = S3Service(bucket_name="my-bucket")
    >>> await s3.connect()
    >>>
    >>> # Upload and download
    >>> await s3.upload_file("data.json", "uploads/data.json")
    >>> content = await s3.download_file("uploads/data.json")
    >>>
    >>> # Context manager
    >>> async with s3.connection() as s3_client:
    ...     await s3_client.upload_file("file.txt", "key.txt")

See Also:
    - agentorchestrator.services.redis: Redis connection service.
"""

from __future__ import annotations

import logging
import mimetypes
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, BinaryIO

from agentorchestrator.config import SecretString

logger = logging.getLogger(__name__)

# Optional boto3/aioboto3 import - gracefully handle if not installed
try:
    import boto3
    import aioboto3
    from botocore.config import Config as BotoConfig
    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False
    boto3 = None  # type: ignore
    aioboto3 = None  # type: ignore
    BotoConfig = None  # type: ignore


# ═══════════════════════════════════════════════════════════════════════════════
#                         EXCEPTIONS
# ═══════════════════════════════════════════════════════════════════════════════


class S3Error(Exception):
    """
    Base exception for all S3-related errors.

    This is the parent class for all S3 exceptions in the AgentOrchestrator
    framework. Catch this to handle any S3-related error.

    Attributes:
        message (str): Error message describing what went wrong.

    Example:
        >>> try:
        ...     await s3.upload_file("file.txt", "key.txt")
        ... except S3Error as e:
        ...     print(f"S3 operation failed: {e}")
    """

    pass


class S3ConnectionError(S3Error):
    """
    Connection to S3 endpoint failed.

    Raised when the client cannot establish a connection to the S3 endpoint.
    This may be due to network issues, invalid endpoint URL, or service
    unavailability.

    Common causes:
        - Network connectivity issues
        - Invalid endpoint URL
        - S3 service is down
        - Firewall blocking connection

    Example:
        >>> try:
        ...     await s3.connect()
        ... except S3ConnectionError as e:
        ...     print(f"Cannot connect to S3: {e}")
        ...     # Implement retry logic or fallback
    """

    pass


class S3ConfigurationError(S3Error):
    """
    S3 configuration is invalid or incomplete.

    Raised when the S3 configuration is missing required fields or contains
    invalid values. This typically occurs during initialization.

    Common causes:
        - Missing AWS credentials
        - Missing bucket name
        - Invalid region name
        - Conflicting configuration options

    Example:
        >>> try:
        ...     s3 = S3Service(bucket_name="")  # Empty bucket name
        ... except S3ConfigurationError as e:
        ...     print(f"Invalid configuration: {e}")
    """

    pass


class S3ObjectNotFoundError(S3Error):
    """
    Requested S3 object does not exist.

    Raised when attempting to access, download, or operate on an object
    that does not exist in the specified S3 bucket.

    Attributes:
        bucket (str): The bucket name where object was not found.
        key (str): The object key that was not found.

    Example:
        >>> try:
        ...     content = await s3.download_file("nonexistent.txt")
        ... except S3ObjectNotFoundError as e:
        ...     print(f"Object not found: {e}")
        ...     # Handle missing object case
    """

    def __init__(self, message: str, bucket: str | None = None, key: str | None = None):
        """
        Initialize the S3ObjectNotFoundError.

        Args:
            message (str): Error message.
            bucket (str | None): The bucket name. Default: None.
            key (str | None): The object key. Default: None.
        """
        super().__init__(message)
        self.bucket = bucket
        self.key = key


class S3UploadError(S3Error):
    """
    Failed to upload object to S3.

    Raised when an upload operation fails. This can occur due to insufficient
    permissions, network errors during upload, or exceeding storage quotas.

    Common causes:
        - Insufficient IAM permissions
        - Network interruption during upload
        - Bucket does not exist
        - Storage quota exceeded
        - Invalid object key

    Example:
        >>> try:
        ...     await s3.upload_file("large_file.bin", "uploads/file.bin")
        ... except S3UploadError as e:
        ...     print(f"Upload failed: {e}")
        ...     # Implement retry or notification logic
    """

    pass


class S3DownloadError(S3Error):
    """
    Failed to download object from S3.

    Raised when a download operation fails. This can occur due to insufficient
    permissions, network errors during download, or object corruption.

    Common causes:
        - Insufficient IAM permissions
        - Network interruption during download
        - Object does not exist (may also raise S3ObjectNotFoundError)
        - Disk space full on local system

    Example:
        >>> try:
        ...     content = await s3.download_file("remote_file.txt")
        ... except S3DownloadError as e:
        ...     print(f"Download failed: {e}")
        ...     # Handle download failure
    """

    pass


class S3AccessDeniedError(S3Error):
    """
    Access denied for S3 operation.

    Raised when the client does not have sufficient permissions to perform
    the requested operation. This is typically due to IAM policy restrictions.

    Common causes:
        - Insufficient IAM permissions
        - Bucket policy denies access
        - Object ACL denies access
        - Cross-account access not configured
        - Invalid or expired credentials

    Example:
        >>> try:
        ...     await s3.delete_file("protected/file.txt")
        ... except S3AccessDeniedError as e:
        ...     print(f"Permission denied: {e}")
        ...     # Log security event or request access
    """

    pass


class S3BucketNotFoundError(S3Error):
    """
    Specified bucket does not exist.

    Raised when attempting to perform operations on a bucket that does not
    exist or is not accessible to the current credentials.

    Common causes:
        - Bucket name is incorrect
        - Bucket does not exist
        - Bucket is in a different AWS account
        - Bucket is in a different region than configured

    Example:
        >>> try:
        ...     await s3.list_objects("nonexistent-bucket")
        ... except S3BucketNotFoundError as e:
        ...     print(f"Bucket not found: {e}")
        ...     # Check bucket name or create bucket
    """

    pass


# ═══════════════════════════════════════════════════════════════════════════════
#                         CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class S3Config:
    """
    S3 connection configuration.

    This dataclass holds all configuration needed to connect to an S3 endpoint,
    including connection parameters, authentication credentials, SSL settings,
    and boto3 client configuration.

    Attributes:
        endpoint_url (str | None): S3 endpoint URL. Default: None (uses AWS S3).
            For on-premises/MinIO: "https://s3.company.com:9000".
        bucket_name (str): S3 bucket name. Required.
        access_key_id (SecretString | None): AWS access key ID. Default: None.
        secret_access_key (SecretString | None): AWS secret access key. Default: None.
        region (str): AWS region name. Default: "us-east-1".
        use_ssl (bool): Use SSL/TLS for connection. Default: True.
        verify_ssl (bool): Verify SSL certificates. Default: True.
        signature_version (str): Signature version. Default: "s3v4".
        max_pool_connections (int): Maximum connection pool size. Default: 50.
        connect_timeout (float): Connection timeout in seconds. Default: 60.0.
        read_timeout (float): Read timeout in seconds. Default: 60.0.
        max_retry_attempts (int): Maximum retry attempts. Default: 3.

    Environment Variables:
        S3_ENDPOINT_URL: S3 endpoint URL
        S3_BUCKET_NAME: Bucket name (required)
        S3_ACCESS_KEY_ID: AWS access key ID
        S3_SECRET_ACCESS_KEY: AWS secret access key
        S3_REGION: AWS region (default: us-east-1)
        S3_USE_SSL: Use SSL (default: true)
        S3_VERIFY_SSL: Verify SSL certificates (default: true)
        S3_SIGNATURE_VERSION: Signature version (default: s3v4)
        S3_MAX_POOL_CONNECTIONS: Max pool connections (default: 50)
        S3_CONNECT_TIMEOUT: Connect timeout in seconds (default: 60)
        S3_READ_TIMEOUT: Read timeout in seconds (default: 60)
        S3_MAX_RETRY_ATTEMPTS: Max retry attempts (default: 3)

    Methods:
        from_env(): Load configuration from environment variables.

    Example:
        >>> # Direct configuration
        >>> config = S3Config(
        ...     endpoint_url="https://s3.company.com:9000",
        ...     bucket_name="my-bucket",
        ...     access_key_id=SecretString("AKIAIOSFODNN7EXAMPLE"),
        ...     secret_access_key=SecretString("wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"),
        ...     region="us-west-2",
        ... )
        >>>
        >>> # From environment
        >>> config = S3Config.from_env()

    See Also:
        S3Service: Service class that uses this configuration.
    """

    bucket_name: str
    endpoint_url: str | None = None
    access_key_id: SecretString | None = None
    secret_access_key: SecretString | None = None
    region: str = "us-east-1"
    use_ssl: bool = True
    verify_ssl: bool = True
    signature_version: str = "s3v4"
    max_pool_connections: int = 50
    connect_timeout: float = 60.0
    read_timeout: float = 60.0
    max_retry_attempts: int = 3

    @classmethod
    def from_env(cls, prefix: str = "S3") -> "S3Config":
        """
        Load configuration from environment variables.

        Reads environment variables with the specified prefix and creates
        a configuration instance. Boolean values accept: true, 1, yes, on.

        Args:
            prefix (str): Environment variable prefix. Default: "S3".
                Variables are read as {prefix}_{KEY}, e.g., S3_BUCKET_NAME.

        Returns:
            S3Config: Configuration loaded from environment.

        Raises:
            S3ConfigurationError: If required configuration (bucket_name) is missing.

        Example:
            >>> import os
            >>> os.environ["S3_BUCKET_NAME"] = "my-bucket"
            >>> os.environ["S3_ENDPOINT_URL"] = "https://s3.company.com:9000"
            >>> os.environ["S3_ACCESS_KEY_ID"] = "my-access-key"
            >>>
            >>> config = S3Config.from_env()
            >>> print(config.bucket_name)  # "my-bucket"
            >>>
            >>> # With custom prefix
            >>> os.environ["BACKUP_BUCKET_NAME"] = "backup-bucket"
            >>> config = S3Config.from_env(prefix="BACKUP")
        """

        def get_env(key: str, default: Any = None) -> str | None:
            return os.getenv(f"{prefix}_{key}", default)

        def get_bool(key: str, default: bool = False) -> bool:
            val = get_env(key)
            if val is None:
                return default
            return val.lower() in ("true", "1", "yes", "on")

        def get_int(key: str, default: int) -> int:
            val = get_env(key)
            return int(val) if val else default

        def get_float(key: str, default: float) -> float:
            val = get_env(key)
            return float(val) if val else default

        # Required field
        bucket_name = get_env("BUCKET_NAME")
        if not bucket_name:
            raise S3ConfigurationError(
                f"Missing required configuration: {prefix}_BUCKET_NAME environment variable"
            )

        # Optional credentials (wrapped in SecretString)
        access_key_id = get_env("ACCESS_KEY_ID")
        secret_access_key = get_env("SECRET_ACCESS_KEY")

        return cls(
            endpoint_url=get_env("ENDPOINT_URL"),
            bucket_name=bucket_name,
            access_key_id=SecretString(access_key_id) if access_key_id else None,
            secret_access_key=SecretString(secret_access_key) if secret_access_key else None,
            region=get_env("REGION", "us-east-1") or "us-east-1",
            use_ssl=get_bool("USE_SSL", True),
            verify_ssl=get_bool("VERIFY_SSL", True),
            signature_version=get_env("SIGNATURE_VERSION", "s3v4") or "s3v4",
            max_pool_connections=get_int("MAX_POOL_CONNECTIONS", 50),
            connect_timeout=get_float("CONNECT_TIMEOUT", 60.0),
            read_timeout=get_float("READ_TIMEOUT", 60.0),
            max_retry_attempts=get_int("MAX_RETRY_ATTEMPTS", 3),
        )


# ═══════════════════════════════════════════════════════════════════════════════
#                         HEALTH STATUS
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class S3HealthStatus:
    """
    S3 health check result.

    Contains detailed information about S3 service health and connectivity,
    including latency measurements and bucket accessibility.

    Attributes:
        healthy (bool): Whether S3 is healthy and accessible. True indicates
            the service is operational and the bucket can be accessed.
        latency_ms (float): Operation latency in milliseconds. Measures the
            time taken for a round-trip health check operation (typically a
            head_bucket request).
        bucket_accessible (bool): Whether the configured bucket exists and is
            accessible with current credentials. True indicates successful
            bucket access validation.
        bucket_region (str | None): AWS region where the bucket is located.
            None if region cannot be determined or health check failed.
            Example: "us-west-2", "eu-central-1".
        endpoint_url (str | None): The S3 endpoint URL being used. Useful for
            debugging and confirming correct endpoint configuration.
            None if using default AWS S3 endpoints.
            Example: "https://s3.us-west-2.amazonaws.com".
        error (str | None): Error message if unhealthy. Contains detailed
            information about what went wrong during the health check.
            None if healthy is True.

    Example:
        >>> status = await s3.health_check()
        >>> if status.healthy:
        ...     print(f"S3 healthy - {status.latency_ms:.1f}ms latency")
        ...     print(f"Bucket in region: {status.bucket_region}")
        ...     print(f"Bucket accessible: {status.bucket_accessible}")
        ... else:
        ...     print(f"S3 unhealthy: {status.error}")
        ...     # Implement alerting or fallback logic

    See Also:
        S3Service.health_check(): Method that returns this dataclass.
    """

    healthy: bool
    latency_ms: float
    bucket_accessible: bool
    bucket_region: str | None = None
    endpoint_url: str | None = None
    error: str | None = None


# ═══════════════════════════════════════════════════════════════════════════════
#                         S3 SERVICE
# ═══════════════════════════════════════════════════════════════════════════════


class S3Service:
    """
    Enterprise S3 connection service.

    Provides a high-level interface for S3 operations with:
    - Support for AWS S3 and S3-compatible storage (MinIO, etc.)
    - Secure credential management with SecretString
    - Connection pooling for performance
    - Comprehensive health checks
    - Automatic reconnection on failure
    - Both async and sync client support

    Attributes:
        config (S3Config): S3 connection configuration.
        is_connected (bool): Whether async client is connected.
        client: Async S3 client (raises if not connected).
        sync_client: Sync S3 client (raises if not connected).

    Methods:
        connect(): Establish async connection.
        connect_sync(): Establish sync connection.
        close(): Close all connections.
        connection(): Async context manager for connection lifecycle.

    Example:
        >>> from agentorchestrator.services import S3Service
        >>>
        >>> # Corporate environment with custom endpoint
        >>> s3 = S3Service(
        ...     endpoint_url="https://s3.company.com:9000",
        ...     bucket_name="my-bucket",
        ...     access_key_id=SecretString("my_access_key"),
        ...     secret_access_key=SecretString("my_secret_key"),
        ...     region="us-west-2",
        ... )
        >>>
        >>> # Connect
        >>> await s3.connect()
        >>>
        >>> # Upload and download
        >>> await s3.upload_file("data.json", "uploads/data.json")
        >>> content = await s3.download_file("uploads/data.json")
        >>>
        >>> # Health check
        >>> status = await s3.health_check()
        >>> print(f"S3 healthy: {status.healthy}")
        >>>
        >>> # Cleanup
        >>> await s3.close()

    Context Manager Usage:
        >>> async with s3.connection() as s3_client:
        ...     await s3_client.upload_file("file.txt", "key.txt")
        ...     # Connection automatically closed

    See Also:
        S3Config: Configuration options.
        S3HealthStatus: Health check result format.
    """

    def __init__(
        self,
        endpoint_url: str | None = None,
        bucket_name: str | None = None,
        access_key_id: SecretString | str | None = None,
        secret_access_key: SecretString | str | None = None,
        region: str = "us-east-1",
        use_ssl: bool = True,
        verify_ssl: bool = True,
        signature_version: str = "s3v4",
        max_pool_connections: int = 50,
        connect_timeout: float = 60.0,
        read_timeout: float = 60.0,
        max_retry_attempts: int = 3,
        config: S3Config | None = None,
    ):
        """
        Initialize S3 service.

        Can be initialized either with individual parameters or an
        S3Config instance. If config is provided, it overrides
        all other parameters.

        Args:
            endpoint_url (str | None): S3 endpoint URL. Default: None (AWS S3).
            bucket_name (str | None): Bucket name. Default: None.
            access_key_id (SecretString | str | None): Access key ID. Default: None.
            secret_access_key (SecretString | str | None): Secret access key. Default: None.
            region (str): AWS region. Default: "us-east-1".
            use_ssl (bool): Use SSL/TLS connection. Default: True.
            verify_ssl (bool): Verify SSL certificates. Default: True.
            signature_version (str): Signature version. Default: "s3v4".
            max_pool_connections (int): Max pool connections. Default: 50.
            connect_timeout (float): Connect timeout in seconds. Default: 60.0.
            read_timeout (float): Read timeout in seconds. Default: 60.0.
            max_retry_attempts (int): Max retry attempts. Default: 3.
            config (S3Config | None): Configuration instance. Default: None.
                If provided, overrides all other parameters.

        Raises:
            ImportError: If boto3/aioboto3 packages are not installed.
            S3ConfigurationError: If bucket_name is not provided.

        Example:
            >>> # Individual parameters
            >>> s3 = S3Service(
            ...     endpoint_url="https://s3.company.com:9000",
            ...     bucket_name="my-bucket",
            ...     region="us-west-2",
            ... )
            >>>
            >>> # Using config
            >>> config = S3Config.from_env()
            >>> s3 = S3Service(config=config)
        """
        if not S3_AVAILABLE:
            raise ImportError(
                "boto3 and aioboto3 packages are required. "
                "Install with: pip install boto3>=1.26.0 aioboto3>=11.0.0"
            )

        if config:
            self.config = config
        else:
            # Validate bucket_name
            if not bucket_name:
                raise S3ConfigurationError(
                    "bucket_name is required. Provide it as a parameter or use S3Service.from_env()"
                )

            # Wrap string credentials in SecretString if needed
            if isinstance(access_key_id, str):
                access_key_id = SecretString(access_key_id)
            if isinstance(secret_access_key, str):
                secret_access_key = SecretString(secret_access_key)

            self.config = S3Config(
                endpoint_url=endpoint_url,
                bucket_name=bucket_name,
                access_key_id=access_key_id,
                secret_access_key=secret_access_key,
                region=region,
                use_ssl=use_ssl,
                verify_ssl=verify_ssl,
                signature_version=signature_version,
                max_pool_connections=max_pool_connections,
                connect_timeout=connect_timeout,
                read_timeout=read_timeout,
                max_retry_attempts=max_retry_attempts,
            )

        self._client: Any = None  # aioboto3 S3 client
        self._sync_client: Any = None  # boto3 S3 client
        self._connected = False

    @classmethod
    def from_env(cls, prefix: str = "S3") -> "S3Service":
        """
        Create service from environment variables.

        Convenience factory that loads S3Config from environment
        and creates a service instance.

        Args:
            prefix (str): Environment variable prefix. Default: "S3".

        Returns:
            S3Service: Service configured from environment.

        Raises:
            S3ConfigurationError: If required configuration is missing.

        Example:
            >>> import os
            >>> os.environ["S3_BUCKET_NAME"] = "my-bucket"
            >>> os.environ["S3_ENDPOINT_URL"] = "https://s3.company.com:9000"
            >>>
            >>> s3 = S3Service.from_env()
            >>> await s3.connect()
        """
        config = S3Config.from_env(prefix)
        return cls(config=config)

    def _get_client_config(self) -> Any:
        """
        Build botocore Config object with connection settings.

        Returns:
            BotoConfig: Botocore configuration object.

        Example:
            >>> config = s3._get_client_config()
        """
        return BotoConfig(
            max_pool_connections=self.config.max_pool_connections,
            connect_timeout=self.config.connect_timeout,
            read_timeout=self.config.read_timeout,
            retries={
                "max_attempts": self.config.max_retry_attempts,
                "mode": "standard",
            },
            signature_version=self.config.signature_version,
        )

    # ═══════════════════════════════════════════════════════════════════════════
    #                         CONNECTION MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════════

    async def connect(self) -> "S3Service":
        """
        Establish async connection to S3.

        Creates an async S3 client with connection pooling and
        verifies the connection with a head_bucket call.

        Returns:
            S3Service: Self for method chaining.

        Raises:
            S3ConnectionError: If connection fails.
            S3BucketNotFoundError: If bucket does not exist.
            S3AccessDeniedError: If authentication fails.

        Example:
            >>> s3 = S3Service(bucket_name="my-bucket")
            >>> await s3.connect()
            >>> # Now ready for operations
            >>> await s3.upload_file("file.txt", "key.txt")
        """
        if self._client and self._connected:
            return self

        try:
            # Create aioboto3 session
            session = aioboto3.Session()

            # Get credentials (unwrap SecretString)
            aws_access_key_id = (
                self.config.access_key_id.get_secret_value()
                if self.config.access_key_id
                else None
            )
            aws_secret_access_key = (
                self.config.secret_access_key.get_secret_value()
                if self.config.secret_access_key
                else None
            )

            # Create async S3 client
            self._client = await session.client(
                "s3",
                endpoint_url=self.config.endpoint_url,
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key,
                region_name=self.config.region,
                use_ssl=self.config.use_ssl,
                verify=self.config.verify_ssl,
                config=self._get_client_config(),
            ).__aenter__()

            # Test connection by checking bucket access
            await self._client.head_bucket(Bucket=self.config.bucket_name)
            self._connected = True

            logger.info(
                f"Connected to S3 bucket '{self.config.bucket_name}' "
                f"at {self.config.endpoint_url or 'AWS S3'}"
            )
            return self

        except Exception as e:
            error_msg = str(e).lower()
            if "404" in error_msg or "notfound" in error_msg:
                raise S3BucketNotFoundError(
                    f"Bucket '{self.config.bucket_name}' does not exist"
                ) from e
            elif "403" in error_msg or "access denied" in error_msg:
                raise S3AccessDeniedError(
                    f"Access denied to bucket '{self.config.bucket_name}'. "
                    f"Check credentials and permissions."
                ) from e
            else:
                raise S3ConnectionError(
                    f"Failed to connect to S3: {e}"
                ) from e

    def connect_sync(self) -> "S3Service":
        """
        Establish synchronous connection to S3.

        Creates a sync S3 client for use in non-async contexts.

        Returns:
            S3Service: Self for method chaining.

        Raises:
            S3ConnectionError: If connection fails.
            S3BucketNotFoundError: If bucket does not exist.
            S3AccessDeniedError: If authentication fails.

        Example:
            >>> s3 = S3Service(bucket_name="my-bucket")
            >>> s3.connect_sync()
            >>> response = s3.sync_client.list_objects_v2(Bucket="my-bucket")
        """
        if self._sync_client:
            return self

        try:
            # Get credentials (unwrap SecretString)
            aws_access_key_id = (
                self.config.access_key_id.get_secret_value()
                if self.config.access_key_id
                else None
            )
            aws_secret_access_key = (
                self.config.secret_access_key.get_secret_value()
                if self.config.secret_access_key
                else None
            )

            # Create boto3 client
            self._sync_client = boto3.client(
                "s3",
                endpoint_url=self.config.endpoint_url,
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key,
                region_name=self.config.region,
                use_ssl=self.config.use_ssl,
                verify=self.config.verify_ssl,
                config=self._get_client_config(),
            )

            # Test connection by checking bucket access
            self._sync_client.head_bucket(Bucket=self.config.bucket_name)

            logger.info(
                f"Connected to S3 (sync) bucket '{self.config.bucket_name}' "
                f"at {self.config.endpoint_url or 'AWS S3'}"
            )
            return self

        except Exception as e:
            error_msg = str(e).lower()
            if "404" in error_msg or "notfound" in error_msg:
                raise S3BucketNotFoundError(
                    f"Bucket '{self.config.bucket_name}' does not exist"
                ) from e
            elif "403" in error_msg or "access denied" in error_msg:
                raise S3AccessDeniedError(
                    f"Access denied to bucket '{self.config.bucket_name}'. "
                    f"Check credentials and permissions."
                ) from e
            else:
                raise S3ConnectionError(
                    f"Failed to connect to S3: {e}"
                ) from e

    async def close(self) -> None:
        """
        Close S3 connections.

        Closes the async S3 client if it exists.
        Safe to call multiple times.

        Example:
            >>> await s3.close()
            >>> # Connections are now closed
        """
        if self._client:
            await self._client.__aexit__(None, None, None)
            self._client = None
            self._connected = False
            logger.info("S3 async connection closed")

    @property
    def is_connected(self) -> bool:
        """
        Check if async client is connected.

        Returns:
            bool: True if connected, False otherwise.

        Example:
            >>> if not s3.is_connected:
            ...     await s3.connect()
        """
        return self._connected and self._client is not None

    @asynccontextmanager
    async def connection(self) -> AsyncIterator["S3Service"]:
        """
        Context manager for S3 connection.

        Automatically connects on enter and closes on exit.
        Useful for ensuring cleanup in scripts.

        Yields:
            S3Service: This service instance.

        Example:
            >>> async with s3.connection() as s3_client:
            ...     await s3_client.upload_file("file.txt", "key.txt")
            ...     content = await s3_client.download_file("key.txt")
            >>> # Connection automatically closed
        """
        await self.connect()
        try:
            yield self
        finally:
            await self.close()

    # Context manager support
    async def __aenter__(self) -> "S3Service":
        """Async context manager entry."""
        return await self.connect()

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    @property
    def client(self) -> Any:
        """
        Get the async S3 client.

        Returns:
            aioboto3 S3 client: The async S3 client.

        Raises:
            RuntimeError: If not connected.

        Example:
            >>> await s3.connect()
            >>> # Direct client access for advanced operations
            >>> response = await s3.client.list_objects_v2(
            ...     Bucket=s3.config.bucket_name
            ... )
        """
        if not self._client:
            raise RuntimeError(
                "S3 not connected. Call connect() first or use connection() context manager."
            )
        return self._client

    @property
    def sync_client(self) -> Any:
        """
        Get the sync S3 client.

        Returns:
            boto3 S3 client: The sync S3 client.

        Raises:
            RuntimeError: If not connected.

        Example:
            >>> s3.connect_sync()
            >>> response = s3.sync_client.list_objects_v2(
            ...     Bucket=s3.config.bucket_name
            ... )
        """
        if not self._sync_client:
            raise RuntimeError(
                "S3 sync client not connected. Call connect_sync() first."
            )
        return self._sync_client

    # ═══════════════════════════════════════════════════════════════════════════
    #                         UPLOAD OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════

    async def upload_file(
        self,
        file_path: str | Path,
        object_key: str,
        bucket: str | None = None,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
        storage_class: str = "STANDARD",
        server_side_encryption: str | None = None,
    ) -> dict[str, Any]:
        """
        Upload a file from local filesystem to S3.

        Uploads a file from the local filesystem to an S3 bucket, with support
        for custom content types, metadata, storage classes, and encryption.
        Automatically detects content type if not specified.

        Args:
            file_path (str | Path): Path to the local file to upload.
            object_key (str): S3 object key (destination path in bucket).
                Example: "uploads/data.json", "images/photo.jpg".
            bucket (str | None): Bucket name. If None, uses configured bucket.
                Default: None.
            content_type (str | None): MIME type of the file. If None, auto-detects
                using mimetypes module. Default: None.
                Example: "application/json", "image/jpeg".
            metadata (dict[str, str] | None): User-defined metadata for the object.
                Stored as key-value pairs. Default: None.
                Example: {"author": "john", "version": "1.0"}.
            storage_class (str): S3 storage class. Default: "STANDARD".
                Options: "STANDARD", "REDUCED_REDUNDANCY", "STANDARD_IA",
                "ONEZONE_IA", "INTELLIGENT_TIERING", "GLACIER", "DEEP_ARCHIVE".
            server_side_encryption (str | None): Server-side encryption algorithm.
                Default: None (no encryption).
                Options: "AES256", "aws:kms".

        Returns:
            dict[str, Any]: Upload result containing:
                - etag (str): Entity tag of the uploaded object
                - version_id (str | None): Version ID if versioning is enabled
                - server_side_encryption (str | None): Encryption used
                - expiration (str | None): Expiration rule applied
                - bucket (str): Target bucket name
                - key (str): Object key
                - content_type (str): Content type used

        Raises:
            S3UploadError: If upload fails.
            S3AccessDeniedError: If permission denied.
            S3BucketNotFoundError: If bucket does not exist.
            FileNotFoundError: If local file does not exist.

        Example:
            >>> # Basic upload
            >>> result = await s3.upload_file(
            ...     "local_data.json",
            ...     "uploads/data.json"
            ... )
            >>> print(f"Uploaded with ETag: {result['etag']}")
            >>>
            >>> # Upload with metadata and encryption
            >>> result = await s3.upload_file(
            ...     "sensitive.pdf",
            ...     "documents/sensitive.pdf",
            ...     content_type="application/pdf",
            ...     metadata={"department": "finance", "confidential": "true"},
            ...     storage_class="STANDARD_IA",
            ...     server_side_encryption="AES256"
            ... )
            >>>
            >>> # Upload to different bucket
            >>> result = await s3.upload_file(
            ...     "backup.zip",
            ...     "backups/backup.zip",
            ...     bucket="backup-bucket"
            ... )

        See Also:
            upload_fileobj(): Upload from file-like object.
            upload_bytes(): Upload bytes directly.
        """
        file_path = Path(file_path)

        # Validate file exists
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not file_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

        # Use configured bucket if not specified
        target_bucket = bucket or self.config.bucket_name

        # Auto-detect content type if not provided
        if content_type is None:
            content_type, _ = mimetypes.guess_type(str(file_path))
            if content_type is None:
                content_type = "application/octet-stream"

        # Build extra arguments
        extra_args: dict[str, Any] = {
            "ContentType": content_type,
            "StorageClass": storage_class,
        }

        if metadata:
            extra_args["Metadata"] = metadata

        if server_side_encryption:
            extra_args["ServerSideEncryption"] = server_side_encryption

        try:
            logger.info(
                f"Uploading file '{file_path}' to s3://{target_bucket}/{object_key}"
            )

            # Use put_object for better control over response
            with open(file_path, "rb") as f:
                response = await self.client.put_object(
                    Bucket=target_bucket,
                    Key=object_key,
                    Body=f,
                    **extra_args,
                )

            result = {
                "etag": response.get("ETag", "").strip('"'),
                "version_id": response.get("VersionId"),
                "server_side_encryption": response.get("ServerSideEncryption"),
                "expiration": response.get("Expiration"),
                "bucket": target_bucket,
                "key": object_key,
                "content_type": content_type,
            }

            logger.info(
                f"Successfully uploaded '{file_path}' to s3://{target_bucket}/{object_key} "
                f"(ETag: {result['etag']})"
            )

            return result

        except Exception as e:
            error_msg = str(e).lower()

            if "404" in error_msg or "nosuchbucket" in error_msg:
                raise S3BucketNotFoundError(
                    f"Bucket '{target_bucket}' does not exist"
                ) from e
            elif "403" in error_msg or "access denied" in error_msg:
                raise S3AccessDeniedError(
                    f"Access denied uploading to s3://{target_bucket}/{object_key}. "
                    f"Check credentials and permissions."
                ) from e
            else:
                raise S3UploadError(
                    f"Failed to upload '{file_path}' to s3://{target_bucket}/{object_key}: {e}"
                ) from e

    async def upload_fileobj(
        self,
        file_obj: BinaryIO,
        object_key: str,
        bucket: str | None = None,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Upload from file-like object to S3.

        Uploads content from a file-like object (such as BytesIO, file handle,
        or any object with a read() method) to S3. Useful for uploading
        in-memory data or streaming uploads.

        Args:
            file_obj (BinaryIO): File-like object to upload. Must be opened in
                binary mode and support read() method.
            object_key (str): S3 object key (destination path in bucket).
                Example: "uploads/data.json", "images/photo.jpg".
            bucket (str | None): Bucket name. If None, uses configured bucket.
                Default: None.
            content_type (str | None): MIME type of the content. Default: None.
                If None, defaults to "application/octet-stream".
                Example: "application/json", "image/jpeg".
            metadata (dict[str, str] | None): User-defined metadata for the object.
                Stored as key-value pairs. Default: None.
                Example: {"author": "john", "version": "1.0"}.

        Returns:
            dict[str, Any]: Upload result containing:
                - etag (str): Entity tag of the uploaded object
                - version_id (str | None): Version ID if versioning is enabled
                - server_side_encryption (str | None): Encryption used
                - bucket (str): Target bucket name
                - key (str): Object key
                - content_type (str): Content type used

        Raises:
            S3UploadError: If upload fails.
            S3AccessDeniedError: If permission denied.
            S3BucketNotFoundError: If bucket does not exist.

        Example:
            >>> from io import BytesIO
            >>>
            >>> # Upload from BytesIO
            >>> data = BytesIO(b'{"name": "test", "value": 123}')
            >>> result = await s3.upload_fileobj(
            ...     data,
            ...     "uploads/data.json",
            ...     content_type="application/json"
            ... )
            >>> print(f"Uploaded with ETag: {result['etag']}")
            >>>
            >>> # Upload with metadata
            >>> data = BytesIO(b"Hello, World!")
            >>> result = await s3.upload_fileobj(
            ...     data,
            ...     "messages/hello.txt",
            ...     content_type="text/plain",
            ...     metadata={"author": "system", "timestamp": "2024-01-01"}
            ... )
            >>>
            >>> # Upload from file handle
            >>> with open("data.bin", "rb") as f:
            ...     result = await s3.upload_fileobj(
            ...         f,
            ...         "uploads/data.bin"
            ...     )

        See Also:
            upload_file(): Upload from filesystem path.
            upload_bytes(): Upload bytes directly.
        """
        # Use configured bucket if not specified
        target_bucket = bucket or self.config.bucket_name

        # Default content type
        if content_type is None:
            content_type = "application/octet-stream"

        # Build extra arguments
        extra_args: dict[str, Any] = {
            "ContentType": content_type,
        }

        if metadata:
            extra_args["Metadata"] = metadata

        try:
            logger.info(
                f"Uploading file object to s3://{target_bucket}/{object_key}"
            )

            # Use put_object with file object
            response = await self.client.put_object(
                Bucket=target_bucket,
                Key=object_key,
                Body=file_obj,
                **extra_args,
            )

            result = {
                "etag": response.get("ETag", "").strip('"'),
                "version_id": response.get("VersionId"),
                "server_side_encryption": response.get("ServerSideEncryption"),
                "bucket": target_bucket,
                "key": object_key,
                "content_type": content_type,
            }

            logger.info(
                f"Successfully uploaded file object to s3://{target_bucket}/{object_key} "
                f"(ETag: {result['etag']})"
            )

            return result

        except Exception as e:
            error_msg = str(e).lower()

            if "404" in error_msg or "nosuchbucket" in error_msg:
                raise S3BucketNotFoundError(
                    f"Bucket '{target_bucket}' does not exist"
                ) from e
            elif "403" in error_msg or "access denied" in error_msg:
                raise S3AccessDeniedError(
                    f"Access denied uploading to s3://{target_bucket}/{object_key}. "
                    f"Check credentials and permissions."
                ) from e
            else:
                raise S3UploadError(
                    f"Failed to upload file object to s3://{target_bucket}/{object_key}: {e}"
                ) from e

    async def upload_bytes(
        self,
        data: bytes,
        object_key: str,
        bucket: str | None = None,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Upload bytes directly to S3.

        Uploads raw bytes to S3. Useful for uploading small in-memory data,
        generated content, or serialized objects without creating intermediate
        file objects.

        Args:
            data (bytes): Raw bytes to upload.
            object_key (str): S3 object key (destination path in bucket).
                Example: "uploads/data.json", "cache/response.bin".
            bucket (str | None): Bucket name. If None, uses configured bucket.
                Default: None.
            content_type (str | None): MIME type of the content. Default: None.
                If None, defaults to "application/octet-stream".
                Example: "application/json", "text/plain".
            metadata (dict[str, str] | None): User-defined metadata for the object.
                Stored as key-value pairs. Default: None.
                Example: {"source": "api", "checksum": "abc123"}.

        Returns:
            dict[str, Any]: Upload result containing:
                - etag (str): Entity tag of the uploaded object
                - version_id (str | None): Version ID if versioning is enabled
                - server_side_encryption (str | None): Encryption used
                - bucket (str): Target bucket name
                - key (str): Object key
                - content_type (str): Content type used
                - size (int): Number of bytes uploaded

        Raises:
            S3UploadError: If upload fails.
            S3AccessDeniedError: If permission denied.
            S3BucketNotFoundError: If bucket does not exist.

        Example:
            >>> # Upload JSON data
            >>> import json
            >>> data = json.dumps({"name": "test", "value": 123}).encode()
            >>> result = await s3.upload_bytes(
            ...     data,
            ...     "uploads/data.json",
            ...     content_type="application/json"
            ... )
            >>> print(f"Uploaded {result['size']} bytes")
            >>>
            >>> # Upload text content
            >>> text = "Hello, World!"
            >>> result = await s3.upload_bytes(
            ...     text.encode("utf-8"),
            ...     "messages/hello.txt",
            ...     content_type="text/plain; charset=utf-8"
            ... )
            >>>
            >>> # Upload with metadata
            >>> data = b"Binary data here"
            >>> result = await s3.upload_bytes(
            ...     data,
            ...     "cache/response.bin",
            ...     metadata={"generated": "2024-01-01", "ttl": "3600"}
            ... )
            >>>
            >>> # Upload to different bucket
            >>> result = await s3.upload_bytes(
            ...     data,
            ...     "backup/data.bin",
            ...     bucket="backup-bucket"
            ... )

        See Also:
            upload_file(): Upload from filesystem path.
            upload_fileobj(): Upload from file-like object.
        """
        # Use configured bucket if not specified
        target_bucket = bucket or self.config.bucket_name

        # Default content type
        if content_type is None:
            content_type = "application/octet-stream"

        # Build extra arguments
        extra_args: dict[str, Any] = {
            "ContentType": content_type,
        }

        if metadata:
            extra_args["Metadata"] = metadata

        try:
            logger.info(
                f"Uploading {len(data)} bytes to s3://{target_bucket}/{object_key}"
            )

            # Use put_object with bytes
            response = await self.client.put_object(
                Bucket=target_bucket,
                Key=object_key,
                Body=data,
                **extra_args,
            )

            result = {
                "etag": response.get("ETag", "").strip('"'),
                "version_id": response.get("VersionId"),
                "server_side_encryption": response.get("ServerSideEncryption"),
                "bucket": target_bucket,
                "key": object_key,
                "content_type": content_type,
                "size": len(data),
            }

            logger.info(
                f"Successfully uploaded {len(data)} bytes to s3://{target_bucket}/{object_key} "
                f"(ETag: {result['etag']})"
            )

            return result

        except Exception as e:
            error_msg = str(e).lower()

            if "404" in error_msg or "nosuchbucket" in error_msg:
                raise S3BucketNotFoundError(
                    f"Bucket '{target_bucket}' does not exist"
                ) from e
            elif "403" in error_msg or "access denied" in error_msg:
                raise S3AccessDeniedError(
                    f"Access denied uploading to s3://{target_bucket}/{object_key}. "
                    f"Check credentials and permissions."
                ) from e
            else:
                raise S3UploadError(
                    f"Failed to upload bytes to s3://{target_bucket}/{object_key}: {e}"
                ) from e

    # ═══════════════════════════════════════════════════════════════════════════
    #                         DOWNLOAD OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════

    async def download_file(
        self,
        object_key: str,
        file_path: str | Path,
        bucket: str | None = None,
        version_id: str | None = None,
    ) -> Path:
        """
        Download S3 object to local file.

        Downloads an object from S3 to a local file path. The parent directory
        will be created if it doesn't exist. Supports versioned objects.

        Args:
            object_key (str): S3 object key (path within bucket).
                Example: "uploads/data.json", "reports/2024/summary.pdf"
            file_path (str | Path): Local file path where object will be saved.
                Parent directories are created automatically.
                Example: "/tmp/downloaded.txt", Path("./output/file.json")
            bucket (str | None): Bucket name. Default: None (uses config bucket).
            version_id (str | None): Object version ID for versioned buckets.
                Default: None (downloads latest version).

        Returns:
            Path: Path object pointing to the downloaded file.

        Raises:
            S3ObjectNotFoundError: If object does not exist.
            S3AccessDeniedError: If access is denied.
            S3DownloadError: If download fails for other reasons.
            RuntimeError: If not connected.

        Example:
            >>> # Download to file
            >>> path = await s3.download_file(
            ...     "reports/summary.pdf",
            ...     "/tmp/summary.pdf"
            ... )
            >>> print(f"Downloaded to: {path}")
            >>>
            >>> # Download specific version
            >>> path = await s3.download_file(
            ...     "data.json",
            ...     "./data.json",
            ...     version_id="abc123"
            ... )
            >>>
            >>> # Download from different bucket
            >>> path = await s3.download_file(
            ...     "file.txt",
            ...     "./file.txt",
            ...     bucket="other-bucket"
            ... )

        See Also:
            download_bytes(): Download object as bytes in memory.
            download_text(): Download object as text string.
            download_fileobj(): Download to file-like object.
        """
        bucket_name = bucket or self.config.bucket_name
        file_path = Path(file_path)

        try:
            # Create parent directory if it doesn't exist
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Build download parameters
            download_params: dict[str, Any] = {
                "Bucket": bucket_name,
                "Key": object_key,
                "Filename": str(file_path),
            }

            # Add version_id if specified
            if version_id:
                download_params["ExtraArgs"] = {"VersionId": version_id}

            # Download file using aioboto3
            await self.client.download_file(**download_params)

            logger.debug(
                f"Downloaded S3 object '{object_key}' from bucket '{bucket_name}' "
                f"to '{file_path}'"
            )

            return file_path

        except Exception as e:
            error_msg = str(e).lower()
            error_code = getattr(e, "response", {}).get("Error", {}).get("Code", "")

            if error_code == "NoSuchKey" or "404" in error_msg or "not found" in error_msg:
                raise S3ObjectNotFoundError(
                    f"Object '{object_key}' not found in bucket '{bucket_name}'",
                    bucket=bucket_name,
                    key=object_key,
                ) from e
            elif error_code == "AccessDenied" or "403" in error_msg or "access denied" in error_msg:
                raise S3AccessDeniedError(
                    f"Access denied to object '{object_key}' in bucket '{bucket_name}'. "
                    f"Check credentials and permissions."
                ) from e
            else:
                raise S3DownloadError(
                    f"Failed to download '{object_key}' from bucket '{bucket_name}': {e}"
                ) from e

    async def download_fileobj(
        self,
        object_key: str,
        file_obj: BinaryIO,
        bucket: str | None = None,
    ) -> int:
        """
        Download S3 object to file-like object.

        Downloads an object directly to a file-like object (e.g., BytesIO, open file).
        Useful for streaming downloads or processing data without writing to disk.

        Args:
            object_key (str): S3 object key (path within bucket).
                Example: "uploads/data.json", "reports/summary.pdf"
            file_obj (BinaryIO): File-like object opened in binary mode.
                Must support write() method. Examples: io.BytesIO, open file handle.
            bucket (str | None): Bucket name. Default: None (uses config bucket).

        Returns:
            int: Number of bytes downloaded.

        Raises:
            S3ObjectNotFoundError: If object does not exist.
            S3AccessDeniedError: If access is denied.
            S3DownloadError: If download fails for other reasons.
            RuntimeError: If not connected.

        Example:
            >>> import io
            >>>
            >>> # Download to BytesIO
            >>> buffer = io.BytesIO()
            >>> bytes_downloaded = await s3.download_fileobj(
            ...     "data.json",
            ...     buffer
            ... )
            >>> print(f"Downloaded {bytes_downloaded} bytes")
            >>> buffer.seek(0)
            >>> data = buffer.read()
            >>>
            >>> # Download to open file
            >>> with open("output.pdf", "wb") as f:
            ...     bytes_count = await s3.download_fileobj("report.pdf", f)
            ...     print(f"Downloaded {bytes_count} bytes")

        See Also:
            download_file(): Download to file path.
            download_bytes(): Download as bytes in memory.
            download_text(): Download as text string.
        """
        bucket_name = bucket or self.config.bucket_name

        try:
            # Get current position to calculate bytes downloaded
            initial_pos = file_obj.tell() if hasattr(file_obj, "tell") else 0

            # Download to file object using aioboto3
            await self.client.download_fileobj(
                Bucket=bucket_name,
                Key=object_key,
                Fileobj=file_obj,
            )

            # Calculate bytes downloaded
            final_pos = file_obj.tell() if hasattr(file_obj, "tell") else 0
            bytes_downloaded = final_pos - initial_pos

            logger.debug(
                f"Downloaded {bytes_downloaded} bytes from S3 object '{object_key}' "
                f"in bucket '{bucket_name}'"
            )

            return bytes_downloaded

        except Exception as e:
            error_msg = str(e).lower()
            error_code = getattr(e, "response", {}).get("Error", {}).get("Code", "")

            if error_code == "NoSuchKey" or "404" in error_msg or "not found" in error_msg:
                raise S3ObjectNotFoundError(
                    f"Object '{object_key}' not found in bucket '{bucket_name}'",
                    bucket=bucket_name,
                    key=object_key,
                ) from e
            elif error_code == "AccessDenied" or "403" in error_msg or "access denied" in error_msg:
                raise S3AccessDeniedError(
                    f"Access denied to object '{object_key}' in bucket '{bucket_name}'. "
                    f"Check credentials and permissions."
                ) from e
            else:
                raise S3DownloadError(
                    f"Failed to download '{object_key}' from bucket '{bucket_name}': {e}"
                ) from e

    async def download_bytes(
        self,
        object_key: str,
        bucket: str | None = None,
    ) -> bytes:
        """
        Download S3 object as bytes.

        Downloads an object and returns its contents as bytes in memory.
        Suitable for small to medium-sized objects. For large files,
        consider using download_file() or download_fileobj() instead.

        Args:
            object_key (str): S3 object key (path within bucket).
                Example: "uploads/data.json", "images/photo.jpg"
            bucket (str | None): Bucket name. Default: None (uses config bucket).

        Returns:
            bytes: Object contents as bytes.

        Raises:
            S3ObjectNotFoundError: If object does not exist.
            S3AccessDeniedError: If access is denied.
            S3DownloadError: If download fails for other reasons.
            RuntimeError: If not connected.

        Example:
            >>> # Download JSON data
            >>> data_bytes = await s3.download_bytes("data.json")
            >>> import json
            >>> data = json.loads(data_bytes)
            >>>
            >>> # Download image
            >>> image_bytes = await s3.download_bytes("images/logo.png")
            >>> with open("logo.png", "wb") as f:
            ...     f.write(image_bytes)
            >>>
            >>> # Download from different bucket
            >>> content = await s3.download_bytes(
            ...     "file.bin",
            ...     bucket="other-bucket"
            ... )

        See Also:
            download_text(): Download object as text string.
            download_file(): Download to file path.
            download_fileobj(): Download to file-like object.
        """
        bucket_name = bucket or self.config.bucket_name

        try:
            # Get object using get_object API
            response = await self.client.get_object(
                Bucket=bucket_name,
                Key=object_key,
            )

            # Read body as bytes
            async with response["Body"] as stream:
                content = await stream.read()

            logger.debug(
                f"Downloaded {len(content)} bytes from S3 object '{object_key}' "
                f"in bucket '{bucket_name}'"
            )

            return content

        except Exception as e:
            error_msg = str(e).lower()
            error_code = getattr(e, "response", {}).get("Error", {}).get("Code", "")

            if error_code == "NoSuchKey" or "404" in error_msg or "not found" in error_msg:
                raise S3ObjectNotFoundError(
                    f"Object '{object_key}' not found in bucket '{bucket_name}'",
                    bucket=bucket_name,
                    key=object_key,
                ) from e
            elif error_code == "AccessDenied" or "403" in error_msg or "access denied" in error_msg:
                raise S3AccessDeniedError(
                    f"Access denied to object '{object_key}' in bucket '{bucket_name}'. "
                    f"Check credentials and permissions."
                ) from e
            else:
                raise S3DownloadError(
                    f"Failed to download '{object_key}' from bucket '{bucket_name}': {e}"
                ) from e

    async def download_text(
        self,
        object_key: str,
        bucket: str | None = None,
        encoding: str = "utf-8",
    ) -> str:
        """
        Download S3 object as text string.

        Downloads an object and returns its contents as a decoded text string.
        Suitable for text files, JSON, XML, CSV, and other text-based formats.

        Args:
            object_key (str): S3 object key (path within bucket).
                Example: "config.json", "logs/app.log", "data.csv"
            bucket (str | None): Bucket name. Default: None (uses config bucket).
            encoding (str): Text encoding to use for decoding.
                Default: "utf-8". Common options: "utf-8", "ascii", "latin-1".

        Returns:
            str: Object contents as decoded text string.

        Raises:
            S3ObjectNotFoundError: If object does not exist.
            S3AccessDeniedError: If access is denied.
            S3DownloadError: If download fails for other reasons.
            UnicodeDecodeError: If content cannot be decoded with specified encoding.
            RuntimeError: If not connected.

        Example:
            >>> # Download JSON config
            >>> config_json = await s3.download_text("config/app.json")
            >>> import json
            >>> config = json.loads(config_json)
            >>>
            >>> # Download log file
            >>> log_content = await s3.download_text("logs/app.log")
            >>> for line in log_content.splitlines():
            ...     print(line)
            >>>
            >>> # Download CSV data
            >>> csv_data = await s3.download_text("data/report.csv")
            >>> import csv
            >>> import io
            >>> reader = csv.DictReader(io.StringIO(csv_data))
            >>>
            >>> # Download with different encoding
            >>> content = await s3.download_text(
            ...     "legacy.txt",
            ...     encoding="latin-1"
            ... )

        See Also:
            download_bytes(): Download object as bytes.
            download_file(): Download to file path.
            download_fileobj(): Download to file-like object.
        """
        bucket_name = bucket or self.config.bucket_name

        try:
            # Download as bytes first
            content_bytes = await self.download_bytes(object_key, bucket)

            # Decode to string
            content_str = content_bytes.decode(encoding)

            logger.debug(
                f"Downloaded and decoded {len(content_str)} characters from S3 object "
                f"'{object_key}' in bucket '{bucket_name}' using {encoding} encoding"
            )

            return content_str

        except UnicodeDecodeError as e:
            raise S3DownloadError(
                f"Failed to decode '{object_key}' from bucket '{bucket_name}' "
                f"using encoding '{encoding}': {e}"
            ) from e
        except S3Error:
            # Re-raise S3 errors as-is (already properly formatted)
            raise
        except Exception as e:
            raise S3DownloadError(
                f"Failed to download text from '{object_key}' in bucket '{bucket_name}': {e}"
            ) from e

    # ═══════════════════════════════════════════════════════════════════════════
    #                         HEALTH CHECK
    # ═══════════════════════════════════════════════════════════════════════════

    async def health_check(self) -> S3HealthStatus:
        """
        Perform a comprehensive health check.

        Checks bucket accessibility, measures latency, and retrieves bucket
        information including region.

        Returns:
            S3HealthStatus: Health status with detailed bucket info.

        Example:
            >>> status = await s3.health_check()
            >>> if status.healthy:
            ...     print(f"S3 healthy - {status.latency_ms:.1f}ms latency")
            ...     print(f"Bucket region: {status.bucket_region}")
            ...     print(f"Bucket accessible: {status.bucket_accessible}")
            ... else:
            ...     print(f"S3 unhealthy: {status.error}")
        """
        import time

        start = time.perf_counter()

        try:
            # Ensure connected
            if not self._connected:
                await self.connect()

            # Perform head_bucket request to check accessibility and measure latency
            response = await self.client.head_bucket(Bucket=self.config.bucket_name)
            latency_ms = (time.perf_counter() - start) * 1000

            # Extract bucket region from response headers
            bucket_region = response.get("ResponseMetadata", {}).get("HTTPHeaders", {}).get("x-amz-bucket-region")
            if not bucket_region:
                # Fallback to configured region
                bucket_region = self.config.region

            return S3HealthStatus(
                healthy=True,
                latency_ms=latency_ms,
                bucket_accessible=True,
                bucket_region=bucket_region,
                endpoint_url=self.config.endpoint_url,
            )

        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000

            # Import ClientError if botocore is available
            try:
                from botocore.exceptions import ClientError

                # Check if this is a ClientError
                if isinstance(e, ClientError):
                    error_code = e.response.get("Error", {}).get("Code", "Unknown")
                    error_msg = f"S3 error ({error_code}): {str(e)}"
                else:
                    error_msg = f"S3 connection error: {str(e)}"
            except ImportError:
                error_msg = f"S3 error: {str(e)}"

            return S3HealthStatus(
                healthy=False,
                latency_ms=latency_ms,
                bucket_accessible=False,
                bucket_region=None,
                endpoint_url=self.config.endpoint_url,
                error=error_msg,
            )

    async def ping(self) -> bool:
        """
        Simple connectivity check.

        Performs a quick check to see if the S3 service and bucket are accessible.
        This is a lightweight wrapper around health_check() that returns a simple
        boolean result.

        Returns:
            bool: True if S3 is accessible, False otherwise.

        Example:
            >>> if await s3.ping():
            ...     print("S3 is accessible")
            ... else:
            ...     print("S3 is not accessible")
        """
        try:
            status = await self.health_check()
            return status.healthy
        except Exception as e:
            logger.debug("S3 ping failed: %s", e)
            return False

        if not self._sync_client:
            raise RuntimeError(
                "S3 sync client not connected. Call connect_sync() first."
            )
        return self._sync_client

    # ═══════════════════════════════════════════════════════════════════════════
    #                         DELETE OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════

    async def delete_object(
        self,
        object_key: str,
        bucket: str | None = None,
        version_id: str | None = None,
    ) -> bool:
        """
        Delete a single object from S3.

        Deletes an object from the specified S3 bucket. For versioned buckets,
        you can specify a version_id to delete a specific version. If the object
        does not exist, returns False without raising an error.

        Args:
            object_key (str): The S3 object key to delete.
                Example: "uploads/data.json" or "logs/2024/file.txt"
            bucket (str | None): Bucket name. Default: None (uses configured bucket).
                Override the default bucket for this operation.
            version_id (str | None): Version ID for versioned buckets. Default: None.
                If specified, deletes only this specific version.

        Returns:
            bool: True if object was deleted, False if object did not exist.

        Raises:
            S3AccessDeniedError: If lacking permissions to delete.
            S3BucketNotFoundError: If bucket does not exist.
            S3Error: For other S3 errors.

        Example:
            >>> # Delete a single object
            >>> await s3.connect()
            >>> deleted = await s3.delete_object("uploads/old_file.txt")
            >>> if deleted:
            ...     print("File deleted successfully")
            ... else:
            ...     print("File did not exist")
            >>>
            >>> # Delete from a different bucket
            >>> await s3.delete_object("data.json", bucket="other-bucket")
            >>>
            >>> # Delete specific version (versioned bucket)
            >>> await s3.delete_object(
            ...     "document.pdf",
            ...     version_id="Reb8RLjFzhEcYjlRTB.N8jSvMK1rWg"
            ... )

        Note:
            - For non-versioned buckets, this permanently deletes the object
            - For versioned buckets without version_id, adds a delete marker
            - Returns False (not an error) if object does not exist (NoSuchKey)
            - Requires s3:DeleteObject permission

        See Also:
            delete_objects(): Batch delete multiple objects efficiently.
        """
        target_bucket = bucket or self.config.bucket_name

        try:
            # Prepare delete parameters
            delete_params: dict[str, Any] = {
                "Bucket": target_bucket,
                "Key": object_key,
            }

            # Add version ID if specified
            if version_id:
                delete_params["VersionId"] = version_id

            # Delete the object
            await self.client.delete_object(**delete_params)

            logger.info(
                f"Deleted object '{object_key}' from bucket '{target_bucket}'"
                + (f" (version: {version_id})" if version_id else "")
            )
            return True

        except Exception as e:
            error_msg = str(e).lower()

            # NoSuchKey is not an error - object didn't exist
            if "nosuchkey" in error_msg or "404" in error_msg:
                logger.debug(
                    f"Object '{object_key}' does not exist in bucket '{target_bucket}'"
                )
                return False

            # Handle specific error cases
            if "403" in error_msg or "access denied" in error_msg:
                raise S3AccessDeniedError(
                    f"Access denied when deleting '{object_key}' from bucket '{target_bucket}'. "
                    f"Check permissions."
                ) from e
            elif "nosuchbucket" in error_msg:
                raise S3BucketNotFoundError(
                    f"Bucket '{target_bucket}' does not exist"
                ) from e
            else:
                raise S3Error(
                    f"Failed to delete object '{object_key}' from bucket '{target_bucket}': {e}"
                ) from e

    async def delete_objects(
        self,
        object_keys: list[str],
        bucket: str | None = None,
    ) -> dict[str, list[str]]:
        """
        Batch delete multiple objects from S3.

        Efficiently deletes multiple objects in a single API call. S3 supports
        deleting up to 1000 objects per request. This method handles partial
        failures gracefully, returning both successfully deleted objects and
        any errors that occurred.

        Args:
            object_keys (list[str]): List of object keys to delete.
                Example: ["uploads/file1.txt", "uploads/file2.txt"]
                Maximum 1000 keys per call (S3 limitation).
            bucket (str | None): Bucket name. Default: None (uses configured bucket).
                Override the default bucket for this operation.

        Returns:
            dict[str, list[str]]: Dictionary with two keys:
                - 'deleted': List of successfully deleted object keys
                - 'errors': List of error messages for failed deletions

        Raises:
            S3AccessDeniedError: If lacking permissions to delete.
            S3BucketNotFoundError: If bucket does not exist.
            S3Error: For other S3 errors.
            ValueError: If object_keys list is empty or exceeds 1000 items.

        Example:
            >>> # Delete multiple objects
            >>> await s3.connect()
            >>> result = await s3.delete_objects([
            ...     "uploads/file1.txt",
            ...     "uploads/file2.txt",
            ...     "logs/old_log.txt",
            ... ])
            >>> print(f"Deleted: {len(result['deleted'])} files")
            >>> if result['errors']:
            ...     print(f"Errors: {result['errors']}")
            >>>
            >>> # Delete from different bucket
            >>> result = await s3.delete_objects(
            ...     ["data1.json", "data2.json"],
            ...     bucket="other-bucket"
            ... )
            >>>
            >>> # Handle partial failures
            >>> result = await s3.delete_objects(keys)
            >>> if result['errors']:
            ...     print("Some deletions failed:")
            ...     for error in result['errors']:
            ...         print(f"  - {error}")
            >>> else:
            ...     print("All objects deleted successfully")

        Note:
            - Maximum 1000 objects per request (S3 API limit)
            - Non-existent objects are counted as successfully deleted
            - Partial failures are returned in the 'errors' list
            - For versioned buckets, adds delete markers (not permanent deletion)
            - Requires s3:DeleteObject permission

        See Also:
            delete_object(): Delete a single object with more control options.
        """
        if not object_keys:
            raise ValueError("object_keys list cannot be empty")

        if len(object_keys) > 1000:
            raise ValueError(
                f"Cannot delete more than 1000 objects per request. "
                f"Got {len(object_keys)} keys. Split into multiple batches."
            )

        target_bucket = bucket or self.config.bucket_name

        try:
            # Prepare delete request
            delete_request = {
                "Objects": [{"Key": key} for key in object_keys],
                "Quiet": False,  # Return list of deleted objects
            }

            # Execute batch delete
            response = await self.client.delete_objects(
                Bucket=target_bucket,
                Delete=delete_request,
            )

            # Parse response
            deleted_objects = response.get("Deleted", [])
            deleted_keys = [obj["Key"] for obj in deleted_objects]

            # Parse errors
            error_objects = response.get("Errors", [])
            error_messages = [
                f"{err['Key']}: {err.get('Code', 'Unknown')} - {err.get('Message', 'No message')}"
                for err in error_objects
            ]

            logger.info(
                f"Batch deleted {len(deleted_keys)} objects from bucket '{target_bucket}'"
                + (f" ({len(error_messages)} errors)" if error_messages else "")
            )

            return {
                "deleted": deleted_keys,
                "errors": error_messages,
            }

        except Exception as e:
            error_msg = str(e).lower()

            # Handle specific error cases
            if "403" in error_msg or "access denied" in error_msg:
                raise S3AccessDeniedError(
                    f"Access denied when batch deleting from bucket '{target_bucket}'. "
                    f"Check permissions."
                ) from e
            elif "nosuchbucket" in error_msg or "404" in error_msg:
                raise S3BucketNotFoundError(
                    f"Bucket '{target_bucket}' does not exist"
                ) from e
            else:
                raise S3Error(
                    f"Failed to batch delete objects from bucket '{target_bucket}': {e}"
                ) from e

    # ═══════════════════════════════════════════════════════════════════════════
    #                         LISTING AND METADATA OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════

    async def list_objects(
        self,
        prefix: str = "",
        bucket: str | None = None,
        max_keys: int = 1000,
        delimiter: str = "",
    ) -> list[dict[str, Any]]:
        """
        List objects in bucket with optional prefix filter.

        Uses the S3 list_objects_v2 API with automatic pagination to retrieve
        all objects matching the given prefix. Returns a list of object metadata
        dictionaries with key information about each object.

        Args:
            prefix (str): Filter objects by key prefix. Default: "" (all objects).
                Example: "uploads/" lists only objects in the uploads folder.
            bucket (str | None): Bucket name to list from. Default: None (uses
                configured bucket).
            max_keys (int): Maximum number of keys to return per API call.
                Default: 1000 (S3 maximum). Total results may exceed this if
                pagination is needed. Range: 1-1000.
            delimiter (str): Delimiter for grouping keys. Default: "" (no grouping).
                Use "/" to group by folders. Example: "/" shows top-level folders.

        Returns:
            list[dict[str, Any]]: List of object metadata dictionaries. Each dict
                contains:
                - Key (str): Object key/path
                - Size (int): Size in bytes
                - LastModified (datetime): Last modification timestamp
                - ETag (str): Entity tag (MD5 hash in quotes)
                - StorageClass (str): Storage class (STANDARD, GLACIER, etc.)

        Raises:
            RuntimeError: If not connected to S3.
            S3BucketNotFoundError: If specified bucket does not exist.
            S3AccessDeniedError: If insufficient permissions to list objects.
            S3Error: For other S3 API errors.

        Example:
            >>> # List all objects
            >>> objects = await s3.list_objects()
            >>> for obj in objects:
            ...     print(f"{obj['Key']}: {obj['Size']} bytes")
            >>>
            >>> # List objects with prefix
            >>> uploads = await s3.list_objects(prefix="uploads/")
            >>> print(f"Found {len(uploads)} files in uploads/")
            >>>
            >>> # List from different bucket
            >>> objects = await s3.list_objects(
            ...     prefix="data/",
            ...     bucket="other-bucket",
            ...     max_keys=100
            ... )
            >>>
            >>> # List with folder grouping (using delimiter)
            >>> folders = await s3.list_objects(prefix="data/", delimiter="/")

        Notes:
            - Automatically handles pagination for large result sets
            - Empty prefix returns all objects in the bucket
            - Keys are returned in UTF-8 binary order
            - LastModified timestamps are in UTC
            - ETag format varies by object creation method (simple upload vs multipart)
            - Delimiter grouping shows CommonPrefixes in results

        See Also:
            get_object_metadata(): Get metadata for a specific object.
            object_exists(): Check if an object exists.
        """
        bucket_name = bucket or self.config.bucket_name

        try:
            objects = []
            continuation_token = None

            # Paginate through all results
            while True:
                # Build request parameters
                params: dict[str, Any] = {
                    "Bucket": bucket_name,
                    "Prefix": prefix,
                    "MaxKeys": max_keys,
                }

                if delimiter:
                    params["Delimiter"] = delimiter

                if continuation_token:
                    params["ContinuationToken"] = continuation_token

                # Make API call
                response = await self.client.list_objects_v2(**params)

                # Extract object metadata
                if "Contents" in response:
                    for obj in response["Contents"]:
                        objects.append({
                            "Key": obj["Key"],
                            "Size": obj["Size"],
                            "LastModified": obj["LastModified"],
                            "ETag": obj["ETag"],
                            "StorageClass": obj.get("StorageClass", "STANDARD"),
                        })

                # Check for more results
                if response.get("IsTruncated", False):
                    continuation_token = response.get("NextContinuationToken")
                else:
                    break

            logger.debug(
                f"Listed {len(objects)} objects from bucket '{bucket_name}' "
                f"with prefix '{prefix}'"
            )
            return objects

        except Exception as e:
            error_msg = str(e).lower()
            if "404" in error_msg or "nosuchbucket" in error_msg:
                raise S3BucketNotFoundError(
                    f"Bucket '{bucket_name}' does not exist"
                ) from e
            elif "403" in error_msg or "access denied" in error_msg:
                raise S3AccessDeniedError(
                    f"Access denied when listing objects in bucket '{bucket_name}'"
                ) from e
            else:
                raise S3Error(
                    f"Failed to list objects in bucket '{bucket_name}': {e}"
                ) from e

    async def get_object_metadata(
        self,
        object_key: str,
        bucket: str | None = None,
    ) -> dict[str, Any]:
        """
        Get object metadata without downloading the object.

        Uses the S3 head_object API to retrieve metadata about an object without
        transferring the object data itself. This is much faster and more efficient
        than downloading when you only need metadata.

        Args:
            object_key (str): S3 object key/path. Required.
                Example: "uploads/data.json"
            bucket (str | None): Bucket name. Default: None (uses configured bucket).

        Returns:
            dict[str, Any]: Object metadata dictionary containing:
                - ContentType (str): MIME type (e.g., "application/json")
                - ContentLength (int): Size in bytes
                - LastModified (datetime): Last modification timestamp (UTC)
                - ETag (str): Entity tag (MD5 hash in quotes)
                - Metadata (dict): User-defined metadata key-value pairs
                - StorageClass (str): Storage class (STANDARD, GLACIER, etc.)
                - VersionId (str | None): Version ID if versioning enabled
                - ServerSideEncryption (str | None): Encryption type if used
                - CacheControl (str | None): Cache-Control header if set
                - ContentEncoding (str | None): Content-Encoding header if set
                - ContentDisposition (str | None): Content-Disposition header if set

        Raises:
            RuntimeError: If not connected to S3.
            S3ObjectNotFoundError: If object does not exist.
            S3AccessDeniedError: If insufficient permissions to access object.
            S3Error: For other S3 API errors.

        Example:
            >>> # Get metadata for an object
            >>> metadata = await s3.get_object_metadata("uploads/data.json")
            >>> print(f"Content-Type: {metadata['ContentType']}")
            >>> print(f"Size: {metadata['ContentLength']} bytes")
            >>> print(f"Last Modified: {metadata['LastModified']}")
            >>>
            >>> # Check custom metadata
            >>> if "Metadata" in metadata:
            ...     for key, value in metadata["Metadata"].items():
            ...         print(f"{key}: {value}")
            >>>
            >>> # Get metadata from different bucket
            >>> metadata = await s3.get_object_metadata(
            ...     "config.yaml",
            ...     bucket="config-bucket"
            ... )
            >>>
            >>> # Use metadata to decide whether to download
            >>> metadata = await s3.get_object_metadata("large-file.bin")
            >>> if metadata["ContentLength"] < 10_000_000:  # < 10MB
            ...     content = await s3.download_file("large-file.bin")

        Notes:
            - This operation does not transfer object data (faster and cheaper)
            - User metadata keys are prefixed with "x-amz-meta-" in S3 but
              returned without the prefix in the Metadata dict
            - LastModified is a datetime object in UTC timezone
            - ETag format varies by upload method (simple vs multipart)
            - Returns None for optional fields that are not set

        See Also:
            object_exists(): Check if object exists (returns bool).
            list_objects(): List multiple objects with basic metadata.
        """
        bucket_name = bucket or self.config.bucket_name

        try:
            # Call head_object to get metadata
            response = await self.client.head_object(
                Bucket=bucket_name,
                Key=object_key
            )

            # Extract and return metadata
            metadata = {
                "ContentType": response.get("ContentType"),
                "ContentLength": response.get("ContentLength"),
                "LastModified": response.get("LastModified"),
                "ETag": response.get("ETag"),
                "Metadata": response.get("Metadata", {}),
                "StorageClass": response.get("StorageClass", "STANDARD"),
                "VersionId": response.get("VersionId"),
                "ServerSideEncryption": response.get("ServerSideEncryption"),
                "CacheControl": response.get("CacheControl"),
                "ContentEncoding": response.get("ContentEncoding"),
                "ContentDisposition": response.get("ContentDisposition"),
            }

            logger.debug(
                f"Retrieved metadata for object '{object_key}' in bucket '{bucket_name}'"
            )
            return metadata

        except Exception as e:
            error_msg = str(e).lower()
            if "404" in error_msg or "nosuchkey" in error_msg or "not found" in error_msg:
                raise S3ObjectNotFoundError(
                    f"Object '{object_key}' not found in bucket '{bucket_name}'",
                    bucket=bucket_name,
                    key=object_key
                ) from e
            elif "403" in error_msg or "access denied" in error_msg:
                raise S3AccessDeniedError(
                    f"Access denied to object '{object_key}' in bucket '{bucket_name}'"
                ) from e
            else:
                raise S3Error(
                    f"Failed to get metadata for object '{object_key}' "
                    f"in bucket '{bucket_name}': {e}"
                ) from e

    async def object_exists(
        self,
        object_key: str,
        bucket: str | None = None,
    ) -> bool:
        """
        Check if an object exists in S3.

        Uses the S3 head_object API to efficiently check for object existence
        without downloading the object. Returns a simple boolean result.

        Args:
            object_key (str): S3 object key/path to check. Required.
                Example: "uploads/data.json"
            bucket (str | None): Bucket name. Default: None (uses configured bucket).

        Returns:
            bool: True if object exists and is accessible, False if object does
                not exist (404/NoSuchKey error). Other errors (access denied,
                connection issues) are raised as exceptions.

        Raises:
            RuntimeError: If not connected to S3.
            S3AccessDeniedError: If insufficient permissions to check object.
            S3BucketNotFoundError: If bucket does not exist.
            S3Error: For other S3 API errors.

        Example:
            >>> # Check if object exists
            >>> exists = await s3.object_exists("uploads/data.json")
            >>> if exists:
            ...     print("File exists")
            ... else:
            ...     print("File not found")
            >>>
            >>> # Conditional download
            >>> if await s3.object_exists("config.yaml"):
            ...     config = await s3.download_file("config.yaml")
            ... else:
            ...     config = get_default_config()
            >>>
            >>> # Check in different bucket
            >>> exists = await s3.object_exists(
            ...     "backup/data.json",
            ...     bucket="backup-bucket"
            ... )
            >>>
            >>> # Validate before upload
            >>> if not await s3.object_exists("data.json"):
            ...     await s3.upload_file("local.json", "data.json")
            ... else:
            ...     print("File already exists, skipping upload")

        Notes:
            - This operation does not transfer object data (fast and efficient)
            - Returns False only for 404/NoSuchKey errors
            - Access denied errors are raised, not returned as False
            - Consider using get_object_metadata() if you need metadata anyway
            - Useful for conditional logic before upload/download operations

        See Also:
            get_object_metadata(): Get full metadata if object exists.
            list_objects(): Check for multiple objects at once.
        """
        bucket_name = bucket or self.config.bucket_name

        try:
            # Try to get object metadata
            await self.client.head_object(
                Bucket=bucket_name,
                Key=object_key
            )
            # If no exception, object exists
            return True

        except Exception as e:
            error_msg = str(e).lower()
            # Return False only for "not found" errors
            if "404" in error_msg or "nosuchkey" in error_msg or "not found" in error_msg:
                return False
            # Raise exceptions for other errors
            elif "nosuchbucket" in error_msg:
                raise S3BucketNotFoundError(
                    f"Bucket '{bucket_name}' does not exist"
                ) from e
            elif "403" in error_msg or "access denied" in error_msg:
                raise S3AccessDeniedError(
                    f"Access denied when checking object '{object_key}' "
                    f"in bucket '{bucket_name}'"
                ) from e
            else:
                raise S3Error(
                    f"Failed to check existence of object '{object_key}' "
                    f"in bucket '{bucket_name}': {e}"
                ) from e

    # ═══════════════════════════════════════════════════════════════════════════
    #                         PRESIGNED URL GENERATION
    # ═══════════════════════════════════════════════════════════════════════════

    def generate_presigned_url(
        self,
        object_key: str,
        bucket: str | None = None,
        expires_in: int = 3600,
        http_method: str = "GET",
    ) -> str:
        """
        Generate presigned URL for temporary object access.

        Creates a presigned URL that allows temporary access to an S3 object
        without requiring AWS credentials. The URL includes authentication
        information in the query string and is valid for a limited time.

        This is a SYNC method (not async) because boto3's presigned URL
        generation is synchronous and does not involve I/O operations.

        Args:
            object_key (str): S3 object key (path within bucket).
                Example: "uploads/document.pdf"
            bucket (str | None): Bucket name. Default: None (uses config bucket).
            expires_in (int): URL expiration time in seconds. Default: 3600 (1 hour).
                Maximum: 604800 (7 days) for AWS IAM credentials.
            http_method (str): HTTP method the URL will be used for.
                Default: "GET" (download). Also supports "PUT" (upload), "DELETE", etc.

        Returns:
            str: Presigned URL that can be used to access the object.

        Raises:
            RuntimeError: If sync client is not connected. Call connect_sync() first.
            S3Error: If URL generation fails.

        Example:
            >>> # Generate download URL (GET)
            >>> s3 = S3Service(bucket_name="my-bucket")
            >>> s3.connect_sync()
            >>>
            >>> # URL expires in 1 hour (default)
            >>> download_url = s3.generate_presigned_url("reports/data.csv")
            >>> print(f"Download: {download_url}")
            >>> # Users can download via: curl -O "{download_url}"
            >>>
            >>> # Generate upload URL (PUT) with custom expiration
            >>> upload_url = s3.generate_presigned_url(
            ...     object_key="uploads/new_file.txt",
            ...     expires_in=1800,  # 30 minutes
            ...     http_method="PUT"
            ... )
            >>> print(f"Upload: {upload_url}")
            >>> # Users can upload via: curl -X PUT --upload-file file.txt "{upload_url}"
            >>>
            >>> # Generate URL for different bucket
            >>> url = s3.generate_presigned_url(
            ...     object_key="shared/document.pdf",
            ...     bucket="shared-bucket"
            ... )

        Security Notes:
            - URLs contain authentication information in query parameters
            - URLs are valid until expiration time
            - Anyone with the URL can access the object during validity period
            - Consider shorter expiration times for sensitive data
            - URLs cannot be revoked before expiration

        See Also:
            generate_presigned_post(): For browser-based uploads with forms.
        """
        if not self._sync_client:
            raise RuntimeError(
                "S3 sync client not connected. Call connect_sync() first."
            )

        try:
            bucket_name = bucket or self.config.bucket_name

            # Map HTTP method to boto3 client method
            # GET -> get_object, PUT -> put_object, etc.
            client_method_map = {
                "GET": "get_object",
                "PUT": "put_object",
                "DELETE": "delete_object",
                "HEAD": "head_object",
            }

            client_method = client_method_map.get(http_method.upper())
            if not client_method:
                raise S3Error(
                    f"Unsupported HTTP method: {http_method}. "
                    f"Supported: {', '.join(client_method_map.keys())}"
                )

            # Generate presigned URL
            url = self._sync_client.generate_presigned_url(
                ClientMethod=client_method,
                Params={
                    "Bucket": bucket_name,
                    "Key": object_key,
                },
                ExpiresIn=expires_in,
                HttpMethod=http_method.upper(),
            )

            logger.debug(
                f"Generated presigned URL for {http_method} {bucket_name}/{object_key} "
                f"(expires in {expires_in}s)"
            )

            return url

        except Exception as e:
            raise S3Error(
                f"Failed to generate presigned URL for '{object_key}': {e}"
            ) from e

    def generate_presigned_post(
        self,
        object_key: str,
        bucket: str | None = None,
        expires_in: int = 3600,
        fields: dict[str, str] | None = None,
        conditions: list | None = None,
    ) -> dict[str, Any]:
        """
        Generate presigned POST data for browser uploads.

        Creates a presigned POST policy that allows direct browser-to-S3 uploads
        via an HTML form. This is more secure and flexible than presigned PUT URLs
        for browser uploads, as it allows setting conditions on the upload.

        This is a SYNC method (not async) because boto3's presigned POST
        generation is synchronous and does not involve I/O operations.

        Args:
            object_key (str): S3 object key where file will be uploaded.
                Example: "uploads/${filename}" (can use placeholders)
            bucket (str | None): Bucket name. Default: None (uses config bucket).
            expires_in (int): Policy expiration time in seconds. Default: 3600 (1 hour).
            fields (dict[str, str] | None): Additional form fields. Default: None.
                Example: {"Content-Type": "image/jpeg", "acl": "public-read"}
            conditions (list | None): Upload conditions/restrictions. Default: None.
                Example: [["content-length-range", 0, 10485760]]  # Max 10MB

        Returns:
            dict[str, Any]: Dictionary with 'url' and 'fields' for form submission.
                - url (str): POST endpoint URL (bucket URL)
                - fields (dict): Form fields to include in POST request

        Raises:
            RuntimeError: If sync client is not connected. Call connect_sync() first.
            S3Error: If POST policy generation fails.

        Example:
            >>> # Generate POST data for browser upload
            >>> s3 = S3Service(bucket_name="my-bucket")
            >>> s3.connect_sync()
            >>>
            >>> # Basic usage
            >>> post_data = s3.generate_presigned_post("uploads/user_photo.jpg")
            >>> print(f"POST URL: {post_data['url']}")
            >>> print(f"Form fields: {post_data['fields']}")
            >>>
            >>> # With file size limit (max 5MB) and content type
            >>> post_data = s3.generate_presigned_post(
            ...     object_key="uploads/document.pdf",
            ...     expires_in=1800,  # 30 minutes
            ...     fields={"Content-Type": "application/pdf"},
            ...     conditions=[
            ...         ["content-length-range", 0, 5242880],  # 0-5MB
            ...         ["eq", "$Content-Type", "application/pdf"]  # Must be PDF
            ...     ]
            ... )
            >>>
            >>> # HTML form example
            >>> # <form action="{post_data['url']}" method="post" enctype="multipart/form-data">
            >>> #   {% for key, value in post_data['fields'].items() %}
            >>> #     <input type="hidden" name="{{key}}" value="{{value}}" />
            >>> #   {% endfor %}
            >>> #   <input type="file" name="file" />
            >>> #   <input type="submit" value="Upload" />
            >>> # </form>
            >>>
            >>> # JavaScript fetch example
            >>> # const formData = new FormData();
            >>> # Object.entries(post_data.fields).forEach(([key, value]) => {
            >>> #   formData.append(key, value);
            >>> # });
            >>> # formData.append('file', fileInput.files[0]);
            >>> # await fetch(post_data.url, { method: 'POST', body: formData });

        Common Conditions:
            - ["content-length-range", min, max]: File size range in bytes
            - ["eq", "$Content-Type", "image/jpeg"]: Exact content type match
            - ["starts-with", "$key", "uploads/"]: Key must start with prefix
            - ["starts-with", "$Content-Type", "image/"]: Any image type

        Security Notes:
            - POST policies are more secure than presigned PUT URLs for browsers
            - Conditions are enforced server-side by S3
            - Policy cannot be modified after generation
            - Users cannot upload to different keys or with different metadata
            - Use content-length-range to prevent abuse with large files

        See Also:
            generate_presigned_url(): For simple GET/PUT presigned URLs.
        """
        if not self._sync_client:
            raise RuntimeError(
                "S3 sync client not connected. Call connect_sync() first."
            )

        try:
            bucket_name = bucket or self.config.bucket_name

            # Build POST policy parameters
            post_params = {
                "Bucket": bucket_name,
                "Key": object_key,
            }

            # Add optional fields
            if fields:
                post_params["Fields"] = fields

            # Add optional conditions
            if conditions:
                post_params["Conditions"] = conditions

            # Set expiration
            post_params["ExpiresIn"] = expires_in

            # Generate presigned POST
            response = self._sync_client.generate_presigned_post(**post_params)

            logger.debug(
                f"Generated presigned POST for {bucket_name}/{object_key} "
                f"(expires in {expires_in}s)"
            )

            return response

        except Exception as e:
            raise S3Error(
                f"Failed to generate presigned POST for '{object_key}': {e}"
            ) from e


# ═══════════════════════════════════════════════════════════════════════════════
#                         MODULE-LEVEL SINGLETON
# ═══════════════════════════════════════════════════════════════════════════════

_default_s3: S3Service | None = None


def get_s3_client() -> S3Service:
    """
    Get the default S3 service instance.

    Returns the globally configured S3 service. If not initialized,
    creates one from environment variables.

    Returns:
        S3Service: The default S3 service instance.

    Example:
        >>> s3 = get_s3_client()
        >>> await s3.connect()
        >>> await s3.upload_file("data.json", "uploads/data.json")
    """
    global _default_s3
    if _default_s3 is None:
        _default_s3 = S3Service.from_env()
    return _default_s3


def init_s3_client(
    endpoint_url: str | None = None,
    bucket_name: str | None = None,
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
    region: str = "us-east-1",
    config: S3Config | None = None,
    **kwargs: Any,
) -> S3Service:
    """
    Initialize the default S3 service instance.

    Creates and sets the global default S3 service. Use this at
    application startup to configure S3.

    Args:
        endpoint_url (str | None): S3 endpoint URL.
        bucket_name (str | None): Bucket name.
        access_key_id (str | None): AWS access key ID.
        secret_access_key (str | None): AWS secret access key.
        region (str): AWS region. Default: "us-east-1".
        config (S3Config | None): Config instance (overrides other params).
        **kwargs: Additional S3Service arguments.

    Returns:
        S3Service: The initialized default service.

    Example:
        >>> # At application startup
        >>> s3 = init_s3_client(
        ...     endpoint_url="https://s3.company.com:9000",
        ...     bucket_name="my-bucket",
        ...     access_key_id="AKIAIOSFODNN7EXAMPLE",
        ...     secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        ...     region="us-west-2",
        ... )
        >>>
        >>> # Later in the application
        >>> s3 = get_s3_client()
    """
    global _default_s3

    if config:
        _default_s3 = S3Service(config=config)
    else:
        _default_s3 = S3Service(
            endpoint_url=endpoint_url or os.getenv("S3_ENDPOINT_URL"),
            bucket_name=bucket_name or os.getenv("S3_BUCKET_NAME"),
            access_key_id=access_key_id or os.getenv("S3_ACCESS_KEY_ID"),
            secret_access_key=secret_access_key or os.getenv("S3_SECRET_ACCESS_KEY"),
            region=region,
            **kwargs,
        )

    return _default_s3


def set_s3_client(client: S3Service) -> None:
    """
    Set a custom S3 service instance as the default.

    Use this to inject a pre-configured or mock S3 service.

    Args:
        client (S3Service): S3 service instance to set as default.

    Example:
        >>> custom_s3 = S3Service(bucket_name="custom-bucket")
        >>> set_s3_client(custom_s3)
    """
    global _default_s3
    _default_s3 = client


__all__ = [
    "S3Config",
    "S3HealthStatus",
    "S3Service",
    "S3Error",
    "S3ConnectionError",
    "S3ConfigurationError",
    "S3ObjectNotFoundError",
    "S3UploadError",
    "S3DownloadError",
    "S3AccessDeniedError",
    "S3BucketNotFoundError",
    "S3_AVAILABLE",
    "get_s3_client",
    "init_s3_client",
    "set_s3_client",
]