# Explicacao Detalhada Do Projeto

## Objetivo deste documento

Este arquivo existe para servir como um guia de estudo do projeto inteiro.
Em vez de apenas listar arquivos, a ideia aqui e explicar:

- o que o sistema faz;
- como a aplicacao sobe;
- como os dados entram no backend;
- como os produtos sao montados;
- como o frontend consome esses dados;
- como os testes garantem o comportamento esperado;
- e quais decisoes de arquitetura aparecem no codigo.

O projeto tem milhares de linhas autorais. Entao, para manter a leitura util, esta explicacao segue um formato de "linha a linha por blocos contiguos": eu explico os arquivos na ordem real de execucao e, dentro de cada arquivo, descrevo o papel de cada bloco relevante de linhas.

---

## Visao geral do sistema

O projeto e um catalogo de produtos com:

- backend em FastAPI;
- frontend principal em React + Vite + TypeScript;
- frontend legado em React via CDN/Babel;
- suporte a fotos locais em pastas do OneDrive;
- suporte opcional a Microsoft Graph;
- importacao de JSON do ERP;
- fallback por planilha de estoque;
- exportacao do catalogo em CSV, JSON, XLSX, PDF e ZIP.

Em termos simples, o sistema tenta montar um catalogo confiavel a partir de varias fontes imperfeitas:

1. pasta local com fotos;
2. CADASTRO.html exportado;
3. arquivo JSON do ERP;
4. planilha POSICAO_ESTOQUE;
5. Microsoft Graph, se configurado.

O desenho geral privilegia fallback e enriquecimento:

- se uma fonte falhar, outra pode completar;
- se um produto nao tiver foto local, o estoque pode ajudar;
- se o produto nao estiver no disco, o ERP pode criar o item;
- se Graph nao estiver configurado, o sistema nao quebra, ele devolve placeholders.

---

## Estrutura principal do repositorio

```text
.
|-- app.py
|-- catalog/
|   |-- bootstrap.py
|   |-- auth.py
|   |-- routes.py
|   |-- onedrive.py
|   |-- spreadsheet.py
|   |-- cadastro.py
|   |-- local_catalog.py
|   |-- product_catalog.py
|   |-- product_media.py
|   |-- stock_catalog.py
|   |-- erp_catalog.py
|   |-- exporter.py
|   |-- graph_client.py
|   |-- graph_catalog.py
|   |-- core/
|   |   |-- settings.py
|   |   `-- logging_config.py
|   |-- api/
|   |   |-- router.py
|   |   |-- frontend.py
|   |   |-- endpoints/
|   |   `-- schemas/
|   `-- services/
|-- frontend/
|   |-- src/
|   |-- legacy/
|   `-- vite.config.ts
|-- tests/
`-- README.md
```

Observacao importante:

- `frontend/legacy/*` e o fallback real usado pelo backend quando nao existe `frontend/dist/index.html`.
- `frontend/node_modules` e `frontend/dist` nao fazem parte da logica autoral do projeto.

---

## Como a aplicacao sobe

## `app.py`

Arquivo: `app.py`

### Linhas 1-2

```python
from catalog.bootstrap import create_app
from catalog.core import load_settings
```

- importa a factory principal da aplicacao;
- importa o carregador de configuracoes.

### Linha 5

```python
app = create_app()
```

- esta e a linha mais importante do arquivo;
- o objeto ASGI global nasce aqui;
- quando o Uvicorn importa `app:app`, ele encontra esse objeto.

### Linhas 7-15

- so executam se o arquivo for chamado diretamente com `python app.py`;
- importam `uvicorn`;
- leem host e porta de `load_settings()`;
- sobem o servidor com `uvicorn.run("app:app", ...)`.

Em outras palavras:

- `create_app()` monta a aplicacao;
- o bloco `if __name__ == "__main__"` apenas decide como executa-la localmente.

---

## Inicializacao do backend

## `catalog/bootstrap.py`

Arquivo: `catalog/bootstrap.py`

Este arquivo e o "montador" da aplicacao.

### Linhas 1-15

- imports de `logging`, `sys`, `load_dotenv`, `FastAPI`;
- imports das funcoes que registram API e frontend;
- imports de `configure_logging` e `load_settings`.

### Linhas 18-35: `_configure_cors(...)`

Esse bloco:

- tenta importar `CORSMiddleware`;
- se a dependencia falhar, apenas loga warning;
- evita uma configuracao invalida de navegador:
  - se `allow_credentials=True` e `allow_origins=["*"]`, ele desliga `allow_credentials`;
- registra middleware com todos os metodos e headers liberados.

Esse detalhe e importante porque navegadores nao aceitam credenciais com origem coringa.

### Linhas 38-54: `create_app()`

Fluxo:

1. chama `load_dotenv()` para carregar `.env`;
2. chama `configure_logging()` para padronizar logs;
3. chama `load_settings()` para descobrir host, porta e frontend;
4. registra um log informando o executavel Python usado;
5. cria o objeto `FastAPI`;
6. aplica CORS;
7. registra rotas da API;
8. registra rotas do frontend;
9. retorna `app`.

Conclusao:

- `bootstrap.py` e o ponto onde tudo se junta;
- o resto do projeto so existe porque essa factory compoe as pecas.

---

## Configuracao e logging

## `catalog/core/settings.py`

Arquivo: `catalog/core/settings.py`

### Linhas 10-16: `_parse_csv_env`

- recebe uma string de env como `"a,b,c"`;
- divide por virgula;
- remove espacos;
- remove entradas vazias;
- se nada sobrar, volta ao default.

### Linhas 18-30: `_resolve_frontend_paths`

Essa funcao escolhe qual frontend o backend vai servir.

Ordem:

1. se existir `frontend/dist/index.html`, usa o build do Vite;
2. senao, se existir `frontend/legacy/index.html`, usa o frontend legado;
3. senao, usa `frontend/index.html`.

Isso explica por que o backend continua funcional mesmo sem build do frontend moderno.

### Linhas 33-40: `Settings`

Dataclass imutavel com:

- `base_dir`;
- `frontend_dir`;
- `frontend_index`;
- `host`;
- `port`;
- `cors_allow_origins`;
- `cors_allow_credentials`.

### Linhas 44-56: `load_settings()`

- resolve a raiz do projeto;
- decide qual frontend servir;
- le host/porta/CORS do ambiente;
- retorna a estrutura `Settings`.

Esse arquivo e pequeno, mas central: ele controla como a aplicacao se adapta ao ambiente.

## `catalog/core/logging_config.py`

Arquivo: `catalog/core/logging_config.py`

### Linhas 9-10

- definem nivel e formato padrao do log.

### Linhas 13-15: `_resolve_level`

- converte string como `"debug"` ou `"INFO"` em constante do modulo `logging`.

### Linhas 18-28: `configure_logging()`

- le `CATALOG_LOG_LEVEL` e `CATALOG_LOG_FORMAT`;
- se ainda nao houver handlers no root logger, chama `logging.basicConfig(...)`;
- se ja houver handlers, apenas atualiza o nivel do root.

Isso evita reconfigurar logging de forma agressiva quando a aplicacao for importada por outro runner.

---

## Fachadas de compatibilidade

## `catalog/__init__.py`

Arquivo: `catalog/__init__.py`

Esse arquivo existe principalmente para compatibilidade.

### Linhas 1-6

- deixam claro no docstring que `catalog_router` e mantido como alias para imports legados.

### Linhas 8-14

- exportam `catalog.routes.router` como `catalog_router`;
- expõem tambem `create_app()`, mas delegando internamente para `bootstrap.create_app`.

### Linha 17

- `__all__` deixa explicito o contrato publico do pacote.

## `catalog/api/__init__.py`

Arquivo: `catalog/api/__init__.py`

Mesmo padrao:

- `register_api_routes(app)` delega para `catalog.api.router`;
- `register_frontend_routes(...)` delega para `catalog.api.frontend`.

Utilidade:

- reduz import circular cedo;
- mantem um ponto estavel de import publico.

---

## Registro das rotas

## `catalog/api/router.py`

Arquivo: `catalog/api/router.py`

### Linhas 5-6

- importa o router de autenticacao;
- importa o router principal do catalogo.

### Linhas 9-10: `register_api_routes`

- inclui `auth_router` sem prefixo extra;
- inclui `catalog_router` com prefixo `/catalog`.

Logo:

- `/auth/...` vem de `catalog.auth`;
- `/catalog/...` vem de `catalog.routes`.

## `catalog/api/frontend.py`

Arquivo: `catalog/api/frontend.py`

Esse arquivo serve o frontend como SPA.

### Linhas 11-21: `_resolve_frontend_file`

Objetivo:

- receber um `path` pedido pelo navegador;
- impedir traversal fora da pasta do frontend;
- devolver o arquivo se ele existir.

Detalhes:

- resolve o root com `frontend_dir.resolve()`;
- resolve o candidato com `(root / path).resolve()`;
- tenta `candidate.relative_to(root)`;
- se isso falhar, devolve `None`;
- se o arquivo existir, retorna o caminho.

Esse bloco e a defesa principal contra algo como `../../app.py`.

### Linhas 24-34: `register_frontend_routes`

Registra:

- `GET /` -> devolve `index_file`;
- `GET /{full_path:path}` -> tenta servir arquivo estatico real;
- se nao encontrar, devolve de novo `index_file`.

Esse comportamento e o padrao de SPA:

- assets reais saem como arquivo;
- rotas do frontend, como `/produto/123`, caem no `index.html`.

---

## Camada HTTP principal do catalogo

## `catalog/routes.py`

Arquivo: `catalog/routes.py`

Esse arquivo hoje e uma fachada entre a API nova e uma rota antiga utilitaria.

### Linhas 10-13

- importa routers menores:
  - `catalog`;
  - `erp`;
  - `export`;
  - `media`.

### Linhas 16-20

- cria `router = APIRouter()`;
- inclui os quatro subrouters.

### Linhas 24-51: `_tiff_to_jpeg_bytes`

Esse helper:

- recebe um caminho local;
- so processa extensoes como `.tif`, `.tiff`, `.psd`, `.heic`, `.heif`;
- tenta importar `PIL.Image`;
- abre a imagem;
- achata transparencia sobre fundo branco quando necessario;
- converte para RGB;
- serializa como JPEG para compatibilidade com o navegador.

Em resumo:

- ele e um adaptador para imagens que browsers nao tratam tao bem no fluxo normal.

### Linhas 52-71: `/local/asset`

Fluxo:

1. exige query param `path`;
2. chama `catalog.onedrive.resolve_local_asset_path(path)`;
3. se nao achar, retorna 404;
4. se a imagem precisar de conversao, devolve `image/jpeg`;
5. senao, usa `FileResponse` diretamente;
6. qualquer excecao vira 500 com log.

Essa rota e importantissima porque quase todas as fotos locais do catalogo viram URLs desse formato:

`/catalog/local/asset?path=<rel_path>`

---

## Schemas da API

## `catalog/api/schemas/catalog.py`

Arquivo: `catalog/api/schemas/catalog.py`

### Linhas 8-18: `CatalogProductSchema`

- permite campos extras com `extra="allow"`;
- define o shape minimo:
  - `Codigo`;
  - `Nome`;
  - `Descricao`;
  - `Categoria`;
  - `URLFoto`;
  - `Especificacoes`;
  - `FotoBranco`;
  - `FotoAmbient`;
  - `FotoMedidas`.

Por que `extra="allow"` importa?

- porque o ERP injeta muitos campos adicionais;
- o schema nao bloqueia essas colunas extras.

## `catalog/api/schemas/media.py`

Arquivo: `catalog/api/schemas/media.py`

Define:

- `ProductPhotosSchema`:
  - `white_background`;
  - `ambient`;
  - `measures`.
- `ProductImageSchema`:
  - `name`;
  - `variant`;
  - `url`.
- `ProductImagesResponseSchema`:
  - `codigo`;
  - `imagens`.

Essa separacao mostra dois casos diferentes:

- um payload "resumido" com tres categorias de foto;
- um payload "galeria completa" com todas as variacoes.

---

## Endpoints e services

## `catalog/api/endpoints/catalog.py`

Arquivo: `catalog/api/endpoints/catalog.py`

### Linhas 18-20: `/items`

Hoje retorna `[]`.

Observacao:

- esse endpoint parece ser um placeholder ou um contrato antigo mantido por compatibilidade;
- o endpoint realmente usado pelo frontend atual e `/catalog/local/produtos`.

### Linhas 23-32: `/sheet`

- exige `url`;
- se faltar, retorna 400;
- chama `fetch_sheet_or_local_products(url)`;
- se algo falhar fora do fallback esperado, loga e retorna 500.

### Linhas 35-42: `/local/produtos`

- chama `list_catalog_products()`;
- em caso de excecao, loga e retorna 500.

## `catalog/services/catalog_service.py`

Arquivo: `catalog/services/catalog_service.py`

### Linhas 14-17: `list_catalog_products`

- importa `catalog.onedrive` por dentro da funcao;
- chama `onedrive.list_local_products()`.

Isso mostra um padrao importante do projeto:

- o modulo `onedrive.py` hoje e a fachada operacional do catalogo.

### Linhas 20-32: `fetch_sheet_or_local_products`

Fluxo:

1. tenta buscar a planilha com `fetch_sheet(url)`;
2. converte DataFrame em lista de dicts;
3. se vier `ValueError`, faz fallback para produtos locais;
4. se o fallback local tambem quebrar, loga e devolve `[]`.

Esse service e um exemplo perfeito da filosofia do projeto:

- tentar fonte principal;
- se falhar, nao derrubar a experiencia;
- usar fallback.

## `catalog/api/endpoints/media.py`

Arquivo: `catalog/api/endpoints/media.py`

### Linhas 18-27: `/photos`

- recebe `shareUrl` e `code`;
- delega para `get_product_photos_payload`;
- `ValueError` vira 400;
- erro inesperado vira 500.

### Linhas 30-39: `/produtos/{codigo}/imagens`

- devolve a galeria completa;
- segue a mesma estrategia de tratamento de erros.

## `catalog/services/media_service.py`

Arquivo: `catalog/services/media_service.py`

### Linhas 11-43: `get_product_photos_payload`

Fluxo:

1. se houver `code`, tenta primeiro foto local;
2. se encontrar alguma, retorna imediatamente;
3. se existir raiz local, mesmo sem foto, devolve o resultado vazio local;
4. se falhar a busca local, faz log de warning e tenta Graph;
5. se nao houver `shareUrl`, gera `ValueError`;
6. se Graph falhar por ambiente/configuracao, devolve placeholders.

Esse metodo e interessante porque ele distingue:

- "nao achei foto local, mas estou em modo local" -> retorna vazio sem obrigar Graph;
- "nao estou em modo local" -> tenta Graph;
- "Graph indisponivel" -> devolve placeholder em vez de quebrar.

### Linhas 46-64: `get_product_images_payload`

Mesma ideia, mas para galeria:

1. tenta `find_local_images_for_code`;
2. se existir raiz local, aceita lista vazia;
3. senao exige `shareUrl`;
4. usa `find_images_for_code` para busca remota.

---

## Autenticacao Azure / MS Graph

## `catalog/auth.py`

Arquivo: `catalog/auth.py`

### Linhas 9-17

- carrega `.env` de novo;
- le `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID`, `AZURE_REDIRECT_URI`.

### Linhas 19-33

- monta `AUTH_CONFIGURED`;
- invalida credenciais ficticias contendo `"seu"` ou `"none"`;
- se nao estiver configurado, `AUTHORITY = None`;
- senao monta a URL do tenant.

### Linhas 35-46

- define escopos;
- define `CACHE_FILE = token_cache.bin`;
- tenta desserializar cache existente;
- ignora cache corrompido com warning.

### Linhas 49-63

- `_save_cache()` persiste cache;
- `_build_msal_app()` cria `ConfidentialClientApplication`;
- se nao houver credenciais validas, levanta erro.

### Linhas 66-81: `get_access_token`

- se nao houver auth configurada, levanta `OSError`;
- tenta `acquire_token_silent` na primeira conta disponivel;
- se nao conseguir, devolve HTTP 401.

### Linhas 87-113

- `/auth/login` gera URL de autorizacao e redireciona;
- `/auth/callback` recebe `code`, troca por token e persiste cache.

Importante:

- as rotas de fotos nao dependem obrigatoriamente disso;
- elas foram escritas para sobreviver mesmo sem Azure configurado.

---

## Cache simples

## `catalog/cache.py`

Arquivo: `catalog/cache.py`

### Linhas 5-23: `TTLCache`

- armazena pares `(valor, expiracao)`;
- `get` remove itens vencidos;
- `set` grava com `time.time() + ttl`.

### Linhas 25-42: `cached`

- gera uma chave com:
  - nome da funcao;
  - args;
  - kwargs ordenados;
- reutiliza valor se ainda estiver valido.

Esse cache e usado para reduzir custo em:

- buscas do Graph;
- alguns builds derivados.

Ele e deliberadamente simples.

---

## Google Sheets

## `catalog/spreadsheet.py`

Arquivo: `catalog/spreadsheet.py`

### Linhas 12-18: `_extract_sheet_id`

- usa regex `/d/<ID>` na URL do Google Sheets;
- se nao bater, levanta `ValueError`.

### Linhas 21-51: `fetch_sheet`

Passos:

1. extrai o ID;
2. monta URL de exportacao CSV;
3. faz `requests.get(..., timeout=10)`;
4. traduz timeout/connection/http error em `ValueError` mais amigavel;
5. le o CSV com `pandas.read_csv(StringIO(resp.text))`;
6. traduz erro de parse para `ValueError`.

Esse modulo e pequeno, mas tem boa ergonomia de erro.

---

## Integracao com Microsoft Graph

## `catalog/graph_client.py`

Arquivo: `catalog/graph_client.py`

Esse arquivo e o cliente HTTP direto do Graph.

### Linhas 10-12: `_get_headers`

- pega token com `get_access_token`;
- monta header `Authorization: Bearer ...`.

### Linhas 15-20: `get_share_info`

- converte share URL para share ID;
- consulta `/shares/{share_id}/driveItem`;
- devolve JSON do Graph.

### Linhas 23-31: `list_children`

- consulta os filhos de um item de drive;
- devolve `data["value"]`.

## `catalog/graph_catalog.py`

Arquivo: `catalog/graph_catalog.py`

Aqui fica a logica "pura", separada do HTTP.

### Linhas 9-12: `encode_share_url`

- remove query string;
- aplica base64 URL-safe;
- remove `=`;
- prefixa com `u!`.

### Linhas 15-29: `list_shared_items`

- usa callbacks `get_share_info_fn` e `list_children_fn`;
- resolve `drive_id` e `item_id`;
- se nao conseguir, levanta `EnvironmentError`.

Essa separacao por callback facilita testes.

### Linhas 32-45: `categorize_photos`

- percorre itens;
- filtra opcionalmente por codigo presente no nome;
- preenche:
  - `white_background`;
  - `ambient`;
  - `measures`.

### Linhas 48-92: `find_images_for_code`

Essa e a busca recursiva remota.

Fluxo:

1. resolve `drive_id` e `item_id`;
2. cria lista `matches`;
3. define funcao interna `_recurse`;
4. interrompe se `depth > max_depth`;
5. lista filhos;
6. se o item for pasta, desce recursivamente;
7. se for arquivo:
   - filtra por extensao de imagem;
   - usa `match_filename_fn` para saber se o nome bate com o codigo;
   - monta URL de download;
   - guarda `{name, variant, url}`;
8. ordena pelo `variant`.

Perceba:

- o Graph client sabe falar HTTP;
- `graph_catalog.py` sabe fazer descoberta sem depender de implementacao concreta.

---

## `catalog/onedrive.py`: fachada operacional

Arquivo: `catalog/onedrive.py`

Apesar do nome, ele nao representa apenas OneDrive remoto.
Hoje ele virou a grande fachada de catalogo:

- Graph remoto;
- indice local;
- merge de produtos;
- fotos de estoque.

### Linhas 7-26

- importa `graph_catalog`, `local_catalog`, `product_catalog`;
- importa `graph_client`;
- importa `cached`;
- importa helpers de midia e estoque.

### Linhas 28-41

- `_encode_share_url`, `list_shared_items`, `categorize_photos` apenas delegam.

### Linhas 44-54: `find_images_for_code`

- usa `@cached`;
- chama `graph_catalog.find_images_for_code(...)`;
- injeta:
  - `get_share_info`;
  - `list_children`;
  - `_match_filename`;
  - `IMG_EXTENSIONS`.

### Linhas 57-100

- delegam descoberta de raiz local e build do indice local;
- `get_local_index` tem comentario explicando que reconstrui o indice para refletir mudancas de pasta imediatamente.

### Linhas 103-143

Camada de alto nivel:

- `list_local_products(...)`;
- `categorize_local_photos(...)`;
- `find_local_images_for_code(...)`;
- `resolve_local_asset_path(...)`.

Esses metodos sao os que o resto do sistema usa de fato.

---

## Descoberta do catalogo local

## `catalog/local_catalog.py`

Arquivo: `catalog/local_catalog.py`

Esse modulo descobre produtos e fotos no disco.

## Bloco 1: constantes e descoberta de raizes

### Linhas 20-25

- definem extensoes suportadas;
- definem regex de codigo;
- definem tokens de categoria para heuristica.

### Linhas 28-32: `_env_flag`

- interpreta env booleana.

### Linhas 35-41: `_local_products_paths`

Gera caminhos candidatos sob uma raiz base:

- `FOTOS_PRODUTOS`;
- `MARKETING/01_PRODUTOS/BACKUP PRODUTOS`;
- `MARKETING/Catalogo`;
- `MARKETING/01_PRODUTOS`.

### Linhas 44-65: `_candidate_local_roots`

Procura candidatos em:

- `CATALOG_LOCAL_PRODUCTS_PATH`;
- `OneDrive`;
- `OneDriveCommercial`;
- `OneDriveConsumer`;
- `USERPROFILE/OneDrive`;
- `Path.home()/OneDrive` se fallback estiver habilitado.

### Linhas 68-87

- `existing_local_roots(...)` deduplica e valida diretorios existentes;
- `resolve_local_products_root(...)` pega o primeiro.

Em resumo:

- o projeto tenta ser resiliente a diferentes layouts de OneDrive.

## Bloco 2: limpeza de nome e inferencia de categoria

### Linhas 90-101: `_clean_product_name`

- limpa espacos, sufixos de variante, sufixo "atalho/shortcut";
- descarta nomes que sejam apenas numero simples.

### Linhas 104-128: `_derive_category_from_product_name`

- tenta extrair categoria a partir das primeiras palavras do nome;
- para ao encontrar digitos;
- remove conectivos e tokens fracos;
- retorna `"Sem categoria"` se nao conseguir.

### Linhas 131-168

- `_extract_code_and_name_from_segment` tenta ler codigo prefixado em um segmento;
- `_extract_code_from_parts` percorre nome do arquivo e pastas acima para inferir:
  - codigo;
  - nome do produto;
  - categoria.

Esse bloco explica por que o sistema entende tanto layouts como:

- `ABAJUR/5989 - ABAJUR TESTE/foto.jpg`
- `1171 - FITA LED C FONTE.jpg`
- `1171_1.jpg`

## Bloco 3: atalhos `.lnk`

### Linhas 171-185: `_rel_path_in_allowed_roots`

- garante que um target absoluto realmente esteja dentro das raizes autorizadas;
- devolve caminho relativo, se valido.

### Linhas 188-238: `resolve_shortcut_targets`

No Windows:

1. cria script PowerShell;
2. usa COM `WScript.Shell`;
3. percorre `.lnk`;
4. resolve `TargetPath`;
5. serializa em JSON;
6. transforma isso em dict `link -> target`.

Ou seja:

- o projeto aceita catalogos compostos de atalhos, nao apenas imagens reais dentro da pasta principal.

## Bloco 4: indexacao local

### Linhas 241-334: `scan_local_photo_index`

Esse e o coracao da indexacao local.

Para cada arquivo encontrado:

1. filtra extensoes aceitas;
2. calcula `rel_path`;
3. quebra em partes de pasta;
4. tenta inferir `code`, `name`, `category`;
5. cria ou atualiza um `record` por codigo;
6. se for imagem real:
   - adiciona em `files`;
   - classifica variante com `_classify_variant`;
7. se for `.lnk`:
   - resolve target;
   - valida extensao do target;
   - valida que esta dentro de raizes permitidas;
   - adiciona `file_info` apontando para a imagem real.

Depois, para cada produto:

- ordena arquivos com `_local_file_sort_key`;
- escolhe `white_background`;
- escolhe `ambient`;
- escolhe `measures`;
- usa `_pick_distinct_fallback` para nao repetir o mesmo arquivo em todas as categorias quando possivel.

Resultado final do indice:

```python
{
  "5989": {
    "code": "5989",
    "name": "...",
    "category": "...",
    "files": [...],
    "variants": {
      "white_background": ...,
      "ambient": ...,
      "measures": ...
    }
  }
}
```

### Linhas 337-370

- `build_local_photo_index(...)` construi o indice principal;
- `get_local_index(...)` reconstrui por raiz para refletir mudancas imediatamente.

---

## Heuristicas de nome de arquivo e categoria

## `catalog/product_media.py`

Arquivo: `catalog/product_media.py`

Esse modulo concentra heuristicas reutilizaveis para arquivos de midia.

### Linhas 17-36: `_match_filename`

Reconhece padroes como:

- `6649.jpg` -> variante `0`;
- `6649-1.jpg` -> variante `1`;
- `6649 (2).png` -> variante `2`.

Se o prefixo numerico nao bater com o codigo esperado, retorna `None`.

### Linhas 39-47: `_classify_variant`

Decide classe semantica pelo nome:

- se contem `branco/white` -> `white_background`;
- se contem `ambient/ambiente/cena` -> `ambient`;
- se contem `medida/measure/dimens` -> `measures`;
- senao -> `other`.

### Linhas 50-109

- removem acentos;
- quebram texto em tokens normalizados.

### Linhas 56-143: categoria canonica

`_token_to_category(...)` e `_canonical_category(...)` mapeiam varios nomes para grupos como:

- `ARANDELA`;
- `ABAJUR`;
- `PENDENTE`;
- `TRILHO`;
- `REFLETOR`;
- `FITA LED`;
- `LUMINARIA`.

Isso ajuda a unificar nomes ruidosos vindos de pasta, arquivo, cadastro e estoque.

### Linhas 146-186

- `_is_description_title(...)` detecta imagem "principal descritiva";
- `_local_file_sort_key(...)` ordena arquivos priorizando:
  1. imagem descritiva;
  2. variantes numericas;
  3. resto.

Essa ordenacao e fundamental para que a galeria mostre primeiro a imagem certa.

### Linhas 189-191: `_asset_url`

- transforma `rel_path` em URL servida pelo backend.

### Linhas 201-206 e 209-213

- escolhem fallbacks distintos;
- ordenam codigos numericos corretamente.

---

## Cadastro HTML

## `catalog/cadastro.py`

Arquivo: `catalog/cadastro.py`

Esse modulo le um `CADASTRO.html` exportado e cria indice por codigo.

## Bloco 1: descoberta e cache

### Linhas 13-15

- regex de codigo;
- lock;
- cache com `path`, `mtime` e `records`.

### Linhas 18-47

- descobrem a raiz do projeto;
- montam candidatos:
  - env `CATALOG_CADASTRO_HTML`;
  - `CADASTRO.html`;
  - `cadastro.html`;
  - `Cadastro.html`;
- resolvem caminho final.

## Bloco 2: higiene de texto

### Linhas 50-80

- `_repair_mojibake` tenta corrigir UTF-8 lido como latin-1;
- `_clean_cell` colapsa espacos e apaga placeholders visuais;
- `_normalize_header` remove acento e caixa;
- `_first_nonempty` escolhe o primeiro valor textual util.

## Bloco 3: selecao do melhor registro

### Linhas 83-87: `_record_score`

- conta campos preenchidos;
- mede riqueza textual;
- serve para escolher, entre varias linhas do mesmo codigo, a melhor.

## Bloco 4: parse do HTML

### Linhas 90-179: `_parse_cadastro_html`

Fluxo:

1. tenta importar `BeautifulSoup`;
2. abre arquivo com `utf-8` e `errors="ignore"`;
3. seleciona `table.waffle tr`;
4. procura, nas primeiras 25 linhas, um cabecalho contendo `CODIGO` e `CATEGORIA`;
5. monta um lookup `header -> indice`;
6. resolve indices para colunas importantes;
7. percorre linhas de dados;
8. extrai codigo por regex;
9. monta `record` com:
   - `code`;
   - `category`;
   - `name`;
   - `description`;
   - `specs`;
10. compara score e guarda o melhor por codigo.

### Linhas 182-203: `load_cadastro_index`

- resolve caminho;
- compara `mtime` com cache;
- se nada mudou, reutiliza;
- senao reparseia.

Esse modulo e uma ponte forte entre o "cadastro comercial" e o catalogo tecnico.

---

## Montagem final do catalogo local

## `catalog/product_catalog.py`

Arquivo: `catalog/product_catalog.py`

Esse modulo pega o indice local bruto e transforma em produtos "prontos para API".

## Bloco 1: cadastro e placeholders

### Linhas 21-32: `load_cadastro_records`

- respeita `CATALOG_CADASTRO_HTML`;
- se houver `path_override` sem cadastro global, evita misturar contexto;
- em erro, loga warning e retorna `{}`.

### Linhas 35-48

- `_stringify`, `_is_placeholder_photo`, `_needs_resolved_photos`.

Objetivo:

- saber quando uma foto ainda precisa ser substituida por algo real.

## Bloco 2: resolucao de fotos

### Linhas 51-67: `_resolved_photo_fields`

- transforma um `record` do indice local/estoque em URLs finais:
  - `URLFoto`;
  - `FotoBranco`;
  - `FotoAmbient`;
  - `FotoMedidas`.

### Linhas 69-107: `_apply_resolved_photos`

- mescla fotos ja existentes com novas resolvidas;
- so substitui placeholders ou campos vazios;
- preserva foto valida que ja existia.

### Linhas 110-132: `_enrich_products_with_resolved_photos`

- localiza produtos ainda com placeholder;
- para codigos fora do indice local, consulta fotos de estoque em lote;
- aplica resolucao produto a produto.

## Bloco 3: resolver produto unico

### Linhas 135-145

- `_resolve_product_record` procura primeiro no indice local;
- se nao achar, tenta foto de estoque por codigo.

## Bloco 4: `list_local_products`

### Linhas 147-215

Esse e o fluxo central do catalogo.

Passos:

1. importa `merge_products_with_erp`;
2. monta indice local;
3. se nao houver indice e o runtime for padrao:
   - tenta usar produtos da planilha de estoque;
   - enriquece com fotos de estoque;
   - ja mescla com ERP;
4. carrega cadastro;
5. para cada item do indice local:
   - pega variantes;
   - gera URLs;
   - mistura nome/descricao/specs do cadastro;
   - resolve categoria do cadastro ou heuristica canonica;
   - cria dict final do produto;
6. depois chama `merge_products_with_erp(products)`;
7. se `path_override` foi passado, para por aqui;
8. senao, ainda tenta enriquecer placeholders com fotos de estoque.

Ou seja:

- o produto nasce do disco;
- e enriquecido pelo cadastro;
- e depois e enriquecido pelo ERP;
- e, se ainda faltar foto, o estoque pode completar.

## Bloco 5: fotos e galeria

### Linhas 218-242: `categorize_local_photos`

- resolve record local/estoque;
- devolve as tres fotos principais.

### Linhas 245-276: `find_local_images_for_code`

- resolve record;
- ordena `files`;
- devolve lista `{name, variant, url}`.

### Linhas 279-302: `resolve_local_asset_path`

- aceita caminho relativo;
- inclui tambem a raiz de fotos do estoque;
- garante que o arquivo final continua dentro de uma raiz permitida;
- devolve caminho absoluto se existir.

Esse metodo e a parte critica de seguranca do fluxo de imagens locais.

---

## Fallback por estoque

## `catalog/stock_catalog.py`

Arquivo: `catalog/stock_catalog.py`

Esse modulo faz duas coisas:

1. carrega produtos da planilha de estoque;
2. tenta associar fotos do estoque a esses produtos.

## Bloco 1: constantes e descoberta

### Linhas 25-50

- nome da aba `POSICAO_ESTOQUE`;
- placeholders;
- extensoes aceitas, inclusive `.psd`;
- regex de codigo de 4 digitos;
- regex de tokens de modelo;
- stopwords da descricao.

### Linhas 60-88: `_candidate_stock_report_paths`

- olha `CATALOG_STOCK_REPORT_PATH`;
- opcionalmente faz auto-discovery em `reports/*.xlsx`;
- ignora arquivos temporarios `~$`;
- deduplica.

### Linhas 124-143: `_resolve_stock_photos_root`

Procura em:

- `path_override`;
- `CATALOG_STOCK_PHOTOS_ROOT`;
- fallback `~/OneDrive/MARKETING/01_PRODUTOS`.

## Bloco 2: normalizacao e matching por texto

### Linhas 91-114: `_normalize_stock_code`

- converte numeros inteiros, floats inteiros e strings;
- aceita codigos entre 3 e 8 digitos;
- remove sufixo `.0`.

### Linhas 156-181

- normalizam texto de busca;
- extraem tokens relevantes;
- extraem tokens de modelo.

### Linhas 184-221: `_build_stock_description_profiles`

Cria perfis por codigo com:

- tokens textuais;
- tokens de modelo;
- indices invertidos `token -> codes`, `model -> codes`.

### Linhas 224-275: `_match_stock_code_by_description`

Quando o arquivo de foto nao tem codigo explicito:

1. extrai tokens do nome/caminho;
2. gera candidatos pelo indice invertido;
3. calcula score:
   - hit de modelo vale mais;
   - hit textual vale menos;
4. evita empates ambiguos;
5. exige score minimo.

Essa parte e uma heuristica inteligente para fotos baguncadas.

## Bloco 3: varredura de fotos de estoque

### Linhas 278-368: `_scan_stock_photo_index`

Fluxo:

1. percorre todas as imagens da raiz;
2. tenta achar codigo diretamente no nome;
3. se nao achar, tenta no caminho;
4. se ainda nao achar, tenta matching por descricao;
5. cria `record` por codigo;
6. classifica variantes;
7. no fim, ordena e escolhe fallbacks como no indice local.

## Bloco 4: enriquecimento de produtos

### Linhas 385-432: `_enrich_stock_products_with_photos`

- pega os codigos dos produtos da planilha;
- monta perfis de descricao;
- constroi indice de fotos;
- substitui placeholders por URLs reais.

### Linhas 435-460

- resolvem fotos de estoque por conjunto de codigos ou por codigo unico.

## Bloco 5: leitura da planilha

### Linhas 463-523: `_load_products_from_stock_report`

Passos:

1. valida arquivo;
2. importa `openpyxl`;
3. abre workbook em modo leitura;
4. exige aba `POSICAO_ESTOQUE`;
5. percorre linhas a partir da linha 2;
6. le codigo da coluna 2;
7. le descricao da coluna 3;
8. cria produto com placeholders e categoria inferida;
9. ordena por codigo e numero da linha.

### Linhas 526-531

- tentam varios caminhos candidatos e param no primeiro que funciona.

Conclusao:

- o estoque e um fallback completo de catalogo, nao apenas uma fonte de foto.

---

## ERP: normalizacao, persistencia e merge

## `catalog/erp_catalog.py`

Arquivo: `catalog/erp_catalog.py`

Esse e o modulo mais importante do projeto em termos de regra de negocio.

Ele faz quatro trabalhos:

1. encontra o JSON ativo do ERP;
2. normaliza payloads heterogeneos;
3. persiste o espelho local;
4. mescla ERP com catalogo montado de outras fontes.

## Bloco 1: constantes e aliases

### Linhas 15-37

- definem caminhos padrao;
- definem chaves candidatas do container de produtos;
- definem regex;
- definem nomes de arquivo candidatos para discovery;
- definem encodings tentados.

### Linhas 39-87

Aliases para varios campos:

- codigo;
- nome;
- descricao;
- categoria;
- especificacoes;
- foto branca;
- foto ambientada;
- foto de medidas;
- foto de capa;
- departamento;
- secao.

Isso e crucial porque o JSON do ERP nao precisa ter um schema fixo.

## Bloco 2: mapas de categoria

### Linhas 88-147

Trazem:

- mapa `departamento + secao -> categoria`;
- mapa `departamento -> categoria`;
- mapa de categorias de negocio finais;
- prioridade por palavras-chave de nome/descricao.

Essa parte transforma categoria tecnica em categoria comercial do catalogo.

## Bloco 3: inferencia e normalizacao

### Linhas 219-347

Funcoes importantes:

- `_env_flag`;
- `_normalized_tokens`;
- `_token_to_category`;
- `_is_numeric_text`;
- `_build_dept_category`;
- `_infer_category`;
- `_to_business_category`.

Leitura conceitual:

- primeiro tenta respeitar categoria textual valida;
- se a categoria estiver ruim ou numerica, tenta inferir por nome/descricao;
- se ainda assim falhar, usa depto/secao;
- no fim, comprime tudo para um conjunto pequeno de categorias de negocio.

Exemplos:

- `PAINEL` vira `ILUMINACAO TECNICA`;
- `BALIZADOR` vira `ILUMINACAO EXTERNA E PUBLICA`;
- `RELE` vira `COMPONENTES E ACESSORIOS`.

## Bloco 4: descoberta do JSON ERP

### Linhas 371-443

Funcoes:

- `resolve_erp_inbox_dir`;
- `_resolve_erp_source_dirs`;
- `_resolve_json_target_path`;
- `_resolve_json_path`.

Regras:

- respeita `CATALOG_ERP_JSON_PATH` se existir;
- se nao existir, pode procurar automaticamente em:
  - raiz do repo;
  - `reports/`;
  - inbox ERP;
  - `catalog/json/`;
  - diretorios extras configurados.

Se houver varios arquivos candidatos:

- escolhe o mais recente por `mtime`.

## Bloco 5: extracao e normalizacao do payload

### Linhas 446-562

Fluxo:

- `_build_lookup` normaliza nomes de chave;
- `_pick_value` procura primeiro alias valido;
- `_normalize_code` extrai o codigo;
- `_extract_records` aceita:
  - lista de produtos;
  - objeto com `products`, `produtos`, `items`, etc.;
  - objeto indexado por codigo.
- `_normalize_erp_record` transforma cada registro em shape padrao do catalogo.

Dentro de `_normalize_erp_record`:

- resolve nome;
- resolve descricao;
- resolve categoria;
- resolve especificacoes;
- resolve URLs de foto;
- preserva campos extras nao vazios.

Esse e o ponto em que payload "sujo" vira modelo padrao do projeto.

## Bloco 6: leitura e seguranca de arquivo

### Linhas 565-632

- `_parse_json_bytes` tenta varios encodings;
- `_load_json_file` traduz erro de leitura;
- `_sanitize_json_filename` impede nomes ruins no upload;
- `_is_within` checa containment seguro;
- `_resolve_candidate_file_path` valida caminhos absolutos e relativos e bloqueia traversal `..`.

Essa parte e fundamental para os endpoints de upload/import-file.

## Bloco 7: importacao e status

### Linhas 634-684

- `import_erp_payload(payload)`:
  - monta indice;
  - exige ao menos um produto valido;
  - grava espelho JSON normalizado;
  - retorna metadata da importacao.

- `import_erp_file(file_path)`:
  - resolve arquivo permitido;
  - carrega;
  - importa;
  - inclui `source_path` e `source_size_bytes`.

- `receive_erp_file(filename, content)`:
  - parseia JSON bruto recebido pela API;
  - grava no inbox;
  - evita sobrescrever arquivo com timestamp;
  - importa o payload;
  - retorna tambem `uploaded_path`.

### Linhas 687-747

- `list_erp_files()` lista todos os JSONs encontrados e marca o ativo;
- `load_erp_index()` carrega o JSON ativo;
- `get_erp_status()` informa caminho, existencia, quantidade e data de atualizacao.

## Bloco 8: merge com produtos do catalogo

### Linhas 750-895

Essa e a parte mais importante do modulo.

#### `_placeholder_urls(code)` - linhas 750-755

- gera placeholders por codigo.

#### `_merge_single_product(base, erp)` - linhas 758-799

Mescla produto local com ERP:

- sobrescreve nome/descricao/specs se ERP trouxer;
- recalcula categoria comercial;
- usa fotos do ERP se existirem;
- preserva e completa campos extras;
- mantem `Codigo` coerente.

#### `_create_product_from_erp(erp)` - linhas 802-835

Cria um produto novo apenas com ERP:

- usa placeholders se nao houver foto;
- normaliza categoria para negocio;
- preserva campos extras.

#### `sort_products_by_category` - linhas 856-857

- ordena por categoria, codigo e nome.

#### `merge_products_with_erp(products)` - linhas 860-895

Fluxo:

1. carrega indice ERP;
2. se nao houver ERP, devolve lista original;
3. le `CATALOG_ERP_STRICT_MODE`;
4. percorre produtos base:
   - se o codigo existir no ERP, mescla;
   - se nao existir:
     - no strict mode, omite;
     - fora do strict mode, mantem;
5. adiciona produtos que existem so no ERP;
6. normaliza categoria final de todos;
7. ordena o resultado.

Interpretacao pratica:

- o ERP pode funcionar como filtro, enriquecedor e criador de itens.

---

## Exportacoes

## `catalog/exporter.py`

Arquivo: `catalog/exporter.py`

Esse modulo concentra todas as exportacoes.

## Bloco 1: constantes e utilitarios tabulares

### Linhas 25-84

- formatos suportados;
- colunas preferidas;
- campos de foto;
- tamanho da pagina PDF;
- candidatos da imagem de banner da marca;
- labels mais amigaveis de atributos.

### Linhas 86-210

- normalizacao de texto;
- conversao segura para string;
- slugificacao;
- carregamento de produtos via `onedrive.list_local_products()`;
- filtro por query/categoria/codigo;
- ordenacao de colunas;
- geracao de CSV/JSON/XLSX.

Observe que:

- exportacao sempre parte da mesma fonte usada pela API;
- isso evita divergencia entre o que a tela mostra e o que e exportado.

## Bloco 2: infraestrutura do PDF

### Linhas 213-468

Essas funcoes:

- carregam fontes;
- medem texto;
- fazem wrap;
- desenham caixas arredondadas;
- ajustam imagens;
- resolvem bytes de foto local ou remota.

Elas sao helpers visuais. A regra de negocio mais relevante aqui e `_resolve_photo_bytes`:

- se a URL for `/catalog/local/asset?...`, tenta resolver arquivo local real;
- se for `http/https`, faz download;
- senao falha silenciosamente.

## Bloco 3: PDF de produto unico

### Linhas 489-642: `_build_product_pdf_pages`

Gera uma ficha tecnica visual com:

- hero da marca;
- codigo;
- categoria;
- nome;
- descricao;
- especificacoes;
- imagem principal;
- thumbnails adicionais;
- cards metricos;
- grade de atributos.

Se houver atributos demais:

- cria paginas extras.

## Bloco 4: PDF tabular do catalogo

### Linhas 645-702: `_build_catalog_pdf_pages`

Quando a exportacao tem varios produtos:

- cria PDF mais tabular;
- repete resumo de filtros;
- lista codigo, nome e categoria;
- pagina os itens.

## Bloco 5: ZIP com manifesto

### Linhas 723-800

- `_build_photo_manifest_rows` cria lista de referencias de foto;
- `_build_zip_bytes` monta pacote com:
  - CSV;
  - JSON;
  - README;
  - pasta `fotos/`;
  - `manifesto_fotos.csv`.

Se uma foto nao puder ser baixada:

- a referencia continua no manifesto;
- apenas o arquivo em si nao entra no ZIP.

## Bloco 6: dispatcher final

### Linhas 803-855

- `_response_metadata` escolhe `media_type` e nome do arquivo;
- `build_catalog_export(...)`:
  - valida formato;
  - filtra produtos;
  - escolhe `base_name`;
  - chama builder correspondente;
  - retorna `payload`, `media_type`, `filename`.

---

## Frontend moderno

## Infraestrutura

## `frontend/package.json`

Arquivo: `frontend/package.json`

Mostra o stack do frontend:

- React 18;
- React DOM;
- React Router DOM;
- TanStack React Query;
- Vite;
- TypeScript;
- ESLint + Prettier.

Scripts principais:

- `npm run dev`;
- `npm run build`;
- `npm run preview`;
- `npm run lint`;
- `npm run format`.

## `frontend/vite.config.ts`

Arquivo: `frontend/vite.config.ts`

### Linhas 4-22

- carrega envs com `loadEnv`;
- define alvo do proxy em `VITE_DEV_PROXY_TARGET` ou `http://127.0.0.1:8000`;
- proxya:
  - `/catalog`;
  - `/auth`.

Isso permite que o frontend em dev converse com o backend sem CORS manual.

## `frontend/index.html`

Arquivo: `frontend/index.html`

### Linhas 1-18

- define HTML base;
- carrega fontes `Manrope` e `Sora`;
- cria `<div id="root"></div>`;
- injeta `src/main.tsx`.

---

## Bootstrap do frontend

## `frontend/src/main.tsx`

Arquivo: `frontend/src/main.tsx`

### Linhas 9-16

- cria `QueryClient` com:
  - `refetchOnWindowFocus: false`;
  - `retry: 1`.

### Linhas 18-30

- cria root React;
- envolve a app com:
  - `React.StrictMode`;
  - `QueryClientProvider`;
  - `BrowserRouter`;
  - `Routes`.

Rotas:

- `/` -> `<App />`
- `/produto/:productId` -> `<App />`
- qualquer outra -> redirect para `/`

Ou seja:

- a mesma tela `App` funciona como grade e como detalhe.

---

## Tipos do frontend

## `frontend/src/types.ts`

Arquivo: `frontend/src/types.ts`

Esse arquivo define o contrato do lado do navegador.

Principais tipos:

- `ProductPhotos`;
- `ProductRecord`;
- `ProductAttribute`;
- `CatalogProduct`;
- `GalleryApiImage`;
- `ProductImagesResponse`;
- `GalleryEntry`;
- `CatalogExportFormat`;
- `CatalogExportOptions`;
- `ErpImportSummary`.

Interpretacao:

- `ProductRecord` e "payload cru";
- `CatalogProduct` e o modelo normalizado para UI.

---

## Nucleo utilitario do frontend

## `frontend/src/lib/catalog-core.ts`

Arquivo: `frontend/src/lib/catalog-core.ts`

### Linhas 3-18

- define bases padrao da API;
- parseia `VITE_API_BASES`;
- define timeout;
- define chave de persistencia de UI.

### Linhas 21-34

- constroem placeholder SVG em `data:` URL.

### Linhas 36-44: `setFallbackImage`

- impede loop de fallback;
- substitui `src` da imagem quando ela quebra.

### Linhas 46-48

- exportam placeholders para card, detalhe e thumb.

## `frontend/src/lib/catalog-storage.ts`

Arquivo: `frontend/src/lib/catalog-storage.ts`

### Linhas 3-11

- definem formato persistido:
  - `query`;
  - `category`.

### Linhas 13-34: `readPersistedUiState`

- le `localStorage`;
- parseia JSON;
- aplica fallback seguro;
- em erro, retorna estado padrao.

### Linhas 36-45: `persistUiState`

- grava estado em `localStorage`.

Observacao:

- as mensagens de `console.warn` aparecem com mojibake no arquivo-fonte;
- isso nao muda a logica, mas revela problema de encoding textual no repositorio.

---

## API client do frontend

## `frontend/src/lib/catalog-api.ts`

Arquivo: `frontend/src/lib/catalog-api.ts`

Esse arquivo centraliza todo o trafego HTTP.

## Bloco 1: origem ativa e URLs

### Linhas 10-35

- `activeApiOrigin` guarda a base da API que funcionou por ultimo;
- `resolveBaseOrigin` transforma base configurada em origin;
- `getActiveApiOrigin` devolve a base atual;
- `absolutizeApiUrl` converte URL relativa para absoluta.

Esse detalhe e muito importante porque o backend pode devolver `/catalog/local/asset?...`, e o frontend precisa transformar isso numa URL valida mesmo se estiver em outra origem durante dev.

## Bloco 2: exportacao e downloads

### Linhas 37-118

- montam URL de exportacao;
- interpretam `Content-Disposition`;
- inferem extensao;
- disparam download no navegador.

### Linhas 120-153: `downloadCatalogExport`

- tenta todas as `API_BASES`;
- baixa blob;
- cria `objectUrl`;
- dispara download;
- atualiza `activeApiOrigin`.

### Linhas 155-175: `downloadImageFile`

- tenta baixar a imagem como blob;
- se falhar, faz fallback abrindo a URL diretamente para download.

## Bloco 3: requests genericos

### Linhas 177-186: `fetchWithTimeout`

- usa `AbortController`;
- cancela apos `REQUEST_TIMEOUT_MS`.

### Linhas 188-214: `fetchFromBases`

- percorre todas as bases configuradas;
- ignora 404 silenciosamente;
- atualiza `activeApiOrigin` na primeira resposta valida.

### Linhas 216-250: `postJsonToBases`

- faz a mesma estrategia para POST com JSON.

## Bloco 4: wrappers de negocio

### Linhas 252-305

- `normalizePhotos`;
- `fetchProducts`;
- `fetchPhotosByCode`;
- `fetchImagesByCode`;
- `importErpCatalog`.

Esses wrappers escondem a complexidade de multiplas origens e normalizacao.

---

## Normalizacao de produtos no frontend

## `frontend/src/lib/catalog-products.ts`

Arquivo: `frontend/src/lib/catalog-products.ts`

Esse modulo transforma payload cru da API em modelo amigavel para UI.

## Bloco 1: leitura tolerante a alias

### Linhas 14-38

- `normalizeText` remove acento e padroniza texto;
- `getField` cria lookup normalizado de chaves e procura aliases.

Resultado:

- tanto `Codigo` quanto `codigo`, `Code`, `SKU` podem alimentar o mesmo campo.

## Bloco 2: especificacoes e descricao composta

### Linhas 40-103

- `parseSpecsMap` quebra texto de especificacoes em `chave: valor`;
- `getSpecValue`, `getRegexValue`, `resolveTemplateValue` extraem dados.

### Linhas 105-176: `buildSiteDescription`

Tenta compor descricao comercial usando:

- categoria;
- tecnologia;
- caracteristica;
- potencia;
- temperatura;
- fluxo ou eficiencia;
- indice de protecao;
- cor;
- formato;
- material.

Se nao houver dados suficientes:

- volta para a descricao original.

Esse e um refinamento interessante: a UI pode exibir algo mais rico sem exigir que o backend entregue um campo pronto.

## Bloco 3: atributos extras

### Linhas 186-249

- `BASE_PRODUCT_FIELD_KEYS` define o que ja e "campo conhecido";
- `collectExtraAttributes` captura tudo que sobrar.

Isso e muito importante porque o ERP traz campos variados.
Em vez de perder esses dados, o frontend os coloca na area de atributos do detalhe.

## Bloco 4: modelo normalizado

### Linhas 251-282: `normalizeProduct`

Cria `CatalogProduct` com:

- `id`;
- `routeId`;
- `code`;
- `name`;
- `description`;
- `category`;
- `cover`;
- `specs`;
- `photos`;
- `attributes`.

Esse e o ponto em que o frontend deixa de lidar com payload cru.

## Bloco 5: fotos e galeria

### Linhas 284-374

- `hasAnyPhoto` checa se fotos existem;
- `fallbackPhotos` cria placeholders por codigo;
- `imageOrderKey` decide ordem da galeria;
- `buildGalleryEntries` usa:
  - lista completa da API se existir;
  - senao, capa + branco + ambientada + medidas;
  - se nada existir, usa placeholder.

---

## Componente principal da UI

## `frontend/src/App.tsx`

Arquivo: `frontend/src/App.tsx`

Esse arquivo governa a aplicacao inteira.

## Bloco 1: hook de produtos

### Linhas 27-33: `useCatalogProducts`

- usa React Query com `queryKey = ["catalog-products"]`;
- busca produtos via `fetchProducts`;
- `staleTime = 60s`.

## Bloco 2: estado inicial e normalizacao

### Linhas 35-48

- le `productId` da rota;
- le estado persistido;
- cria estados `query` e `category`;
- chama `useCatalogProducts()`;
- transforma `productsQuery.data` em `CatalogProduct[]` com `normalizeProduct`.

## Bloco 3: carga de fotos resumidas

### Linhas 50-76

Esse `useQuery`:

- usa como chave a lista concatenada de codigos;
- so roda se houver produtos;
- para cada produto:
  - se ele ja tiver fotos embutidas, reutiliza;
  - senao chama `fetchPhotosByCode`;
  - se vier vazio, usa `fallbackPhotos`.

Resultado:

- `photosByProductId`.

## Bloco 4: selecao por rota

### Linhas 80-90

- encontra produto cujo `routeId` bate com `productId`;
- se a rota apontar para item inexistente e os produtos ja tiverem carregado, faz `navigate("/")`.

## Bloco 5: galeria completa do item selecionado

### Linhas 92-104

- se houver produto selecionado, busca `fetchImagesByCode(code)`;
- se nao houver, devolve array vazio.

## Bloco 6: persistencia de filtros

### Linhas 106-108

- grava `query` e `category` no `localStorage` sempre que mudarem.

## Bloco 7: filtros e agrupamento

### Linhas 110-149

- calcula categorias disponiveis;
- corrige categoria selecionada se ela sumir;
- filtra por texto;
- agrupa produtos por categoria;
- monta `selectedGalleryEntries`.

## Bloco 8: acoes

### Linhas 151-180

- define estados visuais;
- trata mensagens de erro;
- define `openProduct`, `closeDetail`;
- define `exportCatalog` para o recorte atual;
- define `exportSelectedProduct`.

## Bloco 9: render

### Linhas 182-298

Estrutura:

- fundo decorativo;
- hero da marca;
- `main`.

Se houver produto selecionado:

- renderiza `ProductDetail`.

Senao:

- toolbar de busca e categoria;
- painel de exportacao;
- resumo;
- banners de erro/loading;
- cards de estatistica;
- grade por categoria;
- estado vazio, se aplicavel.

Esse componente sozinho concentra:

- roteamento de alto nivel;
- estado da busca;
- integracao com API;
- navegacao para detalhe;
- exportacao.

---

## Componentes visuais

## `frontend/src/components/ProductCard.tsx`

Arquivo: `frontend/src/components/ProductCard.tsx`

- escolhe imagem de preview na ordem:
  - `item.cover`;
  - `photos.white_background`;
  - `photos.ambient`;
  - `photos.measures`;
  - fallback.
- o card inteiro vira botao clicavel;
- mostra:
  - imagem;
  - codigo;
  - categoria;
  - nome;
  - descricao;
  - thumb strip.

## `frontend/src/components/ProductDetail.tsx`

Arquivo: `frontend/src/components/ProductDetail.tsx`

### Destaques

- `activeIndex` controla foto principal;
- reseta para 0 quando muda o item;
- permite:
  - voltar ao catalogo;
  - exportar produto;
  - baixar foto selecionada;
  - baixar todas em ZIP;
- exibe atributos extras em `<dl>`.

Tambem ha um pequeno mapa de renomeacao:

- `CODPROD` -> `Codigo`;
- `CODAUXILIAR` -> `Codigo de barras`;
- `NBM` -> `NCM`;
- `PERCIPIVENDA` -> `IPI`.

## `frontend/src/components/Thumb.tsx`

Arquivo: `frontend/src/components/Thumb.tsx`

- `Thumb` e o mini-componente de uma foto + label;
- `ThumbStrip` mostra branco/ambientada/medidas.

## `frontend/src/components/ExportActions.tsx`

Arquivo: `frontend/src/components/ExportActions.tsx`

- concentra a lista fixa de botoes:
  - CSV;
  - Excel;
  - PDF;
  - ZIP;
  - JSON.

---

## Estilo visual

## `frontend/src/styles.css`

Arquivo: `frontend/src/styles.css`

Esse arquivo e grande, mas a organizacao dele e clara.

## Faixa 1: tokens globais

### Linhas 1-20

- variaveis CSS de cor, radius, shadow e imagem de faixa.

## Faixa 2: fundo e camadas decorativas

### Linhas 22-120

- background do body;
- elementos decorativos `::before`, `::after`;
- orbs desfocados.

## Faixa 3: hero

### Linhas 121-259

- container principal;
- identidade da marca;
- kicker;
- tipografia da marca;
- subtitulo.

## Faixa 4: toolbar, exportacao, banners e stats

### Linhas 289-451

- filtros;
- inputs;
- painel de exportacao;
- mensagens;
- cards resumo.

## Faixa 5: grade de produtos

### Linhas 452-596

- grid responsiva;
- card;
- media;
- chips;
- thumb strip.

## Faixa 6: detalhe do produto

### Linhas 597-802

- painel;
- botao voltar;
- layout em duas colunas;
- bloco de midia;
- metadata;
- galeria;
- toolbar da galeria.

## Faixa 7: estados e responsividade

### Linhas 803-950

- loading;
- empty state;
- animacao;
- media queries;
- agrupamento por categoria.

Em termos visuais, esse CSS nao e generico:

- usa uma identidade azul bem deliberada;
- tipografia `Sora` + `Manrope`;
- composicao com faixas e orbs;
- responsividade real;
- respeito a `prefers-reduced-motion`.

---

## Frontend legado

## `frontend/legacy/index.html`

Arquivo: `frontend/legacy/index.html`

Serve como fallback sem build.

Caracteristicas:

- React via CDN;
- ReactDOM via CDN;
- Babel standalone;
- carrega `js/catalog-core.js`, `js/catalog-products.js`, `js/catalog-api.js`, `js/catalog-storage.js`;
- depois carrega `app.js`.

## `frontend/legacy/app.js`

Arquivo: `frontend/legacy/app.js`

Esse arquivo reimplementa a app em estilo sem bundler.

Observacoes importantes:

- ele depende de `window.Catalog`;
- tem a mesma logica principal do frontend moderno;
- foi mantido para fallback de execucao sem build.

## Testes

## `tests/conftest.py`

Arquivo: `tests/conftest.py`

Esse arquivo prepara o ambiente de testes.

### O que ele faz

- garante que a raiz do projeto esteja no `sys.path`;
- cria pasta temporaria local dentro do proprio repo;
- força `TMP`, `TEMP`, `TMPDIR` e `PYTEST_DEBUG_TEMPROOT` para dentro do projeto;
- isola envs de OneDrive, cadastro, estoque e ERP;
- desliga auto-discovery para testes;
- limpa o cache de `catalog.cache`.

Objetivo:

- evitar flakiness em Windows;
- impedir que testes usem dados reais da maquina.

## `tests/test_routes.py`

Arquivo: `tests/test_routes.py`

Esse e o teste de integracao HTTP mais importante.

Ele valida:

- `/catalog/photos` com Graph mockado;
- erro 400 se `shareUrl` faltar quando necessario;
- protecao contra path traversal na SPA;
- placeholders quando Azure nao esta configurado;
- preferencia por imagens locais;
- comportamento de `/catalog/produtos/{codigo}/imagens`;
- `/catalog/local/produtos`;
- `/catalog/local/asset`;
- conversao TIFF;
- importacao e status do ERP;
- upload bruto do ERP;
- importacao de arquivo ERP ja depositado;
- rejeicao de path traversal em import-file;
- exportacao CSV/XLSX/PDF/ZIP;
- rejeicao de formato invalido.

Esses testes mostram claramente o contrato esperado da API.

## `tests/test_cadastro.py`

Arquivo: `tests/test_cadastro.py`

Valida o parser de `CADASTRO.html`:

- encontra cabecalho real;
- extrai codigo;
- le categoria;
- escolhe nome, descricao e specs.

## `tests/test_spreadsheet.py`

Arquivo: `tests/test_spreadsheet.py`

Pequeno e direto:

- URL valida do Google Sheets gera ID;
- URL invalida gera `ValueError`.

## `tests/test_erp_catalog.py`

Arquivo: `tests/test_erp_catalog.py`

Valida:

- mapeamento de categorias do ERP para categorias de negocio;
- enriquecimento de produto local com dados do ERP;
- criacao de produtos que existem apenas no ERP.

Observacao:

- existe um `test_merge_products_with_erp_data` iniciado e sem corpo util.

## `tests/test_onedrive.py`

Arquivo: `tests/test_onedrive.py`

Esse e o teste mais rico do projeto.

Ele cobre:

- encode de share URL;
- categorizacao de fotos remotas;
- busca recursiva no Graph com cache;
- endpoints de auth com mocks;
- leitura de produtos locais;
- enriquecimento com cadastro;
- fallback para planilha de estoque;
- associacao de fotos de estoque;
- matching por descricao;
- enriquecimento de itens so do ERP com fotos de estoque;
- suporte a TIFF;
- protecao de `resolve_local_asset_path`;
- preferencia de raiz `FOTOS_PRODUTOS`;
- layout flat;
- suporte a arquivos `1171_1.jpg`;
- agrupamento canonico por categoria;
- priorizacao de foto descritiva;
- ordenacao de variacoes 1-4;
- refresh do indice apos mudanca de pasta;
- suporte a atalhos `.lnk`;
- uso da imagem-alvo do atalho.

Se voce quiser entender a intencao do sistema, essa suite e quase tao importante quanto os modulos de producao.

---

## Fluxos completos de execucao

## Cenario 1: abrir a aplicacao

1. `app.py` cria `app`.
2. `bootstrap.create_app()` carrega `.env`, logging e settings.
3. `settings.py` decide se serve `frontend/dist` ou `frontend/legacy`.
4. `api/router.py` registra `/auth` e `/catalog`.
5. o navegador abre `/`.
6. `api/frontend.py` devolve `index.html`.
7. `frontend/src/main.tsx` sobe React Router + React Query.
8. `App.tsx` chama `fetchProducts()`.
9. `catalog/local/produtos` chama `onedrive.list_local_products()`.
10. `product_catalog.py` monta os produtos a partir do indice local, cadastro, ERP e estoque.

## Cenario 2: carregar fotos de um card

1. o frontend recebe produtos;
2. se o produto ja trouxe `FotoBranco/FotoAmbient/FotoMedidas`, o frontend reutiliza;
3. se nao trouxe, chama `/catalog/photos?code=...`;
4. o backend tenta:
   - foto local;
   - Graph, se necessario;
   - placeholder, em ultimo caso.

## Cenario 3: abrir detalhe do produto

1. `App.tsx` navega para `/produto/:routeId`;
2. resolve o produto selecionado;
3. chama `/catalog/produtos/{codigo}/imagens`;
4. backend tenta:
   - indice local;
   - fotos de estoque;
   - Graph remoto.
5. frontend monta galeria ordenada.

## Cenario 4: importar ERP

1. cliente chama `/catalog/erp/import` ou `/catalog/erp/upload`;
2. `erp_catalog.py` normaliza payload;
3. grava espelho JSON local;
4. nas proximas leituras de produtos, `merge_products_with_erp` entra em acao;
5. produtos locais sao enriquecidos;
6. produtos exclusivos do ERP podem entrar no catalogo.

## Cenario 5: exportar ZIP

1. frontend chama `/catalog/export?format=zip...`;
2. `exporter.py` filtra os produtos do recorte atual;
3. gera CSV e JSON;
4. tenta baixar fotos locais/remotas;
5. monta pacote ZIP com manifesto.

---

## Decisoes de arquitetura que aparecem no codigo

### 1. O projeto prefere composicao com fachadas

Exemplos:

- `bootstrap.py` compoe a app;
- `onedrive.py` compoe descoberta local + Graph + estoque;
- `services/*.py` escondem detalhes dos endpoints.

### 2. O projeto aceita dados imperfeitos

Em vez de exigir schema perfeito:

- usa aliases de chave;
- usa regex para inferir codigo;
- usa heuristicas para categoria;
- usa fallbacks encadeados.

### 3. O projeto privilegia degradacao graciosa

Quando algo falha:

- Graph indisponivel -> placeholder;
- planilha falha -> fallback local;
- fotos locais ausentes -> estoque ou placeholder;
- frontend build ausente -> legado.

### 4. O projeto mistura dados de varias fontes

Ordem mental mais fiel:

- disco/fotos;
- cadastro;
- ERP;
- estoque;
- Graph.

Nem sempre todas participam, mas o desenho foi feito para essa combinacao.

### 5. O contrato da API e propositalmente flexivel

`extra="allow"` e `collectExtraAttributes(...)` mostram isso com clareza.

---

## Pontos que merecem atencao ao estudar ou evoluir

### 1. Ha sinais de problemas de encoding textual

Voce vai ver strings com `CatÃ¡logo`, `NÃ£o`, `DescriÃ§Ã£o`.

Isso nao quebra a logica central, mas:

- dificulta leitura;
- pode afetar UX;
- merece uma limpeza posterior de encoding.

### 2. O modulo `onedrive.py` ja nao representa apenas OneDrive

Hoje ele e quase uma fachada geral do dominio.
O nome historico ficou, mas a responsabilidade cresceu.

### 3. `erp_catalog.py`, `stock_catalog.py` e `exporter.py` concentram muita regra

Sao os modulos mais importantes para entender o negocio e tambem os mais sensiveis para manutencao.

---

## Melhor ordem para estudar o codigo

Se voce quiser realmente entender tudo, recomendo esta ordem:

1. `README.md`
2. `app.py`
3. `catalog/bootstrap.py`
4. `catalog/core/settings.py`
5. `catalog/api/router.py`
6. `catalog/api/frontend.py`
7. `catalog/api/endpoints/*.py`
8. `catalog/services/*.py`
9. `catalog/onedrive.py`
10. `catalog/local_catalog.py`
11. `catalog/product_media.py`
12. `catalog/cadastro.py`
13. `catalog/product_catalog.py`
14. `catalog/stock_catalog.py`
15. `catalog/erp_catalog.py`
16. `catalog/exporter.py`
17. `frontend/src/main.tsx`
18. `frontend/src/lib/*.ts`
19. `frontend/src/App.tsx`
20. `frontend/src/components/*.tsx`
21. `tests/*`

Essa ordem acompanha o fluxo da aplicacao e reduz a sensacao de "codigo solto".

---

## Resumo final

O projeto nao e apenas um CRUD ou uma API simples.
Ele e um agregador de catalogo com forte tolerancia a dados inconsistentes.

O coracao da logica esta nesta cadeia:

1. descobrir produtos e fotos no disco;
2. limpar nomes e categorias;
3. enriquecer com cadastro;
4. enriquecer ou filtrar com ERP;
5. completar com estoque quando necessario;
6. servir isso por API;
7. consumir no frontend;
8. exportar em varios formatos.

Se voce entender profundamente estes arquivos, voce entende quase todo o sistema:

- `catalog/local_catalog.py`
- `catalog/product_media.py`
- `catalog/product_catalog.py`
- `catalog/stock_catalog.py`
- `catalog/erp_catalog.py`
- `frontend/src/App.tsx`
- `frontend/src/lib/catalog-products.ts`
- `tests/test_onedrive.py`

---

## Proximo passo sugerido

Se quiser continuar este material, o proximo documento ideal seria um destes:

- `EXPLICACAO_BACKEND_DETALHADA.md`
- `EXPLICACAO_FRONTEND_DETALHADA.md`
- `EXPLICACAO_ERP_E_ESTOQUE.md`

Nesses eu conseguiria ir ainda mais fundo, chegando muito perto de uma leitura linha por linha literal dos modulos grandes.
