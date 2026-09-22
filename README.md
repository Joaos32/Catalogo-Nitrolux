# Catálogo Nitrolux — Plataforma Full Stack de Produtos

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=111)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![AWS](https://img.shields.io/badge/Cloud-AWS-232F3E?logo=amazonwebservices&logoColor=white)](https://aws.amazon.com/)

Plataforma **full stack** desenvolvida para centralizar produtos, imagens e informações comerciais da Nitrolux e Pienza em um catálogo pesquisável, responsivo e preparado para operação com diferentes fontes de dados.

O projeto integra **Python/FastAPI, React/TypeScript, PostgreSQL e AWS**, além de serviços externos de armazenamento e identidade.

## Visão geral

O sistema resolve um problema real de consolidação de informações que podem estar distribuídas entre cadastro HTML, arquivos JSON de ERP, planilhas, banco PostgreSQL, pastas de imagens e serviços de armazenamento em nuvem.

O backend normaliza essas fontes e entrega um contrato único ao frontend. A aplicação permite que representantes naveguem pelo catálogo enquanto funcionalidades administrativas tratam cargas de ERP, produtos e acessos.

## Principais funcionalidades

### Catálogo

- catálogo separado por marcas Nitrolux e Pienza;
- busca por nome, código, descrição e categoria;
- filtros por categoria;
- página de detalhes do produto;
- galeria de imagens;
- destaque de produtos baseado em dados disponíveis;
- persistência de filtros no navegador;
- download de imagens;
- layout responsivo e lazy loading.

### Dados e integrações

- leitura e saneamento de cadastro HTML;
- importação e normalização de JSON do ERP;
- associação de imagens por código, nome e descrição;
- enriquecimento opcional de dados via PostgreSQL;
- integração com arquivos e serviços externos;
- resolução de mídia utilizando fontes locais e remotas.

### Mídia

A aplicação possui uma cadeia de resolução de imagens que pode utilizar:

```text
Arquivos locais → Amazon S3 → Google Drive → Microsoft Graph
```

Também há suporte à classificação de diferentes tipos de fotos de produto e conversão de formatos de imagem quando disponível.
- suporte a fotos gratuitas pelo Google Drive, além de pasta local, CDN, Vercel Blob opcional, Amazon S3 legado e Microsoft Graph;
- classificação de fotos em fundo branco, ambientada e medidas;
- galeria com todas as variações encontradas para um código;
- conversão de TIFF, PSD, HEIC e HEIF para JPEG quando suportada pelo Pillow;
- URLs públicas, CloudFront ou URLs pré-assinadas para objetos do S3.

### Exportações

- CSV;
- XLSX;
- JSON;
- PDF;
- ZIP com dados e imagens;
- ficha técnica individual.

### Administração

- painel administrativo;
- gerenciamento de cargas do ERP;
- prévia de alterações antes da implantação;
- identificação de produtos novos, atualizados, removidos e inalterados;
- gerenciamento de representantes;
- autenticação de representantes;
- recuperação de acesso.

## Stack técnica

### Backend

- Python 3.12;
- FastAPI;
- Uvicorn;
- Pydantic;
- SQL/PostgreSQL via Psycopg;
- Pandas;
- OpenPyXL;
- Pillow;
- Boto3;
- MSAL;
- Beautiful Soup;
- Mangum para execução ASGI em AWS Lambda.

### Frontend

- React 18;
- TypeScript 5;
- Vite;
- React Router;
- TanStack Query;
- CSS responsivo.

### Cloud e infraestrutura

- AWS Lambda;
- Amazon API Gateway;
- Amazon S3;
- AWS SAM / CloudFormation;
- AWS X-Ray;
- Microsoft Graph;
- Microsoft Entra ID;
- PostgreSQL opcional para dados de embalagem;
- arquivos JSON para o espelho ativo do ERP e os cadastros locais de acesso.

### Infraestrutura

- AWS SAM/CloudFormation;
- AWS Lambda;
- Amazon API Gateway HTTP API;
- Amazon S3 privado para frontend e mídia;
- Amazon CloudFront como origem HTTPS única;
- frontend legado sem build como fallback local.

### Cloud

- AWS;
- Google Drive API;
- Google Sheets.

### Qualidade

- Pytest;
- ESLint;
- Prettier;
- TypeScript Compiler;
- GitHub Actions.

## Arquitetura

O backend adota uma organização modular em camadas, separando interface HTTP, serviços, domínio e integrações externas.

```text
Cadastro HTML / ERP JSON / Planilhas / PostgreSQL
                       │
                       ▼
              Normalização e merge
                       │
                       ▼
                Serviços FastAPI
                       │
                       ▼
             API REST / AWS Lambda
                       │
                       ▼
          React + TypeScript + Query
                       │
                       ▼
        Catálogo / ERP / Exportações
```

Estrutura simplificada:

```text
.
├── app.py
├── template.yaml
├── requirements.txt
├── catalog/
│   ├── api/
│   ├── core/
│   ├── services/
│   ├── auth.py
│   ├── erp_catalog.py
│   ├── exporter.py
│   ├── local_catalog.py
│   ├── stock_catalog.py
│   ├── nitrolux_db.py
│   ├── s3_media.py
│   └── lambda_handler.py
As imagens seguem uma cadeia de fallback independente:

```text
arquivos locais → CDN → Vercel Blob → Amazon S3 legado → Google Drive → Microsoft Graph
```

O cache atual é um TTL cache em memória, aplicado às consultas remotas. No frontend, o TanStack Query controla cache, tentativas e revalidação das requisições.

---

## Estrutura do Projeto

```text
.
├── app.py                         # Entrada local ASGI
├── template.yaml                  # Stack AWS SAM
├── requirements.txt               # Dependências Python de produção
├── requirements-dev.txt           # Servidor local e ferramentas de teste
├── catalog/
│   ├── api/
│   │   ├── endpoints/             # Rotas de catálogo, mídia, ERP e acessos
│   │   ├── schemas/               # Contratos Pydantic
│   │   ├── security.py            # Dependências de autorização
│   │   └── router.py
│   ├── core/                      # Settings e logging
│   ├── services/                  # Casos de uso
│   ├── auth.py                    # Sessões, OAuth e JWT
│   ├── erp_catalog.py             # Importação e merge do ERP
│   ├── exporter.py                # CSV, XLSX, JSON, PDF e ZIP
│   ├── local_catalog.py           # Índice de fotos locais
│   ├── stock_catalog.py           # Estoque, vendas e fotos auxiliares
│   ├── nitrolux_db.py             # Integração PostgreSQL opcional
│   ├── vercel_blob_media.py       # Mídia privada no Vercel Blob
│   ├── s3_media.py                # Fallback legado de mídia no S3
│   └── lambda_handler.py          # Entrada AWS Lambda/Mangum
├── frontend/
│   ├── src/
│   └── vite.config.ts
├── tests/
├── scripts/
└── docs/
```

## Competências demonstradas

Este projeto demonstra experiência prática com:

- desenvolvimento full stack;
- APIs REST com FastAPI;
- React e TypeScript;
- arquitetura modular;
- integração entre múltiplas fontes de dados;
- PostgreSQL;
- autenticação e autorização;
- processamento e exportação de arquivos;
- integrações com APIs externas;
- AWS serverless;
- Infrastructure as Code com AWS SAM/CloudFormation;
- testes automatizados;
- CI/CD com GitHub Actions;
- tratamento de um problema de negócio real.

## Como executar

### Pré-requisitos

- Python 3.12;
- Node.js 20+;
- npm;
- Git.

AWS CLI e AWS SAM CLI são necessários apenas para fluxos relacionados a deploy na AWS.

### Clone

```bash
git clone https://github.com/Joaos32/Catalogo-Nitrolux.git
cd Catalogo-Nitrolux
```

### Backend

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
python -m pip install -r requirements-dev.txt
```

Linux/macOS:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
python -m pip install -r requirements-dev.txt
```

### Frontend

```bash
cd frontend
npm ci
npm run dev
```

### Build

```bash
cd frontend
npm run build
```

### Testes e verificações

Backend:

```bash
pytest -q
```

Frontend:

```bash
cd frontend
npm run lint
npm run build
```

## Variáveis de ambiente

O projeto possui exemplos de configuração para os ambientes utilizados. Credenciais e tokens reais não devem ser versionados.

Principais grupos de configuração incluem:

- aplicação e logging;
- CORS;
- PostgreSQL;
- Amazon S3;
- autenticação;
- Microsoft Graph / Entra ID;
- Google Drive;
- parâmetros do catálogo e ERP.

Consulte os arquivos `.env*.example` e a pasta `docs/` para configurações específicas.
Variáveis vazias são opcionais, salvo quando o recurso correspondente está habilitado ou quando a configuração é usada em produção.

### Aplicação, HTTP e logging

| Variável | Padrão | Finalidade |
|---|---:|---|
| `CATALOG_HOST` | `127.0.0.1` | Host do Uvicorn. |
| `CATALOG_PORT` | `8000` | Porta da API. |
| `CATALOG_ENABLE_API_DOCS` | `true` | Habilita Swagger, ReDoc e OpenAPI. |
| `CATALOG_CORS_ALLOW_ORIGINS` | origens locais | Lista CSV de origens permitidas. |
| `CATALOG_CORS_ALLOW_CREDENTIALS` | `true` | Permite credenciais no CORS. |
| `CATALOG_LOG_LEVEL` | `INFO` | Nível do logging Python. |
| `CATALOG_LOG_FORMAT` | formato com data, nível e logger | Formato das mensagens de log. |
| `CATALOG_SKIP_DOTENV` | `false` | Impede o carregamento automático do `.env`. |
| `CATALOG_EXPORT_MAX_REMOTE_IMAGE_BYTES` | `5242880` | Limite de bytes por imagem remota em exportações. |

### Autenticação e autorização

| Variável | Padrão | Finalidade |
|---|---:|---|
| `CATALOG_ALLOW_OPEN_ADMIN` | `false` | Libera rotas administrativas sem credencial; apenas desenvolvimento controlado. |
| `CATALOG_REQUIRE_REPRESENTATIVE_LOGIN` | `false` | Exige JWT/cookie de representante mesmo quando o cadastro ainda não foi carregado. Use `true` em produção. |
| `CATALOG_ERP_ADMIN_TOKEN` | vazio | Token técnico aceito em `X-Catalog-Admin-Token` ou Bearer. |
| `CATALOG_ADMIN_LOGIN_EMAIL` | `admin` quando há senha | Login administrativo local. |
| `CATALOG_ADMIN_LOGIN_PASSWORD` | vazio | Senha administrativa local. |
| `CATALOG_ADMIN_USERS_FILE` | `reports/admin_users.json` | JSON de administradores gerenciados. |
| `CATALOG_REPRESENTATIVE_LOGIN_EMAIL` | vazio | E-mail do representante único configurado por ambiente. |
| `CATALOG_REPRESENTATIVE_LOGIN_PASSWORD` | vazio | Senha do representante único. |
| `CATALOG_REPRESENTATIVE_LOGIN_NAME` | e-mail/`Representante` | Nome exibido para o representante único. |
| `CATALOG_REPRESENTATIVE_USERS_JSON` | vazio | Lista JSON de representantes configurados por ambiente. |
| `CATALOG_REPRESENTATIVE_USERS_FILE` | `reports/representative_users.json` | JSON de representantes gerenciados. |
| `CATALOG_REPRESENTATIVE_JWT_SECRET` | `CATALOG_SESSION_SECRET` | Segredo HMAC dedicado aos JWTs de representantes. |
| `CATALOG_REPRESENTATIVE_JWT_EXPIRES_MINUTES` | `720` | Validade do JWT em minutos. |
| `CATALOG_SESSION_SECRET` | aleatório por processo | Assina a sessão administrativa; obrigatório e estável em produção. |
| `CATALOG_SESSION_MAX_AGE_SECONDS` | `43200` | Duração máxima da sessão administrativa. |
| `CATALOG_SESSION_COOKIE_SECURE` | `false` | Marca o cookie de sessão como `Secure`. |
| `CATALOG_TOKEN_CACHE_FILE` | diretório de dados do usuário | Caminho do cache MSAL. |
| `AZURE_CLIENT_ID` | vazio | Client ID do aplicativo Microsoft. |
| `AZURE_CLIENT_SECRET` | vazio | Segredo do aplicativo Microsoft. |
| `AZURE_TENANT_ID` | vazio | Tenant do Microsoft Entra ID. |
| `AZURE_REDIRECT_URI` | vazio | Callback OAuth, normalmente `/auth/callback`. |

### Catálogo, ERP e arquivos locais

| Variável | Padrão | Finalidade |
|---|---:|---|
| `CATALOG_LOCAL_PRODUCTS_PATH` | autodetecção | Raiz explícita das fotos locais. |
| `CATALOG_LOCAL_PRODUCTS_HOME_FALLBACK` | `true` | Permite procurar pastas conhecidas dentro do diretório do usuário. |
| `CATALOG_CADASTRO_HTML` | autodetecção | Caminho do cadastro HTML. |
| `CATALOG_TECHNICAL_SPECS_PATH` | `reports/technical_specs.txt` | Arquivo de especificações técnicas por código. |
| `CATALOG_ERP_JSON_PATH` | autodetecção | Caminho do espelho JSON ativo do ERP. |
| `CATALOG_ERP_INBOX_DIR` | `reports/erp_inbox` | Diretório de arquivos enviados para revisão/importação. |
| `CATALOG_ERP_SOURCE_DIRS` | diretórios internos conhecidos | Pastas CSV adicionais para descoberta de JSON ERP. |
| `CATALOG_ERP_AUTO_DISCOVERY` | `true` | Habilita descoberta automática de arquivos ERP. |
| `CATALOG_ERP_STRICT_MODE` | `true` | Exibe somente códigos presentes no ERP ativo, além dos itens criados por ele. |
| `CATALOG_ERP_MAX_UPLOAD_BYTES` | `10485760` | Limite do upload de JSON ERP. |
| `CATALOG_STOCK_REPORT_PATH` | autodetecção | Caminho da planilha de posição de estoque. |
| `CATALOG_STOCK_REPORT_AUTO_DISCOVERY` | `true` | Procura automaticamente relatórios de estoque. |
| `CATALOG_STOCK_PHOTOS_ROOT` | autodetecção | Raiz alternativa das fotos do estoque. |
| `CATALOG_STOCK_PHOTOS_HOME_FALLBACK` | `true` | Permite procurar a raiz de fotos dentro do diretório do usuário. |

### Mídia remota

| Variável | Padrão | Finalidade |
|---|---:|---|
| `CATALOG_S3_MEDIA_BUCKET` | vazio | Bucket das imagens de produto. |
| `CATALOG_S3_MEDIA_PREFIX` | vazio local / `produtos/` no SAM | Prefixo dos objetos no bucket. |
| `CATALOG_S3_MEDIA_PUBLIC_BASE_URL` | URL regional do S3 | Base pública ou distribuição CloudFront. |
| `CATALOG_S3_MEDIA_PRESIGNED_URLS` | `false` | Gera URLs pré-assinadas. |
| `CATALOG_S3_MEDIA_PRESIGNED_EXPIRES_SECONDS` | `3600` | Validade das URLs pré-assinadas. |
| `CATALOG_GOOGLE_DRIVE_FOLDER_ID` | vazio | ID ou URL da pasta compartilhada. |
| `CATALOG_GOOGLE_DRIVE_API_KEY` | vazio | Chave da Google Drive API. |
| `CATALOG_GOOGLE_DRIVE_RECURSIVE` | `true` | Percorre subpastas. |
| `CATALOG_GOOGLE_DRIVE_MAX_DEPTH` | `4` | Profundidade máxima da busca. |

### PostgreSQL Nitrolux

| Variável | Padrão | Finalidade |
|---|---:|---|
| `CATALOG_NITROLUX_DB_ENABLED` | `false` | Habilita o enriquecimento via PostgreSQL. |
| `CATALOG_NITROLUX_DB_URL` | vazio | String de conexão completa. |
| `CATALOG_NITROLUX_DB_HOST` | `127.0.0.1` | Host quando não há URL completa. |
| `CATALOG_NITROLUX_DB_PORT` | `5432` | Porta do PostgreSQL. |
| `CATALOG_NITROLUX_DB_NAME` | `nitrolux` | Banco de dados. |
| `CATALOG_NITROLUX_DB_USER` | vazio | Usuário do banco. |
| `CATALOG_NITROLUX_DB_PASSWORD` | vazio | Senha do banco. |
| `CATALOG_NITROLUX_DB_SSLMODE` | `prefer` | Modo SSL do Psycopg. |
| `CATALOG_NITROLUX_DB_SCHEMA` | `public` | Schema consultado. |
| `CATALOG_NITROLUX_DB_TABLE` | `pcprodut` | Tabela consultada. |
| `CATALOG_NITROLUX_DB_CODE_COLUMN` | `codprod` | Coluna do código do produto. |
| `CATALOG_NITROLUX_DB_PACKAGE_COLUMN` | `embalagem` | Coluna de embalagem. |
| `CATALOG_NITROLUX_DB_MASTER_BOX_COLUMN` | `caixa_master` | Coluna de caixa master. |

### Frontend e AWS

| Variável | Padrão | Finalidade |
|---|---:|---|
| `VITE_API_BASES` | mesma origem e APIs locais | Lista CSV de bases que o cliente tenta em sequência. |
| `VITE_REQUEST_TIMEOUT_MS` | `12000` | Timeout das requisições do frontend. |
| `VITE_DEV_PROXY_TARGET` | `http://127.0.0.1:8000` | Destino do proxy Vite para `/catalog` e `/auth`. |
| `AWS_REGION` | definido pelo runtime AWS | Região usada pelo cliente S3. |
| `AWS_DEFAULT_REGION` | definido pelo ambiente AWS | Fallback de região para o cliente S3. |
| `CATALOG_DATA_TABLE_NAME` | definido pelo SAM | Nome da tabela DynamoDB provisionada; ainda não é lida pelo código da aplicação. |

---

## API

As rotas marcadas como **Representante** exigem JWT/cookie quando há representantes configurados ou quando `CATALOG_REQUIRE_REPRESENTATIVE_LOGIN=true`. As rotas **Admin** exigem sessão administrativa, token válido ou a abertura explícita de desenvolvimento.

### Autenticação

| Método | Rota | Acesso | Descrição |
|---|---|---|---|
| `GET` | `/auth/session` | Público | Estado e métodos disponíveis da sessão administrativa. |
| `POST` | `/auth/admin/login` | Público | Login administrativo por senha. |
| `GET` | `/auth/login` | Público | Inicia OAuth com a Microsoft. |
| `GET` | `/auth/callback` | Público | Callback OAuth com validação de `state`. |
| `POST` | `/auth/logout` | Público | Encerra sessões administrativa e de representante. |
| `GET` | `/auth/representative/session` | Público | Estado da sessão do representante. |
| `POST` | `/auth/representative/login` | Público | Autentica e emite o JWT. |
| `POST` | `/auth/representative/reset-password` | Público | Redefine senha com código temporário. |
| `POST` | `/auth/representative/logout` | Público | Remove o cookie do representante. |

### Catálogo e mídia

| Método | Rota | Acesso | Descrição |
|---|---|---|---|
| `GET` | `/catalog/sheet?url=...` | Representante | Lê uma Google Sheet pública ou aplica fallback local. |
| `GET` | `/catalog/local/produtos` | Representante | Retorna o catálogo consolidado. |
| `GET` | `/catalog/local/asset?path=...` | Representante | Entrega uma imagem dentro das raízes locais permitidas. |
| `GET` | `/catalog/photos?code=...&shareUrl=...` | Representante | Retorna as três fotos principais usando a cadeia de fallback. |
| `GET` | `/catalog/produtos/{codigo}/imagens` | Representante | Retorna a galeria completa do produto. |
| `GET` | `/catalog/google-drive/photos?code=...` | Representante | Fotos categorizadas diretamente do Google Drive. |
| `GET` | `/catalog/google-drive/produtos/{codigo}/imagens` | Representante | Galeria diretamente do Google Drive. |
| `GET` | `/catalog/s3/photos?code=...` | Representante | Fotos categorizadas diretamente do S3. |
| `GET` | `/catalog/s3/produtos/{codigo}/imagens` | Representante | Galeria diretamente do S3. |
| `GET` | `/catalog/export?format=...` | Representante | Exporta `csv`, `xlsx`, `json`, `pdf`, `ficha` ou `zip`. |

Parâmetros opcionais de exportação: `query`, `category`, `code` e `brand`. O formato `ficha` exige `code`.

### ERP e representantes

| Método | Rota | Acesso | Descrição |
|---|---|---|---|
| `POST` | `/catalog/erp/import` | Admin | Importa um objeto ou lista JSON. |
| `POST` | `/catalog/erp/upload?filename=...` | Admin | Armazena e importa um arquivo JSON bruto. |
| `POST` | `/catalog/erp/stage-file?filename=...` | Admin | Armazena, valida e gera a prévia sem ativar. |
| `POST` | `/catalog/erp/import-file` | Admin | Ativa um arquivo permitido já presente no backend. |
| `GET` | `/catalog/erp/files` | Admin | Lista arquivos ERP descobertos. |
| `GET` | `/catalog/erp/files/preview?file_path=...` | Admin | Compara um arquivo com a carga ativa. |
| `GET` | `/catalog/erp/products` | Admin | Lista os produtos do JSON ativo. |
| `PUT` | `/catalog/erp/products/{codigo}` | Admin | Inclui ou atualiza um produto. |
| `GET` | `/catalog/erp/status` | Admin | Retorna status, origem e último resumo de alterações. |
| `GET` | `/catalog/representatives` | Admin | Lista representantes e totais. |
| `PUT` | `/catalog/representatives/{email}` | Admin | Cria ou atualiza um representante. |
| `POST` | `/catalog/representatives/{email}/password-reset` | Admin | Gera um código temporário de redefinição. |
| `DELETE` | `/catalog/representatives/{email}` | Admin | Exclui um representante gerenciado. |

Com a documentação habilitada, o contrato OpenAPI completo fica disponível em `/docs`, `/redoc` e `/openapi.json`.

---

## Banco de Dados

O projeto não usa um banco transacional como fonte principal do catálogo nesta versão.

- **ERP:** persistido em arquivo JSON normalizado, com metadados da importação e resumo de alterações;
- **acessos locais:** persistidos em `reports/admin_users.json` e `reports/representative_users.json`, ambos ignorados pelo Git;
- **PostgreSQL:** integração opcional e somente leitura para enriquecer embalagem e caixa master por código.

Não existem ORM nem migrations. A consulta PostgreSQL usa Psycopg e identificadores configuráveis validados antes da montagem do SQL. Na Lambda, arquivos mutáveis não são persistência durável; use variáveis para os usuários iniciais e migre as gravações administrativas antes de tratar o painel como sistema transacional.

---

## Segurança

O projeto possui funcionalidades que trabalham com autenticação, arquivos e serviços externos. Entre os pontos considerados na arquitetura estão:

- variáveis de ambiente para credenciais;
- autenticação administrativa;
- autenticação de representantes;
- cookies e tokens conforme o fluxo configurado;
- separação entre configuração frontend e segredos server-side;
- controle de origem via CORS;
- possibilidade de URLs controladas para objetos armazenados em S3.

Antes de qualquer implantação pública, as configurações de autenticação, CORS, armazenamento e secrets devem ser revisadas para o ambiente de produção.

## Deploy

O projeto possui infraestrutura serverless baseada em **AWS SAM / CloudFormation**, utilizando serviços como Lambda, API Gateway e S3.

O arquivo `template.yaml` concentra a definição principal da infraestrutura versionada.

## Roadmap

- ampliar testes de integração e ponta a ponta;
- evoluir persistência de dados operacionais;
- reforçar observabilidade e métricas;
- melhorar automação de deploy;
- ampliar documentação de decisões arquiteturais;
- evoluir o catálogo e o painel administrativo conforme necessidades comerciais.
Há duas opções documentadas de deploy:

- AWS SAM com Lambda, API Gateway, S3 privado e CloudFront;
- Vercel com frontend Vite e FastAPI em Python Function.

### AWS

```powershell
$env:CATALOG_SESSION_SECRET = "segredo-unico-com-pelo-menos-32-caracteres"
$env:CATALOG_REPRESENTATIVE_JWT_SECRET = "outro-segredo-com-pelo-menos-32-caracteres"
.\scripts\deploy_aws.ps1 -StackName catalogo-prod -Region sa-east-1 -AwsProfile catalogo-prod -UseContainer -PreflightOnly
.\scripts\deploy_aws.ps1 -StackName catalogo-prod -Region sa-east-1 -AwsProfile catalogo-prod -UseContainer
```

O script testa, compila, publica e invalida o cache. O frontend usa a mesma origem do CloudFront para `/catalog/*` e `/auth/*`, preservando os cookies de sessão. Consulte [docs/aws-serverless.md](docs/aws-serverless.md) para parâmetros, mídia e limitações de persistência.

### Vercel

```powershell
npx vercel login
npx vercel
npx vercel --prod
```

As rotas e o build já estão definidos em `vercel.json`. Consulte [docs/vercel.md](docs/vercel.md) para variáveis obrigatórias e limitações de persistência.

Não há manifesto Kubernetes nem pipeline automatizado de publicação no repositório.

---

## Roadmap

- migrar usuários, ERP e acessos mutáveis para um armazenamento durável;
- configurar domínio próprio e certificado ACM no CloudFront;
- adicionar paginação e busca no backend para catálogos maiores;
- extrair processamento pesado de PDF/ZIP para tarefas assíncronas;
- consolidar as cópias do frontend legado;
- evoluir a inferência de categorias e especificações com regras versionadas e auditáveis.

---

## Contribuição

1. Faça um fork do repositório.
2. Crie uma branch a partir da branch principal: `git checkout -b feat/minha-melhoria`.
3. Implemente a alteração sem incluir `.env`, credenciais ou relatórios sensíveis.
4. Execute `pytest -q`, `npm run lint` e `npm run build`.
5. Abra um pull request descrevendo motivação, comportamento alterado e evidências de teste.

Ao alterar contratos HTTP, atualize os schemas, testes e a seção de API. Ao adicionar uma fonte de dados, preserve a degradação graciosa e documente sua posição na cadeia de fallback.

---

## Licença

O repositório não contém um arquivo de licença. Portanto, o código permanece sob os direitos autorais do autor e não deve ser considerado software open source até que uma licença seja adicionada.

---

## Autor

**João Vitor Silva Santos**

- GitHub: [@Joaos32](https://github.com/Joaos32)
- LinkedIn: [João Vitor Silva Santos](https://www.linkedin.com/in/joao-vitor-silva-santos/)
- E-mail: joaovitorsilvasantos3255@gmail.com

---

Este é um dos projetos principais do meu portfólio e representa uma aplicação full stack construída para resolver um cenário real de organização, integração e distribuição de informações de produtos.
---
