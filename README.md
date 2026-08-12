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
```

Linux/macOS:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
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

## Autor

**João Vitor Silva Santos**

- GitHub: [@Joaos32](https://github.com/Joaos32)
- LinkedIn: [João Vitor Silva Santos](https://www.linkedin.com/in/joao-vitor-silva-santos/)
- E-mail: joaovitorsilvasantos3255@gmail.com

---

Este é um dos projetos principais do meu portfólio e representa uma aplicação full stack construída para resolver um cenário real de organização, integração e distribuição de informações de produtos.