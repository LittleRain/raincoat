#!/usr/bin/env node
/**
 * Build `lib/client.js` for dsh-recent-workspace.
 *
 * The plugin replaces the sidebar "workspaces" browser with a patched copy of
 * @deepseek-ai/dsh-client-ui-workspace (the official package keeps its slot;
 * we disable its row and occupy `sidebar.workspaces` ourselves). Instead of
 * vendoring 250 KB of TSX and a CSS-module pipeline, this script takes the
 * *shipped* client bundle, which is unminified and has only five external
 * requires, and applies a small number of anchored splices. Every anchor is
 * asserted, so a DSH upgrade that changes the shape fails the build loudly
 * instead of shipping a silently broken sidebar.
 *
 * Run: node scripts/build.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const UPSTREAM = '@deepseek-ai/dsh-client-ui-workspace';
const OUT = path.join(ROOT, 'lib', 'client.js');
const META = path.join(ROOT, 'lib', 'build-meta.json');
const PKG_ID = 'dsh-recent-workspace';

const dshBinary =
  process.env.DSH_NODE_EXECUTABLE || '/Applications/DeepSeek Harness.app/Contents/MacOS/DeepSeek Harness';

const candidates = [
  process.env.DSH_UI_WORKSPACE_DIR,
  '/Applications/DeepSeek Harness.app/Contents/Resources/app.asar/dsh/node_modules',
  ...(process.env.DSH_INSTALL_DIR
    ? [path.resolve(process.env.DSH_INSTALL_DIR, '..', '..')]
    : []),
  path.join(process.env.HOME || '', '.dsh/profiles/web/node_modules'),
].filter(Boolean);

/** Existence cannot be probed inside app.asar with plain fs, so probe by reading. */
function findUpstream() {
  for (const base of candidates) {
    const dir = path.join(base, UPSTREAM);
    try {
      const raw = readThroughAsar(path.join(dir, 'package.json'));
      return { dir, pkg: JSON.parse(raw) };
    } catch {
      /* not here */
    }
  }
  return undefined;
}

/** The installer lives inside app.asar, which only Electron's fs can read. */
function readThroughAsar(file) {
  try {
    return fs.readFileSync(file, 'utf8');
  } catch (error) {
    if (!String(error?.message || '').match(/asar|ENOTDIR|ENOENT/)) throw error;
    const script =
      'const fs=require("fs");process.stdout.write(fs.readFileSync(process.argv[1],"utf8"))';
    const result = spawnSync(dshBinary, ['-e', script, file], {
      env: { ...process.env, ELECTRON_RUN_AS_NODE: '1' },
      maxBuffer: 64 * 1024 * 1024,
    });
    if (result.status !== 0) {
      throw new Error(
        `cannot read ${file}\nset DSH_NODE_EXECUTABLE to the Harness binary if it is not at the default path\n${result.stderr}`,
      );
    }
    return String(result.stdout);
  }
}

const found = findUpstream();
if (found === undefined) {
  console.error('build: cannot locate', UPSTREAM, '\nlooked in:\n  ' + candidates.join('\n  '));
  process.exit(1);
}
const upstreamDir = found.dir;
const upstreamPkg = found.pkg;
const source = readThroughAsar(path.join(upstreamDir, 'lib', 'client.js'));
const prelude = fs.readFileSync(path.join(ROOT, 'src', 'recent.prelude.js'), 'utf8').trim();

/** Anchor table: [label, find, replace, expectedCount?] is expressed as objects. */
const edits = [
  {
    label: 'wrapper-id',
    find: 'window.__ModuleLoader__.load({id:`' + UPSTREAM + '`',
    replace: 'window.__ModuleLoader__.load({id:`' + PKG_ID + '`',
  },
  {
    label: 'prelude',
    find: 'let react_jsx_runtime=require("react/jsx-runtime");',
    replace: 'let react_jsx_runtime=require("react/jsx-runtime");\n' + prelude + '\n',
  },
  {
    label: 'session-tree-props',
    find: 'function SessionTree({list,',
    replace: 'function SessionTree({recentManualOrder,list,',
  },
  {
    label: 'groups',
    find:
      'const groups=(0,react.useMemo)(()=>deriveGroups(list,workspaces,rowState,statuses,{expandedGroups,ungroupedOrder:ungroupedSessionIds}),[list,workspaces,rowState,statuses,expandedGroups,ungroupedSessionIds]);',
    replace:
      'const baseGroups=(0,react.useMemo)(()=>deriveGroups(list,workspaces,rowState,statuses,{expandedGroups,ungroupedOrder:ungroupedSessionIds}),[list,workspaces,rowState,statuses,expandedGroups,ungroupedSessionIds]);' +
      'const groups=(0,react.useMemo)(()=>withRecentSection(baseGroups,list,rowState,statuses,groupExpansion,recentManualOrder,nestWorkspaces),[baseGroups,list,rowState,statuses,groupExpansion,recentManualOrder,nestWorkspaces]);',
  },
  {
    label: 'watermark',
    find:
      'const watermark=sessionWatermarks[group.key]??SESSION_WATERMARK_BASE;const collapsed=watermarkRows(group.sessions,baselines.get(group.key)??SESSION_WATERMARK_BASE);',
    replace:
      'const recentGroup=group.key===RECENT_KEY;' +
      'const watermark=recentGroup?RECENT_LIMIT:(sessionWatermarks[group.key]??SESSION_WATERMARK_BASE);' +
      'const collapsed=watermarkRows(group.sessions,recentGroup?RECENT_LIMIT:(baselines.get(group.key)??SESSION_WATERMARK_BASE));',
  },
  {
    label: 'collapse',
    find: 'const sessions=visible.rows;',
    replace: 'const sessions=group.key===RECENT_KEY&&!group.expanded?[]:visible.rows;',
  },
  {
    label: 'label',
    find: 'const label=row.workspaceId===void 0?t(`group.ungrouped`):row.label;',
    replace:
      'const label=row.key===RECENT_KEY?t(`recent.section`):row.workspaceId===void 0?t(`group.ungrouped`):row.label;',
  },
  {
    label: 'session-tree-call',
    find: 'setGroupExpanded:actions.setGroupExpanded,setSessionOrder:saveSessionOrder,rowState',
    replace:
      'setGroupExpanded:actions.setGroupExpanded,setSessionOrder:saveSessionOrder,recentManualOrder:orderBy===`manual`,rowState',
  },
];

/** Section title per locale; the upstream bundle already carries all dictionaries. */
const labels = {
  zh: '最近',
  en: 'Recent',
  ja: '最近',
  es: 'Recientes',
  fr: 'Récents',
  de: 'Neueste',
  ru: 'Недавние',
  pt: 'Recentes',
};

function applyEdit(text, edit) {
  const count = text.split(edit.find).length - 1;
  const expected = edit.expected ?? 1;
  if (count !== expected) {
    throw new Error(
      `anchor "${edit.label}" matched ${count} times, expected ${expected}\n` +
        `  find: ${edit.find.slice(0, 140)}${edit.find.length > 140 ? '…' : ''}`,
    );
  }
  return text.replace(edit.find, () => edit.replace);
}

let out = source;
for (const edit of edits) out = applyEdit(out, edit);

for (const [lang, label] of Object.entries(labels)) {
  out = applyEdit(out, {
    label: `locale-${lang}`,
    find: 'const ' + lang + '={',
    replace: 'const ' + lang + '={"recent.section":`' + label + '`,',
  });
}

const checkOnly = process.argv.includes('--check');
if (checkOnly) {
  console.log(
    `compat ok: ${edits.length + Object.keys(labels).length} anchors match ` +
      `${UPSTREAM}@${upstreamPkg.version} (no files written)`,
  );
  process.exit(0);
}

fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, out);
fs.writeFileSync(
  META,
  JSON.stringify(
    {
      upstream: UPSTREAM,
      upstreamVersion: upstreamPkg.version,
      upstreamClientBytes: Buffer.byteLength(source),
      clientBytes: Buffer.byteLength(out),
      anchors: edits.map((edit) => edit.label),
      builtAt: new Date().toISOString(),
    },
    null,
    2,
  ) + '\n',
);

console.log(
  `built lib/client.js from ${UPSTREAM}@${upstreamPkg.version} ` +
    `(${Buffer.byteLength(source)} → ${Buffer.byteLength(out)} bytes, ${edits.length + Object.keys(labels).length} splices)`,
);
