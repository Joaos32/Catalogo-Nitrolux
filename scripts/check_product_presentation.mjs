// Exercise the actual TypeScript product normalizer with representative ERP data.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
const require = createRequire(new URL("../frontend/package.json", import.meta.url));
const ts = require("typescript");
const source = await readFile(new URL("../frontend/src/lib/catalog-products.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module:ts.ModuleKind.ES2022, target:ts.ScriptTarget.ES2022 }}).outputText
  .replace(/import \{[^}]+\} from "\.\/catalog-core";/, 'const DETAIL_FALLBACK_IMAGE="data:image/svg+xml,fallback"; const createPlaceholderDataUrl=()=>DETAIL_FALLBACK_IMAGE;')
  .replace(/import \{[^}]+\} from "\.\/catalog-api";/, 'const absolutizeApiUrl=value=>value.startsWith("/")?"https://catalog.test"+value:value;');
const lib=await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);
const cacheSource=await readFile(new URL("../frontend/src/lib/catalog-photo-cache.ts",import.meta.url),"utf8");
const cacheCompiled=ts.transpileModule(cacheSource,{compilerOptions:{module:ts.ModuleKind.ES2022,target:ts.ScriptTarget.ES2022}}).outputText
  .replace('"./catalog-products"',JSON.stringify(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`));
const photoCache=await import(`data:text/javascript;base64,${Buffer.from(cacheCompiled).toString("base64")}`);
const sessionPhotos={"501131":{white_background:"https://images.test/501131.jpg"},"6002":{white_background:"https://images.test/6002.jpg?token=temporary"}};
const nextBatch=photoCache.mergePhotosByCode(sessionPhotos,{"6010":{white_background:"https://images.test/6010.jpg"}});
assert.equal(nextBatch["501131"],sessionPhotos["501131"],"loading another batch must retain previously loaded photos");
assert.equal(nextBatch["6002"],sessionPhotos["6002"],"nonpersistable signed URLs must remain in the session");
assert.deepEqual(Object.keys(sessionPhotos),["6002","501131"],"merging the next batch must not mutate the previous state");
assert.equal(photoCache.mergePhotosByCode(nextBatch,{"501131":{white_background:"data:image/svg+xml,fallback"}}),nextBatch,"an empty or placeholder response must not replace a real photo");
assert.deepEqual(photoCache.mergePhotoSources({white_background:"data:image/svg+xml,fallback"},sessionPhotos["501131"]),sessionPhotos["501131"]);
const refreshed=photoCache.mergePhotosByCode(nextBatch,{"501131":{ambient:"https://images.test/501131-room.jpg"}});
assert.equal(refreshed["501131"].white_background,sessionPhotos["501131"].white_background,"a partial response must retain the existing cover");
assert.equal(refreshed["501131"].ambient,"https://images.test/501131-room.jpg");
assert.equal(photoCache.mergePhotosByCode(refreshed,refreshed),refreshed,"identical photo data must not cause another state update");
console.log("PASS: stable session photos across batches, signed URLs, placeholder responses, partial updates and immutable cache merges");
const raw={Codigo:"5989",Nome:"Abajur",Categoria:"ABAJUR",CODMARCA:"1",
  Especificacoes:"CODIGO: 5989 | REFERENCIA: 5989 | DIMENSOES: Ø130x350mm | POTENCIA: 5W | TEMP. DE COR(K): 2700K | MATERIAL: MADEIRA E PE",
  INFORMACOESTECNICAS:"CODIGO: 5989\\POTENCIA: 5W\\TEMP. DE COR(K): 2700K",CODPROD:"5989",CODAUXILIAR:"7896688231828"};
const item=lib.normalizeProduct(raw,0);
assert.equal(item.description.match(/2700\s*K/gi)?.length,1,"temperature should appear once");
assert.ok(!item.attributes.some(a=>["CODPROD","INFORMACOESTECNICAS"].includes(a.label)),"base data should not repeat as extra attributes");
assert.ok(item.attributes.some(a=>a.label==="CODAUXILIAR"),"barcode must remain available");
const specs=lib.getTechnicalPresentation(item.specs,item.code);
assert.ok(specs.attributes.some(a=>a.label==="Dimensões"&&a.value.includes("130")));
assert.ok(specs.attributes.some(a=>a.label==="Potência"&&a.value==="5W"));
assert.ok(!specs.attributes.some(a=>["Código","Referência"].includes(a.label)),"identity already has its own display");
const plain=lib.getTechnicalPresentation("Potência: 5W\\Tensão: DC5V\\Potência: 5W\\Nota sem estrutura\nHorário: 10:30", "1");
assert.equal(plain.attributes.filter(a=>a.label==="Potência").length,1);
assert.deepEqual(plain.notes,["Nota sem estrutura"]);
assert.ok(plain.attributes.some(a=>a.value==="10:30"),"keep colons inside values");
assert.deepEqual(lib.getTechnicalPresentation("", "1"),{attributes:[],notes:[]});
const sparse = lib.normalizeProduct({Codigo:"6383",Nome:"LAMPADA G9 4.5W 2400K",Categoria:"LAMPADA",
  Especificacoes:"Cor: -- | Potência: 4.5W | Fluxo luminoso: 650lm | temp. de cor: 2400K | IRC: >80 | Tensão: AC100-240V | Frequencia nominal: -- | Fator de potencia: >0.5 | Medidas: Ø28x46mm | Garantia: | Material: ***",
  Cor:"--",Peso:" ",Garantia:null,Estoque:0,Ativo:false,Observacoes:"N/A",Lista:[],DetalhesExtras:{}},0);
const visible = lib.getTechnicalPresentation(sparse.specs,sparse.code);
assert.equal(visible.attributes.length,7,"hide missing fields while retaining every filled technical value");
assert.deepEqual(visible.notes,[],"blank labeled fields must not become notes");
assert.ok(!sparse.description.includes("--"),"summary must not contain missing color markers");
assert.deepEqual(sparse.attributes.map(a=>a.label),["Estoque","Ativo"],"hide empty extra attributes while preserving zero and false");
for (const missing of [null,undefined,""," ","--","—","***","N/A","Não informado","[]","{}"]) {
  assert.equal(lib.hasProductValue(missing),false,`hide missing value ${missing}`);
}
for (const filled of [0,false,"0","0 W",">0.5","AC100-240V","Ø28x46mm","Preto/branco"]) {
  assert.equal(lib.hasProductValue(filled),true,`retain filled value ${filled}`);
}
assert.deepEqual(lib.getTechnicalPresentation("Cor: -- | Material: *** | Garantia: | -- | N/A", "1"),{attributes:[],notes:[]});
assert.deepEqual(lib.getTechnicalPresentation("Cor: -- | Cor: Branco | Peso: 0", "1").attributes,[{label:"Cor",value:"Branco"},{label:"Peso",value:"0"}]);
console.log("PASS: sparse product 6383, empty markers, blank fields, extra attributes and preserved zero/false values");
const flyer="/catalog/local/asset?path=Flayer%2F5990-flyer.jpg";
const clean="/catalog/local/asset?path=5990_1.jpg";
assert.equal(lib.getPrimaryProductImage({white_background:flyer,ambient:clean}),"https://catalog.test"+clean);
assert.equal(lib.getPrimaryProductImage({white_background:flyer}),"https://catalog.test"+flyer,"keep promotional art when it is the only image");
assert.equal(lib.getPrimaryProductImage({white_background:"https://placehold.co/a",ambient:clean}),"https://catalog.test"+clean);
assert.equal(lib.isPromotionalImage("https://images.test/portrait-product.jpg"),false,"portrait shape is not promotional metadata");
assert.equal(lib.getPrimaryProductImage(null),"");
assert.deepEqual(lib.getProductImageCandidates({white_background:clean,ambient:clean,measures:flyer},clean),[
  "https://catalog.test"+clean,"https://catalog.test"+flyer
],"card fallbacks must be distinct and keep promotional art last");
assert.deepEqual(lib.getProductImageCandidates({white_background:"data:image/svg+xml,fallback",ambient:clean}),[
  "https://catalog.test"+clean
],"a generated placeholder must not hide a real photo");
const gallery=lib.buildGalleryEntries({...item,cover:clean},{white_background:flyer,ambient:clean},[{name:"flyer",url:flyer},{name:"product",url:clean}]);
assert.equal(gallery.length,2,"retain the art without duplicating the same photo");
assert.ok(gallery.some(e=>e.label.startsWith("Divulgação")));
assert.equal(gallery[lib.findPreferredGalleryIndex(gallery,"https://catalog.test"+flyer)].url,"https://catalog.test"+clean);
assert.ok(lib.buildGalleryEntries({...item,cover:""},null,[])[0].label==="Sem imagem");
const fallback=lib.normalizeProduct({Codigo:"1",Nome:"Teste",INFORMACOESTECNICAS:"Potência: 7W\\Tensão: 12V"},0);
assert.ok(lib.getTechnicalPresentation(fallback.specs,"1").attributes.some(a=>a.value==="12V"));
console.log("PASS: product cover selection, retained gallery art, empty photos, technical data, aliases and summary deduplication");

const repeated=[
  {Codigo:"5160",Nome:"Tartaruga LED",VendaMes:0,Ativo:false,FotoBranco:"https://placehold.co/240",Especificacoes:""},
  {Codigo:5160,Nome:"Another name",VendaMes:50,Ativo:true,FotoBranco:"/5160.jpg",Especificacoes:"10W"},
  {COD_PROD:"5160.0",FotoAmbient:"/5160-ambient.jpg"},
  {Codigo:"5161",Nome:"Tartaruga LED",FotoBranco:"/5160.jpg"}
];
const original=structuredClone(repeated);
const unique=lib.deduplicateProducts(repeated);
assert.equal(unique.length,2);
assert.equal(unique[0].Codigo,"5160");
assert.equal(unique[0].Nome,"Tartaruga LED");
assert.equal(unique[0].VendaMes,0,"do not sum sales or replace zero");
assert.equal(unique[0].Ativo,false);
assert.equal(unique[0].FotoBranco,"/5160.jpg");
assert.equal(unique[0].FotoAmbient,"/5160-ambient.jpg");
assert.equal(unique[0].Especificacoes,"10W");
assert.deepEqual(repeated,original,"do not mutate API rows");
assert.deepEqual(lib.deduplicateProducts(unique),unique);
assert.equal(new Set(unique.map(lib.normalizeProduct).map(p=>p.routeId)).size,2);
assert.equal(lib.deduplicateProducts([{Nome:"No code"},{Nome:"No code"}]).length,2);
assert.equal(lib.deduplicateProducts(["1641","2371","005160","5160","SKU-5160"].map(Codigo=>({Codigo,Nome:"Same product",FotoBranco:"same.jpg"}))).length,5);
assert.equal(lib.normalizeProductCode(" 5160.00 "),"5160");
assert.equal(lib.normalizeProductCode(false),"");
assert.equal(lib.normalizeProductCode(NaN),"");
const runtime=JSON.parse(await readFile(new URL("../reports/catalog_runtime.json",import.meta.url),"utf8")).products;
assert.equal(lib.deduplicateProducts(runtime).length,runtime.length,"bundled catalog must already be unique");
console.log("PASS: repeated product codes, complementary photos/specs, preserved sales, distinct codes and stable route IDs");
