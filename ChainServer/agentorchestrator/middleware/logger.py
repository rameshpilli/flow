"""
AgentOrchestrator Logger Middleware

Provides comprehensive logging for chain execution.
"""

import logging
from datetime import datetime
from typing import Any

from agentorchestrator.core.context import ChainContext, StepResult
from agentorchestrator.middleware.base import Middleware


class LoggerMiddleware(Middleware):
    """
    Middleware that logs step execution details.

    Features:
    - Configurable log level
    - Structured logging support
    - Execution timing
    - Context snapshots

    Usage:
        forge.use_middleware(LoggerMiddleware(
            level=logging.INFO,
            include_context=True,
        ))
    """

    def __init__(
        self,
        priority: int = 10,
        applies_to: list[str] | None = None,
        level: int = logging.INFO,
        logger_name: str = "agentorchestrator.execution",
        include_context: bool = False,
        include_output: bool = False,
        max_output_length: int = 500,
    ):
        super().__init__(priority=priority, applies_to=applies_to)
        self.level = level
        self.logger = logging.getLogger(logger_name)
        self.include_context = include_context
        self.include_output = include_output
        self.max_output_length = max_output_length

        self._step_start_times: dict[str, datetime] = {}

    async def before(self, ctx: ChainContext, step_name: str) -> None:
        self._step_start_times[step_name] = datetime.utcnow()

        log_data = {
            "event": "step_start",
            "request_id": ctx.request_id,
            "step": step_name,
            "timestamp": datetime.utcnow().isoformat(),
        }

        if self.include_context:
            log_data["context_keys"] = ctx.keys()

        self.logger.log(
            self.level,
            f"[{ctx.request_id}] Starting step: {step_name}",
            extra={"structured_data": log_data},
        )

    async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        start_time = self._step_start_times.pop(step_name, None)
        actual_duration = None
        if start_time:
            actual_duration = (datetime.utcnow() - start_time).total_seconds() * 1000

        log_data = {
            "event": "step_complete",
            "request_id": ctx.request_id,
            "step": step_name,
            "success": result.success,
            "duration_ms": result.duration_ms,
            "actual_duration_ms": actual_duration,
            "timestamp": datetime.utcnow().isoformat(),
        }

        if self.include_output and result.output:
            output_str = str(result.output)
            if len(output_str) > self.max_output_length:
                output_str = output_str[: self.max_output_length] + "..."
            log_data["output_preview"] = output_str

        status = "completed" if result.success else "failed"
        self.logger.log(
            self.level,
            f"[{ctx.request_id}] Step {step_name} {status} in {result.duration_ms:.2f}ms",
            extra={"structured_data": log_data},
        )

    async def on_error(self, ctx: ChainContext, step_name: str, error: Exception) -> None:
        log_data = {
            "event": "step_error",
            "request_id": ctx.request_id,
            "step": step_name,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "timestamp": datetime.utcnow().isoformat(),
        }

        self.logger.error(
            f"[{ctx.request_id}] Step {step_name} error: {error}",
            extra={"structured_data": log_data},
            exc_info=True,
        )


class MetricsMiddleware(Middleware):
    """
    Middleware that collects execution metrics.

    Tracks:
    - Step execution counts
    - Success/failure rates
    - Execution times (avg, p50, p95, p99)
    """

    def __init__(
        self,
        priority: int = 5,
        applies_to: list[str] | None = None,
    ):
        super().__init__(priority=priority, applies_to=applies_to)
        self._metrics: dict[str, dict[str, Any]] = {}

    async def after(self, ctx: ChainContext, step_name: str, result: StepResult) -> None:
        if step_name not in self._metrics:
            self._metrics[step_name] = {
                "total_count": 0,
                "success_count": 0,
                "failure_count": 0,
                "durations": [],
            }

        metrics = self._metrics[step_name]
        metrics["total_count"] += 1
        if result.success:
            metrics["success_count"] += 1
        else:
            metrics["failure_count"] += 1
        metrics["durations"].append(result.duration_ms)

    def get_metrics(self, step_name: str | None = None) -> dict[str, Any]:
        """Get metrics for a step or all steps"""
        if step_name:
            raw = self._metrics.get(step_name, {})
            return self._compute_stats(raw)

        return {name: self._compute_stats(raw) for name, raw in self._metrics.items()}

    def _compute_stats(self, raw: dict[str, Any]) -> dict[str, Any]:
        if not raw:
            return {}

        durations = sorted(raw.get("durations", []))
        total = raw.get("total_count", 0)

        return {
            "total_count": total,
            "success_count": raw.get("success_count", 0),
            "failure_count": raw.get("failure_count", 0),
            "success_rate": raw.get("success_count", 0) / total if total > 0 else 0,
            "avg_duration_ms": sum(durations) / len(durations) if durations else 0,
            "min_duration_ms": min(durations) if durations else 0,
            "max_duration_ms": max(durations) if durations else 0,
            "p50_duration_ms": self._percentile(durations, 50),
            "p95_duration_ms": self._percentile(durations, 95),
            "p99_duration_ms": self._percentile(durations, 99),
        }

    def _percentile(self, sorted_list: list[float], percentile: int) -> float:
        if not sorted_list:
            return 0
        idx = int(len(sorted_list) * percentile / 100)
        return sorted_list[min(idx, len(sorted_list) - 1)]

    def reset_metrics(self) -> None:
        """Reset all collected metrics"""
        self._metrics.clear()
