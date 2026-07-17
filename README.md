# Catálogo de Produtos

[![CI](https://github.com/devjoao32/catalogo/actions/workflows/ci.yml/badge.svg)](https://github.com/devjoao32/catalogo/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=111)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)

Plataforma full stack para consolidar produtos e imagens de fontes heterogêneas em um catálogo comercial pesquisável, responsivo e exportável. Inclui acesso de representantes, painel administrativo de ERP e implantação serverless na AWS.

---

## Demonstração

O repositório não informa uma URL pública nem contém capturas de tela da aplicação. A interface pode ser executada localmente em `http://localhost:5173` seguindo a seção [Como executar](#como-executar).

Principais telas disponíveis:

- `/`: catálogo das marcas Nitrolux e Pienza, com busca, categorias, destaques mensais e exportações;
- `/produto/:productId`: detalhes, ficha técnica, galeria e download de imagens;
- `/login`: autenticação e recuperação de senha de representantes;
- `/erp`: painel administrativo para representantes, arquivos ERP e produtos.

---

## Índice

- [Sobre o Projeto](#sobre-o-projeto)
- [Funcionalidades](#funcionalidades)
- [Tecnologias Utilizadas](#tecnologias-utilizadas)
- [Arquitetura](#arquitetura)
- [Estrutura do Projeto](#estrutura-do-projeto)
- [Como executar](#como-executar)
- [Variáveis de Ambiente](#variáveis-de-ambiente)
- [API](#api)
- [Banco de Dados](#banco-de-dados)
- [Segurança](#segurança)
- [Testes](#testes)
- [Deploy](#deploy)
- [Roadmap](#roadmap)
- [Contribuição](#contribuição)
- [Licença](#licença)
- [Autor](#autor)
- [Sugestões para melhorar este projeto](#sugestões-para-melhorar-este-projeto)

---

## Sobre o Projeto

O Catálogo de Produtos centraliza informações comerciais que hoje podem estar distribuídas entre pastas de imagens, cadastro HTML, JSON do ERP, planilha de estoque, PostgreSQL e serviços de armazenamento. O backend normaliza essas fontes, associa fotos aos códigos dos produtos e entrega um contrato único ao frontend.

O projeto resolve especialmente três problemas:

- inconsistência de nomes, categorias, códigos e formatos entre diferentes origens;
- dificuldade para localizar e classificar fotos de produto em grande volume;
- necessidade de entregar a representantes um catálogo navegável e materiais exportáveis sem expor as rotinas administrativas.

Como resultado, representantes comerciais acessam dados e imagens em uma experiência responsiva, enquanto administradores podem revisar cargas do ERP, comparar alterações e gerenciar acessos pela mesma aplicação.

---

## Funcionalidades

### Catálogo comercial

- catálogo separado por marcas Nitrolux e Pienza;
- busca por nome, código, descrição e categoria;
- filtro por categoria e agrupamento dos resultados;
- destaque dos produtos mais vendidos no mês quando há dados de vendas;
- carregamento progressivo, adaptado à largura da tela;
- persistência dos filtros no `localStorage`;
- página de detalhes com atributos técnicos e galeria completa;
- download da imagem selecionada ou de todas as imagens em ZIP;
- layout responsivo, imagens com lazy loading e suporte a `prefers-reduced-motion`.

### Agregação e enriquecimento de dados

- descoberta de produtos e imagens em pastas locais, inclusive atalhos `.lnk`;
- leitura e saneamento de um cadastro HTML;
- importação, normalização e espelhamento de JSON do ERP;
- modo ERP estrito, que restringe o catálogo aos códigos da carga ativa;
- inclusão de produtos presentes apenas no ERP, com placeholder quando não há foto;
- fallback por planilha de posição de estoque;
- associação de imagens por código, nome e descrição;
- enriquecimento opcional de embalagem e caixa master via PostgreSQL;
- resolução e inferência de especificações técnicas a partir dos dados disponíveis;
- categorização comercial de produtos e variantes de foto.

### Mídia

- resolução de mídia na ordem: pasta local, Amazon S3, Google Drive e Microsoft Graph;
- classificação de fotos em fundo branco, ambientada e medidas;
- galeria com todas as variações encontradas para um código;
- conversão de TIFF, PSD, HEIC e HEIF para JPEG quando suportada pelo Pillow;
- URLs públicas, CloudFront ou URLs pré-assinadas para objetos do S3.

### Exportações

- catálogo ou recorte filtrado em CSV, XLSX, JSON, PDF e ZIP;
- ficha técnica individual em PDF;
- ZIP com dados, imagens disponíveis e manifesto de fotos;
- filtros de exportação por texto, categoria, código e marca.

### Administração e acesso

- painel administrativo protegido por sessão, token ou Microsoft OAuth;
- fila de arquivos ERP, prévia e comparação antes da implantação;
- resumo de produtos novos, atualizados, removidos e inalterados;
- edição e inclusão de produtos no JSON ERP ativo;
- cadastro, atualização e exclusão de representantes gerenciados;
- emissão de código temporário para redefinição de senha;
- login de representantes com JWT e cookie HTTP-only;
- execução aberta do catálogo quando nenhuma fonte de representantes está configurada.

---

## Tecnologias Utilizadas

### Backend

- Python 3.12;
- FastAPI e Uvicorn;
- Pydantic;
- Mangum para adaptação ASGI ao AWS Lambda;
- Requests e Boto3;
- Pandas, OpenPyXL e Pillow;
- MSAL para Microsoft OAuth e Graph;
- Beautiful Soup para leitura do cadastro HTML;
- Psycopg 3 para PostgreSQL.

### Frontend

- React 18;
- TypeScript 5;
- Vite 5;
- React Router 6;
- TanStack Query 5;
- CSS responsivo sem framework visual.

### Banco de Dados

- PostgreSQL opcional para dados de embalagem;
- arquivos JSON para o espelho ativo do ERP e os cadastros locais de acesso;
- DynamoDB provisionado no stack AWS, mas ainda não consumido pela aplicação.

### Infraestrutura

- AWS SAM/CloudFormation;
- AWS Lambda;
- Amazon API Gateway HTTP API;
- Amazon S3 para frontend e mídia;
- frontend legado sem build como fallback local.

### Cloud

- AWS;
- Google Drive API;
- Microsoft Graph e Microsoft Entra ID (Azure AD);
- Google Sheets público.

### DevOps

- GitHub Actions;
- build serverless com AWS SAM;
- validação de prontidão para produção;
- AWS X-Ray habilitado para a função Lambda.

### Ferramentas

- Pytest;
- ESLint;
- Prettier;
- TypeScript Compiler;
- npm.

---

## Arquitetura

O projeto adota uma arquitetura modular em camadas, com separação entre composição da aplicação, interface HTTP, serviços e módulos de domínio/infraestrutura. Não é uma implementação formal de Clean Architecture, mas aplica princípios semelhantes de divisão de responsabilidades e dependências direcionadas.

### Organização e responsabilidades

- `app.py` e `catalog/bootstrap.py`: criam a aplicação, carregam configurações e registram middlewares e rotas;
- `catalog/api/`: define endpoints, dependências de segurança, schemas e tratamento de erros;
- `catalog/services/`: coordena casos de uso de catálogo e mídia sem expor detalhes aos endpoints;
- `catalog/*_catalog.py`: contém normalização, enriquecimento e regras de composição dos produtos;
- `catalog/local_catalog.py`, `s3_media.py`, `google_drive.py`, `graph_client.py` e `nitrolux_db.py`: integram arquivos locais e serviços externos;
- `frontend/src/lib/`: concentra cliente HTTP, normalização dos produtos e persistência de estado;
- `frontend/src/components/`: implementa catálogo, detalhes, autenticação e painel administrativo.

### Fluxo principal

```text
Pasta local / Cadastro HTML / ERP JSON / Estoque / PostgreSQL
                              │
                              ▼
            normalização, merge e especificações técnicas
                              │
                              ▼
                 serviços → endpoints FastAPI
                              │
                              ▼
                React + TanStack Query + Router
                              │
                              ▼
            catálogo, painel ERP e exportações
```

As imagens seguem uma cadeia de fallback independente:

```text
arquivos locais → Amazon S3 → Google Drive → Microsoft Graph
```

O cache atual é um TTL cache em memória, aplicado às consultas remotas. No frontend, o TanStack Query controla cache, tentativas e revalidação das requisições.

---

## Estrutura do Projeto

```text
.
├── app.py                         # Entrada local ASGI
├── template.yaml                  # Stack AWS SAM
├── requirements.txt               # Dependências Python
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
│   ├── s3_media.py                # Mídia no S3
│   └── lambda_handler.py          # Entrada AWS Lambda/Mangum
├── frontend/
│   ├── src/                       # Aplicação React/TypeScript
│   ├── legacy/                    # Fallback sem build
│   └── vite.config.ts
├── tests/                         # Testes backend e de integração HTTP
├── scripts/                       # Readiness, CORS e redefinição de acesso
├── docs/                          # Deploy e ficha técnica
└── reports/                       # Dados ERP e relatórios locais
```

---

## Como executar

### Pré-requisitos

- Python 3.12;
- Node.js 20 e npm;
- Git;
- opcionalmente, AWS CLI e AWS SAM CLI para deploy.

### Instalação

Clone o repositório e entre no diretório:

```bash
git clone https://github.com/devjoao32/catalogo.git
cd catalogo
```

Crie um ambiente virtual e instale o backend:

```bash
python -m venv .venv
```

No Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

No Linux ou macOS:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Instale o frontend:

```bash
cd frontend
npm ci
cd ..
```

No PowerShell com política de execução restrita, use `npm.cmd ci` e `npm.cmd run <script>`.

### Variáveis de ambiente

O backend carrega automaticamente um arquivo `.env` na raiz. Configure somente as integrações necessárias para o seu ambiente; a referência de produção está em [.env.production.example](.env.production.example). Para o frontend de produção, use [frontend/.env.production.example](frontend/.env.production.example).

Um ambiente local mínimo pode usar os padrões internos, sem arquivo `.env`. Nesse modo:

- o catálogo usa os dados locais disponíveis no repositório e as fontes detectáveis;
- as rotas do catálogo ficam abertas enquanto nenhum representante estiver configurado;
- as rotas administrativas permanecem fechadas até que um login, token ou `CATALOG_ALLOW_OPEN_ADMIN=true` seja configurado.

### Banco e dados

Não há migration obrigatória para desenvolvimento. O ERP é persistido em JSON e o PostgreSQL é uma integração opcional, somente para enriquecer `Embalagem` e `CaixaMaster`.

Para usar o banco, habilite `CATALOG_NITROLUX_DB_ENABLED=true` e configure a URL ou os campos de conexão. A tabela deve expor as colunas configuradas de código, embalagem e caixa master.

### Execução

Terminal 1 — API:

```bash
python app.py
```

Terminal 2 — frontend moderno:

```bash
cd frontend
npm run dev
```

Acesse:

- frontend: `http://localhost:5173`;
- API: `http://127.0.0.1:8000`;
- Swagger: `http://127.0.0.1:8000/docs`, quando habilitado.

O Vite encaminha `/catalog` e `/auth` para `http://127.0.0.1:8000` por padrão.

### Build

```bash
cd frontend
npm run build
```

Quando `frontend/dist/index.html` existe, o FastAPI serve esse build automaticamente. Sem o build, usa `frontend/legacy/index.html` como fallback.

### Testes e verificações

```bash
pytest -q
cd frontend
npm run lint
npm run build
```

### Docker

O repositório não possui `Dockerfile` nem `docker-compose.yml`. A execução suportada atualmente é local via Python/Vite ou serverless via AWS SAM.

---

## Variáveis de Ambiente

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

As rotas marcadas como **Representante** exigem JWT/cookie somente quando há representantes configurados. As rotas **Admin** exigem sessão administrativa, token válido ou a abertura explícita de desenvolvimento.

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
- **PostgreSQL:** integração opcional e somente leitura para enriquecer embalagem e caixa master por código;
- **DynamoDB:** tabela com chave composta `pk`/`sk`, criptografia habilitada e cobrança sob demanda, provisionada pelo SAM para uma migração futura.

Não existem ORM nem migrations. A consulta PostgreSQL usa Psycopg e identificadores configuráveis validados antes da montagem do SQL.

---

## Segurança

- sessão administrativa assinada pelo `SessionMiddleware`, com cookie HTTP-only, `SameSite=Lax`, validade configurável e opção `Secure`;
- autenticação administrativa por senha, token técnico ou Microsoft OAuth 2.0;
- autenticação de representantes com token JWT-like HMAC-SHA256 e expiração;
- senhas gerenciadas com PBKDF2-HMAC-SHA256, salt aleatório e comparação em tempo constante;
- rate limiting em memória para tentativas de login e redefinição de senha;
- códigos de recuperação temporários armazenados como hash SHA-256;
- validação de `state` no fluxo OAuth;
- proteção contra path traversal em arquivos locais e importações ERP;
- bloqueio de URLs privadas/locais no download remoto das exportações para reduzir SSRF;
- limites de tamanho para upload ERP e imagens remotas;
- CORS com origens configuráveis e proteção contra credenciais com origem curinga;
- GZip e cabeçalhos CSP, HSTS em HTTPS, `X-Frame-Options`, `nosniff`, Referrer Policy e Permissions Policy;
- respostas de erro interno sanitizadas.

Em produção, defina segredos exclusivos com pelo menos 32 caracteres, mantenha `CATALOG_ALLOW_OPEN_ADMIN=false`, desabilite a documentação da API e execute o readiness check antes do deploy.

---

## Testes

A suíte usa Pytest e cobre:

- parsing do cadastro HTML, planilhas e especificações técnicas;
- descoberta e classificação de imagens locais, S3, Google Drive e Graph;
- merge de ERP, estoque e PostgreSQL;
- endpoints HTTP, exportações e painel administrativo;
- autenticação, autorização, rate limiting, headers e proteções de arquivos/URLs.

Execute:

```bash
pytest -q
```

Validações do frontend:

```bash
cd frontend
npm run lint
npm run build
```

Estado verificado em julho de 2026: **101 testes aprovados**, lint sem avisos e build de produção concluído. A suíte em Python 3.14 emite avisos de depreciação vindos de FastAPI/Starlette; o CI oficial usa Python 3.12.

O workflow [`.github/workflows/ci.yml`](.github/workflows/ci.yml) executa testes, lint e build em pushes e pull requests sobre Windows, Python 3.12 e Node.js 20.

---

## Deploy

O deploy documentado usa AWS SAM:

1. crie `.env.production` e `frontend/.env.production` fora do Git;
2. valide segredos, CORS, autenticação e URL da API;
3. faça o build e deploy da API;
4. sincronize as imagens e o frontend compilado com os buckets retornados.

```powershell
python scripts/check_production_readiness.py `
  --env-file .env.production `
  --frontend-env frontend/.env.production

sam build
sam deploy --guided
```

Depois do deploy, configure `VITE_API_BASES` com o output `ApiUrl`:

```powershell
cd frontend
npm.cmd ci
npm.cmd run build
aws s3 sync dist s3://NOME_DO_FRONTEND_BUCKET --delete
```

Para mídia:

```powershell
aws s3 sync "CAMINHO_DAS_FOTOS" s3://NOME_DO_MEDIA_BUCKET/produtos/ --delete
```

O stack cria API Gateway, Lambda, buckets S3, Cognito e DynamoDB. Cognito e DynamoDB estão reservados para migração futura; a autenticação e persistência atuais continuam baseadas nos mecanismos descritos neste README. Consulte [docs/aws-serverless.md](docs/aws-serverless.md) para os parâmetros e outputs.

Não há manifesto Kubernetes nem pipeline automatizado de publicação no repositório.

---

## Roadmap

- migrar usuários e autenticação para o Cognito já provisionado;
- substituir a persistência local de ERP e acessos pelo DynamoDB ou outro armazenamento durável;
- tornar mídia e frontend privados atrás de CloudFront, com TLS e domínio próprio;
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

**João Vitor Silva**

- GitHub: [@devjoao32](https://github.com/devjoao32)
- Projeto: [github.com/devjoao32/catalogo](https://github.com/devjoao32/catalogo)

---

## Sugestões para melhorar este projeto

- adicionar screenshots reais do catálogo, detalhe, login e painel ERP;
- gravar um GIF curto com busca, troca de marca, exportação e implantação de JSON;
- publicar uma demonstração protegida e incluir o link na seção de demonstração;
- adicionar uma licença explícita e arquivos `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md` e `CHANGELOG.md`;
- fixar versões das dependências Python e automatizar atualizações de segurança;
- adicionar testes de componentes e fluxos end-to-end do frontend;
- publicar cobertura de testes e configurar análise estática/dependabot;
- testar CI também em Linux e separar jobs de backend e frontend;
- criar Dockerfile e Compose para um ambiente local reproduzível;
- substituir cache e rate limiting em memória por uma solução compartilhada em ambientes distribuídos;
- migrar arquivos JSON mutáveis para armazenamento persistente compatível com Lambda;
- restringir os buckets S3 e servir conteúdo por CloudFront com Origin Access Control;
- remover ou integrar efetivamente os recursos Cognito e DynamoDB para evitar infraestrutura ociosa;
- adicionar métricas, alarmes, dashboards e rastreamento de erros além dos logs e do X-Ray básico;
- automatizar deploy por ambiente, releases semânticos e notas de versão;
- adotar Conventional Commits de forma consistente e validar mensagens no CI;
- documentar exemplos reais de payload ERP e respostas da API sem dados sensíveis;
- gerar e publicar o OpenAPI como artefato versionado;
- adicionar índices, paginação e processamento assíncrono antes de ampliar o volume de produtos.
