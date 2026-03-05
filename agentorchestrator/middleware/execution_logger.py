"""
Execution Logger Middleware for AgentOrchestrator
================================================

Middleware for per-execution logging to separate log files.

This middleware creates a separate log file for each chain execution,
making it easy to debug specific runs without searching through application-wide logs.

Classes:
    ExecutionLoggerMiddleware: Per-execution logging middleware.

Usage:
    from agentorchestrator.middleware import ExecutionLoggerMiddleware

    # Basic usage
    middleware = ExecutionLoggerMiddleware(
        log_dir="output/logs",
        filename_pattern="execution_{execution_id}.log",
    )

    ao.use(middleware)

Example:
    >>> from agentorchestrator.middleware import ExecutionLoggerMiddleware
    >>>
    >>> # With context snapshots
    >>> middleware = ExecutionLoggerMiddleware(
    ...     log_dir="logs/executions",
    ...     filename_pattern="{chain_name}_{execution_id}_{timestamp}.log",
    ...     include_context_snapshots=True,
    ...     log_level="DEBUG",
    ... )
    >>>
    >>> ao.use(middleware)
    >>>
    >>> # Logs written to: logs/executions/my_chain_abc123_20240115_143022.log

See Also:
    - agentorchestrator.middleware.Middleware: Base middleware class.
    - agentorchestrator.middleware.LoggerMiddleware: Application-wide logging.
"""

import logging
import os
import sys
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Any

from agentorchestrator.core.context import ChainContext, StepResult
from agentorchestrator.middleware.base import Middleware

__all__ = ["ExecutionLoggerMiddleware"]

# Context variable to track current execution's request_id
_current_request_id: ContextVar[str | None] = ContextVar('current_request_id', default=None)


class ExecutionLoggerMiddleware(Middleware):
    """
    Middleware for per-execution logging to separate log files.

    Creates a separate log file for each chain execution with configurable
    filename patterns. Useful for debugging specific runs and maintaining
    execution history.

    The middleware:
    - Creates log directory automatically on first use (lazy creation)
    - Sets up file handler for this execution
    - Logs step start/completion/errors
    - Optionally includes context snapshots
    - Cleans up handler after execution

    Note:
        The log directory is created lazily on first use, not at initialization.
        This means the directory won't exist until the first chain execution.
        If you need to verify the directory before execution, create it manually:

        ```python
        from pathlib import Path
        Path("output/logs").mkdir(parents=True, exist_ok=True)
        ```

    Attributes:
        log_dir (str): Directory for log files.
        filename_pattern (str): Pattern for log filenames (supports {execution_id}, {chain_name}, {timestamp}).
        include_context_snapshots (bool): Whether to log context data.
        log_level (str): Log level (DEBUG, INFO, WARNING, ERROR).
        max_context_size (int): Max size of context snapshot in chars.

    Example:
        >>> middleware = ExecutionLoggerMiddleware(
        ...     log_dir="output/logs",
        ...     filename_pattern="execution_{execution_id}.log",
        ...     include_context_snapshots=True,
        ... )
        >>>
        >>> ao.use(middleware)
        >>>
        >>> # Execute chain - logs written to output/logs/execution_req_abc123.log
        >>> result = await ao.launch("my_chain", {"query": "test"})

    Filename Patterns:
        >>> # Available placeholders:
        >>> # {execution_id} - Request ID
        >>> # {chain_name} - Chain name
        >>> # {timestamp} - Current timestamp (YYYYMMDD_HHMMSS)
        >>> # {date} - Current date (YYYYMMDD)
        >>>
        >>> # Examples:
        >>> filename_pattern = "execution_{execution_id}.log"
        >>> filename_pattern = "{chain_name}_{execution_id}_{timestamp}.log"
        >>> filename_pattern = "{date}/{chain_name}_{execution_id}.log"

    Context Snapshots:
        >>> # Enable context snapshots to see data flow
        >>> middleware = ExecutionLoggerMiddleware(
        ...     log_dir="logs",
        ...     filename_pattern="exec_{execution_id}.log",
        ...     include_context_snapshots=True,
        ...     max_context_size=1000,  # Limit size
        ... )

    See Also:
        Middleware: Base middleware class.
        LoggerMiddleware: Application-wide structured logging.
    """

    def __init__(
        self,
        log_dir: str = "output/logs",
        filename_pattern: str = "execution_{execution_id}.log",
        include_context_snapshots: bool = False,
        log_level: str = "INFO",
        max_context_size: int = 5000,
        priority: int = 100,
    ):
        """
        Initialize the execution logger middleware.

        Args:
            log_dir (str): Directory for log files. The directory and any parent
                directories are created automatically on first use (lazy creation).
                If you need to verify the directory exists before execution, create
                it manually: `Path("output/logs").mkdir(parents=True, exist_ok=True)`.
                Default: "output/logs".
            filename_pattern (str): Pattern for log filenames. Supports placeholders:
                {execution_id}, {chain_name}, {timestamp}, {date}.
                Default: "execution_{execution_id}.log".
            include_context_snapshots (bool): Whether to log context data at each step.
                Default: False (only logs step names and results).
            log_level (str): Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
                Default: "INFO".
            max_context_size (int): Maximum size of context snapshot in characters.
                Context larger than this is truncated. Default: 5000.
            priority (int): Middleware priority. Default: 100 (low - runs last).

        Example:
            >>> middleware = ExecutionLoggerMiddleware(
            ...     log_dir="logs/production",
            ...     filename_pattern="{date}/{chain_name}_{execution_id}.log",
            ...     include_context_snapshots=True,
            ...     log_level="DEBUG",
            ... )
        """
        super().__init__(priority=priority)
        self.log_dir = log_dir
        self.filename_pattern = filename_pattern
        self.include_context_snapshots = include_context_snapshots
        self.log_level = getattr(logging, log_level.upper(), logging.INFO)
        self.max_context_size = max_context_size

        # Ensure log directory exists
        Path(log_dir).mkdir(parents=True, exist_ok=True)

        # Store file handlers per execution
        self._handlers: dict[str, logging.FileHandler] = {}
        self._loggers: dict[str, logging.Logger] = {}
        # Store root logger handlers for cleanup
        self._root_handlers: dict[str, logging.FileHandler] = {}
        # Track if we've installed the global filter on root logger
        self._global_filter_installed = False

    def _get_log_filename(self, ctx: ChainContext, chain_name: str = "") -> str:
        """
        Generate log filename from pattern.

        Args:
            ctx (ChainContext): The chain context.
            chain_name (str): Name of the chain.

        Returns:
            str: Full path to log file.
        """
        now = datetime.now()
        filename = self.filename_pattern.format(
            execution_id=ctx.request_id,
            chain_name=chain_name,
            timestamp=now.strftime("%Y%m%d_%H%M%S"),
            date=now.strftime("%Y%m%d"),
        )

        # Handle subdirectories in pattern
        full_path = os.path.join(self.log_dir, filename)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        return full_path

    def _setup_logger(self, ctx: ChainContext, chain_name: str = "") -> logging.Logger:
        """
        Set up logger for this execution with proper isolation for concurrent jobs.

        Args:
            ctx (ChainContext): The chain context.
            chain_name (str): Name of the chain.

        Returns:
            logging.Logger: Logger instance for this execution.
        """
        if ctx.request_id in self._loggers:
            return self._loggers[ctx.request_id]

        # Create logger for this execution
        logger_name = f"agentorchestrator.execution.{ctx.request_id}"
        logger = logging.getLogger(logger_name)
        logger.setLevel(self.log_level)
        logger.propagate = False  # Don't propagate to root logger

        # Create formatter (shared by both handlers)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Create file handler
        log_file = self._get_log_filename(ctx, chain_name)
        file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
        file_handler.setLevel(self.log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Create console handler (so logs appear in console too)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(self.log_level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # Store for cleanup (store both handlers)
        self._handlers[ctx.request_id] = (file_handler, console_handler)
        self._loggers[ctx.request_id] = logger

        # ALSO attach file handler to root logger to capture ALL application logs
        # BUT with a filter that only allows logs from THIS execution
        root_logger = logging.getLogger()
        root_file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
        root_file_handler.setLevel(self.log_level)
        root_file_handler.setFormatter(formatter)
        
        # Create a filter that only allows logs for this request_id
        class RequestIdFilter(logging.Filter):
            """Filter that only allows logs for a specific request_id."""
            def __init__(self, target_request_id: str):
                super().__init__()
                self.target_request_id = target_request_id
            
            def filter(self, record):
                # Check if the current context matches this request_id
                current_id = _current_request_id.get()
                return current_id == self.target_request_id
        
        root_file_handler.addFilter(RequestIdFilter(ctx.request_id))
        root_logger.addHandler(root_file_handler)
        self._root_handlers[ctx.request_id] = root_file_handler

        logger.info(f"=== Execution Started: {ctx.request_id} ===")
        if chain_name:
            logger.info(f"Chain: {chain_name}")

        return logger

    def _cleanup_logger(self, ctx: ChainContext) -> None:
        """
        Clean up logger and handler for this execution.

        Args:
            ctx (ChainContext): The chain context.
        """
        if ctx.request_id in self._handlers:
            handlers = self._handlers[ctx.request_id]
            logger = self._loggers[ctx.request_id]

            logger.info(f"=== Execution Completed: {ctx.request_id} ===")

            # CRITICAL: Flush all handlers before closing to ensure logs are written
            if isinstance(handlers, tuple):
                # New format: (file_handler, console_handler)
                for handler in handlers:
                    handler.flush()  # Flush before removing
                    logger.removeHandler(handler)
                    handler.close()
            else:
                # Old format: single handler (for backwards compatibility)
                handlers.flush()  # Flush before removing
                logger.removeHandler(handlers)
                handlers.close()

            # Clean up storage
            del self._handlers[ctx.request_id]
            del self._loggers[ctx.request_id]

        # Remove root logger handler and flush it
        if ctx.request_id in self._root_handlers:
            root_logger = logging.getLogger()
            root_handler = self._root_handlers[ctx.request_id]
            root_handler.flush()  # Flush before removing
            root_logger.removeHandler(root_handler)
            root_handler.close()
            del self._root_handlers[ctx.request_id]

    def _truncate_context(self, context_str: str) -> str:
        """
        Truncate context string if too large.

        Args:
            context_str (str): Context string to truncate.

        Returns:
            str: Truncated context string.
        """
        if len(context_str) <= self.max_context_size:
            return context_str

        return context_str[:self.max_context_size] + f"\n... (truncated, {len(context_str) - self.max_context_size} more chars)"

    async def on_chain_start(self, ctx: ChainContext, chain_name: str) -> None:
        """
        Called when chain execution starts - create log file immediately.
        
        This ensures log files are created even if the job fails before any steps execute,
        or if the job is picked up immediately by a worker.
        
        Args:
            ctx (ChainContext): The chain context.
            chain_name (str): Name of the chain being executed.
        """
        # Set the current request_id in context for log filtering
        _current_request_id.set(ctx.request_id)
        
        # Set up logger immediately when chain starts
        logger = self._setup_logger(ctx, chain_name)
        logger.info(f"Chain execution started: {chain_name}")
        logger.info(f"Request ID: {ctx.request_id}")
    
    async def on_chain_end(self, ctx: ChainContext, chain_name: str) -> None:
        """
        Called when chain execution completes successfully.
        
        Args:
            ctx (ChainContext): The chain context.
            chain_name (str): Name of the chain that completed.
        """
        # Set context for final logs
        _current_request_id.set(ctx.request_id)
        
        if ctx.request_id in self._loggers:
            logger = self._loggers[ctx.request_id]
            logger.info(f"Chain execution completed successfully: {chain_name}")
        
        # Cleanup logger
        self._cleanup_logger(ctx)
        
        # Clear context
        _current_request_id.set(None)
    
    async def on_chain_error(self, ctx: ChainContext, chain_name: str, error: Exception) -> None:
        """
        Called when chain execution fails.
        
        Args:
            ctx (ChainContext): The chain context.
            chain_name (str): Name of the chain that failed.
            error (Exception): The error that occurred.
        """
        # Set context for error logs
        _current_request_id.set(ctx.request_id)
        
        # Ensure logger exists (in case error happened before any steps)
        if ctx.request_id not in self._loggers:
            logger = self._setup_logger(ctx, chain_name)
        else:
            logger = self._loggers[ctx.request_id]
        
        logger.error(f"Chain execution failed: {chain_name}")
        logger.error(f"Error: {type(error).__name__}: {error}", exc_info=True)
        
        # Cleanup logger
        self._cleanup_logger(ctx)
        
        # Clear context
        _current_request_id.set(None)

    async def before(self, ctx: ChainContext, step_name: str) -> None:
        """
        Called before step execution - log step start and set context.

        Args:
            ctx (ChainContext): The chain context.
            step_name (str): Name of the step about to execute.
        """
        # Set the current request_id in context for log filtering
        _current_request_id.set(ctx.request_id)
        
        # Get chain name from context if available
        chain_name = ctx.metadata.get("chain_name", "")

        # Set up logger if not already done
        logger = self._setup_logger(ctx, chain_name)

        logger.info(f"Step Started: {step_name}")

        # Log context snapshot if enabled
        if self.include_context_snapshots:
            try:
                context_data = ctx.to_dict()
                context_str = str(context_data)
                truncated = self._truncate_context(context_str)
                logger.debug(f"Context before {step_name}:\n{truncated}")
            except Exception as e:
                logger.warning(f"Failed to log context snapshot: {e}")

    async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        """
        Called after successful step execution - log step completion and clear context.

        Args:
            ctx (ChainContext): The chain context.
            step_name (str): Name of the completed step.
            result (StepResult): The step result.
        """
        # Ensure context is set for this step's completion logs
        _current_request_id.set(ctx.request_id)
        
        if ctx.request_id not in self._loggers:
            return

        logger = self._loggers[ctx.request_id]

        if result.success:
            logger.info(
                f"Step Completed: {step_name} "
                f"(duration: {result.duration_ms:.2f}ms, tokens: {result.token_count})"
            )
            if self.include_context_snapshots and result.output is not None:
                output_str = str(result.output)
                truncated = self._truncate_context(output_str)
                logger.debug(f"Output from {step_name}:\n{truncated}")
        elif result.skipped:
            logger.info(
                f"Step Skipped: {step_name} "
                f"(reason: {result.skipped_reason})"
            )
        
        # Clear the context after step completion
        _current_request_id.set(None)

    async def on_error(self, ctx: ChainContext, step_name: str, error: Exception) -> None:
        """
        Called when a step fails - log error details.
        
        Note: Cleanup is handled by on_chain_error() at the chain level.

        Args:
            ctx (ChainContext): The chain context.
            step_name (str): Name of the failed step.
            error (Exception): The error that occurred.
        """
        # Set context for error logs
        _current_request_id.set(ctx.request_id)
        
        if ctx.request_id not in self._loggers:
            # Set up logger if not already done (in case error happens before any steps)
            logger = self._setup_logger(ctx)
        else:
            logger = self._loggers[ctx.request_id]

        logger.error(
            f"Step Failed: {step_name} - {type(error).__name__}: {error}",
            exc_info=True
        )
        
        # Clear context (cleanup happens at chain level in on_chain_error)
        _current_request_id.set(None)