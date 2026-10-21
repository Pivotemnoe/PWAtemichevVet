import { build } from 'esbuild';
import { cp, mkdir, readFile, writeFile, rm } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const out = path.join(root, 'dist');
const platform = process.env.TVV_PLATFORM || 'android';
if (!['android', 'ios'].includes(platform)) throw new Error('Unknown native platform');
const packageInfo = JSON.parse(await readFile(path.join(root, 'package.json'), 'utf8'));
const apiBase = process.env.TVV_API_BASE || 'https://temichevvet.ru';
const apiUrl = new URL(apiBase);
if (apiUrl.username || apiUrl.password || apiUrl.pathname !== '/' || apiUrl.search || apiUrl.hash) throw new Error('API must be a plain origin');
if (apiUrl.protocol !== 'https:' && !(process.env.TVV_DEBUG_API === '1' && apiUrl.protocol === 'http:' && ['10.0.2.2', '127.0.0.1'].includes(apiUrl.hostname))) throw new Error('HTTPS is required');
// Only this generated directory is replaced; no credentials or database are copied.
await rm(out, { recursive: true, force: true });
await mkdir(path.join(out, 'static'), { recursive: true });
await cp(path.join(root, 'web'), path.join(out, 'static'), { recursive: true });
let html = await readFile(path.join(root, 'web/index.html'), 'utf8');
html = html.replace(/<script src="https:\/\/st\.max\.ru[^>]+><\/script>/, '')
  .replace(/<script src="\/static\/app\.js[^>]+><\/script>/, '<script src="/static/native.js" type="module"></script>');
await writeFile(path.join(out, 'index.html'), html);
await writeFile(path.join(out, 'mobile-build.json'), JSON.stringify({ platform, appVersion: packageInfo.version, apiOrigin: apiUrl.origin,
  debugApi: process.env.TVV_DEBUG_API === '1', builtAt: new Date().toISOString() }, null, 2) + '\n');
await build({ entryPoints: [path.join(root, platform === 'ios' ? 'mobile/ios-entry.js' : 'mobile/native-entry.js')], outfile: path.join(out, 'static/native.js'),
  bundle: true, format: 'esm', target: 'es2022', minify: true,
  define: { __TVV_API_BASE__: JSON.stringify(apiUrl.origin), __TVV_DEBUG_API__: JSON.stringify(process.env.TVV_DEBUG_API === '1') } });
console.log(`${platform} assets built; API: ${apiUrl.origin}`);
