# Vercel com PostgreSQL remoto

Alternativa a configuracao atual com [Blob privado](vercel-blob.md). Para usa-la,
altere tambem `CATALOG_STATE_BACKEND` para `postgres` em `vercel.json`.

O backend publicado na Vercel precisa de um PostgreSQL acessível a partir dos
servidores da Vercel. `localhost` na conexão aponta para a função da Vercel,
não para o computador em que o código foi publicado.

## Projeto e conta corretos

O novo endereço informado é `https://catalogo-nitrolux-ten.vercel.app`.
A configuração local da CLI ainda aponta para o projeto pessoal anterior.
Entre com a conta que administra o projeto da empresa:

```powershell
npx.cmd vercel login
npx.cmd vercel teams list
```

Antes de publicar pelo terminal, vincule o diretório à equipe e ao projeto
corretos, usando os nomes mostrados no painel da empresa:

```powershell
npx.cmd vercel link --scope <ESCOPO_EMPRESA> --project <PROJETO_EMPRESA>
```

## Conexão PostgreSQL

Use o PostgreSQL remoto da empresa ou provisione um PostgreSQL gerenciado.
Uma opção com plano gratuito é o Neon, disponível no Marketplace da Vercel.
Confira o plano e os limites na contratação; o aplicativo usa PostgreSQL
diretamente por Psycopg e não depende de um SDK específico do provedor.

- https://vercel.com/marketplace/neon
- https://vercel.com/docs/postgres
- https://neon.com/blog/neon-free-plan-1-gb-per-project

Guarde a conexão em `.env.local` para preparar o banco e como
`CATALOG_STATE_DATABASE_URL` em **Production** no projeto da empresa.
Não use `VITE_*` para essa conexão. Para hosts remotos, o backend exige TLS.
O código também é compatível com poolers de transações.

No ambiente local, execute para criar a estrutura no banco selecionado:

```powershell
python scripts/setup_catalog_database.py
python scripts/setup_catalog_database.py --apply
```

O segundo comando cria somente o schema privado e as tabelas. Não importa os
arquivos antigos nem apaga dados existentes.

## Variáveis do novo projeto

O diagnóstico público de 15/10/2026 encontrou ausência de login, segredo de
sessão e armazenamento ERP no novo deploy. Configure valores próprios para o
ambiente da empresa; as configurações do projeto anterior não são transferidas
automaticamente:

```text
CATALOG_STATE_BACKEND=postgres
CATALOG_STATE_DATABASE_URL=<conexao PostgreSQL remota>
CATALOG_SESSION_SECRET=<segredo aleatorio com pelo menos 32 caracteres>
CATALOG_REPRESENTATIVE_JWT_SECRET=<outro segredo aleatorio>
CATALOG_REQUIRE_REPRESENTATIVE_LOGIN=true
CATALOG_SESSION_COOKIE_SECURE=true
CATALOG_ALLOW_OPEN_ADMIN=false
CATALOG_ENABLE_API_DOCS=false
CATALOG_MEDIA_BLOB_ENABLED=false
CATALOG_ERP_BLOB_ENABLED=false
```

Configure também as credenciais administrativas, o acesso inicial autorizado
e as variáveis da fonte de fotos. Até a migração dos usuários, um acesso de
contingência pode ser definido em `CATALOG_REPRESENTATIVE_USERS_JSON`, com hash
de senha. A conta temporária criada no projeto anterior não existe
automaticamente neste projeto.

Não envie o arquivo `.env.local` inteiro para a configuração de produção: ele
contém a conexão PostgreSQL do computador e credenciais do ambiente anterior.

## Código e catálogo empacotado

Publique a versão que inclui `catalog/state_database.py` e as alterações de
autenticação e persistência. O diretório local tem arquivos novos ainda não
versionados; confirme que eles estão presentes no repositório usado pela Vercel.

A validação do catálogo foi corrigida para aceitar a conversão de quebras de
linha CRLF/LF feita pelo Git. Ela mantém a rejeição de snapshots quando os dados
dos produtos mudam. Inclua essa correção na nova publicação.

## Preservar os dados recentes

O usuário informou que os dados atuais de usuários e ERP existem somente no
Blob anterior. As cópias locais de setembro não devem ser usadas como substitutas.
Mudar o projeto Vercel ou criar um PostgreSQL não transfere os objetos do Blob.

Quando o acesso de leitura ao Blob for recuperado, use o token de origem apenas
no ambiente de migração e execute:

```powershell
python scripts/migrate_blob_state.py
python scripts/migrate_blob_state.py --apply
```

O primeiro comando valida os dados atuais. O segundo copia usuários e ERP numa
transação e recusa sobrescrever objetos já existentes no destino. Suspenda as
alterações administrativas durante a cópia e a troca de armazenamento.

Após publicar, valide `/health/ready`, login, leitura de produtos e atualização
ERP. A disponibilidade dos dados recentes depende da recuperação da origem.
