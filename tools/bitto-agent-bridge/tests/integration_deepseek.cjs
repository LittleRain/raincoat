// Run with the installed DeepSeek Harness Electron runtime in Node mode.
const { createRequire } = require('node:module');
const path = require('node:path');
const req = createRequire('/Applications/DeepSeek Harness.app/Contents/Resources/app.asar/dsh/package.json');
const { Client } = req('@modelcontextprotocol/client');
const { StdioClientTransport } = req('@modelcontextprotocol/client/stdio');
(async () => {
  const client = new Client({name:'dsh-bitto-bridge-verification',version:'1.0.0'}, {
    capabilities:{},versionNegotiation:{mode:'auto'}
  });
  try {
    await client.connect(new StdioClientTransport({
      command:'/opt/homebrew/opt/python@3.14/bin/python3.14',
      args:[path.resolve(__dirname,'../bridge.py'),'mcp']
    }));
    const listed = await client.listTools();
    if (listed.tools.length !== 5) throw new Error('Expected 5 tools');
    const result = await client.callTool({name:'bitto_status',arguments:{}});
    if (result.isError) throw new Error(JSON.stringify(result));
    process.stdout.write(JSON.stringify({deepseek_bundled_sdk:'PASS',tools:listed.tools.map(t=>t.name),status:result.structuredContent},null,2)+'\n');
  } finally { await client.close(); }
})().catch(e=>{console.error(e);process.exitCode=1;});
