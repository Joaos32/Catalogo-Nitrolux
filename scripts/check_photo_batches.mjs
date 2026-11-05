// Execute the actual TypeScript API client against a bounded, synthetic server.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";

const require = createRequire(new URL("../frontend/package.json", import.meta.url));
const ts = require("typescript");
const source = await readFile(new URL("../frontend/src/lib/catalog-api.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022 },
}).outputText.replace(/import \{ API_BASES, REQUEST_TIMEOUT_MS \} from "\.\/catalog-core";/,
  'const API_BASES = [""]; const REQUEST_TIMEOUT_MS = 1000;')
  .replace(/import \{ prepareTechnicalSheet \} from "\.\/prepare-technical-sheet";/,
    'const prepareTechnicalSheet = () => { throw new Error("not used in photo checks"); };');
const client = await import(`data:text/javascript;base64,${Buffer.from(compiled + "\n//# sourceURL=synthetic-photo-client.mjs").toString("base64")}`);
globalThis.window = { setTimeout, clearTimeout, location: { origin: "http://synthetic.test" } };
const requests = [];
let active = 0, peak = 0, fail = false;
globalThis.fetch = async (input, options) => {
  assert.equal(options.cache,"no-cache","revalidate cached empty photo responses");
  const url = new URL(input, window.location.origin);
  const codes = url.searchParams.get("codes").split(",");
  requests.push(codes);
  assert.ok(codes.length <= 30, "API rejects batches larger than 30");
  active++; peak = Math.max(peak, active);
  await new Promise(resolve => setTimeout(resolve, 1));
  active--;
  if (fail) return new Response(JSON.stringify({error:"synthetic outage"}), {status:503});
  return new Response(JSON.stringify(Object.fromEntries(codes.map(code => [code, {
    white_background: `https://images.test/${code}.jpg`, ambient:null, measures:null,
  }]))), {status:200, headers:{"Content-Type":"application/json"}});
};
const codes = Array.from({length:71}, (_, index) => String(1000 + index));
const photos = await client.fetchPhotosByCodes([...codes, " 1000 ", ""]);
assert.equal(Object.keys(photos).length, 71);
assert.deepEqual(requests.map(batch => batch.length), [30,30,11]);
assert.equal(peak,1);
assert.equal(photos["1070"].white_background,"https://images.test/1070.jpg");
requests.length = 0;
assert.deepEqual(await client.fetchPhotosByCodes([]),{});
assert.equal(requests.length,0);
fail = true;
await assert.rejects(client.fetchPhotosByCodes(codes), /synthetic outage/);
assert.equal(requests.length,1);
console.log("PASS: 71 photos, bounded batches, combined results, deduplication, empty input and failure propagation");
