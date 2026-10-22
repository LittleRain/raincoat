"""Generate current-machine MCP config; does not change any client settings."""
from pathlib import Path
import json
import sys

def main():
    root=Path(__file__).resolve().parent
    out=root/'config/generated';out.mkdir(parents=True,exist_ok=True)
    command={'command':sys.executable,'args':[str(root/'bridge.py'),'mcp']}
    (out/'mcp.json').write_text(json.dumps({'mcpServers':{'local_agents':command}},ensure_ascii=False,indent=2)+'\n')
    (out/'codex.toml').write_text('[mcp_servers.local_agents]\ncommand = '+json.dumps(command['command'])+'\nargs = '+json.dumps(command['args'])+'\nstartup_timeout_sec = 20\ntool_timeout_sec = 60\n')
    (out/'deepseek.patch.yml').write_text('- insert:\n    - id: local-agent-mcp\n      name: "@deepseek-ai/dsh-mcp-client"\n      config:\n        serverName: local_agents\n        transport: stdio\n        command: '+json.dumps(command['command'])+'\n        args: '+json.dumps(command['args'])+'\n        failOnStartupError: true\n')
    print(out)
if __name__=='__main__':main()
