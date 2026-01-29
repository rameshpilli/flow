# Large Agent Response Handling: LlamaIndex vs LangChain vs Your Middleware Approach

## Executive Summary

After analyzing both LlamaIndex and LangChain repositories, here's how they handle large agent responses compared to your middleware-based approach.

---

## Your Current Approach (Middleware Pattern)

```
Agent Output → TokenManager → Summarizer → Offload → Small Context
```

| Middleware | Purpose |
|------------|---------|
| `SummarizerMiddleware` | Compress text while preserving key info |
| `OffloadMiddleware` | Store large payloads in Redis, keep refs |
| `TokenManagerMiddleware` | Track budget and auto-trigger compression |

With per-step targeting via `applies_to`:
```python
ao.use(SummarizerMiddleware(
    max_tokens=4000,
    applies_to=["gather_sec", "gather_news"],
))
```

---

## LlamaIndex Approach

### 1. Context Management - `PromptHelper`

LlamaIndex uses a centralized `PromptHelper` class for context window management:

```python
class PromptHelper:
    context_window: int = 3900  # Max context size
    num_output: int = 256       # Reserved for response

    def _get_available_context_size(self, num_prompt_tokens: int) -> int:
        return self.context_window - num_prompt_tokens - self.num_output

    def truncate(self, text_chunks, ...) -> List[str]:
        """Truncate chunks to fit context"""

    def repack(self, prompt_template, text_chunks, ...) -> List[str]:
        """Combine chunks to maximize context utilization"""
```

#### Example: PromptHelper in Action

**Input:**
```python
# User has 5 document chunks, each ~1000 tokens
chunks = [
    "Apple Inc. Q4 2024 earnings report shows revenue of $89.5B...[1000 tokens]",
    "Microsoft Azure growth continues with 29% YoY increase...[1000 tokens]",
    "Google Cloud Platform announces new AI features...[1000 tokens]",
    "Amazon AWS maintains market leadership position...[1000 tokens]",
    "Meta's Reality Labs division reports $4.5B loss...[1000 tokens]",
]
# Total: ~5000 tokens, but context_window is only 3900
```

**During Processing:**
```python
prompt_helper = PromptHelper(context_window=3900, num_output=256)

# Step 1: Calculate available space
available = 3900 - 500 (system prompt) - 256 (output) = 3144 tokens

# Step 2: Repack chunks to fit
repacked = prompt_helper.repack(template, chunks)
# Combines chunks 1+2+3 into one group (~3000 tokens)
# Leaves chunks 4+5 for next iteration
```

**Output:**
```python
# First batch (fits in context):
repacked_batch_1 = [
    "Apple Inc. Q4 2024 earnings report shows revenue of $89.5B... "
    "Microsoft Azure growth continues with 29% YoY increase... "
    "Google Cloud Platform announces new AI features..."
]  # ~3000 tokens

# Second batch (processed separately):
repacked_batch_2 = [
    "Amazon AWS maintains market leadership position... "
    "Meta's Reality Labs division reports $4.5B loss..."
]  # ~2000 tokens
```

**Comparison to your approach:** Your `TokenManagerMiddleware` is similar but more middleware-oriented. LlamaIndex bakes this into the core.

---

### 2. Summarization - Multiple Strategies

**ChatSummaryMemoryBuffer** (conversation compression):
```python
class ChatSummaryMemoryBuffer(BaseMemory):
    token_limit: int
    llm: LLM  # For summarization
    summarize_prompt: str

    def get(self, input: str, initial_token_count: int = 0):
        # Recent messages: full text
        # Older messages: LLM-summarized
        chat_history_full_text, chat_history_to_be_summarized = \
            self._split_messages_summary_or_full_text(chat_history)

        if len(chat_history_to_be_summarized) > 0:
            summary = self._summarize_oldest_chat_history(
                chat_history_to_be_summarized
            )
            return [summary] + chat_history_full_text
```

#### Example: ChatSummaryMemoryBuffer in Action

**Input:**
```python
# Conversation with 10 messages, token_limit=2000
messages = [
    {"role": "user", "content": "What were Apple's Q4 earnings?"},                    # 8 tokens
    {"role": "assistant", "content": "Apple reported Q4 2024 revenue of $89.5B, up 6% YoY. iPhone revenue was $46.2B, Services hit $22.2B all-time high. EPS was $1.64, beating estimates of $1.60. Tim Cook highlighted strong performance in emerging markets, particularly India where revenue doubled. The company announced a $110B stock buyback program..."},  # 800 tokens
    {"role": "user", "content": "How about Microsoft?"},                              # 5 tokens
    {"role": "assistant", "content": "Microsoft Q4 showed Azure growing 29% YoY. Total cloud revenue reached $36.8B. Gaming division saw 61% growth post-Activision. LinkedIn revenue up 10%. Copilot AI features drove Office 365 adoption. Satya Nadella emphasized AI transformation across all product lines..."},  # 750 tokens
    {"role": "user", "content": "Compare their cloud strategies"},                     # 6 tokens
    {"role": "assistant", "content": "Azure focuses on enterprise hybrid cloud with strong AI integration via OpenAI partnership. AWS leads in market share (32%) but Azure growing faster (29% vs 12%). Google Cloud emphasizes data analytics and ML tools. Key differentiators: Microsoft's enterprise relationships, Amazon's breadth of services, Google's AI/ML capabilities..."},  # 850 tokens
    {"role": "user", "content": "What about Google?"},                                # 5 tokens
    {"role": "assistant", "content": "Google Cloud Platform grew 28% to $9.4B quarterly revenue. Achieved profitability milestone with $900M operating income. Key wins in AI infrastructure with TPU v5. Announced Gemini integration across Workspace. Ruth Porat highlighted enterprise momentum..."},  # 650 tokens
    {"role": "user", "content": "And Amazon?"},                                       # 4 tokens
    {"role": "assistant", "content": "AWS revenue hit $24.2B, up 12% YoY..."},        # 600 tokens
]
# Total: ~3700 tokens, exceeds limit of 2000
```

**During Processing:**
```python
memory = ChatSummaryMemoryBuffer(token_limit=2000, llm=llm)

# Step 1: Split messages
# Recent (keep full): messages[6:10] = ~1260 tokens (Google, Amazon exchanges)
# Old (summarize): messages[0:6] = ~2420 tokens (Apple, Microsoft, comparison)

# Step 2: LLM summarizes old messages
summary_prompt = """
Summarize this conversation, preserving key facts:
- User asked about Apple Q4: $89.5B revenue, iPhone $46.2B, EPS $1.64
- User asked about Microsoft: Azure 29% growth, cloud $36.8B
- User asked to compare clouds: Azure enterprise-focused, AWS market leader, Google ML-focused
"""

# Step 3: LLM generates summary
summary = llm.complete(summary_prompt)
```

**Output:**
```python
# Compressed memory returned to agent:
[
    {
        "role": "system",
        "content": "Previous conversation summary: User inquired about tech earnings. "
                   "Apple Q4: $89.5B revenue (+6%), iPhone $46.2B, EPS $1.64. "
                   "Microsoft: Azure 29% growth, cloud $36.8B, gaming +61%. "
                   "Cloud comparison: Azure enterprise/AI focus, AWS market leader (32%), Google ML-focused."
    },  # ~80 tokens (was 2420!)
    {"role": "user", "content": "What about Google?"},
    {"role": "assistant", "content": "Google Cloud Platform grew 28% to $9.4B..."},
    {"role": "user", "content": "And Amazon?"},
    {"role": "assistant", "content": "AWS revenue hit $24.2B, up 12% YoY..."},
]
# Total: ~1340 tokens (under 2000 limit!)
```

---

**TreeSummarize** (hierarchical compression):
```python
class TreeSummarize(BaseSynthesizer):
    """
    Recursively merges chunks in tree structure:
    1. Repack chunks to fill context window
    2. Summarize each chunk
    3. Recursively summarize summaries until one chunk remains
    """
```

#### Example: TreeSummarize in Action

**Input:**
```python
# 8 SEC filing sections, each ~2000 tokens
chunks = [
    "10-K Section 1: Business Overview - Company manufactures semiconductors...[2000 tokens]",
    "10-K Section 2: Risk Factors - Supply chain dependencies, geopolitical...[2000 tokens]",
    "10-K Section 3: Financial Data - Revenue $45.2B, gross margin 58%...[2000 tokens]",
    "10-K Section 4: MD&A - Management discusses AI chip demand surge...[2000 tokens]",
    "10-K Section 5: Market Risk - Currency exposure, interest rate...[2000 tokens]",
    "10-K Section 6: Controls - SOX compliance, internal audit...[2000 tokens]",
    "10-K Section 7: Legal - Pending litigation, patent disputes...[2000 tokens]",
    "10-K Section 8: Exhibits - Material contracts, subsidiaries...[2000 tokens]",
]
# Total: 16,000 tokens - way too large!
# Query: "What are the key investment risks?"
```

**During Processing:**
```python
tree_summarizer = TreeSummarize(llm=llm, context_window=4000)

# === LEVEL 1: First pass - 4 groups of 2 ===

# Group A: Sections 1+2 → summarize together
summary_A = llm.complete("""
Summarize for investment risk analysis:
- Business: Semiconductor manufacturing, fabless model...
- Risks: Taiwan supply chain 78%, China revenue 25%...
""")  # Output: 400 tokens

# Group B: Sections 3+4 → summarize together
summary_B = llm.complete("""
Summarize for investment risk analysis:
- Financials: $45.2B revenue, 58% margins, but declining...
- MD&A: AI demand strong but consumer weak...
""")  # Output: 400 tokens

# Group C: Sections 5+6 → summarize together
summary_C = llm.complete(...)  # Output: 400 tokens

# Group D: Sections 7+8 → summarize together
summary_D = llm.complete(...)  # Output: 400 tokens

# === LEVEL 2: Second pass - 2 groups of 2 summaries ===

# Group AB: summary_A + summary_B
summary_AB = llm.complete("""
Combine these summaries focusing on investment risks:
[summary_A + summary_B = 800 tokens]
""")  # Output: 300 tokens

# Group CD: summary_C + summary_D
summary_CD = llm.complete(...)  # Output: 300 tokens

# === LEVEL 3: Final pass - combine all ===
final_summary = llm.complete("""
Final synthesis of investment risks:
[summary_AB + summary_CD = 600 tokens]
""")  # Output: 500 tokens
```

**Output:**
```python
# Tree structure visualization:
#
#     [Final: 500 tokens]
#           /    \
#    [AB: 300]  [CD: 300]
#      /   \      /    \
#   [A:400][B:400][C:400][D:400]
#    / \    / \    / \    / \
#   S1 S2  S3 S4  S5 S6  S7 S8  (original 2000 each)

final_answer = """
Key Investment Risks for NVIDIA (synthesized from 10-K):

1. **Supply Chain Concentration**: 78% of chips manufactured by TSMC in Taiwan,
   creating significant geopolitical and operational risk.

2. **Revenue Concentration**: China represents 25% of revenue; export restrictions
   already impacted $400M in Q4. Further restrictions possible.

3. **Margin Pressure**: Gross margins declined from 64% to 58% YoY due to
   new product ramp costs and competitive pricing pressure from AMD.

4. **Customer Concentration**: Top 5 customers = 42% of revenue.
   Loss of major cloud provider contract would significantly impact results.

5. **Litigation Risk**: 3 active patent disputes with estimated exposure of $2.1B.
   Qualcomm suit trial scheduled for Q2 2025.

6. **AI Market Cyclicality**: Current AI infrastructure boom may normalize;
   management acknowledges "demand visibility limited beyond 2 quarters."
"""
# 500 tokens (vs original 16,000 = 97% reduction!)
```

**Comparison to your approach:** Your `SummarizerMiddleware` is closest to `ChatSummaryMemoryBuffer`. Consider adding `TreeSummarize` for very large payloads like SEC filings.

---

### 3. Offloading - Waterfall Memory Architecture

LlamaIndex's modern `Memory` class implements a sophisticated waterfall system:

```python
class Memory(BaseMemory):
    token_limit: int = 30000
    token_flush_size: int = 3000  # Flush in chunks
    chat_history_token_ratio: float = 0.7
    memory_blocks: List[BaseMemoryBlock]  # Vector, fact, static storage
    sql_store: SQLAlchemyChatStore  # Persistent storage
```

#### Example: Waterfall Memory in Action

**Input:**
```python
# Long-running research agent conversation
# Current FIFO queue has 45,000 tokens of messages
fifo_queue = [
    # Messages 1-50: Historical research on various companies
    msg_1,   # "Research Apple's supply chain" + response (800 tokens)
    msg_2,   # "What about their India expansion?" + response (600 tokens)
    ...
    msg_50,  # "Compare all findings" + response (1200 tokens)
    # Messages 51-60: Current task - analyzing Microsoft
    msg_51,  # "Now research Microsoft Azure" + response (900 tokens)
    ...
    msg_60,  # "What's their AI strategy?" + response (750 tokens)
]

# Memory configuration
memory = Memory(
    token_limit=30000,
    token_flush_size=3000,
    chat_history_token_ratio=0.7,  # 70% for chat = 21,000 tokens max
    memory_blocks=[
        VectorMemoryBlock(embed_model=embed),   # For semantic retrieval
        FactExtractionBlock(llm=llm),           # Extract key facts
    ],
    sql_store=SQLAlchemyChatStore(uri="sqlite:///memory.db")
)

# Current state: 45,000 tokens in queue, limit is 21,000
```

**During Processing:**
```python
async def _manage_queue(self):
    current_tokens = count_tokens(self.fifo_queue)  # 45,000
    max_allowed = self.token_limit * self.chat_history_token_ratio  # 21,000

    if current_tokens > max_allowed:
        # Need to flush 45,000 - 21,000 = 24,000 tokens
        # Flush in chunks of 3,000

        while current_tokens > max_allowed:
            # Step 1: Collect oldest 3000 tokens worth of messages
            messages_to_flush = []
            flush_tokens = 0
            while flush_tokens < self.token_flush_size:
                oldest = self.fifo_queue.pop(0)  # Remove from queue
                messages_to_flush.append(oldest)
                flush_tokens += count_tokens(oldest)

            # Step 2: Archive to SQL (permanent storage)
            await self.sql_store.archive_messages(
                session_id=self.session_id,
                messages=messages_to_flush
            )
            # SQL now has: messages 1-8 (first 3000 tokens)

            # Step 3: Send to memory blocks (parallel)
            await asyncio.gather(
                # Vector store: embed for semantic retrieval
                self.memory_blocks[0].aput(messages_to_flush),
                # Fact extraction: pull out key facts
                self.memory_blocks[1].aput(messages_to_flush),
            )

            current_tokens = count_tokens(self.fifo_queue)

        # After 8 flush cycles: removed 24,000 tokens
```

**Output:**
```python
# FIFO Queue (hot - immediate context): 21,000 tokens
fifo_queue = [
    msg_35,  # "Analyze Samsung competition" + response
    ...
    msg_60,  # "What's their AI strategy?" + response (most recent)
]

# SQL Archive (cold - permanent storage): 24,000 tokens
sql_store.query("SELECT * FROM messages WHERE session_id=?")
# Returns: msg_1 through msg_34

# Vector Store (warm - semantic retrieval): embeddings for msg_1-34
vector_store.similarity_search("Apple supply chain Taiwan")
# Returns: msg_1, msg_5, msg_12 (relevant historical context)

# Fact Store (extracted knowledge): key facts from msg_1-34
fact_store.get_facts()
# Returns:
[
    {"entity": "Apple", "fact": "78% chips from TSMC Taiwan", "source": "msg_1"},
    {"entity": "Apple", "fact": "India revenue doubled YoY", "source": "msg_2"},
    {"entity": "Samsung", "fact": "3nm process ahead of TSMC", "source": "msg_35"},
    ...
]

# When agent needs historical context:
relevant_history = await memory.aget_all()
# Returns:
{
    "recent_messages": fifo_queue[-10:],           # Last 10 messages (full)
    "relevant_past": vector_store.search(query),   # Semantically similar old msgs
    "extracted_facts": fact_store.get_facts(),     # Key facts
    "summary": "Previously researched: Apple supply chain, India expansion..."
}
```

**Comparison to your approach:** Your `OffloadMiddleware` with Redis is simpler but similar in concept. LlamaIndex's approach is more sophisticated with multiple "memory blocks" (vector store, fact store, etc.) and automatic waterfall management.

---

### 4. Token Tracking - Callback-Based

```python
class TokenCountingHandler(BaseCallbackHandler):
    llm_token_counts: List[TokenCountingEvent] = []

    def on_event_end(self, event_type: CBEventType, payload: Dict):
        if event_type == CBEventType.LLM:
            self.llm_token_counts.append(
                get_llm_token_counts(self._token_counter, payload)
            )

    @property
    def total_llm_token_count(self) -> int:
        return sum([x.total_token_count for x in self.llm_token_counts])
```

#### Example: Token Counting Handler in Action

**Input:**
```python
# Multi-step agent task
agent_task = "Research NVIDIA, AMD, and Intel, then compare their AI strategies"

# Set up token tracking
token_handler = TokenCountingHandler(tokenizer=tiktoken.get_encoding("cl100k_base"))
callback_manager = CallbackManager([token_handler])

agent = OpenAIAgent.from_tools(
    tools=[search_tool, analyze_tool],
    callback_manager=callback_manager
)
```

**During Processing:**
```python
# Step 1: Agent calls LLM to plan
# Event: LLM call with 500 input tokens, 200 output tokens
token_handler.on_event_end(CBEventType.LLM, {
    "messages": [...],  # 500 tokens
    "response": "I'll research each company using the search tool..."  # 200 tokens
})
token_handler.llm_token_counts.append(TokenCountingEvent(
    prompt_tokens=500, completion_tokens=200, total=700
))

# Step 2: Agent searches for NVIDIA
# Event: Tool call (no LLM tokens)

# Step 3: Agent processes NVIDIA results
# Event: LLM call with 2000 input tokens, 500 output tokens
token_handler.on_event_end(CBEventType.LLM, {...})
token_handler.llm_token_counts.append(TokenCountingEvent(
    prompt_tokens=2000, completion_tokens=500, total=2500
))

# Step 4-7: Similar for AMD and Intel...

# Step 8: Agent synthesizes comparison
# Event: LLM call with 4000 input tokens, 800 output tokens
token_handler.on_event_end(CBEventType.LLM, {...})
token_handler.llm_token_counts.append(TokenCountingEvent(
    prompt_tokens=4000, completion_tokens=800, total=4800
))
```

**Output:**
```python
# After agent completes:
print(token_handler.total_llm_token_count)
# Output: 15,200 tokens

print(token_handler.llm_token_counts)
# Output:
[
    TokenCountingEvent(step="planning", prompt=500, completion=200, total=700),
    TokenCountingEvent(step="nvidia_analysis", prompt=2000, completion=500, total=2500),
    TokenCountingEvent(step="amd_analysis", prompt=2100, completion=450, total=2550),
    TokenCountingEvent(step="intel_analysis", prompt=1900, completion=480, total=2380),
    TokenCountingEvent(step="comparison", prompt=4000, completion=800, total=4800),
    TokenCountingEvent(step="final_response", prompt=1500, completion=670, total=2170),
]

# Cost calculation
cost = (token_handler.prompt_tokens * 0.01 + token_handler.completion_tokens * 0.03) / 1000
print(f"Estimated cost: ${cost:.4f}")
# Output: Estimated cost: $0.2120

# Budget alert
if token_handler.total_llm_token_count > 10000:
    print("WARNING: Token budget exceeded, triggering compression...")
```

**Comparison:** Similar to your `TokenManagerMiddleware` but implemented as a callback handler rather than middleware.

---

### 5. Per-Step Configuration

LlamaIndex uses response synthesizer selection per query:

```python
# Different strategies per use case
Generation(llm=llm)        # Single pass
Refine(llm=llm)            # Iterative refinement
TreeSummarize(llm=llm)     # Hierarchical
CompactAndRefine(llm=llm)  # Combined
```

#### Example: Per-Step Synthesizer Selection

**Input:**
```python
# Different queries require different strategies
queries = [
    ("What is NVIDIA's stock price?", "simple"),           # Simple fact
    ("Summarize this 50-page 10-K filing", "large_doc"),   # Large document
    ("Analyze sentiment across 100 news articles", "multi_doc"),  # Many docs
]

# Retrieved context varies by query
contexts = {
    "simple": ["NVIDIA (NVDA) closed at $875.32 on Jan 28, 2025"],  # 20 tokens
    "large_doc": [chunk_1, chunk_2, ..., chunk_50],  # 50,000 tokens
    "multi_doc": [article_1, article_2, ..., article_100],  # 80,000 tokens
}
```

**During Processing:**
```python
from llama_index.core.response_synthesizers import get_response_synthesizer

def select_synthesizer(query_type: str, context_size: int):
    if query_type == "simple" or context_size < 2000:
        # Simple: just generate directly
        return get_response_synthesizer(
            response_mode="generation",
            llm=llm
        )

    elif query_type == "large_doc" or context_size < 30000:
        # Medium: compact then refine
        return get_response_synthesizer(
            response_mode="compact_and_refine",
            llm=llm,
            text_qa_template=SEC_FILING_TEMPLATE,  # Domain-specific!
        )

    else:
        # Large: hierarchical tree summarization
        return get_response_synthesizer(
            response_mode="tree_summarize",
            llm=llm,
            summary_template=NEWS_SUMMARY_TEMPLATE,
        )

# Process each query with appropriate synthesizer
for query, query_type in queries:
    context = contexts[query_type]
    synthesizer = select_synthesizer(query_type, count_tokens(context))
    response = synthesizer.synthesize(query, nodes=context)
```

**Output:**
```python
# Query 1: Simple fact (Generation mode)
# Input: 20 tokens context + 10 token query
# Processing: Single LLM call
# Output: "NVIDIA's current stock price is $875.32"
# Tokens used: 150

# Query 2: Large 10-K (CompactAndRefine mode)
# Input: 50,000 tokens across 50 chunks
# Processing:
#   - Compact: Pack chunks to fit context window (5 groups)
#   - Refine: Iteratively build answer across groups
# Output: "Key findings from NVIDIA 10-K: Revenue grew 122%..."
# Tokens used: 8,500

# Query 3: 100 news articles (TreeSummarize mode)
# Input: 80,000 tokens across 100 articles
# Processing:
#   - Level 1: Summarize groups of 10 articles (10 summaries)
#   - Level 2: Summarize groups of 5 summaries (2 summaries)
#   - Level 3: Final synthesis
# Output: "Sentiment analysis across 100 articles: 67% positive..."
# Tokens used: 12,000
```

**Comparison:** Your `applies_to` parameter is more explicit and flexible. LlamaIndex requires configuring different synthesizers.

---

## LangChain Approach

### 1. Context Management - Agent Limits

LangChain uses iteration limits rather than explicit context management:

```python
class AgentExecutor:
    max_iterations: int = 15
    max_execution_time: Optional[float] = None

    # Token counting via LLM method
    llm.get_num_tokens_from_messages(messages)
```

#### Example: Agent Iteration Limits

**Input:**
```python
# Complex research task that could spiral
agent = AgentExecutor(
    agent=research_agent,
    tools=[web_search, document_reader, calculator],
    max_iterations=10,          # Stop after 10 tool calls
    max_execution_time=120.0,   # Or after 2 minutes
)

task = "Find all SEC filings for FAANG companies from 2024, extract revenue, and calculate growth rates"
```

**During Processing:**
```python
# Iteration 1: Agent plans
action = AgentAction(tool="web_search", input="Apple 10-K 2024 SEC filing")
# Token count: 800

# Iteration 2: Process Apple results
action = AgentAction(tool="document_reader", input="apple_10k.pdf")
# Token count: 3,500 (cumulative)

# Iteration 3: Extract Apple revenue
action = AgentAction(tool="calculator", input="89.5B - 83.4B / 83.4B * 100")
# Token count: 4,200

# ... iterations 4-9: Same for Amazon, Meta, Netflix, Google ...

# Iteration 10: Agent tries to continue but hits limit
# Token count: 45,000

if iteration_count >= self.max_iterations:
    return AgentFinish(
        return_values={"output": "Reached max iterations. Partial results: ..."},
        log="Stopped due to iteration limit"
    )
```

**Output:**
```python
# Agent stopped at iteration 10
result = {
    "output": """
    Partial Analysis (stopped at iteration limit):

    Completed:
    - Apple: $89.5B revenue (+7.3% YoY)
    - Amazon: $143.1B revenue (+11.2% YoY)
    - Meta: $40.1B revenue (+23.8% YoY)
    - Netflix: $9.8B revenue (+15.1% YoY)

    Not completed:
    - Google (Alphabet): Analysis in progress when limit reached

    Note: Increase max_iterations to complete full analysis.
    """,
    "iterations_used": 10,
    "tokens_consumed": 45000,
    "execution_time": 87.3,  # seconds
}
```

---

### 2. Summarization - Memory Classes

**ConversationSummaryBufferMemory**:
```python
class ConversationSummaryBufferMemory(BaseChatMemory):
    max_token_limit: int = 2000
    moving_summary_buffer: str = ""

    def prune(self) -> None:
        """Prune buffer if exceeds max_token_limit"""
```

#### Example: Moving Summary Buffer in Action

**Input:**
```python
# Long conversation about investment research
memory = ConversationSummaryBufferMemory(
    llm=llm,
    max_token_limit=2000,
    return_messages=True
)

# Conversation so far (simplified)
messages = [
    HumanMessage("What's Apple's P/E ratio?"),
    AIMessage("Apple's P/E ratio is 28.5, which is...detailed 500 token response..."),
    HumanMessage("Compare to Microsoft"),
    AIMessage("Microsoft's P/E is 35.2, compared to Apple's 28.5...detailed 600 token response..."),
    HumanMessage("What about growth rates?"),
    AIMessage("Apple's 5Y growth CAGR is 8.2%, Microsoft is 12.1%...detailed 700 token response..."),
    HumanMessage("Factor in their debt levels"),
    AIMessage("Apple's debt-to-equity is 1.87, Microsoft is 0.35...detailed 650 token response..."),
    # New message comes in:
    HumanMessage("Now summarize which is a better investment"),
]
# Total tokens: ~2700 (exceeds 2000 limit)
```

**During Processing:**
```python
def prune(self):
    buffer = self.chat_memory.messages
    curr_buffer_length = self.llm.get_num_tokens_from_messages(buffer)
    # curr_buffer_length = 2700, max = 2000

    if curr_buffer_length > self.max_token_limit:
        pruned_memory = []

        # Pop oldest messages until under limit
        while curr_buffer_length > self.max_token_limit:
            oldest = buffer.pop(0)  # Remove P/E ratio exchange
            pruned_memory.append(oldest)
            curr_buffer_length = self.llm.get_num_tokens_from_messages(buffer)

        # pruned_memory now has: P/E ratio Q&A, Microsoft comparison Q&A
        # buffer now has: growth rates Q&A, debt levels Q&A, new question

        # Update the rolling summary (KEY DIFFERENCE: incremental!)
        self.moving_summary_buffer = self.predict_new_summary(
            messages=pruned_memory,
            existing_summary=self.moving_summary_buffer  # Build on previous!
        )
```

**Output:**
```python
# BEFORE pruning:
memory.buffer = [all 9 messages]  # 2700 tokens
memory.moving_summary_buffer = ""

# AFTER pruning:
memory.moving_summary_buffer = """
Investment comparison context:
- Apple P/E: 28.5 (lower, more value-oriented)
- Microsoft P/E: 35.2 (premium valuation)
- User interested in relative valuation metrics
"""  # ~60 tokens

memory.buffer = [
    HumanMessage("What about growth rates?"),
    AIMessage("Apple's 5Y growth CAGR is 8.2%, Microsoft is 12.1%..."),
    HumanMessage("Factor in their debt levels"),
    AIMessage("Apple's debt-to-equity is 1.87, Microsoft is 0.35..."),
    HumanMessage("Now summarize which is a better investment"),
]  # ~1400 tokens

# Total context sent to LLM:
full_context = f"""
Previous conversation summary:
{memory.moving_summary_buffer}

Recent messages:
{format_messages(memory.buffer)}
"""  # ~1500 tokens (under 2000 limit!)

# CRITICAL INSIGHT: Next pruning will UPDATE the summary, not replace it
# If growth rates get pruned next:
memory.moving_summary_buffer = """
Investment comparison context:
- Apple P/E: 28.5 (lower, more value-oriented)
- Microsoft P/E: 35.2 (premium valuation)
- Apple growth CAGR: 8.2% (slower)
- Microsoft growth CAGR: 12.1% (faster)
- User building comprehensive comparison
"""  # Still compact, but accumulates knowledge!
```

**Comparison:** Similar to your `SummarizerMiddleware`. The `moving_summary_buffer` concept is interesting - maintaining a rolling summary instead of re-summarizing everything.

---

### 3. Offloading - Document Compression

LangChain focuses on RAG context compression:

```python
class BaseDocumentCompressor(ABC):
    @abstractmethod
    def compress_documents(
        self,
        documents: Sequence[Document],
        query: str,
    ) -> Sequence[Document]:
        """Compress documents based on query relevance"""
```

#### Example: Document Compression in Action

**Input:**
```python
# RAG retrieval returns too many documents
query = "What are NVIDIA's AI chip competitive advantages?"

# Retriever returns 20 documents, each ~500 tokens = 10,000 tokens
retrieved_docs = retriever.get_relevant_documents(query)
# [
#     Document("NVIDIA H100 specs: 80GB HBM3, 3.35TB/s bandwidth..."),
#     Document("AMD MI300X comparison: 192GB HBM3, competitive but..."),
#     Document("NVIDIA CUDA ecosystem has 4M+ developers..."),
#     Document("Intel Gaudi3 announcement: targeting inference..."),
#     Document("NVIDIA Q4 earnings call transcript page 1..."),
#     ... 15 more documents ...
# ]
```

**During Processing:**
```python
from langchain.retrievers.document_compressors import LLMChainExtractor

# Compressor extracts only query-relevant content
compressor = LLMChainExtractor.from_llm(llm)

compressed_docs = compressor.compress_documents(
    documents=retrieved_docs,
    query=query
)

# For each document, LLM extracts relevant portions:
# Document 1: "NVIDIA H100 specs..." (500 tokens)
# LLM prompt: "Extract parts relevant to 'NVIDIA AI chip competitive advantages'"
# LLM output: "H100: 80GB HBM3, 3.35TB/s bandwidth - 3x faster than A100"
# Compressed: 25 tokens

# Document 2: "AMD MI300X comparison..." (500 tokens)
# LLM output: "" (not about NVIDIA advantages, filtered out)
# Compressed: 0 tokens (removed!)

# Document 3: "NVIDIA CUDA ecosystem..." (500 tokens)
# LLM output: "CUDA ecosystem advantage: 4M+ developers, extensive libraries"
# Compressed: 15 tokens
```

**Output:**
```python
# Original: 20 documents, 10,000 tokens
# Compressed: 8 documents, 450 tokens

compressed_docs = [
    Document(
        page_content="H100: 80GB HBM3, 3.35TB/s bandwidth - 3x faster than A100",
        metadata={"source": "nvidia_specs.pdf", "relevance": 0.95}
    ),
    Document(
        page_content="CUDA ecosystem advantage: 4M+ developers, extensive libraries",
        metadata={"source": "developer_report.pdf", "relevance": 0.89}
    ),
    Document(
        page_content="NVLink 4.0 enables 900GB/s GPU-to-GPU, critical for large models",
        metadata={"source": "nvidia_specs.pdf", "relevance": 0.87}
    ),
    Document(
        page_content="Transformer Engine: automatic FP8 precision, 2x inference speed",
        metadata={"source": "h100_whitepaper.pdf", "relevance": 0.85}
    ),
    # ... 4 more compressed documents ...
]

# Now fits easily in context for final LLM call!
final_prompt = f"""
Based on these key points about NVIDIA's AI chip advantages:
{format_docs(compressed_docs)}

Answer: What are NVIDIA's AI chip competitive advantages?
"""
# Total: ~600 tokens (was 10,000!)
```

**Comparison:** Your `OffloadMiddleware` goes further by storing in Redis. LangChain's approach is more about trimming than offloading.

---

### 4. Token Tracking - Usage Callbacks

```python
class UsageMetadataCallbackHandler(BaseCallbackHandler):
    """Thread-safe per-model token aggregation"""
```

#### Example: Usage Metadata Tracking

**Input:**
```python
# Multi-model agent with different LLMs for different tasks
from langchain_core.callbacks import UsageMetadataCallbackHandler

usage_handler = UsageMetadataCallbackHandler()

# Agent uses different models
planning_llm = ChatOpenAI(model="gpt-4", callbacks=[usage_handler])
execution_llm = ChatOpenAI(model="gpt-3.5-turbo", callbacks=[usage_handler])
summary_llm = ChatAnthropic(model="claude-3-sonnet", callbacks=[usage_handler])
```

**During Processing:**
```python
# Agent executes multi-step task

# Step 1: Planning with GPT-4
planning_response = planning_llm.invoke("Plan research for NVIDIA analysis")
# Callback fired:
usage_handler.on_llm_end(LLMResult(
    generations=[[Generation(
        message=AIMessage(
            content="I'll analyze NVIDIA in 5 steps...",
            usage_metadata={"input_tokens": 150, "output_tokens": 200}
        )
    )]]
))

# Step 2-4: Execution with GPT-3.5-turbo (cheaper)
for step in ["search", "extract", "calculate"]:
    execution_llm.invoke(f"Execute {step}...")
    # Each callback updates usage_by_model["gpt-3.5-turbo"]

# Step 5: Summary with Claude
summary_llm.invoke("Synthesize findings into investment thesis...")
# Callback updates usage_by_model["claude-3-sonnet"]
```

**Output:**
```python
# Aggregated usage across all models:
print(usage_handler.total_usage)
# UsageMetadata(
#     input_tokens=4500,
#     output_tokens=2100,
#     total_tokens=6600
# )

print(usage_handler.usage_by_model)
# {
#     "gpt-4": UsageMetadata(input=150, output=200, total=350),
#     "gpt-3.5-turbo": UsageMetadata(input=3200, output=1400, total=4600),
#     "claude-3-sonnet": UsageMetadata(input=1150, output=500, total=1650),
# }

# Cost breakdown by model:
costs = {
    "gpt-4": 350 * 0.00003 + 200 * 0.00006,        # $0.0225
    "gpt-3.5-turbo": 3200 * 0.0000005 + 1400 * 0.0000015,  # $0.0037
    "claude-3-sonnet": 1150 * 0.000003 + 500 * 0.000015,   # $0.0110
}
total_cost = sum(costs.values())  # $0.0372

print(f"Total cost: ${total_cost:.4f}")
print(f"Most expensive model: gpt-4 (60% of cost for 5% of tokens)")
```

---

### 5. Per-Step Configuration - RunnableConfig

```python
from langchain_core.runnables import RunnableConfig

# Different config per step
config1 = RunnableConfig(
    tags=["gather_sec"],
    callbacks=[CustomCallback()],
    max_concurrency=2,
)
```

#### Example: RunnableConfig Per-Step

**Input:**
```python
# Research pipeline with different configs per step
from langchain_core.runnables import RunnableConfig, RunnableParallel

# Step 1 config: SEC filings (needs summarization)
sec_config = RunnableConfig(
    tags=["gather_sec", "needs_compression"],
    callbacks=[
        TokenTracker(),
        SECCompressionCallback(max_tokens=4000),
    ],
    metadata={"source": "SEC EDGAR"},
    max_concurrency=2,  # Rate limit for SEC
)

# Step 2 config: News articles (different compression)
news_config = RunnableConfig(
    tags=["gather_news", "needs_compression"],
    callbacks=[
        TokenTracker(),
        NewsCompressionCallback(max_tokens=2000),
    ],
    metadata={"source": "News APIs"},
    max_concurrency=5,  # Higher concurrency OK
)

# Step 3 config: Final synthesis (no compression needed)
synthesis_config = RunnableConfig(
    tags=["synthesis", "final"],
    callbacks=[TokenTracker()],
    configurable={"temperature": 0.3},  # More deterministic
)
```

**During Processing:**
```python
# Execute pipeline with different configs per step

# Step 1: Gather SEC filings with sec_config
sec_results = await sec_chain.ainvoke(
    {"query": "NVIDIA 10-K 2024"},
    config=sec_config  # Uses SEC-specific compression
)
# SECCompressionCallback intercepts output:
# - Original: 50,000 tokens from 10-K
# - Compressed: 4,000 tokens (key financials, risks, MD&A summary)

# Step 2: Gather news with news_config (parallel to step 1!)
news_results = await news_chain.ainvoke(
    {"query": "NVIDIA AI chips news"},
    config=news_config  # Uses news-specific compression
)
# NewsCompressionCallback intercepts output:
# - Original: 30,000 tokens from 50 articles
# - Compressed: 2,000 tokens (headlines, key quotes, sentiment)

# Step 3: Synthesize with synthesis_config
final_report = await synthesis_chain.ainvoke(
    {
        "sec_data": sec_results,      # 4,000 tokens
        "news_data": news_results,    # 2,000 tokens
        "query": "Investment thesis for NVIDIA"
    },
    config=synthesis_config  # No compression, low temperature
)
```

**Output:**
```python
# Each step tracked separately via tags:
token_tracker.get_by_tag("gather_sec")
# {"input": 50000, "output": 4000, "compression_ratio": 0.08}

token_tracker.get_by_tag("gather_news")
# {"input": 30000, "output": 2000, "compression_ratio": 0.067}

token_tracker.get_by_tag("synthesis")
# {"input": 6000, "output": 1500, "compression_ratio": 1.0}  # No compression

# Total pipeline:
# Input to LLM: 6,000 tokens (was 80,000 without compression!)
# Compression saved: 74,000 tokens = ~$2.22 at GPT-4 prices

final_report = """
NVIDIA Investment Thesis:

Based on SEC 10-K analysis and recent news sentiment:

1. Financial Strength: 122% YoY revenue growth, 78% gross margins
2. Competitive Moat: CUDA ecosystem with 4M+ developers
3. Growth Drivers: H200 launch, Blackwell architecture in 2025
4. Risks: Taiwan supply chain (78% TSMC), China export restrictions
5. Valuation: P/E of 65 reflects growth expectations

Recommendation: Strong Buy with 18-month price target of $1,200
"""
```

**Comparison:** This is similar to your `applies_to` but requires manual config per invoke rather than declarative middleware registration.

---

## Comparison Matrix

| Feature | Your Middleware | LlamaIndex | LangChain |
|---------|-----------------|------------|-----------|
| **Architecture** | Middleware chain | Callbacks + Memory classes | Callbacks + RunnableConfig |
| **Per-step targeting** | `applies_to` parameter | Synthesizer selection | RunnableConfig per invoke |
| **Summarization** | `SummarizerMiddleware` | `ChatSummaryMemoryBuffer`, `TreeSummarize` | `ConversationSummaryBufferMemory` |
| **Offloading** | Redis storage | SQL + Memory Blocks (waterfall) | Document compression only |
| **Token tracking** | `TokenManagerMiddleware` | `TokenCountingHandler` callback | `UsageMetadataCallbackHandler` |
| **Domain prompts** | Custom prompts per domain | Configurable `summarize_prompt` | Configurable prompts |
| **Auto-compression trigger** | Token budget threshold | `token_limit` in memory | `max_token_limit` in memory |

---

## Recommendations for Your Framework

### 1. Consider Adding: Hierarchical Summarization

LlamaIndex's `TreeSummarize` pattern is powerful for very large contexts:

```python
class HierarchicalSummarizerMiddleware(SummarizerMiddleware):
    """Tree-based summarization for very large payloads"""

    def summarize(self, chunks: List[str]) -> str:
        # Recursively summarize in tree structure
        while len(chunks) > 1:
            packed = self.repack(chunks, self.max_tokens_per_chunk)
            chunks = [self.summarize_single(c) for c in packed]
        return chunks[0]
```

#### Example Implementation:

**Input:**
```python
# Your current middleware with hierarchical option
ao.use(HierarchicalSummarizerMiddleware(
    max_tokens=4000,
    applies_to=["gather_sec"],
    strategy="tree",  # NEW: "flat" (current) or "tree" (hierarchical)
    levels=3,         # Max tree depth
))

# Input: 100,000 token SEC filing
sec_filing = "..." # 100,000 tokens
```

**Output:**
```python
# Level 1: Split into 25 chunks of 4000, summarize each → 25 × 400 = 10,000 tokens
# Level 2: Group into 5 groups of 5, summarize each → 5 × 500 = 2,500 tokens
# Level 3: Summarize all 5 → 1 × 800 = 800 tokens

# Final output: 800 tokens (99.2% reduction!)
```

---

### 2. Consider Adding: Rolling Summary Buffer

LangChain's `moving_summary_buffer` pattern:

```python
class RollingSummarizerMiddleware(SummarizerMiddleware):
    """Maintains rolling summary instead of re-summarizing"""

    moving_summary: str = ""

    def process(self, output: str) -> str:
        if self.exceeds_limit(output):
            # Only summarize new content, append to existing summary
            self.moving_summary = self.update_summary(
                self.moving_summary, output
            )
            return self.moving_summary
        return output
```

#### Example Implementation:

**Input:**
```python
ao.use(RollingSummarizerMiddleware(
    max_tokens=4000,
    applies_to=["gather_news"],
    strategy="rolling",  # NEW: incremental updates
))

# Iteration 1: First batch of news
news_batch_1 = "50 articles about NVIDIA earnings..."  # 15,000 tokens

# Iteration 2: Second batch
news_batch_2 = "30 more articles about AMD response..."  # 10,000 tokens
```

**Output:**
```python
# After iteration 1:
moving_summary = "NVIDIA beat Q4 estimates. Revenue $22.1B (+265%). AI demand strong."
# 20 tokens (was 15,000)

# After iteration 2 (INCREMENTAL update, not full re-summarization):
moving_summary = """
NVIDIA beat Q4 estimates. Revenue $22.1B (+265%). AI demand strong.
AMD responded with MI300X pricing cut. Competitive pressure increasing.
"""
# 35 tokens total (was 25,000 cumulative)

# Benefit: No need to re-summarize iteration 1 content!
```

---

### 3. Consider Adding: Memory Block Architecture

LlamaIndex's waterfall with multiple storage backends:

```python
class MultiTierOffloadMiddleware(OffloadMiddleware):
    """Waterfall to multiple storage tiers"""

    tiers: List[StorageBackend] = [
        InMemoryCache(max_tokens=5000),     # Hot
        RedisCache(max_tokens=50000),       # Warm
        VectorStore(),                       # Cold (for retrieval)
    ]

    def offload(self, data: str, priority: int):
        for tier in self.tiers:
            if tier.has_capacity():
                return tier.store(data)
        # Waterfall to next tier
```

#### Example Implementation:

**Input:**
```python
ao.use(MultiTierOffloadMiddleware(
    applies_to=["gather_*"],
    tiers=[
        {"type": "memory", "max_tokens": 5000},    # Hot: recent, frequent
        {"type": "redis", "max_tokens": 50000},     # Warm: session data
        {"type": "postgres", "max_tokens": None},   # Cold: archival
        {"type": "pinecone", "for_retrieval": True} # Semantic: for RAG
    ]
))

# Large research session
data_stream = [
    ("nvidia_10k", 50000, "high"),    # Recent SEC filing
    ("amd_10k", 45000, "medium"),     # Earlier SEC filing
    ("old_research", 30000, "low"),   # Historical data
]
```

**Output:**
```python
# Tier allocation:
memory_tier = {
    "nvidia_10k_summary": "Key: $22.1B revenue, 78% margins...",  # 500 tokens
}  # Hot access, in-process

redis_tier = {
    "nvidia_10k_full": "",  # 50,000 tokens stored
    "amd_10k_summary": "Key: MI300X launch, 192GB HBM3...",  # 400 tokens
}  # Warm access, fast retrieval

postgres_tier = {
    "amd_10k_full": "",        # 45,000 tokens archived
    "old_research": "",        # 30,000 tokens archived
}  # Cold storage, slower retrieval

pinecone_tier = {
    # Embeddings for semantic search
    "nvidia_10k_chunks": ["emb_1", "emb_2", ...],  # For RAG retrieval
    "amd_10k_chunks": ["emb_3", "emb_4", ...],
}  # Semantic retrieval when needed

# Agent context only sees:
context = {
    "nvidia_10k_summary": "Key: $22.1B revenue, 78% margins...",
    "amd_10k_summary": "Key: MI300X launch, 192GB HBM3...",
    "redis_refs": ["abc123"],      # Can hydrate if needed
    "can_retrieve": ["nvidia", "amd", "old_research"]  # Semantic search available
}  # ~1000 tokens instead of 125,000!
```

---

### 4. Strengthen: Your Per-Step Pattern

Your `applies_to` pattern is actually more elegant than both frameworks. Consider adding:

```python
# Add glob pattern support
ao.use(SummarizerMiddleware(
    max_tokens=4000,
    applies_to=["gather_*"],      # Glob patterns
    excludes=["gather_final"],    # Explicit exclusions
))

# Add condition-based application
ao.use(TokenManagerMiddleware(
    applies_when=lambda step: step.output_tokens > 2000,
))
```

#### Example Implementation:

**Input:**
```python
# Enhanced applies_to with patterns and conditions
ao.use(SummarizerMiddleware(
    max_tokens=4000,
    applies_to=["gather_*", "research_*"],   # Match multiple patterns
    excludes=["gather_final", "*_summary"],   # Exclude patterns
    applies_when=lambda step: (
        step.output_tokens > 2000 and
        step.source_type in ["sec", "news", "research"]
    ),
    priority=10,  # Higher priority = runs first
))

# Pipeline steps
steps = [
    Step("gather_sec", output_tokens=50000, source_type="sec"),      # ✓ Matches
    Step("gather_news", output_tokens=15000, source_type="news"),    # ✓ Matches
    Step("gather_final", output_tokens=3000, source_type="sec"),     # ✗ Excluded
    Step("calculate_metrics", output_tokens=500, source_type="calc"), # ✗ Too small
    Step("research_competitors", output_tokens=8000, source_type="research"), # ✓ Matches
]
```

**Output:**
```python
# Middleware application results:
step_results = {
    "gather_sec": {
        "original_tokens": 50000,
        "summarized_tokens": 3800,
        "middleware_applied": ["SummarizerMiddleware"],
    },
    "gather_news": {
        "original_tokens": 15000,
        "summarized_tokens": 2500,
        "middleware_applied": ["SummarizerMiddleware"],
    },
    "gather_final": {
        "original_tokens": 3000,
        "summarized_tokens": 3000,  # Unchanged - excluded by name
        "middleware_applied": [],
    },
    "calculate_metrics": {
        "original_tokens": 500,
        "summarized_tokens": 500,  # Unchanged - below threshold
        "middleware_applied": [],
    },
    "research_competitors": {
        "original_tokens": 8000,
        "summarized_tokens": 2200,
        "middleware_applied": ["SummarizerMiddleware"],
    },
}

# Total context: 3800 + 2500 + 3000 + 500 + 2200 = 12,000 tokens
# (vs 76,500 without middleware = 84% reduction)
```

---

### 5. Add: Token Budget Propagation

LlamaIndex reserves tokens for output. Consider:

```python
class TokenManagerMiddleware:
    context_window: int = 128000
    reserved_for_output: int = 4000
    reserved_for_system: int = 2000

    @property
    def available_for_content(self) -> int:
        return self.context_window - self.reserved_for_output - self.reserved_for_system

    def should_compress(self, current_tokens: int) -> bool:
        return current_tokens > self.available_for_content * 0.8  # 80% threshold
```

#### Example Implementation:

**Input:**
```python
ao.use(TokenManagerMiddleware(
    context_window=128000,
    reserved_for_output=8000,    # Max expected response
    reserved_for_system=3000,    # System prompt + tools
    reserved_for_history=10000,  # Conversation history
    warning_threshold=0.8,       # Warn at 80%
    critical_threshold=0.95,     # Force compression at 95%
))

# Current agent state
agent_state = {
    "system_prompt": 2500,       # tokens
    "tools_schema": 500,         # tokens
    "conversation_history": 8000, # tokens
    "current_step_output": 95000, # tokens (huge SEC filing!)
}
# Total: 106,000 tokens
```

**During Processing:**
```python
def manage_budget(self, agent_state):
    # Calculate budget
    total_used = sum(agent_state.values())  # 106,000
    available = self.available_for_content  # 128000 - 8000 - 3000 = 117,000

    usage_ratio = total_used / available  # 0.906 (90.6%)

    if usage_ratio > self.critical_threshold:  # > 95%
        # FORCE compression
        return CompressionAction(
            type="force",
            target="current_step_output",
            target_tokens=available * 0.7,  # Compress to 70% of available
            message="Critical: forcing compression to avoid context overflow"
        )

    elif usage_ratio > self.warning_threshold:  # > 80%
        # RECOMMEND compression
        return CompressionAction(
            type="recommend",
            target="current_step_output",
            target_tokens=available * 0.6,
            message="Warning: approaching context limit, compression recommended"
        )

    return None  # No action needed
```

**Output:**
```python
# Budget analysis output:
budget_report = {
    "context_window": 128000,
    "allocated": {
        "system": 3000,
        "output_reserved": 8000,
        "history": 10000,
        "content": 107000,  # Available for step outputs
    },
    "current_usage": {
        "system_prompt": 2500,
        "tools_schema": 500,
        "history": 8000,
        "step_outputs": 95000,
    },
    "total_used": 106000,
    "available_remaining": 11000,  # Only 11K left before output!
    "usage_percentage": 90.6,
    "status": "WARNING",
    "action": {
        "type": "recommend_compression",
        "target": "step_outputs",
        "current_tokens": 95000,
        "target_tokens": 64200,  # 60% of 107K available
        "compression_needed": 30800,  # Need to trim ~32%
    }
}

# After compression:
final_state = {
    "system_prompt": 2500,
    "tools_schema": 500,
    "history": 8000,
    "step_outputs": 62000,  # Compressed from 95K
}
# Total: 73,000 tokens (57% of context, leaving room for output)
```

---

## Key Insights

1. **LlamaIndex is more sophisticated** for memory management with its waterfall architecture and multiple memory blocks, but your middleware approach is simpler and more explicit.

2. **LangChain is more callback-oriented**, which gives flexibility but requires more boilerplate for per-step configuration. Your `applies_to` pattern is cleaner.

3. **Neither framework has explicit Redis offloading** like your `OffloadMiddleware` - this is a differentiator for your framework.

4. **Domain-specific prompts** (your feature) is supported by both but not as first-class. This is valuable for SEC filings, news, etc.

5. **Your middleware chain** (`TokenManager → Summarizer → Offload`) is a good pattern that combines aspects of both frameworks.

---

## Missing from Both Frameworks (Opportunities)

1. **Semantic chunking for summarization** - Neither does smart chunking based on content structure
2. **Cost-aware compression** - Choosing compression strategy based on API costs
3. **Differential compression** - Only compress what changed since last call
4. **Compression quality metrics** - Measuring information loss during summarization

---

# PRIORITIZED IMPLEMENTATION GUIDE

Based on your current framework capabilities vs. LlamaIndex/LangChain patterns, here's what to implement, ranked by **impact × ease of implementation**.

## Priority Matrix

| Feature | Impact | Effort | Priority | Status in Your Framework |
|---------|--------|--------|----------|--------------------------|
| **Glob patterns for `applies_to`** | High | Low | 🔴 P0 | Missing - only exact matches |
| **Token budget reservation** | High | Low | 🔴 P0 | Partial - have thresholds, not reservations |
| **True Tree Summarization** | High | Medium | 🟠 P1 | Missing - MAP_REDUCE is flat |
| **Rolling Summary Buffer** | Medium | Low | 🟠 P1 | Missing |
| **Query-aware compression** | High | Medium | 🟠 P1 | Missing |
| **Condition-based `applies_when`** | Medium | Low | 🟢 P2 | Missing |
| **Multi-tier waterfall storage** | Medium | High | 🟢 P2 | Have Redis only |
| **Compression quality metrics** | Low | Medium | 🔵 P3 | Missing |

---

## 🔴 P0: Implement Now (High Impact, Low Effort)

### 1. Glob Patterns for `applies_to`

**Why**: You're currently doing `applies_to=["gather_sec", "gather_news", "gather_earnings"]` for every middleware. This doesn't scale.

**Current State** (from your docs):
```python
ao.use(SummarizerMiddleware(
    applies_to=["gather_sec", "gather_news", "gather_earnings"],  # Exact matches only
))
```

**Implement This**:
```python
import fnmatch
from typing import List, Optional, Callable

class MiddlewareBase:
    def __init__(
        self,
        applies_to: Optional[List[str]] = None,      # ["gather_*", "research_*"]
        excludes: Optional[List[str]] = None,         # ["*_final", "gather_summary"]
        applies_when: Optional[Callable] = None,      # lambda ctx, step: step.tokens > 2000
    ):
        self.applies_to = applies_to
        self.excludes = excludes or []
        self.applies_when = applies_when

    def should_apply(self, step_name: str, ctx=None, step_result=None) -> bool:
        # Check excludes first (explicit exclusion wins)
        for pattern in self.excludes:
            if fnmatch.fnmatch(step_name, pattern):
                return False

        # Check applies_to patterns
        if self.applies_to:
            matched = any(fnmatch.fnmatch(step_name, p) for p in self.applies_to)
            if not matched:
                return False

        # Check condition
        if self.applies_when and ctx and step_result:
            if not self.applies_when(ctx, step_result):
                return False

        return True
```

**Usage After Implementation**:
```python
# Before: Enumerate every step
ao.use(SummarizerMiddleware(
    applies_to=["gather_sec", "gather_news", "gather_earnings", "gather_filings"],
))

# After: Pattern matching
ao.use(SummarizerMiddleware(
    applies_to=["gather_*"],           # All gather steps
    excludes=["gather_summary"],        # Except this one
))

ao.use(OffloadMiddleware(
    applies_to=["*"],                   # All steps
    excludes=["extract_*", "format_*"], # Except extraction/formatting
))
```

**Effort**: ~50 lines of code, 2-3 hours

---

### 2. Token Budget Reservation

**Why**: Your `TokenManagerMiddleware` tracks usage but doesn't reserve space for output. This causes silent truncation.

**Current State** (from your docs):
```python
ao.use(TokenManagerMiddleware(
    max_total_tokens=100_000,
    warning_threshold=0.8,  # Warn at 80%
))
```

**Problem**: If content uses 95K tokens and you need 8K for output, you're over by 3K.

**Implement This**:
```python
from dataclasses import dataclass
from enum import Enum

class BudgetStatus(Enum):
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"
    OVERFLOW = "overflow"

@dataclass
class TokenBudget:
    context_window: int = 128000
    reserved_output: int = 8000      # Max expected response
    reserved_system: int = 3000      # System prompt + tools
    reserved_history: int = 10000    # Conversation context

    @property
    def available_for_content(self) -> int:
        return self.context_window - self.reserved_output - self.reserved_system - self.reserved_history

    def get_status(self, current_content_tokens: int) -> BudgetStatus:
        ratio = current_content_tokens / self.available_for_content
        if ratio > 1.0:
            return BudgetStatus.OVERFLOW
        elif ratio > 0.95:
            return BudgetStatus.CRITICAL
        elif ratio > 0.8:
            return BudgetStatus.WARNING
        return BudgetStatus.OK

    def tokens_to_compress(self, current: int, target_ratio: float = 0.7) -> int:
        """How many tokens to compress to reach target ratio."""
        target = int(self.available_for_content * target_ratio)
        return max(0, current - target)

class TokenManagerMiddleware:
    def __init__(
        self,
        budget: TokenBudget = None,
        # Legacy support
        max_total_tokens: int = None,
        warning_threshold: float = 0.8,
        # New features
        auto_summarize: bool = True,
        auto_offload: bool = True,
        target_ratio_after_compression: float = 0.7,
    ):
        if budget:
            self.budget = budget
        elif max_total_tokens:
            # Legacy: convert to budget
            self.budget = TokenBudget(
                context_window=max_total_tokens,
                reserved_output=int(max_total_tokens * 0.08),
                reserved_system=int(max_total_tokens * 0.03),
                reserved_history=int(max_total_tokens * 0.1),
            )
        else:
            self.budget = TokenBudget()

        self.target_ratio = target_ratio_after_compression
```

**Usage After Implementation**:
```python
# Explicit budget allocation
budget = TokenBudget(
    context_window=128000,
    reserved_output=8000,    # Claude's response
    reserved_system=3000,    # System prompt
    reserved_history=15000,  # Chat history
)
# Available for content: 128000 - 8000 - 3000 - 15000 = 102,000 tokens

ao.use(TokenManagerMiddleware(
    budget=budget,
    auto_summarize=True,
    target_ratio_after_compression=0.7,  # Compress to 70% when critical
))
```

**Effort**: ~100 lines of code, 3-4 hours

---

## 🟠 P1: Implement Soon (High Impact, Medium Effort)

### 3. True Tree Summarization (TREE Strategy)

**Why**: Your docs say "MAP_REDUCE uses flat recursion, not tree structure". For 100K+ token documents, tree is 2-3x more efficient.

**Current State**:
```python
# MAP_REDUCE: chunks → summaries → combine (flat)
# Missing: hierarchical tree structure
```

**Implement This**:
```python
from enum import Enum
import asyncio
from typing import List

class SummarizationStrategy(Enum):
    STUFF = "stuff"
    MAP_REDUCE = "map_reduce"
    REFINE = "refine"
    TREE = "tree"  # NEW

class TreeSummarizer:
    def __init__(
        self,
        llm_client,
        chunk_size: int = 4000,
        summary_ratio: float = 0.1,  # Each summary is ~10% of input
        max_concurrent: int = 5,
        domain_prompts: dict = None,
    ):
        self.llm = llm_client
        self.chunk_size = chunk_size
        self.summary_ratio = summary_ratio
        self.max_concurrent = max_concurrent
        self.domain_prompts = domain_prompts or {}

    async def summarize(
        self,
        text: str,
        max_tokens: int,
        content_type: str = "general",
    ) -> str:
        """
        Tree summarization:
        Level 1: 16 chunks → 16 summaries (parallel)
        Level 2: 4 groups of 4 → 4 summaries (parallel)
        Level 3: 1 group of 4 → 1 final summary
        """
        chunks = self._chunk_text(text, self.chunk_size)

        if len(chunks) == 1:
            return chunks[0] if count_tokens(chunks[0]) <= max_tokens else await self._summarize_single(chunks[0], content_type)

        level = 1
        while len(chunks) > 1:
            # Group chunks (e.g., groups of 4)
            groups = self._group_chunks(chunks, group_size=4)

            # Summarize each group in parallel
            semaphore = asyncio.Semaphore(self.max_concurrent)
            async def summarize_with_limit(group):
                async with semaphore:
                    combined = "\n\n---\n\n".join(group)
                    return await self._summarize_single(combined, content_type, level=level)

            chunks = await asyncio.gather(*[summarize_with_limit(g) for g in groups])
            level += 1

            # Check if we're under target
            total_tokens = sum(count_tokens(c) for c in chunks)
            if total_tokens <= max_tokens:
                break

        # Final combination if multiple chunks remain
        if len(chunks) > 1:
            final = "\n\n".join(chunks)
            if count_tokens(final) > max_tokens:
                return await self._summarize_single(final, content_type, level=level, is_final=True)
            return final

        return chunks[0]

    async def _summarize_single(self, text: str, content_type: str, level: int = 1, is_final: bool = False) -> str:
        prompt = self._get_prompt(content_type, level, is_final)
        response = await self.llm.generate_async(
            prompt=prompt.format(text=text),
            system_prompt="You are a precise summarizer. Preserve key facts, numbers, and named entities."
        )
        return response

    def _get_prompt(self, content_type: str, level: int, is_final: bool) -> str:
        if content_type in self.domain_prompts:
            prompts = self.domain_prompts[content_type]
            if is_final and "final" in prompts:
                return prompts["final"]
            return prompts.get("map", prompts.get("default", DEFAULT_PROMPT))

        if is_final:
            return """Create a comprehensive final summary from these intermediate summaries.
Preserve all key facts, numbers, dates, and named entities.

SUMMARIES:
{text}

FINAL SUMMARY:"""

        return """Summarize this content, preserving:
- Key facts and numbers
- Named entities (companies, people, products)
- Dates and timeframes
- Critical relationships

CONTENT:
{text}

SUMMARY:"""

    def _chunk_text(self, text: str, chunk_size: int) -> List[str]:
        # Your existing chunking logic
        pass

    def _group_chunks(self, chunks: List[str], group_size: int = 4) -> List[List[str]]:
        return [chunks[i:i+group_size] for i in range(0, len(chunks), group_size)]
```

**Usage After Implementation**:
```python
ao.use(SummarizerMiddleware(
    max_tokens=4000,
    step_strategies={
        "gather_sec": SummarizationStrategy.TREE,      # 100K+ tokens → tree
        "gather_news": SummarizationStrategy.MAP_REDUCE, # 20K tokens → flat
        "gather_earnings": SummarizationStrategy.REFINE,  # Quality critical
    },
    applies_to=["gather_*"],
))
```

**Effort**: ~200 lines of code, 1 day

---

### 4. Rolling Summary Buffer

**Why**: Currently, if you summarize a 50K document to 5K, then add 10K more content, you re-summarize all 15K. LangChain's pattern only summarizes the NEW 10K and appends.

**Implement This**:
```python
from dataclasses import dataclass, field
from typing import Dict

@dataclass
class RollingSummary:
    summary: str = ""
    token_count: int = 0
    sources_included: List[str] = field(default_factory=list)
    version: int = 0

class RollingSummaryMiddleware:
    def __init__(
        self,
        max_tokens: int = 4000,
        llm_client = None,
        applies_to: List[str] = None,
    ):
        self.max_tokens = max_tokens
        self.llm = llm_client
        self.applies_to = applies_to
        self._summaries: Dict[str, RollingSummary] = {}  # key -> rolling summary

    async def after(self, ctx, step_name: str, result) -> None:
        if not self.should_apply(step_name):
            return

        # Get or create rolling summary for this context key
        key = f"{ctx.request_id}:{step_name}"
        rolling = self._summaries.get(key, RollingSummary())

        # Get new content
        new_content = result.output
        new_tokens = count_tokens(str(new_content))

        # If new content alone exceeds limit, summarize just the new content
        if new_tokens > self.max_tokens:
            new_content = await self._summarize(new_content)
            new_tokens = count_tokens(new_content)

        # Check if combined would exceed limit
        combined_tokens = rolling.token_count + new_tokens

        if combined_tokens > self.max_tokens:
            # Only summarize the NEW content, then append to existing summary
            if new_tokens > self.max_tokens * 0.5:
                new_summary = await self._summarize(new_content)
            else:
                new_summary = str(new_content)

            # Update rolling summary by appending
            rolling.summary = await self._merge_summaries(
                existing=rolling.summary,
                new=new_summary
            )
            rolling.token_count = count_tokens(rolling.summary)
            rolling.version += 1
        else:
            # Just append, no summarization needed
            rolling.summary = f"{rolling.summary}\n\n{new_content}" if rolling.summary else str(new_content)
            rolling.token_count = combined_tokens
            rolling.version += 1

        rolling.sources_included.append(step_name)
        self._summaries[key] = rolling

        # Update context with rolling summary
        ctx.set(f"{step_name}_summary", rolling.summary)

    async def _merge_summaries(self, existing: str, new: str) -> str:
        """Merge new summary into existing, preserving key facts from both."""
        prompt = f"""You have an existing summary and new information to incorporate.
Update the summary to include the new information while staying concise.
Preserve all key facts, numbers, and named entities from BOTH sources.

EXISTING SUMMARY:
{existing}

NEW INFORMATION:
{new}

UPDATED SUMMARY:"""

        return await self.llm.generate_async(prompt)
```

**Usage After Implementation**:
```python
# For iterative data gathering (pagination, streaming)
ao.use(RollingSummaryMiddleware(
    max_tokens=4000,
    applies_to=["gather_news", "gather_social"],  # Steps that accumulate data
))

# In step:
@ao.step(name="gather_news")
async def gather_news(ctx):
    for page in range(10):
        articles = await fetch_news_page(page)
        ctx.set("news_batch", articles)  # Middleware handles rolling summary
        # Context now has ctx.get("gather_news_summary") with rolling summary
```

**Effort**: ~150 lines of code, half day

---

### 5. Query-Aware Compression

**Why**: LangChain's `LLMChainExtractor` filters documents by query relevance BEFORE summarizing. This is more efficient than summarizing everything.

**Implement This**:
```python
class QueryAwareCompressor:
    """Extract only query-relevant content before summarization."""

    def __init__(self, llm_client, relevance_threshold: float = 0.3):
        self.llm = llm_client
        self.threshold = relevance_threshold

    async def compress(
        self,
        documents: List[Dict],
        query: str,
        max_tokens: int,
    ) -> List[Dict]:
        """
        1. Score each document for query relevance
        2. Filter low-relevance docs
        3. Extract relevant portions from remaining docs
        """
        results = []

        for doc in documents:
            # Extract query-relevant portions
            extracted = await self._extract_relevant(doc, query)

            if extracted and count_tokens(extracted) > 10:  # Meaningful content
                results.append({
                    **doc,
                    "content": extracted,
                    "original_tokens": count_tokens(doc.get("content", "")),
                    "compressed_tokens": count_tokens(extracted),
                })

        # Sort by relevance, take top N that fit in budget
        total_tokens = 0
        final_results = []
        for doc in results:
            if total_tokens + doc["compressed_tokens"] <= max_tokens:
                final_results.append(doc)
                total_tokens += doc["compressed_tokens"]

        return final_results

    async def _extract_relevant(self, doc: Dict, query: str) -> str:
        content = doc.get("content", "")
        if not content:
            return ""

        prompt = f"""Extract ONLY the parts of this document that are relevant to answering: "{query}"

If nothing is relevant, respond with "NOT_RELEVANT".
Preserve exact quotes, numbers, and facts. Do not add interpretation.

DOCUMENT:
{content[:8000]}  # Limit input

RELEVANT EXCERPTS:"""

        response = await self.llm.generate_async(prompt)

        if "NOT_RELEVANT" in response:
            return ""
        return response
```

**Usage in Middleware**:
```python
class SummarizerMiddleware:
    def __init__(
        self,
        # ... existing params
        query_aware: bool = False,  # NEW
        query_key: str = "user_query",  # Context key containing query
    ):
        self.query_aware = query_aware
        self.query_key = query_key

    async def after(self, ctx, step_name, result):
        if self.query_aware:
            query = ctx.get(self.query_key, "")
            if query:
                # First: query-aware extraction
                compressed = await self.compressor.compress(
                    documents=result.output,
                    query=query,
                    max_tokens=self.max_tokens * 2,  # Allow more before summarization
                )
                # Then: summarize the compressed content
                if count_tokens(str(compressed)) > self.max_tokens:
                    result.output = await self.summarizer.summarize(compressed)
                else:
                    result.output = compressed
        # ... rest of existing logic
```

**Effort**: ~100 lines of code, half day

---

## 🟢 P2: Implement Later (Medium Impact)

### 6. Condition-Based `applies_when`

Already included in P0 glob patterns implementation. Usage:

```python
ao.use(SummarizerMiddleware(
    applies_to=["*"],
    applies_when=lambda ctx, step_result: (
        step_result.output_tokens > 5000 and
        step_result.metadata.get("source_type") in ["sec", "news"]
    ),
))

ao.use(OffloadMiddleware(
    applies_when=lambda ctx, step_result: (
        step_result.output_bytes > 100_000 or
        ctx.get("force_offload") == True
    ),
))
```

### 7. Multi-Tier Waterfall Storage

Only implement if you need:
- Long-running sessions (hours/days)
- Semantic retrieval of historical context
- Cross-session memory

```python
class WaterfallStorageMiddleware:
    """
    Tier 1: In-memory (hot) - Current step outputs
    Tier 2: Redis (warm) - Session data, fast retrieval
    Tier 3: Postgres (cold) - Archival, slow retrieval
    Tier 4: Vector store (semantic) - RAG retrieval
    """

    def __init__(
        self,
        memory_limit: int = 10000,      # tokens
        redis_limit: int = 100000,       # tokens
        vector_store = None,             # For semantic retrieval
        postgres_store = None,           # For archival
    ):
        self.tiers = [
            InMemoryTier(max_tokens=memory_limit),
            RedisTier(max_tokens=redis_limit),
            PostgresTier() if postgres_store else None,
            VectorTier(store=vector_store) if vector_store else None,
        ]
        self.tiers = [t for t in self.tiers if t]  # Remove None

    async def store(self, key: str, data: Any, priority: str = "normal") -> StorageRef:
        """Store data in appropriate tier based on size and priority."""
        size = count_tokens(str(data))

        for tier in self.tiers:
            if tier.accepts(size, priority):
                ref = await tier.store(key, data)
                return ref

        # Fallback: compress and try again
        compressed = await self._compress(data)
        return await self.tiers[-1].store(key, compressed)  # Last tier

    async def retrieve(self, ref: StorageRef) -> Any:
        """Retrieve from appropriate tier."""
        tier = self.tiers[ref.tier_index]
        return await tier.retrieve(ref)

    async def query_semantic(self, query: str, top_k: int = 5) -> List[Any]:
        """Semantic search across vector tier."""
        vector_tier = next((t for t in self.tiers if isinstance(t, VectorTier)), None)
        if vector_tier:
            return await vector_tier.search(query, top_k)
        return []
```

**Effort**: ~300 lines, 2 days

---

## 🔵 P3: Nice to Have

### 8. Compression Quality Metrics

Measure information loss during summarization:

```python
@dataclass
class CompressionMetrics:
    original_tokens: int
    compressed_tokens: int
    compression_ratio: float
    entities_preserved: float  # % of named entities kept
    numbers_preserved: float   # % of numbers kept
    semantic_similarity: float # Embedding similarity 0-1

class MetricsMiddleware:
    async def after(self, ctx, step_name, result):
        if result.was_compressed:
            metrics = await self._calculate_metrics(
                original=result.original_output,
                compressed=result.output,
            )
            ctx.set(f"{step_name}_compression_metrics", metrics)

            # Alert if quality degraded
            if metrics.entities_preserved < 0.8:
                logger.warning(f"Low entity preservation in {step_name}: {metrics.entities_preserved:.0%}")
```

---

## Implementation Roadmap

```
Week 1:
├── Day 1-2: Glob patterns + applies_when (P0)
├── Day 3-4: Token budget reservation (P0)
└── Day 5: Tests + documentation

Week 2:
├── Day 1-2: Tree summarization (P1)
├── Day 3: Rolling summary buffer (P1)
├── Day 4-5: Query-aware compression (P1)

Week 3:
├── Day 1-2: Integration testing
├── Day 3-5: Multi-tier storage (P2) if needed
```

---

## Quick Wins You Can Do Today

1. **Add `fnmatch` to your middleware base class** - 30 minutes
2. **Add `reserved_output` to TokenManagerMiddleware** - 1 hour
3. **Add `TREE` to your SummarizationStrategy enum** - Stub it out

---

## What NOT to Implement

Based on comparing your framework to LangChain/LlamaIndex, you should **skip**:

1. ❌ **Callback-based architecture** - Your middleware pattern is cleaner
2. ❌ **RunnableConfig per-invoke** - Your `applies_to` is more declarative
3. ❌ **Memory class hierarchy** - Your Redis offloading is simpler and sufficient
4. ❌ **Document loaders** - Out of scope for response handling

Your framework already has the right architecture. These recommendations fill specific gaps while preserving your design.

---

# MULTI-AGENT PATTERN SUPPORT

After reviewing your `ContextIsolationManager`, `AgentContextNamespace`, and `ResultAggregator` architecture, here are the gaps and enhancements needed for full multi-agent support.

## Gap Analysis: Proposals vs. Agent Patterns

| Proposal | Sequential | Multi-Agent | Supervisory | Hierarchical |
|----------|------------|-------------|-------------|--------------|
| Glob patterns | ✅ | ✅ | ✅ | ✅ |
| Token budget | ✅ | ⚠️ Needs namespace integration | ⚠️ Needs budget allocation | ⚠️ Needs hierarchical propagation |
| Tree summarization | ✅ | ✅ | ✅ | ✅ |
| Rolling summary | ✅ | ⚠️ Needs agent_id keying | ⚠️ Needs namespace storage | ⚠️ Needs namespace storage |
| Query-aware compression | ✅ | ⚠️ Per-agent queries | ⚠️ Consumer-aware sharing | ⚠️ Cross-level awareness |

---

## 🔴 CRITICAL: Namespace-Aware Token Budget

### Problem
Current `TokenBudget` is per-chain. Multi-agent needs per-namespace budgets:

```python
# Supervisor has 100K total budget
# 5 workers need fair allocation
# Each worker: 100K / 5 = 20K budget
# BUT: Supervisor needs space for aggregation too!
```

### Solution: `NamespaceTokenBudget`

```python
from dataclasses import dataclass, field
from typing import Dict, Optional

@dataclass
class NamespaceTokenBudget:
    """Token budget scoped to an agent namespace."""

    # Allocation
    allocated: int                    # Tokens allocated to this namespace
    reserved_output: int = 2000       # Reserved for agent's response
    reserved_publish: int = 1000      # Reserved for published results

    # Tracking
    consumed: int = 0
    published: int = 0

    @property
    def available(self) -> int:
        return self.allocated - self.reserved_output - self.reserved_publish - self.consumed

    def can_consume(self, tokens: int) -> bool:
        return tokens <= self.available

    def consume(self, tokens: int) -> bool:
        if self.can_consume(tokens):
            self.consumed += tokens
            return True
        return False

    def get_publish_budget(self) -> int:
        """How many tokens can this agent publish to others."""
        return self.reserved_publish


@dataclass
class SupervisorBudgetAllocator:
    """Allocates token budgets from supervisor to workers."""

    total_budget: int
    reserved_for_aggregation: int = 10000  # Supervisor needs space for final synthesis
    reserved_for_system: int = 3000
    allocation_strategy: str = "equal"  # "equal", "weighted", "dynamic"

    def allocate(self, agent_ids: List[str], weights: Dict[str, float] = None) -> Dict[str, NamespaceTokenBudget]:
        """Allocate budgets to worker agents."""
        distributable = self.total_budget - self.reserved_for_aggregation - self.reserved_for_system

        if self.allocation_strategy == "equal":
            per_agent = distributable // len(agent_ids)
            return {
                agent_id: NamespaceTokenBudget(allocated=per_agent)
                for agent_id in agent_ids
            }

        elif self.allocation_strategy == "weighted":
            weights = weights or {aid: 1.0 for aid in agent_ids}
            total_weight = sum(weights.values())
            return {
                agent_id: NamespaceTokenBudget(
                    allocated=int(distributable * weights.get(agent_id, 1.0) / total_weight)
                )
                for agent_id in agent_ids
            }

        elif self.allocation_strategy == "dynamic":
            # Start with equal, reallocate as agents complete
            per_agent = distributable // len(agent_ids)
            return {
                agent_id: NamespaceTokenBudget(allocated=per_agent)
                for agent_id in agent_ids
            }

    def reallocate_unused(self, budgets: Dict[str, NamespaceTokenBudget], completed_agents: List[str]) -> None:
        """Reallocate unused budget from completed agents to running ones."""
        unused = sum(
            b.available for aid, b in budgets.items()
            if aid in completed_agents
        )
        running = [aid for aid in budgets if aid not in completed_agents]
        if running and unused > 0:
            bonus = unused // len(running)
            for aid in running:
                budgets[aid].allocated += bonus
```

### Integration with `AgentContextNamespace`

```python
# In squad/context/namespace.py

class AgentContextNamespace:
    def __init__(
        self,
        agent_id: str,
        isolation_level: IsolationLevel,
        token_budget: Optional[NamespaceTokenBudget] = None,  # NEW
    ):
        self.agent_id = agent_id
        self.isolation_level = isolation_level
        self.token_budget = token_budget
        self._local_store = {}

    def set(self, key: str, value: Any) -> bool:
        """Set value, respecting token budget."""
        if self.token_budget:
            tokens = count_tokens(str(value))
            if not self.token_budget.consume(tokens):
                # Budget exceeded - trigger compression
                compressed = self._compress(value)
                tokens = count_tokens(str(compressed))
                if not self.token_budget.consume(tokens):
                    raise TokenBudgetExceeded(
                        f"Agent {self.agent_id} exceeded token budget. "
                        f"Available: {self.token_budget.available}, Required: {tokens}"
                    )
                value = compressed

        self._local_store[key] = value
        return True

    def publish(self, key: str, value: Any) -> bool:
        """Publish value for other agents, respecting publish budget."""
        if self.token_budget:
            tokens = count_tokens(str(value))
            if tokens > self.token_budget.get_publish_budget():
                # Must compress before publishing
                value = self._compress_for_publish(value, self.token_budget.get_publish_budget())

        self._published[key] = value
        return True
```

### Usage in Supervisor Pattern

```python
class SupervisorAgent:
    async def execute_team(self, query: str, ctx: ChainContext):
        # 1. Allocate budgets to workers
        allocator = SupervisorBudgetAllocator(
            total_budget=100000,
            reserved_for_aggregation=15000,
            allocation_strategy="weighted",
        )

        weights = {
            "research_agent": 2.0,   # Needs more (fetches data)
            "analyst_agent": 1.5,    # Medium (analysis)
            "writer_agent": 1.0,     # Less (just formats)
        }

        budgets = allocator.allocate(
            agent_ids=["research_agent", "analyst_agent", "writer_agent"],
            weights=weights,
        )

        # 2. Create isolated namespaces with budgets
        isolation = ContextIsolationManager(coordinator_context=ctx)

        for agent_id, budget in budgets.items():
            namespace = isolation.create_namespace(
                agent_id=agent_id,
                isolation_level=IsolationLevel.FULL,
                token_budget=budget,  # NEW: Budget attached to namespace
            )

        # 3. Execute workers (each respects its budget)
        async with isolation.execute_parallel(self.team, self._run_worker, query):
            pass

        # 4. Aggregate (uses reserved aggregation budget)
        aggregator = ResultAggregator(
            strategy=AggregationStrategy.SYNTHESIZE,
            max_input_tokens=allocator.reserved_for_aggregation,  # NEW
        )
        # ... aggregate results
```

---

## 🔴 CRITICAL: ResultAggregator Compression Integration

### Problem
When aggregating 5 agent outputs, total may exceed context:

```
Agent1: 50K tokens ─┐
Agent2: 40K tokens ─┼─→ ResultAggregator → 200K tokens → LLM 💥
Agent3: 45K tokens ─┘
```

### Solution: Pre-Aggregation Compression

```python
# In squad/context/aggregator.py

class ResultAggregator:
    def __init__(
        self,
        strategy: AggregationStrategy,
        max_input_tokens: int = 50000,           # NEW: Max tokens for aggregation
        compress_before_aggregate: bool = True,   # NEW: Auto-compress
        summarizer: Optional[Summarizer] = None,  # NEW: Compression engine
    ):
        self.strategy = strategy
        self.max_input_tokens = max_input_tokens
        self.compress_before_aggregate = compress_before_aggregate
        self.summarizer = summarizer

    async def aggregate(self, llm=None) -> AggregatedResult:
        # 1. Collect all results
        all_results = self._collect_results()
        total_tokens = sum(count_tokens(str(r)) for r in all_results)

        # 2. Compress if needed
        if self.compress_before_aggregate and total_tokens > self.max_input_tokens:
            all_results = await self._compress_results(all_results)

        # 3. Aggregate using strategy
        if self.strategy == AggregationStrategy.SYNTHESIZE:
            return await self._synthesize(all_results, llm)
        # ... other strategies

    async def _compress_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Compress each result proportionally to fit budget."""
        total_tokens = sum(count_tokens(str(r)) for r in results.values())

        compressed = {}
        for agent_id, result in results.items():
            result_tokens = count_tokens(str(result))
            # Proportional allocation
            allocation = int(self.max_input_tokens * (result_tokens / total_tokens))

            if result_tokens > allocation:
                compressed[agent_id] = await self.summarizer.summarize(
                    str(result),
                    max_tokens=allocation,
                )
            else:
                compressed[agent_id] = result

        return compressed
```

### Usage

```python
aggregator = ResultAggregator(
    strategy=AggregationStrategy.SYNTHESIZE,
    max_input_tokens=40000,  # Total tokens for all agent results
    compress_before_aggregate=True,
    summarizer=TreeSummarizer(llm_client=llm),
)

# Each agent contributes up to 40K / num_agents tokens
for agent in team:
    aggregator.add_from_namespace(agent.id, agent.namespace)

result = await aggregator.aggregate(llm=llm)
```

---

## 🟠 IMPORTANT: Namespace-Aware Rolling Summary

### Problem
Rolling summary keys by `step_name`, breaks with parallel agents running same step:

```python
# Two agents both running "gather_data" step
# Current: key = f"{request_id}:gather_data"  # Collision!
# Needed: key = f"{request_id}:{agent_id}:gather_data"
```

### Solution: Namespace-Scoped Rolling Summary

```python
class RollingSummaryMiddleware:
    def __init__(self, ...):
        # ... existing params
        self.namespace_aware: bool = True  # NEW

    async def after(self, ctx, step_name: str, result, namespace: AgentContextNamespace = None) -> None:
        # Generate key based on context
        if self.namespace_aware and namespace:
            key = f"{ctx.request_id}:{namespace.agent_id}:{step_name}"
            storage = namespace  # Store in agent's namespace
        else:
            key = f"{ctx.request_id}:{step_name}"
            storage = ctx

        rolling = self._summaries.get(key, RollingSummary())

        # ... existing rolling logic ...

        # Store in appropriate scope
        if self.namespace_aware and namespace:
            namespace.set("_rolling_summary", rolling.summary)
        else:
            ctx.set(f"{step_name}_summary", rolling.summary)
```

---

## 🟠 IMPORTANT: Consumer-Aware Sharing

### Problem
When sharing between agents, compression should consider consumer's needs:

```python
# Research agent has detailed findings
# Analyst agent only needs financial data
# Currently: shares everything
# Needed: compress for analyst's query
```

### Solution: Query-Aware `share_between()`

```python
class ContextIsolationManager:
    async def share_between(
        self,
        source_agent: str,
        key: str,
        target_agents: List[str],
        # NEW parameters:
        compress: bool = False,
        compress_for_query: Optional[str] = None,  # Consumer's query
        max_tokens: Optional[int] = None,
    ) -> None:
        """Share data between agents with optional query-aware compression."""

        source_ns = self._namespaces[source_agent]
        data = source_ns.get(key)

        for target_agent in target_agents:
            target_ns = self._namespaces[target_agent]

            if compress:
                # Get target agent's query if not provided
                query = compress_for_query or target_ns.get("current_query", "")

                # Respect target's available budget
                target_budget = target_ns.token_budget
                allowed_tokens = max_tokens or (target_budget.available if target_budget else 10000)

                # Compress for consumer
                compressed = await self._query_aware_compress(
                    data=data,
                    query=query,
                    max_tokens=allowed_tokens,
                )
                target_ns.grant_access(key, compressed)
            else:
                target_ns.grant_access(key, data)

    async def _query_aware_compress(self, data: Any, query: str, max_tokens: int) -> Any:
        """Compress data keeping only what's relevant to query."""
        if not query:
            # No query - use standard compression
            return await self.summarizer.summarize(str(data), max_tokens=max_tokens)

        # Query-aware extraction
        return await self.compressor.compress(
            documents=[{"content": str(data)}],
            query=query,
            max_tokens=max_tokens,
        )
```

### Usage in Supervisor

```python
# Research agent publishes findings
research_ns.publish("findings", detailed_research)

# Share with analyst, compressed for their query
await isolation.share_between(
    source_agent="research_agent",
    key="findings",
    target_agents=["analyst_agent"],
    compress=True,
    compress_for_query="What are the financial risks and opportunities?",
    max_tokens=5000,
)

# Analyst receives compressed, relevant data
analyst_data = analyst_ns.get("findings")  # 5000 tokens, focused on financial aspects
```

---

## 🟠 IMPORTANT: Hierarchical Budget Propagation

### Problem
In hierarchical patterns (supervisor → sub-supervisors → workers), budgets need to cascade:

```
Supervisor (100K budget)
├── Sub-supervisor A (40K)
│   ├── Worker A1 (12K)
│   ├── Worker A2 (12K)
│   └── Worker A3 (12K)
│   └── Reserved for sub-aggregation (4K)
├── Sub-supervisor B (40K)
│   └── ... similar ...
└── Reserved for final aggregation (20K)
```

### Solution: Hierarchical Budget Manager

```python
@dataclass
class HierarchicalBudget:
    """Budget that can be subdivided to children."""

    total: int
    reserved_for_self: int  # This level's aggregation/output
    children_budgets: Dict[str, 'HierarchicalBudget'] = field(default_factory=dict)

    @property
    def distributable(self) -> int:
        return self.total - self.reserved_for_self

    def allocate_to_children(
        self,
        child_ids: List[str],
        strategy: str = "equal",
        weights: Dict[str, float] = None,
        child_reserves: Dict[str, int] = None,
    ) -> Dict[str, 'HierarchicalBudget']:
        """Allocate budget to child supervisors/agents."""
        child_reserves = child_reserves or {}

        if strategy == "equal":
            per_child = self.distributable // len(child_ids)
            for child_id in child_ids:
                self.children_budgets[child_id] = HierarchicalBudget(
                    total=per_child,
                    reserved_for_self=child_reserves.get(child_id, 2000),
                )

        elif strategy == "weighted":
            weights = weights or {cid: 1.0 for cid in child_ids}
            total_weight = sum(weights.values())
            for child_id in child_ids:
                allocation = int(self.distributable * weights[child_id] / total_weight)
                self.children_budgets[child_id] = HierarchicalBudget(
                    total=allocation,
                    reserved_for_self=child_reserves.get(child_id, 2000),
                )

        return self.children_budgets

    def get_child_budget(self, child_id: str) -> 'HierarchicalBudget':
        return self.children_budgets.get(child_id)

    def to_namespace_budget(self) -> NamespaceTokenBudget:
        """Convert to namespace-level budget for leaf agents."""
        return NamespaceTokenBudget(
            allocated=self.total,
            reserved_output=self.reserved_for_self,
        )
```

### Usage in Hierarchical Pattern

```python
class HierarchicalSupervisor:
    async def execute(self, query: str, ctx: ChainContext):
        # 1. Create hierarchical budget
        root_budget = HierarchicalBudget(
            total=128000,
            reserved_for_self=20000,  # Final synthesis
        )

        # 2. Allocate to sub-supervisors
        sub_budgets = root_budget.allocate_to_children(
            child_ids=["research_team", "analysis_team", "writing_team"],
            strategy="weighted",
            weights={"research_team": 2.0, "analysis_team": 1.5, "writing_team": 1.0},
            child_reserves={"research_team": 5000, "analysis_team": 4000, "writing_team": 3000},
        )

        # 3. Sub-supervisor further allocates to workers
        research_budget = sub_budgets["research_team"]
        worker_budgets = research_budget.allocate_to_children(
            child_ids=["sec_agent", "news_agent", "social_agent"],
            strategy="equal",
        )

        # 4. Create namespaces with budgets
        isolation = ContextIsolationManager(coordinator_context=ctx)

        for agent_id, budget in worker_budgets.items():
            namespace = isolation.create_namespace(
                agent_id=agent_id,
                isolation_level=IsolationLevel.FULL,
                token_budget=budget.to_namespace_budget(),
            )

        # 5. Execute (budgets enforced at each level)
        # ...
```

---

## Updated Priority Matrix

| Feature | Impact | Effort | Priority | Multi-Agent Ready? |
|---------|--------|--------|----------|-------------------|
| **Glob patterns for `applies_to`** | High | Low | 🔴 P0 | ✅ Yes |
| **Namespace-aware token budget** | Critical | Medium | 🔴 P0 | 🆕 NEW |
| **ResultAggregator compression** | Critical | Medium | 🔴 P0 | 🆕 NEW |
| **Token budget reservation** | High | Low | 🔴 P0 | ✅ Yes (with namespace integration) |
| **True Tree Summarization** | High | Medium | 🟠 P1 | ✅ Yes |
| **Namespace-aware rolling summary** | High | Low | 🟠 P1 | 🆕 NEW |
| **Consumer-aware sharing** | High | Medium | 🟠 P1 | 🆕 NEW |
| **Query-aware compression** | High | Medium | 🟠 P1 | ✅ Yes |
| **Hierarchical budget propagation** | Medium | Medium | 🟢 P2 | 🆕 NEW |
| **Condition-based `applies_when`** | Medium | Low | 🟢 P2 | ✅ Yes |
| **Multi-tier waterfall storage** | Medium | High | 🟢 P2 | ✅ Yes |

---

## Updated Implementation Roadmap

```
Week 1: Core Multi-Agent Support
├── Day 1-2: NamespaceTokenBudget + integration with AgentContextNamespace
├── Day 3: ResultAggregator compression integration
├── Day 4: Glob patterns + applies_when
└── Day 5: Tests for multi-agent scenarios

Week 2: Advanced Compression
├── Day 1-2: Tree summarization
├── Day 3: Namespace-aware rolling summary
├── Day 4: Consumer-aware share_between()
└── Day 5: Query-aware compression

Week 3: Hierarchical Support
├── Day 1-2: HierarchicalBudget for nested supervisors
├── Day 3-4: Integration testing (supervisor → sub-supervisor → workers)
└── Day 5: Documentation + examples
```

---

## Architecture Diagram: Multi-Agent Context Flow with Compression

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           SUPERVISOR (Budget: 128K)                              │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────────┐│
│  │                    SupervisorBudgetAllocator                                 ││
│  │  ┌─────────────┬─────────────┬─────────────┬──────────────────────────────┐ ││
│  │  │ Research    │ Analyst     │ Writer      │ Reserved for Aggregation     │ ││
│  │  │ 35K tokens  │ 25K tokens  │ 20K tokens  │ 28K tokens                   │ ││
│  │  └─────────────┴─────────────┴─────────────┴──────────────────────────────┘ ││
│  └─────────────────────────────────────────────────────────────────────────────┘│
│                                      │                                           │
│         ┌────────────────────────────┼────────────────────────────┐              │
│         ▼                            ▼                            ▼              │
│  ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐          │
│  │ Research Agent  │      │ Analyst Agent   │      │ Writer Agent    │          │
│  │ Namespace       │      │ Namespace       │      │ Namespace       │          │
│  │ Budget: 35K     │      │ Budget: 25K     │      │ Budget: 20K     │          │
│  │                 │      │                 │      │                 │          │
│  │ Output: 50K ────┼──┐   │                 │      │                 │          │
│  │ Compressed: 10K │  │   │                 │      │                 │          │
│  │                 │  │   │                 │      │                 │          │
│  │ Rolling Summary │  │   │ Receives        │      │                 │          │
│  │ stored locally  │  │   │ compressed      │      │                 │          │
│  └─────────────────┘  │   │ research (5K)   │      │                 │          │
│                       │   └─────────────────┘      └─────────────────┘          │
│                       │              │                      │                    │
│                       │   share_between(                    │                    │
│                       │     compress=True,                  │                    │
│                       │     query="financial risks",        │                    │
│                       │     max_tokens=5000)                │                    │
│                       │              │                      │                    │
│                       ▼              ▼                      ▼                    │
│                ┌──────────────────────────────────────────────────┐             │
│                │              ResultAggregator                     │             │
│                │  ┌──────────────────────────────────────────────┐ │             │
│                │  │ Pre-Aggregation Compression                  │ │             │
│                │  │ Research: 10K → 8K                           │ │             │
│                │  │ Analyst:  15K → 10K                          │ │             │
│                │  │ Writer:   12K → 8K                           │ │             │
│                │  │ ─────────────────────                        │ │             │
│                │  │ Total:    26K (fits in 28K reserved)         │ │             │
│                │  └──────────────────────────────────────────────┘ │             │
│                │                      │                            │             │
│                │                      ▼                            │             │
│                │  ┌──────────────────────────────────────────────┐ │             │
│                │  │ SYNTHESIZE Strategy                          │ │             │
│                │  │ LLM combines 26K tokens → Final Response     │ │             │
│                │  └──────────────────────────────────────────────┘ │             │
│                └──────────────────────────────────────────────────┘             │
│                                      │                                           │
│                                      ▼                                           │
│                              Final Response (8K)                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```