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

O cadastro de representantes usa um Vercel Blob privado quando `BLOB_READ_WRITE_TOKEN` está configurado. Sem essa variável, o projeto mantém o arquivo JSON local para desenvolvimento.

Crie e conecte um Blob privado ao projeto. A Vercel injeta `BLOB_READ_WRITE_TOKEN` automaticamente nos ambientes selecionados. O objeto é salvo como `catalogo/representative_users.json`; o caminho pode ser alterado por `CATALOG_REPRESENTATIVE_BLOB_PATH`.

As importações ERP ainda usam JSON local e não devem ser tratadas como persistência durável na Vercel.

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
```

Nunca grave segredos no `vercel.json` ou no Git.

## Fotos gratuitas no Google Drive

O Google Drive é a fonte recomendada enquanto o catálogo precisar operar sem custo de armazenamento. Uma conta pessoal oferece até 15 GB compartilhados entre Drive, Gmail e Google Fotos; o acervo atual de aproximadamente 1,36 GB cabe nesse limite.

1. Crie uma pasta exclusiva para o catálogo no Google Drive e envie as fotos.
2. Compartilhe a pasta como **Qualquer pessoa com o link → Leitor**.
3. Em um projeto do Google Cloud, habilite a **Google Drive API** e crie uma chave de API restrita a essa API.
4. Na Vercel, configure `CATALOG_GOOGLE_DRIVE_FOLDER_ID` e `CATALOG_GOOGLE_DRIVE_API_KEY` para Production e Preview.
5. Mantenha `CATALOG_MEDIA_BLOB_ENABLED=false` e remova as variáveis/credenciais S3 do projeto.

Os nomes dos arquivos devem começar com o código do produto, por exemplo `1234 (1).jpg`, `1234 (2).jpg` e `1234 (3).jpg`. A busca é recursiva por padrão e o resultado da listagem remota usa cache no backend.

O uso padrão da Drive API não tem custo adicional dentro das cotas publicadas pelo Google. Monitore o consumo caso o catálogo passe a gerar tráfego muito alto.

## Vercel Blob opcional

A integração com Vercel Blob permanece disponível, mas desativada. O utilitário `scripts/upload_vercel_media.py` apenas simula a sincronização sem `--apply`; não execute a carga enquanto a opção gratuita estiver em uso.

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
