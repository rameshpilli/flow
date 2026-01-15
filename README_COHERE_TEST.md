# Cohere Compass Test Suite

This test suite helps you understand what features are available in your corporate Cohere deployment.

## 📋 What You Have

According to what you provided, you have:
- ✅ Cohere index name
- ✅ Server URL
- ✅ Server bearer token
- ✅ Parser URL
- ✅ Parser bearer token

## 🚀 How to Run Tests

### Option 1: Interactive Test (Full Suite)

This will ask you for your credentials and run comprehensive tests:

```bash
# Install dependency
pip install httpx

# Run interactive test
python cohere_compass_test.py
```

**When prompted, enter:**
1. Server URL (e.g., `https://cohere.yourcompany.com`)
2. Server Bearer Token (your token)
3. Index Name (your index name)
4. Parser URL (if you have it)
5. Parser Bearer Token (if you have parser)

**Output:**
- ✅ What features work
- ❌ What features are missing
- 📊 Detailed test results
- 📄 `cohere_test_results.json` with full details

---

### Option 2: Simple Test (Quick Check)

Edit configuration in the file and run:

```bash
# 1. Edit cohere_compass_test_simple.py
# Update CONFIG section with your values:
#   - server_url
#   - server_bearer_token
#   - index_name
#   - parser_url (optional)
#   - parser_bearer_token (optional)

# 2. Run test
python cohere_compass_test_simple.py
```

**Output:**
- Quick pass/fail for core features
- Configuration snippet for mem0
- `cohere_quick_test_results.json` with results

---

## 🧪 What Gets Tested

### Test 1: Server Connectivity
- ✅ Can we reach the server?
- ✅ Is the URL correct?

### Test 2: Authentication
- ✅ Does the bearer token work?
- ✅ Are we authorized?

### Test 3: Embedding Generation
- ✅ Can we generate embeddings?
- ✅ What's the embedding dimension?
- ✅ Which endpoint works?

### Test 4: Index Operations
- ✅ Does the index exist?
- ✅ Can we list indexes?
- ✅ Can we get index info?

### Test 5: Document Operations
- ✅ Can we add documents?
- ✅ Can we search documents?
- ✅ Which endpoints work?

### Test 6: Parser Service (Optional)
- ✅ Is parser available?
- ✅ Can we parse documents?
- ✅ Does chunking work?

### Test 7: Available Models
- ✅ What embedding models are available?
- ✅ What versions?

---

## 📊 Expected Results

### ✅ If Everything Works:
```
🎉 READY FOR MEM0 INTEGRATION!

Available Capabilities:
  ✅ Server connectivity
  ✅ Authentication working
  ✅ Embeddings (1024D) via /v1/embed
  ✅ Document storage via /v1/indexes/your-index/documents
  ✅ Vector search via /v1/indexes/your-index/search
  ✅ Parser service via /v1/parse

Next steps:
  1. Update mem0 config with these endpoints
  2. Configure vector store to use Cohere Compass
  3. Test with mem0 client
```

### ⚠️ If Something's Missing:
```
NOT READY - Missing capabilities

Missing/Failed:
  ❌ Cannot add documents
  ❌ Cannot search documents

You need to resolve:
  • Contact platform team for API documentation
  • Check required permissions/scopes
  • Verify index exists and is accessible
```

---

## 🔍 Common Issues & Solutions

### Issue 1: "Server not reachable"
**Possible causes:**
- Wrong URL
- Network firewall blocking
- VPN required

**Solution:**
```bash
# Test with curl
curl -H "Authorization: Bearer your_token" https://your-server-url/
```

### Issue 2: "Authentication failed"
**Possible causes:**
- Wrong bearer token
- Token expired
- Missing permissions

**Solution:**
- Check token with your platform team
- Regenerate token if expired
- Request correct scopes/permissions

### Issue 3: "Could not generate embeddings"
**Possible causes:**
- Embedding endpoint different from standard
- Model name incorrect
- Insufficient quota

**Solution:**
- Ask platform team for API documentation
- Try different model names: `embed-english-v3.0`, `embed-multilingual-v3.0`
- Check usage limits

### Issue 4: "Index not found"
**Possible causes:**
- Index name is incorrect
- Index hasn't been created
- No access to index

**Solution:**
- Verify index name with platform team
- Request index creation if needed
- Check access permissions

---

## 📝 What to Ask Your Platform Team

If tests fail, ask for:

### 1. API Documentation
```
"Can you share the API documentation for our Cohere deployment?"
```

### 2. Endpoint URLs
```
"What are the correct endpoints for:
  - Generating embeddings
  - Adding documents to index
  - Searching documents
  - Listing available models"
```

### 3. Index Setup
```
"Does the index '{your-index-name}' exist?
If not, can you create it with:
  - Dimension: 1024 (for embed-english-v3.0)
  - Metric: cosine similarity"
```

### 4. Permissions
```
"What permissions/scopes does my bearer token have?
I need:
  - Read/write access to index
  - Embedding generation
  - Document search"
```

### 5. Model Names
```
"What embedding models are available?
Are they:
  - embed-english-v3.0
  - embed-multilingual-v3.0
  - Other?"
```

---

## 🎯 Integration with mem0

Once tests pass, you'll get output like:

```bash
Configuration for mem0:
  COHERE_SERVER_URL=https://cohere.yourcompany.com
  COHERE_BEARER_TOKEN=<your-token>
  COHERE_INDEX_NAME=agent_memories
  COHERE_EMBED_ENDPOINT=/v1/embed
  COHERE_ADD_ENDPOINT=/v1/indexes/agent_memories/documents
  COHERE_SEARCH_ENDPOINT=/v1/indexes/agent_memories/search
```

**Next steps:**
1. I'll update mem0 configuration with these values
2. Create custom Cohere Compass adapter for mem0
3. Test end-to-end integration
4. Update deployment (Docker, Helm) to use Compass

---

## 📦 Requirements

```bash
pip install httpx
```

That's it! No other dependencies needed.

---

## 🤝 Need Help?

After running the tests:

1. **If all tests pass:**
   - Share the output with me
   - I'll help integrate with mem0

2. **If some tests fail:**
   - Share `cohere_test_results.json`
   - Share error messages
   - I'll help troubleshoot

3. **If you need more details:**
   - Ask your platform team the questions above
   - Run tests again with updated info

---

## 📧 Example Request to Platform Team

```
Hi Platform Team,

I'm integrating our Cohere Compass deployment with our memory store service.

I have:
- Server URL: https://cohere.ourcompany.com
- Bearer token: <my-token>
- Index name: agent_memories

Can you please confirm:
1. Is this the correct API endpoint?
2. What endpoints should I use for:
   - Generating embeddings
   - Adding documents to the index
   - Searching documents
3. Does the index "agent_memories" exist? If not, can you create it?
4. What embedding model should I use? (embed-english-v3.0?)
5. Are there any API documentation/examples available?

I'm running a test script that tries common endpoints but want to confirm
the correct ones for our deployment.

Thanks!
```

---

**Ready to run the tests!** Let me know what results you get. 🚀
