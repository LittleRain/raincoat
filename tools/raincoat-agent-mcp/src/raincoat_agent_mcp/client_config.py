"""Client configuration migration without dependency on source checkout paths."""
from pathlib import Path
import json
import os
import re
import shutil
import tomllib

def codex_config(text,command,entry):
    args=[entry,'mcp'] if isinstance(entry,str) else entry
    # Preserve unrelated services.
    text=re.sub(r'^\[mcp_servers\.(?:"(?:bitto|local_agents)"|bitto|local_agents)(?:\.[^\]\n]+)?\][ \t]*(?:#[^\n]*)?\n.*?(?=^\[|\Z)','',text,flags=re.M|re.S)
    block='\n[mcp_servers.local_agents]\ncommand = '+json.dumps(command)+'\nargs = '+json.dumps(args)+'\nstartup_timeout_sec = 20\ntool_timeout_sec = 60\n'
    result=text.rstrip()+'\n'+block
    parsed=tomllib.loads(result)
    assert 'bitto' not in parsed['mcp_servers']
    assert parsed['mcp_servers']['local_agents']['args']==args
    return result


def dsh_config(text,command,entry):
    args=[entry,'mcp'] if isinstance(entry,str) else entry
    block='    - id: raincoat-agent-mcp\n      name: "@deepseek-ai/dsh-mcp-client"\n      config:\n        serverName: local_agents\n        transport: stdio\n        command: '+json.dumps(command)+'\n        args: '+json.dumps(args)+'\n        failOnStartupError: true\n'
    pattern=r'^    - id: (?:bitto-agent-bridge|local-agent-mcp|raincoat-agent-mcp)\n.*?(?=^    - id:|^\S|\Z)'
    if re.search(pattern,text,flags=re.M|re.S):
        result=re.sub(pattern,lambda _:block,text,count=1,flags=re.M|re.S)
    else:result=text.rstrip()+'\n\n- insert:\n'+block
    if len(re.findall(r'^\s+serverName: local_agents$',result,re.M))!=1:
        raise ValueError('Expected a single local_agents registration')
    if re.search(r'^\s+serverName: bitto$',result,re.M):raise ValueError('Old Bitto registration remains')
    return result


def write_backed_up(path,text,stamp):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():shutil.copy2(path,path.with_name(path.name+'.before-local-agents-'+stamp))
    temp=path.with_name(path.name+'.tmp-'+stamp)
    with open(temp,'x',opener=lambda p,flags:os.open(p,flags,0o600)) as f:f.write(text)
    temp.replace(path)
