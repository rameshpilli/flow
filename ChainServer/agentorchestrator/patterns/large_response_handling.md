# Large Agent Response Handling: Patterns & Comparison

A practical guide covering middleware patterns for managing large agent responses, with comparisons to LlamaIndex and LangChain approaches.

---

## Your Framework's Approach

### 1. Per-Step Middleware Configuration

Apply middleware selectively using `applies_to`:

```python
ao.use(SummarizerMiddleware(
    max_tokens=4000,
    applies_to=["gather_sec", "gather_news"],  # Only these steps
))
```

### 2. Three Middleware Options

| Middleware | Purpose | Use Case |
|------------|---------|----------|
| **SummarizerMiddleware** | Compress text while preserving key info | Large document analysis, research tasks |
| **OffloadMiddleware** | Store large payloads in Redis, keep lightweight refs | Multi-agent pipelines, long-running workflows |
| **TokenManagerMiddleware** | Track budget and auto-trigger compression | Cost control, context window management |

### 3. Middleware Layering

Combine middleware in the correct order:

```
Agent Output → TokenManager → Summarizer → Offload → Small Context
```

### 4. Domain-Specific Prompts

Register custom summarization prompts for SEC filings, news, etc.

---

## LlamaIndex's Approach

LlamaIndex uses a **multi-layered memory and callback system** rather than explicit middleware.

### Memory-Based Token Management

#### ChatMemoryBuffer (Simple Truncation)
**File**: `llama_index/core/memory/chat_memory_buffer.py`

```python
class ChatMemoryBuffer(BaseChatStoreMemory):
    token_limit: int  # Maximum tokens allowed in buffer

    def get(self, input: Optional[str] = None, initial_token_count: int = 0) -> List[ChatMessage]:
        """Get chat history, truncating old messages to fit token limit."""
        chat_history = self.get_all()
        cur_messages = chat_history[-message_count:]
        token_count = self._token_count_for_messages(cur_messages) + initial_token_count

        # Remove oldest messages until under token limit
        while token_count > self.token_limit and message_count > 1:
            message_count -= 1
            # Skip ASSISTANT/TOOL messages to maintain message pair integrity
            while chat_history[-message_count].role in (MessageRole.TOOL, MessageRole.ASSISTANT):
                message_count -= 1
            cur_messages = chat_history[-message_count:]
            token_count = self._token_count_for_messages(cur_messages) + initial_token_count
```

**Key insight**: Maintains message structure integrity (preserves ASSISTANT-TOOL pairs during truncation).

#### ChatSummaryMemoryBuffer (Summarization)
**File**: `llama_index/core/memory/chat_summary_memory_buffer.py`

```python
class ChatSummaryMemoryBuffer(BaseMemory):
    token_limit: int
    llm: Optional[LLM] = None  # For summarization

    def _split_messages_summary_or_full_text(self, chat_history: List[ChatMessage]):
        """Split messages into full-text (recent) and summarized (old) parts."""
        chat_history_full_text: List[ChatMessage] = []

        # Keep recent messages in full text
        while message_count > 0 and self.get_token_count() + self._token_count_for_messages([chat_history[-1]]) <= self.token_limit:
            chat_history_full_text.insert(0, chat_history.pop())
            message_count -= 1

        # Remaining old messages will be summarized
        return chat_history_full_text, chat_history  # to_be_summarized

    def _summarize_oldest_chat_history(self, chat_history_to_be_summarized):
        """Use LLM to summarize old messages."""
        summarize_prompt = [
            ChatMessage(role=MessageRole.SYSTEM, content=self.summarize_prompt),
            ChatMessage(role=MessageRole.USER, content=self._get_prompt_to_summarize(chat_history_to_be_summarized))
        ]
        r = self.llm.chat(summarize_prompt)
        return ChatMessage(role=MessageRole.SYSTEM, content=r.message.content)
```

**Equivalent to**: `SummarizerMiddleware` - but applied at the memory layer rather than middleware.

### Token Budget Enforcement

**File**: `llama_index/core/callbacks/token_counting.py`

```python
class TokenCountingHandler(PythonicallyPrintingBaseHandler):
    def __init__(self, tokenizer=None, token_budget: Optional[int] = None):
        self.llm_token_counts: List[TokenCountingEvent] = []
        self.token_budget = token_budget
        self._token_counter = TokenCounter(tokenizer=self.tokenizer)

    def _check_budget(self) -> None:
        if self.token_budget is not None and self.total_llm_token_count > self.token_budget:
            raise ValueError(f"Token budget exceeded! Limit: {self.token_budget}, Current: {self.total_llm_token_count}")
```

**Equivalent to**: `TokenManagerMiddleware` - but as a callback handler rather than middleware.

### Waterfall Memory Architecture

**File**: `llama_index/core/memory/memory.py`

```python
class Memory(BaseMemory):
    token_limit: int = Field(default=30000)  # 30k tokens
    token_flush_size: int = Field(default=3000)  # 10% of limit - triggers flush
    chat_history_token_ratio: float = Field(default=0.7)  # 70% reserved for chat
    memory_blocks: List[BaseMemoryBlock] = Field(default_factory=list)

class BaseMemoryBlock(BaseModel, Generic[T]):
    """Base memory block with optional truncation support."""

    async def atruncate(self, content: T, tokens_to_truncate: int) -> Optional[T]:
        """Truncate the memory block content to reduce token usage."""
        return None  # Default: remove entire block
```

**Key insight**: Each memory block can implement custom truncation logic - similar to your domain-specific prompts concept.

### Context Window Management (PromptHelper)

**File**: `llama_index/core/indices/prompt_helper.py`

```python
class PromptHelper(BaseComponent):
    context_window: int = Field(default=DEFAULT_CONTEXT_WINDOW)
    num_output: int = Field(default=DEFAULT_NUM_OUTPUTS)  # Space reserved for response
    chunk_overlap_ratio: float = Field(default=0.1)

    def _get_available_context_size(self, num_prompt_tokens: int) -> int:
        """available = context_window - input - output_reserved"""
        return self.context_window - num_prompt_tokens - self.num_output

    def truncate(self, prompt, text_chunks: Sequence[str]) -> List[str]:
        """Truncate text chunks to fit available context window."""
        text_splitter = self.get_text_splitter_given_prompt(...)
        return [truncate_text(chunk, text_splitter) for chunk in text_chunks]

    def repack(self, prompt, text_chunks: Sequence[str]) -> List[str]:
        """Repack chunks to maximally use available context."""
        combined_str = "\n\n".join([c.strip() for c in text_chunks if c.strip()])
        return text_splitter.split_text(combined_str)
```

**Unique pattern**: `repack()` optimizes context usage by recombining chunks - not just truncating.

---

## LangChain's Approach

LangChain uses a **streaming-first architecture** with callback-based middleware.

### Callback System

**File**: `langchain_core/callbacks/manager.py`

```python
# Response handling via callbacks
on_llm_start()      # Pre-processing
on_llm_new_token()  # Stream tokens one at a time
on_llm_end()        # Post-processing with complete LLMResult
```

**File**: `langchain_core/callbacks/streaming_stdout.py`

```python
class StreamingStdOutCallbackHandler(BaseCallbackHandler):
    def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        """Run on new LLM token. Only available when streaming is enabled."""
        sys.stdout.write(token)
        sys.stdout.flush()

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Run when LLM ends running."""
        # Process complete response
```

### Chunked Response Structure

**File**: `langchain_core/outputs/llm_result.py`

```python
class LLMResult(BaseModel):
    generations: list[list[Generation | ChatGeneration | GenerationChunk | ChatGenerationChunk]]
    llm_output: dict | None = None  # Provider-specific data (token counts, etc.)
    run: list[RunInfo] | None = None
```

Multi-dimensional list allows:
- Multiple completions per prompt (first dimension)
- Multiple candidate generations (second dimension)
- Support for chunked streaming data (`GenerationChunk` types)

### LangGraph Channel-Based State Management

**File**: `langgraph/channels/base.py`

```python
class BaseChannel(Generic[Value, Update, Checkpoint], ABC):
    def get(self) -> Value:
        """Return the current value of the channel."""

    def update(self, values: Sequence[Update]) -> bool:
        """Update the channel's value with sequence of updates."""

    def checkpoint(self) -> Checkpoint | Any:
        """Return a serializable representation of the channel's state."""

    def from_checkpoint(self, checkpoint: Checkpoint | Any) -> Self:
        """Restore from checkpoint."""
```

Channel implementations:
- **LastValue** - stores only most recent value (memory efficient)
- **EphemeralValue** - temporary values that don't persist
- **BinaryOperatorAggregate** - combines multiple responses using an operator

**Equivalent to**: `OffloadMiddleware` - but with channels abstracting storage.

### Response Caching

**File**: `langgraph/_internal/_cache.py`

```python
def _freeze(obj: Any, depth: int = 10) -> Hashable:
    """Recursively freeze objects for caching."""
    if isinstance(obj, Hashable) or depth <= 0:
        return obj
    elif isinstance(obj, Mapping):
        return tuple(sorted((_freeze(k, depth - 1), _freeze(v, depth - 1)) for k, v in obj.items()))
    elif isinstance(obj, Sequence):
        return tuple(_freeze(x, depth - 1) for x in obj)

def default_cache_key(*args: Any, **kwargs: Any) -> str | bytes:
    """Generate cache key using pickle with protocol 5."""
    return pickle.dumps((_freeze(args), _freeze(kwargs)), protocol=5)
```

---

## Side-by-Side Comparison

| Feature | Your Framework | LlamaIndex | LangChain |
|---------|---------------|------------|-----------|
| **Architecture** | Explicit middleware chain | Memory + Callbacks | Streaming + Channels |
| **Selective Application** | `applies_to=["step1"]` | Memory block types | Channel types |
| **Summarization** | `SummarizerMiddleware` | `ChatSummaryMemoryBuffer` | Not built-in (manual) |
| **External Storage** | `OffloadMiddleware` (Redis) | Not built-in | Channel checkpointing |
| **Token Tracking** | `TokenManagerMiddleware` | `TokenCountingHandler` | `llm_output` metadata |
| **Budget Enforcement** | Auto-trigger compression | Raise `ValueError` | Manual handling |
| **Domain Prompts** | Registered prompts | Memory block `atruncate()` | Manual |
| **Streaming** | Not mentioned | `AgentStream` events | `on_llm_new_token()` |

---

## Key Patterns to Consider Adopting

### 1. From LlamaIndex: Message Pair Integrity

When truncating, preserve ASSISTANT-TOOL message pairs:

```python
class SummarizerMiddleware:
    def truncate(self, messages):
        while over_limit:
            # Don't break tool call sequences
            if messages[-idx].role in (MessageRole.TOOL, MessageRole.ASSISTANT):
                idx += 1
                continue
            messages.pop(-idx)
```

### 2. From LlamaIndex: Repacking vs Truncation

Instead of just truncating, repack content to maximize context usage:

```python
class RepackMiddleware:
    def process(self, chunks: List[str]) -> List[str]:
        # Combine all chunks, then re-split optimally
        combined = "\n\n".join([c.strip() for c in chunks])
        return self.splitter.split_text(combined)
```

### 3. From LlamaIndex: Waterfall Memory Blocks

Allow each step to define its own truncation strategy:

```python
class StepConfig:
    truncation_strategy: Literal["summarize", "drop", "compress"]
    priority: int  # Lower priority truncated first

ao.register_step("gather_sec", truncation_strategy="summarize", priority=1)
ao.register_step("gather_news", truncation_strategy="drop", priority=2)
```

### 4. From LangChain: Channel Abstraction

Abstract storage from processing:

```python
class ResponseChannel(ABC):
    def get(self) -> Any: ...
    def update(self, value: Any) -> bool: ...
    def checkpoint(self) -> bytes: ...

class RedisChannel(ResponseChannel):
    """Your OffloadMiddleware as a channel"""

class LastValueChannel(ResponseChannel):
    """Only keeps most recent value"""
```

### 5. From LangChain: Streaming-First Design

Process responses as they arrive:

```python
class StreamingTokenManager:
    def on_token(self, token: str):
        self.current_count += 1
        if self.current_count > self.warning_threshold:
            self.emit_warning()
        return token
```

---

## Recommended Enhancements for Your Framework

### 1. Add Streaming Support

```python
class StreamingSummarizerMiddleware(SummarizerMiddleware):
    """Summarize in chunks as response streams in."""

    async def process_stream(self, token_stream):
        buffer = []
        async for token in token_stream:
            buffer.append(token)
            if len(buffer) >= self.chunk_size:
                yield self._summarize_chunk(buffer)
                buffer = []
        if buffer:
            yield self._summarize_chunk(buffer)
```

### 2. Add Budget Modes

```python
class TokenManagerMiddleware:
    mode: Literal["error", "compress", "warn"] = "compress"

    def check_budget(self, count: int):
        if count > self.budget:
            if self.mode == "error":
                raise TokenBudgetExceeded(f"Limit: {self.budget}, Current: {count}")
            elif self.mode == "compress":
                return self._trigger_compression()
            else:
                self._emit_warning()
```

### 3. Add Checkpoint/Resume

```python
class OffloadMiddleware:
    def checkpoint(self, step_id: str) -> str:
        """Return a reference that can resume later."""
        return self.redis.set(f"checkpoint:{step_id}", self._serialize_state())

    def resume(self, checkpoint_ref: str) -> Any:
        """Resume from a checkpoint."""
        return self._deserialize_state(self.redis.get(checkpoint_ref))
```

### 4. Add Priority-Based Truncation

```python
@dataclass
class TruncationConfig:
    priority: int  # 1 = truncate first, 10 = truncate last
    strategy: Literal["drop", "summarize", "compress"]
    min_retain: int = 0  # Minimum tokens to always keep

ao.use(SummarizerMiddleware(
    max_tokens=4000,
    applies_to=["gather_sec"],
    truncation=TruncationConfig(priority=2, strategy="summarize", min_retain=500)
))
```

---

## Summary

| Framework | Philosophy | Strengths | Gaps |
|-----------|------------|-----------|------|
| **Yours** | Explicit middleware chain | Clear ordering, selective application | No streaming, no repacking |
| **LlamaIndex** | Memory-centric | Rich memory types, summarization built-in | Complex configuration |
| **LangChain** | Streaming-first | Real-time processing, channel abstraction | Summarization not built-in |

**Your framework's unique value**: The `applies_to` pattern for selective middleware application is more explicit than both LlamaIndex and LangChain. Consider keeping this as your core differentiator while adopting streaming and repacking patterns.
