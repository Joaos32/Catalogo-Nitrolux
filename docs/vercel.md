# Deploy na Vercel

O projeto pode ser publicado na Vercel como uma aplicação única:

- o Vite gera o frontend estático em `frontend/dist`;
- `api/index.py` expõe a aplicação FastAPI como uma Python Function;
- `/catalog/*` e `/auth/*` são reescritos para a função sem mudar a URL pública;
- frontend, API e cookies permanecem na mesma origem HTTPS.

## Domínios do catálogo e do painel

Associe dois domínios ao mesmo projeto Vercel. O domínio principal entrega
somente o catálogo público; o subdomínio administrativo entrega somente o
painel interno. Exemplo:

```text
catalogo.example.com
painel.example.com
```

Configure os dois valores abaixo em Production antes de gerar o frontend:

```text
VITE_ADMIN_HOSTS=painel.example.com
CATALOG_ADMIN_HOSTS=painel.example.com
```

`VITE_ADMIN_HOSTS` seleciona a interface pelo hostname no navegador.
`CATALOG_ADMIN_HOSTS` faz a proteção no servidor: fora do subdomínio, as rotas
`/auth/*` e `/catalog/erp/*` respondem com 404. Se houver mais de um subdomínio
administrativo, separe-os por vírgulas nas duas variáveis.

O catálogo exige autenticação de representante por JWT quando há usuários
cadastrados. Mantenha `CATALOG_REQUIRE_REPRESENTATIVE_LOGIN=true` para deixar
explícito esse fluxo.

## Persistência de representantes

O projeto usa `CATALOG_STATE_BACKEND=blob` para manter usuarios e ERP em um
Vercel Blob privado, mesmo que ainda existam variaveis de PostgreSQL ou S3.
Consulte [a configuracao e transferencia entre Blobs](vercel-blob.md) antes de
publicar o novo projeto da empresa.

Conecte o Blob privado ao projeto e ao ambiente Production. A Vercel fornece
`BLOB_READ_WRITE_TOKEN`; os objetos sao `catalogo/representative_users.json` e
`catalogo/erp_products.json`. `CATALOG_ERP_BLOB_ENABLED=true` habilita o ERP.
Sem token ou objetos atuais, a configuracao sozinha nao recupera os dados.

A atividade online nao grava no Blob. As fotos permanecem na fonte atual,
com `CATALOG_MEDIA_BLOB_ENABLED=false`.

Arquivos temporários enviados para prévia continuam no diretório da função e não são persistentes. O catálogo ERP ativado é armazenado no Blob.

## Variáveis obrigatórias

Configure em **Project Settings > Environment Variables** para Production e Preview:

```text
CATALOG_SKIP_DOTENV=true
CATALOG_ENABLE_API_DOCS=false
CATALOG_ALLOW_OPEN_ADMIN=false
CATALOG_ADMIN_HOSTS=<subdomínio administrativo sem https://>
CATALOG_REQUIRE_REPRESENTATIVE_LOGIN=true
CATALOG_SESSION_COOKIE_SECURE=true
CATALOG_SESSION_SECRET=<segredo aleatorio com 32 ou mais caracteres>
CATALOG_REPRESENTATIVE_JWT_SECRET=<outro segredo aleatorio>
CATALOG_ADMIN_LOGIN_EMAIL=<email administrativo>
CATALOG_ADMIN_LOGIN_PASSWORD=<senha forte>
CATALOG_INTEGRATION_API_KEY=<chave aleatoria exclusiva para integracoes>
```

Nunca grave segredos no `vercel.json` ou no Git.

As tentativas de login têm limite em memória por instância no Vercel. Para
compartilhar esse limite entre instâncias, configure no WAF da plataforma uma
regra de taxa para `/auth/representative/login`,
`/auth/representative/reset-password` e `/auth/admin/login`.

## API de integracao de produtos

Configure `CATALOG_INTEGRATION_API_KEY` como segredo no ambiente da aplicacao.
Consumidores servidor a servidor enviam a chave no cabecalho
`X-Catalog-Api-Key`:

- `GET /catalog/integration/products` exporta o cadastro consolidado, incluindo
  os campos `URLFoto`, `FotoBranco`, `FotoAmbient` e `FotoMedidas`;
- `GET /catalog/integration/pienza/products` entrega somente os produtos Pienza,
  com os campos `codigo` e `descricao`;
- `GET /catalog/integration/categories` lista as categorias e quantidades.

As rotas sao somente de leitura. O endpoint Pienza filtra pelo codigo de marca
`CODMARCA=2` e nao inclui fotos nem outros campos. O endpoint geral continua
disponivel para consumidores que precisem do cadastro completo.

## Fotos gratuitas no Google Drive

O Google Drive é a fonte recomendada enquanto o catálogo precisar operar sem custo de armazenamento. Uma conta pessoal oferece até 15 GB compartilhados entre Drive, Gmail e Google Fotos; o acervo atual de aproximadamente 1,36 GB cabe nesse limite.

1. Crie uma pasta exclusiva para o catálogo no Google Drive e envie as fotos.
2. Compartilhe a pasta como **Qualquer pessoa com o link → Leitor**.
3. Em um projeto do Google Cloud, habilite a **Google Drive API** e crie uma chave de API restrita a essa API.
4. Na Vercel, configure `CATALOG_GOOGLE_DRIVE_FOLDER_ID` e `CATALOG_GOOGLE_DRIVE_API_KEY` para Production e Preview.
5. Mantenha `CATALOG_MEDIA_BLOB_ENABLED=false` e remova as variáveis/credenciais S3 do projeto.

Os nomes dos arquivos devem começar com o código do produto, por exemplo `1234 (1).jpg`, `1234 (2).jpg` e `1234 (3).jpg`. A busca é recursiva por padrão e o resultado da listagem remota usa cache no backend.

O uso padrão da Drive API não tem custo adicional dentro das cotas publicadas pelo Google. Monitore o consumo caso o catálogo passe a gerar tráfego muito alto.

## Fotos no Vercel Blob (opcional)

O armazenamento de fotos no Vercel Blob permanece desativado; usuarios e ERP usam o Blob privado. O utilitário `scripts/upload_vercel_media.py` apenas simula a sincronização sem `--apply`; não execute a carga enquanto a opção gratuita estiver em uso.

## Validação local

```powershell
python -m pytest
$env:VITE_API_BASES = "/"
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run build
```

Antes de cada deploy, gere o catálogo pré-processado. O arquivo inclui hashes
dos JSONs de origem; se estiver desatualizado, a API ignora o snapshot e usa o
processamento completo para preservar a correção dos dados.

```powershell
python scripts/build_runtime_catalog.py
npx.cmd vercel --prod --yes
```

## Publicação

Com Node.js instalado:

```powershell
npx vercel login
npx vercel
npx vercel --prod
```

Na primeira execução, selecione a raiz atual do repositório. Não altere manualmente o Build Command nem o Output Directory: ambos já estão definidos em `vercel.json`.
