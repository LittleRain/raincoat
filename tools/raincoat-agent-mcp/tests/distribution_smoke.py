"""Build/install/upgrade/rollback a wheel in an isolated uv home; no model calls."""
import asyncio
import email.parser
import zipfile
from packaging.version import Version
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT=Path(__file__).resolve().parents[1]


def run(args,env,cwd,**kwargs):
    result=subprocess.run([str(x) for x in args],env=env,cwd=cwd,text=True,capture_output=True,**kwargs)
    if result.returncode:raise RuntimeError(f'{args[0]} failed:\n{result.stdout}\n{result.stderr}')
    return result.stdout.strip()


async def handshake(config,env,cwd):
    entry=config['mcp_servers']['local_agents']
    async with stdio_client(StdioServerParameters(command=entry['command'],args=entry['args'],env=env,cwd=str(cwd))) as (r,w),ClientSession(r,w) as session:
        await session.initialize()
        tools=[x.name for x in (await session.list_tools()).tools]
        assert len(tools)==11,tools
        result=await session.call_tool('agent_status',{'backend':'workbuddy'})
        assert not result.isError,result
        result=await session.call_tool('agent_status',{'backend':'gpt'})
        assert not result.isError,result
    return len(tools)


def main(wheel):
    uv=shutil.which('uv');assert uv,'uv required'
    with zipfile.ZipFile(wheel) as archive:
        assert 'raincoat_agent_mcp/workbuddy.mjs' in archive.namelist()
        assert 'raincoat_agent_mcp/gpt.py' in archive.namelist()
        assert not any(x.endswith(('state.json','auth.json','runtime.json')) for x in archive.namelist())
        name=next(x for x in archive.namelist() if x.endswith('.dist-info/METADATA'))
        original=email.parser.Parser().parsestr(archive.read(name).decode())['Version']
    parsed=Version(original);next_version=f'{parsed.major}.{parsed.minor}.{parsed.micro+1}'
    with tempfile.TemporaryDirectory(prefix='raincoat-package-smoke-') as tmp:
        root=Path(tmp);home=root/'home';home.mkdir()
        env={k:v for k,v in os.environ.items() if k not in {'PYTHONPATH','PYTHONHOME','VIRTUAL_ENV','WORKBUDDY_CREDENTIAL_HELPER','LOCAL_AGENT_NODE'}}
        env.update(HOME=str(home),UV_TOOL_DIR=str(root/'tools'),UV_TOOL_BIN_DIR=str(root/'bin'),LOCAL_AGENT_MCP_STATE_DIR=str(root/'state'))
        run([uv,'tool','install','--python',sys.executable,'--force',wheel],env,home)
        cli=root/'bin/local-agent'
        version=run([cli,'--version'],env,home);assert version==original,version
        assert not (home/'.dsh').exists()
        helper_installed=False
        if os.environ.get('RAINCOAT_SMOKE_INSTALL_HELPER')=='1':
            doctor=json.loads(run([cli,'doctor','--backend','workbuddy','--install-deps'],env,home))
            assert doctor['backends']['workbuddy']['available'],doctor
            helper=doctor['backends']['workbuddy']['credential_helper']
            assert str(home/'.local/share/raincoat-agent-mcp/workbuddy') in helper
            node=doctor['backends']['workbuddy']['node']['path']
            script='import {pathToFileURL} from "node:url"; const lib=await import(pathToFileURL(process.argv[1]).href); if(!lib.m||!lib.S) throw Error("incompatible helper");'
            run([node,'--input-type=module','-e',script,helper],env,home)
            helper_installed=True
        run([cli,'setup','--client','codex','--apply'],env,home)
        configfile=home/'.codex/config.toml';before=configfile.read_text();config=tomllib.loads(before)
        assert 'bridge.py' not in before and str(ROOT) not in before
        assert asyncio.run(handshake(config,env,home))==11
        python=config['mcp_servers']['local_agents']['command']
        # The native adapters must import from the wheel, never the repository.
        imported=run([python,'-c','import raincoat_agent_mcp;print(raincoat_agent_mcp.__file__)'],env,home)
        assert str(root/'tools') in imported and str(ROOT) not in imported,imported
        # Spawn a detached installed worker; it fails before native auth because this
        # clean HOME deliberately lacks WorkBuddy product config. No model is called.
        worker_script='''import asyncio,json
from unittest.mock import patch
from raincoat_agent_mcp import bridge,shared
with patch('raincoat_agent_mcp.workbuddy.status',return_value={'installed':True,'execution_ready':True}),patch('raincoat_agent_mcp.workbuddy.validate_model'):
 state=bridge.submit_task('workbuddy','No execution; isolated package import verification',timeout_seconds=2)
result=asyncio.run(shared.wait_task(state['job_id'],5))
assert result['status']=='failed',result
print(json.dumps({'worker_status':result['status']}))
'''
        worker=json.loads(run([python,'-c',worker_script],env,home))
        # Build a synthetic next version in a separate source copy for a real upgrade.
        source=root/'next-source';shutil.copytree(ROOT,source,ignore=shutil.ignore_patterns('dist','build','*.egg-info','__pycache__'))
        (source/'src/raincoat_agent_mcp/_version.py').write_text(f'__version__ = "{next_version}"\n')
        run([sys.executable,'-c',"from setuptools.build_meta import build_wheel;build_wheel('dist')"],os.environ.copy(),source)
        next_wheel=next((source/'dist').glob('*.whl'))
        upgraded=json.loads(run([cli,'update','--from',next_wheel],env,home));assert upgraded['installed_version']==next_version,upgraded
        assert run([cli,'--version'],env,home)==next_version
        assert configfile.read_text()==before
        assert asyncio.run(handshake(config,env,home))==11
        rolled_back=json.loads(run([cli,'update','--from',wheel],env,home));assert rolled_back['installed_version']==original,rolled_back
        assert configfile.read_text()==before
        run([cli,'setup','--client','codex','--apply'],env,home)
        assert configfile.read_text()==before
        print(json.dumps({'installed_version':version,'upgrade_version':upgraded['installed_version'],'rollback_version':rolled_back['installed_version'],
            'tools':11,'checkout_independent':True,'dsh_absent':True,'independent_helper_installed':helper_installed,'worker_import':worker,'config_preserved':True}))

if __name__=='__main__':main(Path(sys.argv[1]).resolve())
