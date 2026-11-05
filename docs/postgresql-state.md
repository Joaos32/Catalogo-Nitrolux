# PostgreSQL direto para o catálogo

O catálogo conecta diretamente ao PostgreSQL por Psycopg. Supabase não é
necessário: qualquer servidor PostgreSQL acessível pelo backend, com TLS e
permissões adequadas, pode guardar os cadastros de usuários, o snapshot ERP
e a atividade online.

As fotos continuam na fonte de mídia existente. O ERP guarda as URLs das fotos;
esta integração não transfere os arquivos de imagem para o banco.

## Preparar o banco

Execute [catalog_state.sql](../scripts/sql/catalog_state.sql) no banco escolhido,
usando uma conexão administrativa ou uma role autorizada a criar o schema e
as tabelas. Isso cria `catalog_private.objects` e `catalog_private.presence`.

As tabelas têm RLS habilitado e não possuem políticas públicas. A conexão da
aplicação precisa usar a role proprietária das tabelas ou uma role específica
com USAGE no schema, SELECT/INSERT/UPDATE nas tabelas e políticas RLS próprias
que autorizem essas operações. Somente GRANT não libera uma role sujeita a RLS.

Guarde a conexão em `.env.local`, somente no servidor:

```text
CATALOG_STATE_DATABASE_URL=postgresql://USUARIO:SENHA@HOST:5432/BANCO
```

Substitua os exemplos e use URL encoding para caracteres especiais na senha.
Para servidores remotos, o backend exige TLS (`sslmode=require`). Em conexões
explícitas a `127.0.0.1`, `localhost` ou `::1`, usa `sslmode=prefer` para
aceitar a instalação local padrão sem TLS. Um `sslmode` de verificação
explicitamente configurado na URL é preservado. O timeout de conexão é de
cinco segundos. Não use uma variável `VITE_*` para essa conexão.

Se o catálogo continuar na Vercel, o PostgreSQL precisa estar acessível a partir
das funções da Vercel. Um banco disponível apenas em `localhost` no seu computador
não poderá ser acessado por essas funções. Se backend e banco estiverem no mesmo
servidor, o endereço pode ser local. A Vercel continua hospedando a aplicação; o servidor PostgreSQL é separado.

## Inicializar a estrutura pelo terminal

Depois de configurar a conexao em `.env.local`, voce pode criar a estrutura
sem executar SQL manualmente:

```powershell
python scripts/setup_catalog_database.py
python scripts/setup_catalog_database.py --apply
```

O primeiro comando apenas verifica a conexao e as tabelas. O segundo cria o
schema e as tabelas se ainda nao existirem; nao apaga dados nem cria outro banco.
Se ainda nao existe um banco dedicado ao catalogo, crie-o pelo pgAdmin e use
seu nome na conexao. O banco `postgres` tambem permite validar a conexao inicial.
A role utilizada para `--apply` deve poder criar o schema e as tabelas.

## Migrar antes de ativar

Com o Blob disponível e seu token configurado no ambiente local:

```powershell
python scripts/migrate_blob_state.py
python scripts/migrate_blob_state.py --apply
```

O primeiro comando somente valida. O segundo copia usuários e ERP em uma única
transação, recusando sobrescrever dados existentes no destino. Os hashes de
senha e permissões são preservados e os arquivos do Blob não são apagados.

Se o Blob estiver suspenso, use backups locais atualizados:

```powershell
python scripts/migrate_blob_state.py --users-file reports/representative_users.json --erp-file reports/erp_products.json
python scripts/migrate_blob_state.py --users-file reports/representative_users.json --erp-file reports/erp_products.json --apply
```

Confirme que os backups contêm o cadastro e o ERP atuais. Suspenda alterações
administrativas durante a migração e a troca de backend.

Após a cópia, configure `CATALOG_STATE_DATABASE_URL` no ambiente de produção da
Vercel e publique o código. Essa variável dá prioridade ao PostgreSQL para
usuários, ERP e presença, mesmo que as credenciais antigas do Blob existam.
Valide `/health/ready`, login, edição de produto e usuários online antes de
retirar as credenciais antigas.

Mantenha `CATALOG_MEDIA_BLOB_ENABLED=false` para que as fotos também não dependam
de listagens no Blob. Usar PostgreSQL não remove os limites dos outros recursos
da Vercel ou da hospedagem escolhida para o banco.
