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

## Project Structure
```
mcpjam-dummy-server/
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

## License

MIT
