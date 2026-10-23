"""Preview or apply a backed-up migration of Codex and desktop DeepSeek Harness."""
import argparse
from datetime import datetime
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sys
import tomllib

SOURCE=Path(__file__).resolve().parent
FILES=['bridge.py','shared.py','bitto.py','workbuddy.py','workbuddy.mjs','requirements.txt','README.md']


def codex_config(text,command,entry):
    # Replace only this bridge's registrations, preserving all unrelated sections.
    text=re.sub(r'^\[mcp_servers\.(?:"(?:bitto|local_agents)"|bitto|local_agents)(?:\.[^\]\n]+)?\][ \t]*(?:#[^\n]*)?\n.*?(?=^\[|\Z)','',text,flags=re.M|re.S)
    block='\n[mcp_servers.local_agents]\ncommand = '+json.dumps(command)+'\nargs = '+json.dumps([entry,'mcp'])+'\nstartup_timeout_sec = 20\ntool_timeout_sec = 60\n'
    result=text.rstrip()+'\n'+block
    parsed=tomllib.loads(result)
    assert 'bitto' not in parsed['mcp_servers']
    assert parsed['mcp_servers']['local_agents']['args']==[entry,'mcp']
    return result


def dsh_config(text,command,entry):
    block='    - id: local-agent-mcp\n      name: "@deepseek-ai/dsh-mcp-client"\n      config:\n        serverName: local_agents\n        transport: stdio\n        command: '+json.dumps(command)+'\n        args: '+json.dumps([entry,'mcp'])+'\n        failOnStartupError: true\n'
    pattern=r'^    - id: (?:bitto-agent-bridge|local-agent-mcp)\n.*?(?=^    - id:|^\S|\Z)'
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


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    if sys.version_info<(3,11):raise RuntimeError('Python 3.11+ required')
    for name in ['mcp','websockets']:importlib.metadata.version(name)
    home=Path.home();prefix=home/'.local/share/local-agent-mcp'
    digest=hashlib.sha256(b''.join((SOURCE/f).read_bytes() for f in FILES)).hexdigest()[:16]
    release=prefix/'releases'/digest;current=prefix/'current';entry=str(current/'bridge.py')
    command=sys.executable
    codex=home/'.codex/config.toml';dsh=home/'.dsh/profiles/desktop/cordis.patch.yml'
    updates={codex:codex_config(codex.read_text(),command,entry),dsh:dsh_config(dsh.read_text(),command,entry)}
    updates[home/'.local/bin/local-agent']='#!/bin/sh\nexec '+shlex.quote(command)+' '+shlex.quote(entry)+' "$@"\n'
    updates[home/'.local/bin/bitto-agent']='#!/bin/sh\ncommand_name="$1"\nshift\ncase "$command_name" in\n  submit|status) exec '+shlex.quote(command)+' '+shlex.quote(entry)+' "$command_name" bitto "$@" ;;\n  *) exec '+shlex.quote(command)+' '+shlex.quote(entry)+' "$command_name" "$@" ;;\nesac\n'
    print(json.dumps({'apply':args.apply,'runtime_release':str(release),'update_files':[str(p) for p in updates]},indent=2))
    if not args.apply:return
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    release.mkdir(parents=True,exist_ok=True,mode=0o700)
    for name in FILES:
        shutil.copyfile(SOURCE/name,release/name);(release/name).chmod(0o600)
    manifest={'source':str(SOURCE),'content_digest':digest,'installed_at':stamp,'python':command,'node':shutil.which('node')}
    (release/'install.json').write_text(json.dumps(manifest,indent=2));(release/'install.json').chmod(0o600)
    link=prefix/('current.tmp-'+stamp);link.symlink_to(release);link.replace(current)
    for path,text in updates.items():
        write_backed_up(path,text,stamp)
        if path.parent==home/'.local/bin':path.chmod(0o755)
    print('Installed. Reload MCP clients to load local_agents; previous configurations have timestamped backups.')

if __name__=='__main__':main()
