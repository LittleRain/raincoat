// Run WorkBuddy's bundled Agent, keeping desktop credentials only in memory.
import {spawn} from 'node:child_process';
import {readFile} from 'node:fs/promises';
import {homedir} from 'node:os';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';

let secrets = [];
const redact = text => secrets.reduce((value, secret) => value.split(secret).join('[REDACTED]'), String(text));
const emit = event => process.stdout.write(redact(JSON.stringify(event))+'\n');

async function credentialHelper() {
  const override = process.env.WORKBUDDY_CREDENTIAL_HELPER;
  if (override) return override;
  throw new Error('Missing managed WorkBuddy helper; run local-agent doctor --backend workbuddy --install-deps');
}

async function main() {
  const request = JSON.parse(await readFile(process.argv[2],'utf8'));
  const app = '/Applications/WorkBuddy.app/Contents';
  const electron = join(app,'MacOS/Electron');
  const configPath = join(homedir(),'.workbuddy/cache/acc-product-config-v3.json');
  const product = JSON.parse(await readFile(configPath,'utf8'));
  if (product.endpoint !== 'https://www.workbuddy.cn') throw new Error('Unexpected WorkBuddy endpoint');
  if (!product.models?.some(x=>x.id === request.model)) throw new Error('Model must be an official WorkBuddy model ID');
  const custom = JSON.parse(await readFile(join(homedir(),'.workbuddy/models.json'),'utf8').catch(e=>{
    if(e.code==='ENOENT')return '[]';throw e;
  }));
  const customModels = Array.isArray(custom) ? custom : (custom.models || []);
  if (customModels.some(x=>x.id === request.model)) throw new Error('Model ID is overridden by a custom model; choose an official WorkBuddy model');
  process.env.WORKBUDDY_ELECTRON_BIN = electron;
  const lib = await import(pathToFileURL(await credentialHelper()).href);
  if (!lib.m || !lib.S) throw new Error('Unsupported WorkBuddy credential helper version (expected 0.7.9)');
  const credential = await new lib.m({variant:lib.S}).current();
  if (!credential?.accessToken || !(credential.expiresAtMs > Date.now())) throw new Error('Existing WorkBuddy login missing or expired; open WorkBuddy and sign in again');
  secrets = [credential.accessToken,credential.refreshToken].filter(Boolean);
  if (!['www.codebuddy.cn','www.workbuddy.cn'].includes(credential.domain)) throw new Error('Unexpected desktop credential domain');
  const env = Object.fromEntries(Object.entries(process.env).filter(([k])=>! /^(CODEBUDDY_|WORKBUDDY_|ACC_PRODUCT_|ANTHROPIC_|OPENAI_)/.test(k)));
  Object.assign(env,{
    ELECTRON_RUN_AS_NODE:'1',CODEBUDDY_FORCE_LITE_WB_BUNDLE:'1',CODEBUDDY_FORCE_HEADLESS_BUNDLE:'1',
    CODEBUDDY_HOST:'workbuddy-desktop',CODEBUDDY_CONFIG_DIR:join(homedir(),'.workbuddy'),WORKBUDDY_CONFIG_DIR:join(homedir(),'.workbuddy'),
    ACC_PRODUCT_CONFIG_PATH:configPath,CODEBUDDY_AUTH_TOKEN:credential.accessToken,CODEBUDDY_CREDENTIALS_IN_MEMORY:'1',
    DISABLE_AUTOUPDATER:'1',CODEBUDDY_DISABLE_CRON:'1',CODEBUDDY_API_KEY_HELPER_DISABLED:'1'
  });
  const allowed = request.allowed_tools || [];
  const tools = [...new Set(allowed.map(x=>x.split('(')[0]))].join(',');
  const args = [join(app,'Resources/app.asar/cli/bin/codebuddy'),'--print','--verbose','--output-format','stream-json',
    ...(request.resume ? ['--resume',request.session_id] : ['--session-id',request.session_id]),
    '--model',request.model,'--strict-mcp-config','--mcp-config','{"mcpServers":{}}','--tools',tools];
  if (allowed.length) args.push('--allowedTools',...allowed);
  args.push('--',request.prompt);
  const child = spawn(electron,args,{cwd:request.cwd||homedir(),env,stdio:['ignore','pipe','pipe']});
  child.stdout.setEncoding('utf8');
  child.stderr.setEncoding('utf8');
  // Parse complete lines before redaction, including secrets split across OS chunks.
  let stdout='',stderr='';
  function forward(line) {
    try {
      const event = JSON.parse(line);
      if (event.message?.content) event.message.content = event.message.content.filter(x=>x.type!=='thinking' && x.type!=='redacted_thinking');
      emit(event);
    } catch { process.stderr.write(redact(line.slice(0,4000))+'\n'); }
  }
  child.stdout.on('data',chunk=>{stdout+=chunk;let pos;while((pos=stdout.indexOf('\n'))>=0){forward(stdout.slice(0,pos));stdout=stdout.slice(pos+1);}});
  child.stderr.on('data',chunk=>{stderr+=chunk;let pos;while((pos=stderr.indexOf('\n'))>=0){process.stderr.write(redact(stderr.slice(0,pos))+'\n');stderr=stderr.slice(pos+1);}});
  child.on('error',error=>emit({type:'bridge_error',error:String(error)}));
  child.on('close',(code,signal)=>{
    if(stdout.trim())forward(stdout);
    if(stderr)process.stderr.write(redact(stderr)+'\n');
    emit({type:'bridge_exit',code,signal});
  });
}
main().catch(error=>{emit({type:'bridge_error',error:String(error)});process.exitCode=1;});
