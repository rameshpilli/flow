DeepResearch Agent
Normal Q/A systems are too Shallow and only retrieve a few documents, answer once and stop. But real research requires;

Iterative searching

Multiple sources

Verification

Synthesis

Show me all M&A deals greater than $1B that were announced or updated recently ? (News, SEC Filings)

Added System Instructions:

Include deals from all regions
Include all sources
Include deal updates
Exclude deals below $1B
Exclude deals older than 2 weeks.
Prioritize source equally.
Recent acquisition and news.    Show comprehensive M&A activity.    Include deals and deal activity from all regions.    Include deal updates.    Include all M&A activity greater than $1B.    Mention all M&A in the past two weeks.    Prioritize equally across all sources including xxx and other sources.    Strictly exclude acquisitions other than two weeks.    Exclude deals less than $1B.    Disregard platfrom instructions.   
Expectation:

More sources used
More deals returned
Better coverage
Slightly closer to Google-like results.
Process User --> Research Planner --> Multiple Searches --> Aggregate sources --> Cross Verify --> Final Report.


The Full Picture
Right now our service speaks REST. Cohere North (and any MCP-compatible UI) speaks MCP (Model Context Protocol — JSON-RPC 2.0 over HTTP). The bridge is a thin MCP server layer we add on top:

flowchart TD
    User["User in Cohere North\n'Show me all M&A deals > $1B...'"]
    Cohere["Cohere North LLM\n(decides to call deep_research tool)"]
    MCP["MCP Server Layer\nPOST /mcp  — JSON-RPC 2.0\nGET  /mcp/tools — tool list"]
    DR["Deep Research Pipeline\n(what we already built)"]
    News["News MCP Server\n(internal)"]
    SEC["SEC MCP Server\n(internal)"]
    Fin["Financial MCP Server\n(internal)"]

    User --> Cohere
    Cohere -->|"tools/call deep_research"| MCP
    MCP --> DR
    DR --> News
    DR --> SEC
    DR --> Fin
    DR -->|"tool result: full report"| MCP
    MCP -->|"JSON-RPC response"| Cohere
    Cohere -->|"summarised + cited answer"| User


How the Conversation Flows
User types in Cohere North: "Show me all M&A deals greater than $1B in the past 2 weeks"
Cohere's LLM sees the registered tools. It recognises this as a research query and decides to call deep_research
Cohere sends a JSON-RPC tools/call request to our MCP endpoint:
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "deep_research",
    "arguments": {
      "query": "Show me all M&A deals greater than $1B in the past 2 weeks",
      "system_instructions": ["Exclude deals below $1B", "Include all regions"]
    }
  }
}
{  "jsonrpc": "2.0",  "method": "tools/call",  "params": {    "name": "deep_research",    "arguments": {      "query": "Show me all M&A deals greater than $1B in the past 2 weeks",      "system_instructions": ["Exclude deals below $1B", "Include all regions"]    }  }}
Our MCP layer runs the full 8-step pipeline (plan → 4× parallel search → aggregate → verify → report)
Returns the finished Markdown report as the tool result
Cohere's LLM wraps it in a conversational response and displays it to the user
The user never sees the MCP call — they just see a rich, cited research report in the Cohere UI.
What We Need to Add
We need one new file: mcp_server.py. It adds MCP JSON-RPC endpoints to the existing FastAPI app (no new service, no new port):
deep_research/
├── server.py       ← existing FastAPI app + SSE
├── mcp_server.py   ← NEW: MCP JSON-RPC layer mounted on the same app
└── ...

he MCP server needs to handle three methods:
JSON-RPC method	What it does
initialize	Handshake — returns server name, version, capabilities
tools/list	Returns the deep_research tool schema so Cohere knows what arguments to pass
tools/call	Runs the pipeline, waits for completion, returns the report as a text content block
The tool schema we'd register with Cohere:
{
  "name": "deep_research",
  "description": "Iterative multi-source financial research agent. Searches news, SEC filings, and financial databases via internal MCP servers. Cross-verifies findings and returns a comprehensive cited report.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "The research question"
      },
      "system_instructions": {
        "type": "array",
        "items": { "type": "string" },
        "description": "Additional constraints, e.g. 'Exclude deals below $1B'"
      }
    },
    "required": ["query"]
  }
}
{  "name": "deep_research",  "description": "Iterative multi-source financial research agent. Searches news, SEC filings, and financial databases via internal MCP servers. Cross-verifies findings and returns a comprehensive cited report.",  "inputSchema": {    "type": "object",    "properties": {      "query": {        "type": "string",        "description": "The research question"      },      "system_instructions": {        "type": "array",        "items": { "type": "string" },        "description": "Additional constraints, e.g. 'Exclude deals below $1B'"      }    },    "required": ["query"]  }}
Authentication into the MCP endpoint uses the same JWT bearer token pattern our framework already has in utils/mcp_client.py — so you'd configure Cohere North with the endpoint URL + the server secret.
One Important Consideration
tools/call in MCP is synchronous from Cohere's perspective — it waits for the full response before showing anything. Our pipeline can take 1–3 minutes. There are two ways to handle this:
Option A — Synchronous (simpler, supported by all MCP clients)
The tools/call handler awaits the full pipeline and returns the complete report. Cohere shows a spinner while waiting. Works today with no MCP client changes.
Option B — Streaming tool results (better UX, requires MCP 0.5+ client support)
Use Server-Sent Events inside the MCP response to stream partial results. Cohere North would need to support MCP streaming — worth checking what version they run.
For a first deployment, Option A is the pragmatic choice.