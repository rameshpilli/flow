# MCPJam Dummy Server

A simple MCP server example with an interactive UI for testing with MCPJam Inspector.

## Quick Start

### Prerequisites
- Node.js 18+
- npm or yarn

### Installation & Development
```bash
# Install dependencies
npm install

# Build the UI
npm run build

# Start the server
npm start
```

### Test with MCPJam Inspector

In another terminal:
```bash
npx @mcpjam/inspector@latest
```

Then add the server in MCPJam and test the tools!

### LLM Gateway Configuration (Optional)

To use the internal LLM gateway from your corporate environment, set:

```bash
export LLM_SERVER_URL="https://your-llm-gateway/v1/chat/completions"
export LLM_MODEL_NAME="claude-sonnet-4"

# Choose one auth method:
export LLM_API_KEY="your-api-key"
# OR OAuth:
export LLM_OAUTH_ENDPOINT="https://auth.example.com/oauth/token"
export LLM_CLIENT_ID="your-client-id"
export LLM_CLIENT_SECRET="your-client-secret"

# Optional tuning:
export LLM_TEMPERATURE="0.2"
export LLM_MAX_TOKENS="4096"
export LLM_TOP_P="0.9"
export LLM_VERIFY_SSL="true"
```

## Project Structure
```
.
├── server.ts              # MCP Server implementation
├── dummy-app.html         # HTML entry point
├── src/
│   └── dummy-app.tsx      # React UI component
├── tsconfig.json          # TypeScript config
├── vite.config.ts         # Vite bundler config
├── package.json           # Dependencies and scripts
└── dist/                  # Built output (generated)
```

## Features

- **show-dashboard**: Interactive UI tool that renders in MCPJam Inspector
- **get-status**: Regular tool that returns system status
- **llm-chat**: Calls your internal LLM gateway using env-configured credentials

## License

MIT
