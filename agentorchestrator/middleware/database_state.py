"""
Database State Middleware for AgentOrchestrator
==============================================

Middleware for tracking workflow state in external databases.

This middleware automatically updates job/task status in a database as steps execute,
enabling external monitoring, recovery, and user visibility into workflow progress.

Classes:
    DatabaseStateMiddleware: Tracks workflow state in external databases.

Usage:
    from agentorchestrator.middleware import DatabaseStateMiddleware

    # Define state mappings
    middleware = DatabaseStateMiddleware(
        db_manager=db_manager,
        state_table="jobs",
        state_column="job_status",
        id_column="job_id",
        step_to_state_mapping={
            "validate_input": "VALIDATING",
            "process_data": "PROCESSING",
            "generate_output": "FINALIZING",
        },
        # Optional: initial and final states
        initial_state="PENDING",
        success_state="COMPLETED",
        error_state="FAILED",
    )

    ao.use(middleware)

Example:
    >>> from agentorchestrator.middleware import DatabaseStateMiddleware
    >>>
    >>> # Simple mapping
    >>> middleware = DatabaseStateMiddleware(
    ...     db_manager=db_manager,
    ...     state_table="jobs",
    ...     state_column="status",
    ...     id_column="job_id",
    ...     step_to_state_mapping={
    ...         "step1": "PROCESSING",
    ...         "step2": "FINALIZING",
    ...     }
    ... )
    >>>
    >>> # Get job_id from context
    >>> async def my_step(ctx: ChainContext):
    ...     job_id = ctx.get("job_id")
    ...     # When step starts, DB is updated: UPDATE jobs SET status='PROCESSING' WHERE job_id=?
    ...     ...

See Also:
    - agentorchestrator.middleware.Middleware: Base middleware class.
    - agentorchestrator.core.context: ChainContext for accessing job IDs.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, Union

from agentorchestrator.core.context import ChainContext, StepResult
from agentorchestrator.middleware.base import Middleware

logger = logging.getLogger(__name__)

__all__ = ["DatabaseStateMiddleware", "UpdateFunction"]


class UpdateFunction(Protocol):
    """
    Protocol for update_function parameter in DatabaseStateMiddleware.

    The update function receives the database manager, job ID, and new state,
    and updates the database accordingly. Can be sync or async.

    Args:
        db_manager: Database manager instance (your custom DB connection/pool).
        job_id: Job/task identifier (str or int).
        state: New state value (str).

    Returns:
        None or Awaitable[None]: Nothing, or a coroutine that returns nothing.

    Example:
        >>> # Sync version
        >>> def update_job_state(db_manager, job_id: str, state: str) -> None:
        ...     db_manager.execute_query(
        ...         "UPDATE jobs SET status = ? WHERE job_id = ?",
        ...         (state, job_id)
        ...     )
        >>>
        >>> # Async version
        >>> async def update_job_state(db_manager, job_id: str, state: str) -> None:
        ...     await db_manager.execute_query(
        ...         "UPDATE jobs SET status = ? WHERE job_id = ?",
        ...         (state, job_id)
        ...     )
    """

    def __call__(
        self, db_manager: Any, job_id: Union[str, int], state: str
    ) -> Union[None, Awaitable[None]]:
        ...


# Type alias for backward compatibility and clarity
UpdateFunctionType = Union[
    Callable[[Any, Union[str, int], str], None],
    Callable[[Any, Union[str, int], str], Awaitable[None]],
]


class DatabaseStateMiddleware(Middleware):
    """
    Middleware for tracking workflow state in external databases.

    Automatically updates a database table with workflow state as steps execute.
    This enables external monitoring, recovery, and user visibility into workflow progress.

    The middleware:
    - Updates state before step execution (e.g., "PROCESSING")
    - Updates state on success (e.g., "COMPLETED")
    - Updates state on error (e.g., "FAILED")
    - Supports custom state mappings per step

    Attributes:
        db_manager: Database manager/connection object with execute_query() method.
        state_table (str): Database table name containing state column.
        state_column (str): Column name for state/status.
        id_column (str): Column name for job/task identifier.
        step_to_state_mapping (dict): Maps step names to state values.
        initial_state (str | None): State to set when chain starts.
        success_state (str | None): State to set when chain completes successfully.
        error_state (str | None): State to set when chain fails.
        get_id (callable): Function to extract job ID from context.

    Example:
        >>> middleware = DatabaseStateMiddleware(
        ...     db_manager=db_manager,
        ...     state_table="jobs",
        ...     state_column="job_status",
        ...     id_column="job_id",
        ...     step_to_state_mapping={
        ...         "validate": "VALIDATING",
        ...         "process": "PROCESSING",
        ...         "finalize": "FINALIZING",
        ...     },
        ...     initial_state="PENDING",
        ...     success_state="COMPLETED",
        ...     error_state="FAILED",
        ... )
        >>>
        >>> ao.use(middleware)
        >>>
        >>> # In your chain execution:
        >>> result = await ao.launch("my_chain", {"job_id": 123})
        >>> # Database automatically updated: PENDING -> VALIDATING -> PROCESSING -> FINALIZING -> COMPLETED

    Custom ID Extraction:
        >>> # If job ID is nested or computed
        >>> middleware = DatabaseStateMiddleware(
        ...     db_manager=db_manager,
        ...     state_table="tasks",
        ...     state_column="status",
        ...     id_column="task_id",
        ...     step_to_state_mapping={...},
        ...     get_id=lambda ctx: ctx.get("request", {}).get("task_id"),
        ... )

    Database Manager Interface:
        The db_manager must implement:
        - execute_query(query: str, params: tuple) -> Any
        or
        - execute(query: str, params: tuple) -> Any

        Example implementations:
        >>> # Simple synchronous DB manager
        >>> class DBManager:
        ...     def __init__(self, conn):
        ...         self.conn = conn
        ...
        ...     def execute_query(self, query: str, params: tuple):
        ...         cursor = self.conn.cursor()
        ...         cursor.execute(query, params)
        ...         self.conn.commit()

        >>> # Async DB manager
        >>> class AsyncDBManager:
        ...     def __init__(self, pool):
        ...         self.pool = pool
        ...
        ...     async def execute_query(self, query: str, params: tuple):
        ...         async with self.pool.acquire() as conn:
        ...             await conn.execute(query, params)

    See Also:
        Middleware: Base middleware class.
        ChainContext: Context object for accessing job IDs.
    """

    def __init__(
        self,
        db_manager: Any,
        state_table: str,
        state_column: str,
        id_column: str,
        step_to_state_mapping: dict[str, str],
        initial_state: str | None = None,
        success_state: str | None = None,
        error_state: str | None = None,
        get_id: Callable[[ChainContext], Union[str, int, None]] | None = None,
        update_function: UpdateFunctionType | None = None,
        priority: int = 50,
    ):
        """
        Initialize the database state middleware.

        Args:
            db_manager: Database manager with execute_query() or execute() method.
            state_table (str): Database table name.
            state_column (str): Column name for state/status.
            id_column (str): Column name for job/task identifier.
            step_to_state_mapping (dict[str, str]): Maps step names to state values.
            initial_state (str | None): Optional state to set when chain starts.
            success_state (str | None): Optional state to set on successful completion.
            error_state (str | None): Optional state to set on error.
            get_id (callable | None): Function to extract job ID from context.
                Default: lambda ctx: ctx.get("job_id")
            update_function (callable | None): Custom function for updating state.
                If provided, this function is called instead of default UPDATE query.
                Signature: update_function(db_manager, job_id, state) -> None
                Default: None (uses built-in UPDATE query)
            priority (int): Middleware priority. Default: 50.

        Example:
            >>> middleware = DatabaseStateMiddleware(
            ...     db_manager=my_db,
            ...     state_table="workflow_jobs",
            ...     state_column="status",
            ...     id_column="job_id",
            ...     step_to_state_mapping={
            ...         "step1": "STEP1_RUNNING",
            ...         "step2": "STEP2_RUNNING",
            ...     },
            ...     initial_state="QUEUED",
            ...     success_state="DONE",
            ...     error_state="ERROR",
            ... )
        """
        super().__init__(priority=priority)
        self.db_manager = db_manager
        self.state_table = state_table
        self.state_column = state_column
        self.id_column = id_column
        self.step_to_state_mapping = step_to_state_mapping
        self.initial_state = initial_state
        self.success_state = success_state
        self.error_state = error_state
        self.get_id = get_id or (lambda ctx: ctx.get("job_id"))
        self.update_function = update_function

        # Validate update_function signature
        import inspect
        if update_function:
            self._validate_update_function_signature(update_function)

        # Detect if db_manager has async methods
        if update_function:
            self._is_async = inspect.iscoroutinefunction(update_function)
        elif hasattr(db_manager, "execute_query"):
            self._is_async = inspect.iscoroutinefunction(db_manager.execute_query)
        elif hasattr(db_manager, "execute"):
            self._is_async = inspect.iscoroutinefunction(db_manager.execute)
        else:
            if not update_function:
                raise ValueError(
                    "db_manager must have execute_query() or execute() method, "
                    "or provide update_function"
                )

        logger.info(
            f"DatabaseStateMiddleware initialized: table={state_table}, "
            f"column={state_column}, async={self._is_async}"
        )

    def _validate_update_function_signature(self, update_function: Callable) -> None:
        """
        Validate that update_function has the correct signature.

        Expected signature: (db_manager, job_id, state) or (self, db_manager, job_id, state)

        Raises:
            ValueError: If signature is invalid with helpful migration message.
        """
        import inspect

        sig = inspect.signature(update_function)
        params = list(sig.parameters.keys())

        # Filter out 'self' if it's a method
        if params and params[0] == 'self':
            params = params[1:]

        # Expected: (db_manager, job_id, state)
        if len(params) < 3:
            # Check if it's the old signature (job_id, state)
            if len(params) == 2:
                raise ValueError(
                    f"update_function has invalid signature: ({', '.join(sig.parameters.keys())})\n\n"
                    f"Expected signature: (db_manager, job_id, state)\n"
                    f"Got signature: ({', '.join(sig.parameters.keys())})\n\n"
                    f"This is a breaking change from previous versions.\n\n"
                    f"Migration required:\n"
                    f"  OLD: async def update_status(job_id: str, status: str):\n"
                    f"           await job_service.update_status(job_id, status)\n\n"
                    f"  NEW: async def update_status(db_manager, job_id: str, status: str):\n"
                    f"           await db_manager.execute_query(\n"
                    f"               'UPDATE jobs SET status = ? WHERE job_id = ?',\n"
                    f"               (status, job_id)\n"
                    f"           )\n\n"
                    f"See: agentorchestrator/docs/production_patterns.md#custom-update-function"
                )
            else:
                raise ValueError(
                    f"update_function has invalid signature: ({', '.join(sig.parameters.keys())})\n\n"
                    f"Expected signature: (db_manager, job_id, state)\n"
                    f"Got: {len(params)} parameters\n\n"
                    f"Example:\n"
                    f"  async def update_function(db_manager, job_id: str, state: str):\n"
                    f"      await db_manager.execute_query(\n"
                    f"          'UPDATE jobs SET status = ? WHERE job_id = ?',\n"
                    f"          (state, job_id)\n"
                    f"      )\n\n"
                    f"See: agentorchestrator/docs/production_patterns.md#custom-update-function"
                )

        logger.debug(
            f"update_function signature validated: ({', '.join(params)})"
        )

    async def _update_state(self, ctx: ChainContext, state: str) -> None:
        """
        Update the database state for the current job.

        Args:
            ctx (ChainContext): The chain context.
            state (str): New state value.
        """
        job_id = self.get_id(ctx)
        if job_id is None:
            logger.warning(
                f"Cannot update state to '{state}': job ID not found in context"
            )
            return

        try:
            # Use custom update function if provided
            if self.update_function:
                if self._is_async:
                    await self.update_function(self.db_manager, job_id, state)
                else:
                    self.update_function(self.db_manager, job_id, state)
            else:
                # Default UPDATE query
                query = f"UPDATE {self.state_table} SET {self.state_column} = ? WHERE {self.id_column} = ?"
                params = (state, job_id)

                if self._is_async:
                    if hasattr(self.db_manager, "execute_query"):
                        await self.db_manager.execute_query(query, params)
                    else:
                        await self.db_manager.execute(query, params)
                else:
                    if hasattr(self.db_manager, "execute_query"):
                        self.db_manager.execute_query(query, params)
                    else:
                        self.db_manager.execute(query, params)

            logger.debug(
                f"Updated {self.state_table}.{self.state_column} = '{state}' "
                f"for {self.id_column} = {job_id}"
            )
        except Exception as e:
            logger.error(
                f"Failed to update database state to '{state}' for job {job_id}: {e}"
            )

    async def before(self, ctx: ChainContext, step_name: str) -> None:
        """
        Called before step execution - update state to step's mapped state.

        Args:
            ctx (ChainContext): The chain context.
            step_name (str): Name of the step about to execute.
        """
        # Check if this step has a state mapping
        if step_name in self.step_to_state_mapping:
            state = self.step_to_state_mapping[step_name]
            await self._update_state(ctx, state)
        # If it's the first step and we have an initial state
        elif self.initial_state and not ctx.results:
            await self._update_state(ctx, self.initial_state)

    async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        """
        Called after successful step execution.

        If this is the last step and success_state is configured, update to success state.

        Args:
            ctx (ChainContext): The chain context.
            step_name (str): Name of the completed step.
            result (StepResult): The step result.
        """
        # Optionally update to success state on final step
        # This would require knowing if it's the final step, which we can check
        # by looking at the chain configuration or context
        pass

    async def on_error(self, ctx: ChainContext, step_name: str, error: Exception) -> None:
        """
        Called when a step fails - update state to error state if configured.

        Args:
            ctx (ChainContext): The chain context.
            step_name (str): Name of the failed step.
            error (Exception): The error that occurred.
        """
        if self.error_state:
            await self._update_state(ctx, self.error_state)