"""
AgentOrchestrator Reflection Middleware
=======================================

Provides agent self-critique and reflection capabilities. This middleware
allows steps to automatically review and potentially revise their outputs
before returning, implementing the common AI pattern of "think twice."

Features:
- Automatic output critique using LLM
- Configurable retry on critique failure
- Quality scoring and thresholds
- Detailed reflection traces for debugging

Usage:
    from agentorchestrator.middleware.reflection import (
        ReflectionMiddleware,
        ReflectionConfig,
        reflect,
    )

    # Option 1: Apply middleware globally
    ao.add_middleware(ReflectionMiddleware(
        config=ReflectionConfig(
            quality_threshold=0.8,
            max_revisions=2,
        ),
    ))

    # Option 2: Use @reflect decorator on specific steps
    @ao.step(name="generate_report")
    @reflect(critique_prompt="Review this report for accuracy...")
    async def generate_report(ctx):
        return {"report": "..."}

Example:
    >>> @ao.step(name="draft_email")
    ... @reflect(
    ...     critique_prompt="Is this email professional and clear?",
    ...     quality_threshold=0.85,
    ... )
    ... async def draft_email(ctx):
    ...     return {"email": "Dear Sir..."}
    >>>
    >>> # The step will:
    >>> # 1. Generate initial output
    >>> # 2. Critique the output using LLM
    >>> # 3. If quality < threshold, revise and repeat
    >>> # 4. Return final output with reflection trace
"""

import asyncio
import functools
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

from agentorchestrator.core.context import ChainContext, StepResult
from agentorchestrator.middleware.base import Middleware

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

__all__ = [
    "ReflectionMiddleware",
    "ReflectionConfig",
    "ReflectionResult",
    "reflect",
    "create_reflection_middleware",
]


@dataclass
class ReflectionResult:
    """Result of a reflection/critique cycle."""
    
    original_output: Any
    """The initial output before reflection."""
    
    final_output: Any
    """The final output after reflection/revision."""
    
    quality_score: float
    """Quality score from 0.0 to 1.0."""
    
    revision_count: int
    """Number of revisions performed."""
    
    critique_history: list[dict[str, Any]] = field(default_factory=list)
    """History of critiques and revisions."""
    
    passed_threshold: bool = True
    """Whether the final output met the quality threshold."""
    
    reflection_time_ms: float = 0.0
    """Time spent in reflection/revision."""


@dataclass
class ReflectionConfig:
    """Configuration for reflection middleware."""
    
    quality_threshold: float = 0.8
    """Minimum quality score (0.0-1.0) to accept output without revision."""
    
    max_revisions: int = 2
    """Maximum number of revision attempts."""
    
    critique_prompt: str | None = None
    """
    Custom prompt for critiquing output. If None, uses default prompt.
    Use {output} placeholder for the step output.
    """
    
    revision_prompt: str | None = None
    """
    Custom prompt for revision. If None, uses default prompt.
    Use {output}, {critique}, and {score} placeholders.
    """
    
    enabled: bool = True
    """Whether reflection is enabled."""
    
    store_trace: bool = True
    """Whether to store reflection trace in context."""
    
    trace_key: str = "_reflection_trace"
    """Context key for storing reflection trace."""
    
    applies_to: list[str] | None = None
    """List of step names to apply to. None means all steps."""
    
    excludes: list[str] | None = None
    """List of step names to exclude from reflection."""


# Default prompts
DEFAULT_CRITIQUE_PROMPT = """
Evaluate the following output for quality, accuracy, and completeness.

OUTPUT:
{output}

{criteria}

Respond with a JSON object containing:
- "score": A quality score from 0.0 to 1.0
- "issues": A list of specific issues found (empty if none)
- "suggestions": A list of improvement suggestions (empty if none)
- "should_revise": Boolean indicating if revision is needed

Example response:
{{"score": 0.85, "issues": ["Minor formatting issue"], "suggestions": ["Add conclusion"], "should_revise": false}}
"""

DEFAULT_REVISION_PROMPT = """
Revise the following output based on the critique provided.

ORIGINAL OUTPUT:
{output}

CRITIQUE (Score: {score}):
Issues: {issues}
Suggestions: {suggestions}

Please provide an improved version that addresses the issues and incorporates the suggestions.
Maintain the same output format/structure as the original.
"""


class ReflectionMiddleware(Middleware):
    """
    Middleware that adds self-critique and reflection to steps.
    
    This middleware intercepts step outputs and uses an LLM to:
    1. Critique the output quality
    2. Score the output (0.0-1.0)
    3. If below threshold, revise and repeat
    4. Return final output with reflection trace
    
    Attributes:
        config: ReflectionConfig with settings.
        llm_client: LLM client for critique/revision (auto-detected if not provided).
    
    Example:
        >>> middleware = ReflectionMiddleware(
        ...     config=ReflectionConfig(
        ...         quality_threshold=0.85,
        ...         max_revisions=3,
        ...     ),
        ... )
        >>> ao.add_middleware(middleware)
    """
    
    _ao_priority = 90  # Run late, after most other middleware
    
    def __init__(
        self,
        config: ReflectionConfig | None = None,
        llm_client: Any = None,
        applies_to: list[str] | None = None,
    ):
        """
        Initialize reflection middleware.
        
        Args:
            config: Reflection configuration.
            llm_client: LLM client for critique. If None, uses default client.
            applies_to: List of step names to apply to. Overrides config.applies_to.
        """
        self.config = config or ReflectionConfig()
        self._llm_client = llm_client
        self._ao_applies_to = applies_to or self.config.applies_to
        self._stats = {
            "total_reflections": 0,
            "revisions_performed": 0,
            "threshold_failures": 0,
            "avg_quality_score": 0.0,
        }
    
    @property
    def llm_client(self):
        """Get LLM client, auto-detecting if not provided."""
        if self._llm_client is None:
            try:
                from agentorchestrator.services.llm_gateway import get_default_llm_client
                self._llm_client = get_default_llm_client()
            except Exception:
                logger.warning("No LLM client available for reflection")
        return self._llm_client
    
    def _should_reflect(self, step_name: str) -> bool:
        """Check if step should have reflection applied."""
        if not self.config.enabled:
            return False
        
        # Check excludes
        if self.config.excludes and step_name in self.config.excludes:
            return False
        
        # Check applies_to
        if self._ao_applies_to and step_name not in self._ao_applies_to:
            return False
        
        return True
    
    async def after(
        self,
        ctx: ChainContext,
        step_name: str,
        result: StepResult,
    ) -> StepResult:
        """
        Apply reflection to step output after execution.
        """
        if not self._should_reflect(step_name):
            return result
        
        if not result.success:
            return result
        
        if self.llm_client is None:
            logger.debug(f"Skipping reflection for {step_name}: no LLM client")
            return result
        
        start_time = time.perf_counter()
        
        try:
            reflection_result = await self._reflect_on_output(
                step_name=step_name,
                output=result.output,
                ctx=ctx,
            )
            
            # Update result with reflected output
            result.output = reflection_result.final_output
            
            # Store trace in context if enabled
            if self.config.store_trace:
                traces = ctx.get(self.config.trace_key, default={})
                traces[step_name] = {
                    "quality_score": reflection_result.quality_score,
                    "revision_count": reflection_result.revision_count,
                    "passed_threshold": reflection_result.passed_threshold,
                    "critique_history": reflection_result.critique_history,
                    "reflection_time_ms": reflection_result.reflection_time_ms,
                }
                ctx.set(self.config.trace_key, traces)
            
            # Update stats
            self._stats["total_reflections"] += 1
            self._stats["revisions_performed"] += reflection_result.revision_count
            if not reflection_result.passed_threshold:
                self._stats["threshold_failures"] += 1
            
            # Update running average
            n = self._stats["total_reflections"]
            old_avg = self._stats["avg_quality_score"]
            self._stats["avg_quality_score"] = (
                old_avg * (n - 1) + reflection_result.quality_score
            ) / n
            
            logger.info(
                f"Reflection for {step_name}: score={reflection_result.quality_score:.2f}, "
                f"revisions={reflection_result.revision_count}, "
                f"passed={reflection_result.passed_threshold}"
            )
            
        except Exception as e:
            logger.warning(f"Reflection failed for {step_name}: {e}")
            # Don't fail the step if reflection fails
        
        return result
    
    async def _reflect_on_output(
        self,
        step_name: str,
        output: Any,
        ctx: ChainContext,
    ) -> ReflectionResult:
        """
        Perform reflection cycle on step output.
        """
        import json
        
        start_time = time.perf_counter()
        original_output = output
        current_output = output
        critique_history = []
        revision_count = 0
        quality_score = 0.0
        
        for iteration in range(self.config.max_revisions + 1):
            # Critique current output
            critique = await self._critique_output(current_output, step_name, ctx)
            quality_score = critique.get("score", 0.5)
            
            critique_history.append({
                "iteration": iteration,
                "score": quality_score,
                "issues": critique.get("issues", []),
                "suggestions": critique.get("suggestions", []),
                "should_revise": critique.get("should_revise", False),
            })
            
            # Check if quality threshold met
            if quality_score >= self.config.quality_threshold:
                break
            
            # Check if more revisions allowed
            if iteration >= self.config.max_revisions:
                break
            
            # Check if critique recommends revision
            if not critique.get("should_revise", True):
                break
            
            # Revise output
            current_output = await self._revise_output(
                original_output=current_output,
                critique=critique,
                step_name=step_name,
                ctx=ctx,
            )
            revision_count += 1
        
        reflection_time_ms = (time.perf_counter() - start_time) * 1000
        
        return ReflectionResult(
            original_output=original_output,
            final_output=current_output,
            quality_score=quality_score,
            revision_count=revision_count,
            critique_history=critique_history,
            passed_threshold=quality_score >= self.config.quality_threshold,
            reflection_time_ms=reflection_time_ms,
        )
    
    async def _critique_output(
        self,
        output: Any,
        step_name: str,
        ctx: ChainContext,
    ) -> dict[str, Any]:
        """
        Use LLM to critique output quality.
        """
        import json
        
        # Format output for prompt
        if isinstance(output, dict):
            output_str = json.dumps(output, indent=2, default=str)
        else:
            output_str = str(output)
        
        # Get criteria from step spec if available
        criteria = ""
        try:
            from agentorchestrator.core.registry import get_step_registry
            spec = get_step_registry().get_spec(step_name)
            if spec and hasattr(spec, "reflection_criteria"):
                criteria = f"CRITERIA: {spec.reflection_criteria}"
        except Exception:
            pass
        
        prompt = (self.config.critique_prompt or DEFAULT_CRITIQUE_PROMPT).format(
            output=output_str,
            criteria=criteria,
        )
        
        try:
            response = await self.llm_client.generate_async(
                prompt=prompt,
                system_prompt="You are a quality reviewer. Respond only with valid JSON.",
                max_tokens=500,
            )
            
            # Parse JSON response
            return json.loads(response)
        except json.JSONDecodeError:
            logger.warning("Failed to parse critique response as JSON")
            return {"score": 0.5, "issues": [], "suggestions": [], "should_revise": False}
        except Exception as e:
            logger.warning(f"Critique failed: {e}")
            return {"score": 0.5, "issues": [], "suggestions": [], "should_revise": False}
    
    async def _revise_output(
        self,
        original_output: Any,
        critique: dict[str, Any],
        step_name: str,
        ctx: ChainContext,
    ) -> Any:
        """
        Use LLM to revise output based on critique.
        """
        import json
        
        # Format output for prompt
        if isinstance(original_output, dict):
            output_str = json.dumps(original_output, indent=2, default=str)
        else:
            output_str = str(original_output)
        
        prompt = (self.config.revision_prompt or DEFAULT_REVISION_PROMPT).format(
            output=output_str,
            score=critique.get("score", 0.5),
            issues=", ".join(critique.get("issues", [])) or "None",
            suggestions=", ".join(critique.get("suggestions", [])) or "None",
        )
        
        try:
            response = await self.llm_client.generate_async(
                prompt=prompt,
                system_prompt="You are revising output based on feedback. Maintain the original format.",
                max_tokens=2000,
            )
            
            # Try to parse as JSON if original was dict
            if isinstance(original_output, dict):
                try:
                    return json.loads(response)
                except json.JSONDecodeError:
                    pass
            
            return response
        except Exception as e:
            logger.warning(f"Revision failed: {e}")
            return original_output
    
    def get_stats(self) -> dict[str, Any]:
        """Get reflection statistics."""
        return dict(self._stats)
    
    def reset_stats(self) -> None:
        """Reset statistics."""
        self._stats = {
            "total_reflections": 0,
            "revisions_performed": 0,
            "threshold_failures": 0,
            "avg_quality_score": 0.0,
        }


def reflect(
    critique_prompt: str | None = None,
    quality_threshold: float = 0.8,
    max_revisions: int = 2,
    llm_client: Any = None,
) -> Callable[[F], F]:
    """
    Decorator to add reflection/self-critique to a step.
    
    This decorator wraps a step handler to automatically:
    1. Execute the step
    2. Critique the output using an LLM
    3. If below quality threshold, revise and repeat
    4. Store reflection trace in context
    
    Args:
        critique_prompt: Custom prompt for critiquing output.
        quality_threshold: Minimum score (0.0-1.0) to accept output.
        max_revisions: Maximum revision attempts.
        llm_client: LLM client for critique. If None, uses default.
    
    Returns:
        Decorated function with reflection capability.
    
    Example:
        >>> @ao.step(name="write_summary")
        ... @reflect(quality_threshold=0.9, max_revisions=3)
        ... async def write_summary(ctx):
        ...     text = ctx.get("document")
        ...     return {"summary": summarize(text)}
    
    Note:
        The decorator should be applied AFTER @ao.step() (i.e., closer to the function).
    """
    config = ReflectionConfig(
        critique_prompt=critique_prompt,
        quality_threshold=quality_threshold,
        max_revisions=max_revisions,
    )
    
    middleware = ReflectionMiddleware(config=config, llm_client=llm_client)
    
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(ctx: ChainContext) -> Any:
            # Execute original function
            result = await func(ctx)
            
            # Apply reflection
            if middleware.llm_client is not None:
                reflection_result = await middleware._reflect_on_output(
                    step_name=func.__name__,
                    output=result,
                    ctx=ctx,
                )
                
                # Store trace
                if config.store_trace:
                    traces = ctx.get(config.trace_key, default={})
                    traces[func.__name__] = {
                        "quality_score": reflection_result.quality_score,
                        "revision_count": reflection_result.revision_count,
                        "passed_threshold": reflection_result.passed_threshold,
                    }
                    ctx.set(config.trace_key, traces)
                
                return reflection_result.final_output
            
            return result
        
        return wrapper  # type: ignore
    
    return decorator


def create_reflection_middleware(
    quality_threshold: float = 0.8,
    max_revisions: int = 2,
    applies_to: list[str] | None = None,
    excludes: list[str] | None = None,
    llm_client: Any = None,
) -> ReflectionMiddleware:
    """
    Factory function to create a ReflectionMiddleware with common settings.
    
    Args:
        quality_threshold: Minimum quality score (0.0-1.0).
        max_revisions: Maximum revision attempts.
        applies_to: Step names to apply to (None = all).
        excludes: Step names to exclude.
        llm_client: LLM client for critique/revision.
    
    Returns:
        Configured ReflectionMiddleware.
    
    Example:
        >>> middleware = create_reflection_middleware(
        ...     quality_threshold=0.9,
        ...     applies_to=["generate_report", "write_summary"],
        ... )
        >>> ao.add_middleware(middleware)
    """
    config = ReflectionConfig(
        quality_threshold=quality_threshold,
        max_revisions=max_revisions,
        applies_to=applies_to,
        excludes=excludes,
    )
    return ReflectionMiddleware(config=config, llm_client=llm_client)
