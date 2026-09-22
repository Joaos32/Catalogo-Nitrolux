# Deploy AWS Serverless

O deploy de produção usa uma única origem HTTPS:

- CloudFront publica a aplicação;
- o frontend React/Vite fica em um bucket S3 privado;
- `/catalog/*` e `/auth/*` são encaminhados pelo CloudFront ao API Gateway;
- a API FastAPI roda em Lambda por meio do Mangum;
- as fotos ficam em outro bucket S3 privado e são entregues por URLs temporárias assinadas.

Essa topologia mantém frontend, API e cookies de sessão no mesmo domínio. Os buckets não possuem acesso público.

## Pré-requisitos

- AWS CLI v2 configurado (`aws sts get-caller-identity`);
- AWS SAM CLI;
- Python 3.12 para reproduzir o runtime da Lambda;
- Node.js 20 ou superior;
- Docker, caso o build seja executado com `-UseContainer`.

## Preparação no Windows

Instale AWS CLI e SAM CLI pelos instaladores oficiais e abra um novo PowerShell. Confira:

```powershell
aws --version
sam --version
docker version
```

Para dependências Python nativas, o Docker Desktop deve estar instalado, iniciado e configurado para containers Linux. A instalação do Docker/WSL exige privilégios administrativos no Windows.

Para acesso humano, prefira credenciais temporárias pelo IAM Identity Center:

```powershell
aws configure sso
aws sso login --profile catalogo-prod
aws sts get-caller-identity --profile catalogo-prod
```

Não coloque access keys no repositório nem em `.env`.

## Deploy automatizado

Defina os segredos apenas na sessão atual do PowerShell:

```powershell
$env:CATALOG_SESSION_SECRET = "gere-um-segredo-aleatorio-com-32-ou-mais-caracteres"
$env:CATALOG_REPRESENTATIVE_JWT_SECRET = "gere-outro-segredo-independente-com-32-ou-mais-caracteres"
$env:CATALOG_ADMIN_LOGIN_EMAIL = "admin@empresa.com"
$env:CATALOG_ADMIN_LOGIN_PASSWORD = "uma-senha-forte"
```

Execute na raiz do repositório:

```powershell
.\scripts\deploy_aws.ps1 `
  -StackName catalogo-prod `
  -Region sa-east-1 `
  -AwsProfile catalogo-prod `
  -UseContainer `
  -PreflightOnly
```

Esse primeiro comando valida ferramentas, Docker, identidade AWS, segredos, administrador, representantes e template, sem criar recursos. Quando ele terminar com `Preflight AWS concluido sem criar recursos.`, publique:

```powershell
.\scripts\deploy_aws.ps1 `
  -StackName catalogo-prod `
  -Region sa-east-1 `
  -AwsProfile catalogo-prod `
  -UseContainer
```

O script:

1. valida a identidade AWS e o template SAM;
2. roda os testes Python;
3. instala e compila o frontend para mesma origem;
4. executa `sam build` e `sam deploy`;
5. envia `frontend/dist` ao bucket privado;
6. invalida o cache do CloudFront;
7. mostra a URL pública final.

Para enviar as fotos no mesmo comando:

```powershell
.\scripts\deploy_aws.ps1 `
  -StackName catalogo-prod `
  -Region sa-east-1 `
  -MediaSource "C:\caminho\para\Flayer" `
  -UseContainer
```

O envio de fotos não usa `--delete`, evitando remoção acidental de objetos existentes.

## Configuração de usuários

Na Lambda, alterações gravadas somente no sistema de arquivos não persistem entre execuções. Para o primeiro deploy, forneça os representantes por variável:

```powershell
$env:CATALOG_REPRESENTATIVE_USERS_JSON = '[{"email":"vendas@empresa.com","name":"Vendas","password_hash":"HASH_GERADO"}]'
```

O catálogo fica público quando nenhuma fonte de representantes é configurada. O painel pode ler as credenciais administrativas informadas no deploy, mas cadastros mutáveis e importações ERP precisam ser tratados como dados de origem e republicados; a migração dessas gravações para armazenamento persistente deve ser feita antes de usar o painel como sistema transacional.

## Deploy manual

O equivalente básico é:

```powershell
cd frontend
$env:VITE_API_BASES = "/"
npm ci
npm run build
cd ..

sam build --use-container
sam deploy --guided
```

Depois consulte os outputs da stack e publique:

```powershell
aws s3 sync frontend/dist s3://BUCKET_DO_FRONTEND --delete
aws s3 sync "C:\caminho\para\Flayer" s3://BUCKET_DE_MIDIA/produtos/
aws cloudfront create-invalidation --distribution-id ID_DA_DISTRIBUICAO --paths "/*"
```

Abra o output `ApplicationUrl`, não o endpoint direto do API Gateway.

## CORS e domínio próprio

O frontend usa `VITE_API_BASES=/`, portanto as chamadas normais são same-origin e não dependem de CORS. O parâmetro `CorsAllowOrigins` existe apenas para clientes hospedados em outro domínio.

Para um domínio próprio, adicione ao template um certificado ACM na região `us-east-1` e configure `Aliases` e `ViewerCertificate` na distribuição. Depois use esse domínio em `CorsAllowOrigins`.

## Custos e retenção

O template usa recursos cobrados por uso: Lambda, API Gateway, S3 e CloudFront. Os dois buckets possuem `DeletionPolicy: Retain`; remover a stack não apaga automaticamente builds nem fotos.
