"""Client configuration migration without dependency on source checkout paths."""
from pathlib import Path
import json
import os
import re
import shutil
import tomllib

# Current registration key, and every key this bridge has used before it.
SERVER_NAME='buck'
LEGACY_SERVER_NAMES=('bitto','local_agents')
LEGACY_ENTRY_IDS=('bitto-agent-bridge','local-agent-mcp','raincoat-agent-mcp')

def codex_config(text,command,entry):
    args=[entry,'mcp'] if isinstance(entry,str) else entry
    names='|'.join(LEGACY_SERVER_NAMES+(SERVER_NAME,))
    # Preserve unrelated services; drop this bridge's older and current registrations.
    text=re.sub(r'^\[mcp_servers\.(?:"(?:'+names+')"|'+names+r')(?:\.[^\]\n]+)?\][ \t]*(?:#[^\n]*)?\n.*?(?=^\[|\Z)','',text,flags=re.M|re.S)
    block='\n[mcp_servers.'+SERVER_NAME+']\ncommand = '+json.dumps(command)+'\nargs = '+json.dumps(args)+'\nstartup_timeout_sec = 20\ntool_timeout_sec = 60\n'
    result=text.rstrip()+'\n'+block
    parsed=tomllib.loads(result)
    for legacy in LEGACY_SERVER_NAMES:assert legacy not in parsed['mcp_servers']
    assert parsed['mcp_servers'][SERVER_NAME]['args']==args
    return result


def dsh_config(text,command,entry):
    args=[entry,'mcp'] if isinstance(entry,str) else entry
    block='    - id: raincoat-buck\n      name: "@deepseek-ai/dsh-mcp-client"\n      config:\n        serverName: '+SERVER_NAME+'\n        transport: stdio\n        command: '+json.dumps(command)+'\n        args: '+json.dumps(args)+'\n        failOnStartupError: true\n        reconnect:\n          enabled: true\n          initialDelayMs: 1000\n          maxDelayMs: 30000\n          maxAttempts: 1000\n'
    ids='|'.join(LEGACY_ENTRY_IDS+('raincoat-buck',))
    pattern=r'^    - id: (?:'+ids+r')\n.*?(?=^    - id:|^\S|\Z)'
    if re.search(pattern,text,flags=re.M|re.S):
        result=re.sub(pattern,lambda _:block,text,count=1,flags=re.M|re.S)
    else:result=text.rstrip()+'\n\n- insert:\n'+block
    if len(re.findall(r'^\s+serverName: '+SERVER_NAME+r'$',result,re.M))!=1:
        raise ValueError('Expected a single '+SERVER_NAME+' registration')
    for legacy in LEGACY_SERVER_NAMES:
        if re.search(r'^\s+serverName: '+legacy+r'$',result,re.M):raise ValueError('Old '+legacy+' registration remains')
    return result


def write_backed_up(path,text,stamp):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():shutil.copy2(path,path.with_name(path.name+'.before-buck-'+stamp))
    temp=path.with_name(path.name+'.tmp-'+stamp)
    with open(temp,'x',encoding='utf-8',opener=lambda p,flags:os.open(p,flags,0o600)) as f:f.write(text)
    temp.replace(path)
