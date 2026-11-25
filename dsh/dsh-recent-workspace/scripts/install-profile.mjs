#!/usr/bin/env node
/**
 * Link this bundle into a DSH profile and register it for loading.
 *
 *   node scripts/install-profile.mjs                # current profile ($DSH_PROFILE) or web
 *   node scripts/install-profile.mjs desktop        # a named profile
 *
 * This mirrors what the in-app plugin manager does when it installs a bundle
 * from a directory: a `link:` dependency in the profile package.json, an entry
 * in `dsh.profile.bundles`, and the node_modules symlink pnpm would create.
 * It is idempotent and backs up package.json before writing.
 *
 * The profile decides which app picks it up: `web` serves the browser GUI,
 * `desktop` the Electron app. A running app needs a reload to see it.
 */
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

const pkgDir = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const manifest = JSON.parse(fs.readFileSync(path.join(pkgDir, 'package.json'), 'utf8'));
const name = manifest.name;

const profile = process.argv[2] || process.env.DSH_PROFILE || 'web';
const profileDir = path.join(os.homedir(), '.dsh', 'profiles', profile);
const manifestPath = path.join(profileDir, 'package.json');
if (!fs.existsSync(manifestPath)) {
  console.error(`no such profile: ${profile} (${manifestPath})`);
  process.exit(1);
}

const raw = fs.readFileSync(manifestPath, 'utf8');
const profilePkg = JSON.parse(raw);
const spec = `link:${pkgDir}`;

const before = JSON.stringify(profilePkg);
profilePkg.dependencies = { ...(profilePkg.dependencies ?? {}), [name]: spec };
const bundles = (profilePkg.dsh ??= {}).profile?.bundles ?? [];
const profileSection = (profilePkg.dsh.profile ??= {});
if (!Array.isArray(profileSection.bundles)) profileSection.bundles = bundles;
if (!profileSection.bundles.includes(name)) profileSection.bundles.push(name);

if (JSON.stringify(profilePkg) === before) {
  console.log(`${profile}: already installed`);
} else {
  const stamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\..+/, '');
  fs.writeFileSync(`${manifestPath}.bak-recent-${stamp}`, raw);
  fs.writeFileSync(manifestPath, `${JSON.stringify(profilePkg, null, 2)}\n`);
  console.log(`${profile}: added ${name} -> ${spec}`);
}

const linksDir = path.join(profileDir, 'node_modules');
const linkPath = path.join(linksDir, name);
fs.mkdirSync(linksDir, { recursive: true });
try {
  const existing = fs.readlinkSync(linkPath);
  if (path.resolve(linksDir, existing) === pkgDir) {
    console.log(`${profile}: node_modules link ok`);
    process.exit(0);
  }
  fs.rmSync(linkPath, { force: true });
} catch {
  /* not a symlink or missing */
}
const relative = path.relative(linksDir, pkgDir);
fs.symlinkSync(relative, linkPath);
console.log(`${profile}: linked node_modules/${name} -> ${relative}`);
