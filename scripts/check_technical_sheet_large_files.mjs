// Regression checks for the real XLSX preparation code and the existing Python reader.
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync, mkdirSync, openAsBlob } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const requireFrontend = createRequire(resolve(root, 'frontend/package.json'));
const ts = requireFrontend('typescript');
const XLSX = requireFrontend('xlsx');
const modules = new Map();
function loadTypeScript(path) {
  if (modules.has(path)) return modules.get(path);
  const module = { exports: {} };
  modules.set(path, module.exports);
  const compiled = ts.transpileModule(readFileSync(path, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  new Function('module', 'exports', 'require', compiled)(module, module.exports, (name) =>
    name.startsWith('.') ? loadTypeScript(resolve(dirname(path), name + '.ts')) : requireFrontend(name));
  return module.exports;
}
const { compactTechnicalWorkbook } = loadTypeScript(resolve(root, 'frontend/src/lib/technical-sheet-workbook.ts'));
const fixtureRoot = resolve(root, '.codex-tmp/large-excel-check');
mkdirSync(fixtureRoot, { recursive: true });
const fixture = spawnSync('python', ['-c', `
from pathlib import Path
from openpyxl import Workbook
from openpyxl.drawing.image import Image
from openpyxl.comments import Comment
from PIL import Image as PillowImage
from io import BytesIO
from zipfile import ZipFile, ZIP_STORED
root=Path(${JSON.stringify(fixtureRoot)})
w=Workbook()
w.active.title='Instrucoes'
w.active.append(['Preencha a aba Produtos'])
s=w.create_sheet('Produtos')
s.append(['Titulo'])
s.append([])
s.append(['Codigo','Nome','Potencia','Tensao'])
s.append([12,'Com zeros','12 W','Bivolt'])
s['A4'].number_format='0000'
s.append([])
s.append([1234,'Formula','=1+1','220 V'])
s.append([5678,'Zero',0,'Bivolt'])
s.append(['0020','Quebras de linha','Linha 1'+chr(13)+'Linha 2'+chr(10)+'Linha 3','Bivolt'])
picture=BytesIO()
PillowImage.new('RGB',(1,1),'white').save(picture,format='PNG')
s.add_image(Image(BytesIO(picture.getvalue())),'F4')
s['B4'].comment=Comment('Ignored comment','QA')
s['B4'].hyperlink='https://example.test/details'
w.save(root/'small.xlsx')
(root/'large.xlsx').write_bytes((root/'small.xlsx').read_bytes())
with ZipFile(root/'large.xlsx','a',compression=ZIP_STORED) as z:
    z.writestr('xl/media/large-fixture.bin', bytes(range(256))*24576)
    for i in range(1001): z.writestr(f'xl/media/fixture-{i}.bin', b'x')
`, ], { cwd: root, encoding: 'utf8' });
assert.equal(fixture.status, 0, fixture.stderr);
function arrayBuffer(bytes) { return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength); }
const source = readFileSync(resolve(fixtureRoot, 'large.xlsx'));
assert.ok(source.byteLength > 4 * 1024 * 1024);
const prepared = compactTechnicalWorkbook(arrayBuffer(source));
assert.ok(prepared.byteLength < 4 * 1024 * 1024);
assert.ok(prepared.byteLength < source.byteLength / 100);
writeFileSync(resolve(fixtureRoot, 'prepared.xlsx'), Buffer.from(prepared));
const roundtrip = XLSX.read(prepared, { type: 'array', cellNF: true });
assert.deepEqual(roundtrip.SheetNames, ['Instrucoes', 'Produtos']);
assert.equal(roundtrip.Sheets.Produtos.A4.v, 12);
assert.equal(roundtrip.Sheets.Produtos.A4.z, '0000');
assert.equal(roundtrip.Sheets.Produtos.C6.f, '1+1', 'server must still see formulas');
assert.equal(roundtrip.Sheets.Produtos.C7.v, 0, 'zero is a real value');
const backend = spawnSync('python', ['-c', `
from pathlib import Path
from catalog.technical_sheet import _read_rows
root=Path(${JSON.stringify(fixtureRoot)})
small=_read_rows((root/'small.xlsx').read_bytes(),'small.xlsx',None)
prepared=_read_rows((root/'prepared.xlsx').read_bytes(),'large.xlsx',None)
assert small==prepared, (small, prepared)
assert prepared[2][0]['code']=='0012'
assert prepared[2][1]['issues'], 'Formula must be rejected by the server'
assert prepared[2][1]['row']==6
assert 'Linha 1'+chr(10)+'Linha 2'+chr(10)+'Linha 3' in prepared[2][3]['specs']
print('Python reader: identical data, row positions, leading zeros and formula validation')
`], { cwd: root, encoding: 'utf8' });
assert.equal(backend.status, 0, backend.stderr);
console.log(backend.stdout.trim());
function workbookWithCell(address, cell) {
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, { [address]: cell, '!ref': `A1:${address}` }, 'Produtos');
  return XLSX.write(workbook, { type: 'array', bookType: 'xlsx' });
}
assert.throws(() => compactTechnicalWorkbook(new ArrayBuffer(0)), /vazio/);
assert.throws(() => compactTechnicalWorkbook(new ArrayBuffer(301 * 1024 * 1024)), /300 MB/);
assert.throws(() => compactTechnicalWorkbook(new TextEncoder().encode('fake spreadsheet').buffer), /inválido/);
assert.throws(() => compactTechnicalWorkbook(workbookWithCell('CW1', { t: 's', v: 'outside columns' })), /100 colunas/);
assert.throws(() => compactTechnicalWorkbook(workbookWithCell('A10021', { t: 's', v: 'outside rows' })), /10.000 produtos/);
assert.throws(() => compactTechnicalWorkbook(workbookWithCell('A1', { t: 's', v: 'x'.repeat(8001) })), /8.000 caracteres/);
const styled = XLSX.utils.book_new();
const styledSheet = XLSX.utils.aoa_to_sheet([['Codigo', 'Especificacoes'], ['0012', '12 W']]);
styledSheet.A20000 = { t: 's', v: '', z: '0.00' };
styledSheet['!ref'] = 'A1:B20000';
XLSX.utils.book_append_sheet(styled, styledSheet, 'Produtos');
const trimmed = compactTechnicalWorkbook(XLSX.write(styled, { type: 'array', bookType: 'xlsx' }));
assert.equal(XLSX.read(trimmed, { type: 'array' }).Sheets.Produtos['!ref'], 'A1:B2');
console.log(JSON.stringify({ passed: true, original_bytes: source.byteLength, prepared_bytes: prepared.byteLength, cases: ['large workbook', 'images discarded', 'multiple sheets', 'formulas preserved', 'leading zeros', 'zero values', 'row positions', 'invalid file', '300 MB limit', 'column limit', 'row limit', 'cell length limit', 'empty styled rows discarded'] }, null, 2));

// Use a disk-backed 300 MB workbook and account for every byte range read.
const { readTechnicalWorkbookParts } = loadTypeScript(resolve(root, 'frontend/src/lib/technical-sheet-archive.ts'));
// Recent Excel files include people and metadata parts that the cell-only reader
// intentionally skips. Their content-type declarations must not survive extraction.
const modernFixture = spawnSync('python', ['-c', `
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
root=Path(${JSON.stringify(fixtureRoot)})
extra_types=(
    '<Override PartName="/xl/persons/person.xml" ContentType="application/vnd.ms-excel.person+xml"/>'
    '<Override PartName="/xl/metadata.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheetMetadata+xml"/>'
)
with ZipFile(root/'small.xlsx') as source, ZipFile(root/'modern.xlsx','w',compression=ZIP_DEFLATED) as target:
    for item in source.infolist():
        data=source.read(item.filename)
        if item.filename=='[Content_Types].xml':
            data=data.decode().replace('</Types>',extra_types+'</Types>').encode()
        target.writestr(item.filename,data)
    target.writestr('xl/persons/person.xml','<personList xmlns="http://schemas.microsoft.com/office/spreadsheetml/2018/threadedcomments"><person displayName="QA" id="{00000000-0000-0000-0000-000000000001}"/></personList>')
    target.writestr('xl/metadata.xml','<metadata xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>')
`], { cwd: root, encoding: 'utf8' });
assert.equal(modernFixture.status, 0, modernFixture.stderr);
const modernParts = await readTechnicalWorkbookParts(await openAsBlob(resolve(fixtureRoot, 'modern.xlsx')));
const modernBook = XLSX.read(compactTechnicalWorkbook(modernParts), { type: 'array', cellNF: true });
assert.deepEqual(modernBook.SheetNames, roundtrip.SheetNames);
for (const name of roundtrip.SheetNames) {
  assert.deepEqual(modernBook.Sheets[name], roundtrip.Sheets[name]);
}
const modernArchive = XLSX.CFB.read(new Uint8Array(modernParts), { type: 'array' });
const modernManifest = XLSX.CFB.find(modernArchive, '[Content_Types].xml').content;
assert.doesNotMatch(Buffer.from(modernManifest).toString('utf8'), /persons|metadata|comments|drawing|theme|media/i);
console.log('Modern Excel: omitted comments, people and metadata do not break cell parsing');
const largeFixture = spawnSync('python', ['-c', `
from pathlib import Path
from zipfile import ZipFile, ZIP_STORED
root=Path(${JSON.stringify(fixtureRoot)})
(root/'300mb.xlsx').write_bytes((root/'small.xlsx').read_bytes())
with ZipFile(root/'300mb.xlsx','a',compression=ZIP_STORED) as z:
    with z.open('xl/media/large-photo-fixture.bin','w') as entry:
        block=bytes(range(256))*4096
        for _ in range(299): entry.write(block)
`], { cwd: root, encoding: 'utf8' });
assert.equal(largeFixture.status, 0, largeFixture.stderr);
const diskFile = await openAsBlob(resolve(fixtureRoot, '300mb.xlsx'));
let bytesRead = 0;
let largestRange = 0;
const trackedFile = new Proxy(diskFile, {
  get(target, key) {
    if (key === 'slice') return (start, end, ...args) => {
      const portion = target.slice(start, end, ...args);
      bytesRead += portion.size;
      largestRange = Math.max(largestRange, portion.size);
      return portion;
    };
    const value = Reflect.get(target, key, target);
    return typeof value === 'function' ? value.bind(target) : value;
  },
});
const cellPackage = await readTechnicalWorkbookParts(trackedFile);
writeFileSync(resolve(fixtureRoot, 'cell-package.xlsx'), Buffer.from(cellPackage));
const preparedLarge = compactTechnicalWorkbook(cellPackage);
assert.ok(diskFile.size > 298 * 1024 * 1024 && diskFile.size <= 300 * 1024 * 1024);
assert.ok(bytesRead < 1024 * 1024, `read only cell ranges, got ${bytesRead}`);
assert.ok(largestRange < 1024 * 1024, `must not read the full file, got ${largestRange}`);
assert.ok(cellPackage.byteLength < 64 * 1024 * 1024);
assert.deepEqual(XLSX.utils.sheet_to_json(XLSX.read(preparedLarge, {type:'array'}).Sheets.Produtos, {header:1}), XLSX.utils.sheet_to_json(roundtrip.Sheets.Produtos, {header:1}));
writeFileSync(resolve(fixtureRoot, 'prepared-300mb.xlsx'), Buffer.from(preparedLarge));
await assert.rejects(() => readTechnicalWorkbookParts({ size: 300 * 1024 * 1024 + 1 }), /300 MB/);
await assert.rejects(() => readTechnicalWorkbookParts(new Blob(['fake Excel'])), /Excel/);
console.log(JSON.stringify({ case:'disk-backed 300 MB workbook', original_bytes:diskFile.size, bytes_read:bytesRead, largest_range:largestRange, cell_package_bytes:cellPackage.byteLength, prepared_bytes:preparedLarge.byteLength, passed:true }, null, 2));
