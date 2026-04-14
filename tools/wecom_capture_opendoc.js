#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');
const { spawnSync } = require('child_process');

function parseArgs(argv) {
  const out = {
    url: '',
    outDir: '/tmp',
    profileDir: '/tmp/wecom-playwright-profile',
    prefix: '',
    waitMs: 120000,
    timeoutMs: 45000,
    headless: false,
  };

  for (let i = 2; i < argv.length; i += 1) {
    const a = argv[i];
    const next = argv[i + 1];
    if (a === '--url') {
      out.url = next || '';
      i += 1;
    } else if (a === '--out-dir') {
      out.outDir = next || out.outDir;
      i += 1;
    } else if (a === '--profile-dir') {
      out.profileDir = next || out.profileDir;
      i += 1;
    } else if (a === '--prefix') {
      out.prefix = next || '';
      i += 1;
    } else if (a === '--wait-ms') {
      out.waitMs = Number(next || out.waitMs);
      i += 1;
    } else if (a === '--timeout-ms') {
      out.timeoutMs = Number(next || out.timeoutMs);
      i += 1;
    } else if (a === '--headless') {
      out.headless = true;
    }
  }
  return out;
}

function mustMkdir(p) {
  fs.mkdirSync(p, { recursive: true });
}

function parseDocId(url) {
  const m = String(url).match(/\/doc\/(w3_[A-Za-z0-9]+)/);
  if (m) return m[1];
  return '';
}

function keepString(s) {
  if (!s) return false;
  const t = String(s).replace(/\s+/g, ' ').trim();
  const hasCjk = /[\u4e00-\u9fff]/.test(t);
  if (!t || t.length < 2) return false;
  if (t.length > 800) return false;
  if (/^https?:\/\//.test(t)) return false;
  if (/^[\d\s.,:%\-+()/]+$/.test(t)) {
    const digits = t.replace(/\D/g, '');
    if (digits.length >= 10) return false; // likely timestamp/noise
    if (t.length <= 2 && !/%/.test(t)) return false;
    return true; // preserve metric-like numeric cells in tables
  }
  if (/^[A-Za-z0-9_\-=+/.:,;#%\s]+$/.test(t) && !/(mall\.|maill\.|->|→)/.test(t)) {
    const allowAscii = /(mall-|feature\/|snapshot|groupid|artifactid|<version>|@schema|public class|private\s+\w+|api\/|itemqueryservice|ticket-|\.java|\.xml)/i.test(
      t
    );
    if (!allowAscii) return false;
  }
  if (/^[{}\[\]",]+$/.test(t)) return false;
  if (!hasCjk && t.length > 120) return false;
  if (/function\(|=>|var\s|const\s|window\.|<\/?[a-z]/i.test(t) && !hasCjk) {
    const allowTagLine = /<(groupid|artifactid|version)>/i.test(t);
    if (!allowTagLine) return false;
  }
  return true;
}

function decodeBase64Maybe(s) {
  const t = String(s || '').trim();
  if (t.length < 256) return '';
  if (!/^[A-Za-z0-9+/=]+$/.test(t)) return '';
  try {
    const b = Buffer.from(t, 'base64');
    if (!b || b.length < 128) return '';
    return b.toString('utf8');
  } catch (_) {
    return '';
  }
}

function emitCandidate(text, out) {
  const normalized = String(text)
    .replace(/\r/g, '\n')
    .replace(/[\x00-\x09\x0B-\x1F]/g, '\n');
  const lines = normalized.split('\n');
  for (const raw of lines) {
    const t = raw.replace(/\s+/g, ' ').trim();
    if (keepString(t)) out.push(t);
  }
}

function collectText(node, out) {
  if (node == null) return;
  if (typeof node === 'string') {
    const maybeDecoded = decodeBase64Maybe(node);
    if (maybeDecoded) emitCandidate(maybeDecoded, out);
    emitCandidate(node, out);
    return;
  }
  if (Array.isArray(node)) {
    for (const x of node) collectText(x, out);
    return;
  }
  if (typeof node === 'object') {
    for (const k of Object.keys(node)) collectText(node[k], out);
  }
}

function uniq(arr) {
  const seen = new Set();
  const out = [];
  for (const x of arr) {
    if (!seen.has(x)) {
      seen.add(x);
      out.push(x);
    }
  }
  return out;
}

async function main() {
  const args = parseArgs(process.argv);
  if (!args.url) {
    console.error('Usage: node tools/wecom_capture_opendoc.js --url <wecom_doc_url> [--out-dir /tmp] [--wait-ms 120000]');
    process.exit(1);
  }

  const docId = parseDocId(args.url);
  const prefix = args.prefix || (docId ? `wecom_${docId}` : 'wecom_doc');
  mustMkdir(args.outDir);
  mustMkdir(args.profileDir);

  const hitsPath = path.join(args.outDir, `${prefix}_network_hits.json`);
  const opendocPath = path.join(args.outDir, `${prefix}_opendoc.json`);
  const keyframePath = path.join(args.outDir, `${prefix}_keyframe.json`);
  const fullTextPath = path.join(args.outDir, `${prefix}_full_fidelity.md`);
  const forAiPath = path.join(args.outDir, `${prefix}_for_ai.md`);
  const draftPath = path.join(args.outDir, `${prefix}_decoded_draft.md`);

  const hits = [];
  let opendocPayload = null;
  let opendocLen = 0;
  const addonPayloads = [];

  const context = await chromium.launchPersistentContext(args.profileDir, {
    channel: 'chrome',
    headless: args.headless,
    viewport: null,
  });

  const page = context.pages()[0] || (await context.newPage());

  page.on('response', async (resp) => {
    const url = resp.url();
    if (!url.includes('doc.weixin.qq.com')) return;

    const headers = resp.headers();
    const ct = String(headers['content-type'] || '');
    const status = resp.status();

    const hit = { url, status, ct, len: 0, sample: '' };

    try {
      const body = await resp.text();
      hit.len = body.length;
      hit.sample = body.slice(0, 400);

      if (url.includes('/dop-api/opendoc') && body) {
        try {
          const parsed = JSON.parse(body);
          if (body.length >= opendocLen) {
            opendocPayload = parsed;
            opendocLen = body.length;
          }
        } catch (_) {
          if (body.length >= opendocLen) {
            opendocPayload = { raw: body };
            opendocLen = body.length;
          }
        }
      }

      if (url.includes('/flowchart-addon') && body) {
        addonPayloads.push(body);
      }
    } catch (_) {
      // ignore unreadable bodies
    }

    hits.push(hit);
  });

  await page.goto(args.url, { waitUntil: 'domcontentloaded', timeout: args.timeoutMs });

  const start = Date.now();
  while (Date.now() - start < args.waitMs) {
    // Trigger lazy-load/chunk fetch for long docs.
    await page.evaluate(() => {
      try {
        const h = document.body ? document.body.scrollHeight : 0;
        window.scrollTo(0, h);
      } catch (_) {
        // ignore
      }
    }).catch(() => {});
    await page.waitForTimeout(1000);
  }

  fs.writeFileSync(hitsPath, JSON.stringify(hits, null, 2), 'utf8');

  if (!opendocPayload) {
    console.error(`No opendoc payload captured. Please confirm login in opened Chrome and rerun. network hits: ${hitsPath}`);
    await context.close();
    process.exit(2);
  }
  fs.writeFileSync(opendocPath, JSON.stringify(opendocPayload, null, 2), 'utf8');

  let keyframeObj = null;
  try {
    const keyframeRaw = await page.evaluate(() => {
      if (typeof window.generateDocumentKeyFrame !== 'function') return '';
      return window.generateDocumentKeyFrame() || '';
    });
    if (keyframeRaw && typeof keyframeRaw === 'string' && keyframeRaw.length > 1000) {
      keyframeObj = JSON.parse(keyframeRaw);
      fs.writeFileSync(keyframePath, JSON.stringify(keyframeObj, null, 2), 'utf8');
    }
  } catch (_) {
    // fallback to opendoc decode path
  }

  const lines = [];
  if (keyframeObj) {
    collectText(keyframeObj, lines);
  }
  collectText(opendocPayload, lines);
  for (const raw of addonPayloads) {
    try {
      const parsed = JSON.parse(raw);
      collectText(parsed, lines);
    } catch (_) {
      emitCandidate(raw, lines);
    }
  }

  const textLines = uniq(lines);
  if (keyframeObj && Array.isArray(keyframeObj.commands)) {
    const full = [];
    for (const cmd of keyframeObj.commands) {
      const muts = Array.isArray(cmd?.mutations) ? cmd.mutations : [];
      for (const m of muts) {
        if (typeof m?.s === 'string' && m.s.trim()) {
          full.push(m.s.replace(/\r/g, '\n'));
        }
      }
    }
    const fullMd = [
      '# WeCom Doc Full Fidelity',
      '',
      `- source: ${args.url}`,
      `- captured_at: ${new Date().toISOString()}`,
      '',
      '## Content (mutation.s raw)',
      '',
      full.join('\n'),
      '',
    ].join('\n');
    fs.writeFileSync(fullTextPath, fullMd, 'utf8');

    // Minimal-clean version for AI ingestion: keep order/content, only remove control chars.
    const aiMd = fullMd
      .split('')
      .map((ch) => {
        const code = ch.charCodeAt(0);
        if (ch === '\n' || ch === '\t' || code >= 32) return ch;
        return ' ';
      })
      .join('')
      .replace(/\n{4,}/g, '\n\n\n');
    fs.writeFileSync(forAiPath, aiMd, 'utf8');
  }

  const md = [
    '# WeCom Doc Decoded Draft',
    '',
    `- source: ${args.url}`,
    `- captured_at: ${new Date().toISOString()}`,
    `- network_hits: ${hits.length}`,
    `- addon_hits: ${addonPayloads.length}`,
    '',
    '## Content (cleaned draft)',
    '',
    ...textLines,
    '',
  ].join('\n');

  fs.writeFileSync(draftPath, md, 'utf8');
  console.log(`WROTE ${hitsPath}`);
  console.log(`WROTE ${opendocPath}`);
  if (keyframeObj) console.log(`WROTE ${keyframePath}`);
  if (fs.existsSync(fullTextPath)) console.log(`WROTE ${fullTextPath}`);
  if (fs.existsSync(forAiPath)) console.log(`WROTE ${forAiPath}`);
  console.log(`WROTE ${draftPath}`);

  const py = spawnSync('python3', [
    path.join(__dirname, 'wecom_archive.py'),
    '--draft',
    draftPath,
    '--out-dir',
    args.outDir,
    '--prefix',
    prefix,
  ], { stdio: 'inherit' });

  await context.close();

  if (py.status !== 0) {
    process.exit(py.status || 1);
  }
}

main().catch((err) => {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
