# Estado do catálogo em PostgreSQL gratuito

O backend aceita PostgreSQL (incluindo o plano Free do Supabase) para os
cadastros de representantes, o snapshot ERP e os usuários online. As fotos
continuam na fonte de mídia existente e não são copiadas para o banco.

O plano gratuito do Supabase inclui 500 MB de banco por projeto. Pode pausar
projetos com baixa atividade durante uma semana. Consulte os limites atuais:

- https://supabase.com/docs/guides/platform/billing-on-supabase
- https://supabase.com/docs/guides/platform/free-project-pausing

## Criar e preparar o banco

1. Crie um projeto **Free** no Supabase.
2. Execute [scripts/sql/catalog_state.sql](../scripts/sql/catalog_state.sql) no
   SQL Editor. As duas tabelas ficam no schema privado `catalog_private`, sem
   políticas públicas. Não adicione esse schema aos schemas expostos pela Data API.
3. Em **Connect**, selecione **Transaction pooler** e copie a conexão PostgreSQL.
   Use a senha do banco na conexão; caracteres especiais precisam de URL encoding.
4. Guarde a conexão como `CATALOG_STATE_DATABASE_URL` em `.env.local` para a
   migração. Nunca use uma variável `VITE_*`, nem envie essa conexão ao navegador.

O backend exige TLS, limita a abertura da conexão a cinco segundos e desativa
prepared statements para compatibilidade com o pooler de transações. A conexão
usada precisa ter acesso às tabelas privadas; a conexão administrativa do
projeto tem esse acesso. Em produção, também é possível usar uma role dedicada
com USAGE no schema e SELECT/INSERT/UPDATE nas duas tabelas, além de uma política
RLS exclusiva para essa role. A conexão administrativa não precisa dessas políticas.

## Migrar os dados antes de ativar na Vercel

Mantenha `BLOB_READ_WRITE_TOKEN` somente no ambiente local/server-side durante
a migração. O script lê os dois objetos privados conhecidos diretamente, sem
listar o Blob. Por padrão, apenas valida os dados e mostra os tamanhos:

```powershell
python scripts/migrate_blob_state.py
python scripts/migrate_blob_state.py --apply
```

O modo `--apply` insere usuários e ERP numa única transação. Se qualquer objeto
já existir no destino, aborta toda a transação. Os objetos originais no Blob
não são apagados. Hashes de senha, permissões e metadados são preservados.

Se o Blob estiver suspenso pela cota, a migração remota depende do retorno do
acesso. Com backups locais atuais, é possível migrar sem consultar o Blob:

```powershell
python scripts/migrate_blob_state.py --users-file reports/representative_users.json --erp-file reports/erp_products.json
python scripts/migrate_blob_state.py --users-file reports/representative_users.json --erp-file reports/erp_products.json --apply
```

Confira que os backups representam os usuários e o ERP ativos. O script recusa
origens vazias ou inválidas. Suspenda alterações administrativas durante a cópia
e a troca de backend, para não perder atualizações feitas no Blob nesse intervalo.

## Ativar

Após a migração, configure `CATALOG_STATE_DATABASE_URL` na Vercel para o ambiente
correspondente e publique uma nova versão. Quando essa variável está configurada,
o banco tem prioridade sobre Blob e S3 para usuários, ERP e presença. Falhas de
conexão não provocam gravações em outro armazenamento. Sem essa variável, os
backends anteriores de usuários e ERP continuam disponíveis.

Valide `/health/ready`, login de um representante, alteração de produto e lista
de usuários online. Use um banco separado em Preview para evitar alterações nos
dados de produção.

As fotos no Blob permanecem opcionais: mantenha `CATALOG_MEDIA_BLOB_ENABLED=false`
para que o acesso normal não liste imagens no Blob. Depois de validar a migração,
o token Blob pode ser retirado se nenhum outro recurso do projeto o utilizar.

## Consumo e disponibilidade

As sessões não gravam mais presença no Blob. Sem banco ou DynamoDB compartilhado
em serverless, o acompanhamento online informa que está desativado e não grava
heartbeats. O login continua protegido pelo cadastro configurado.

Com PostgreSQL, há uma linha de presença por usuário, atualizada no máximo uma
vez por minuto entre abas e instâncias. O frontend consulta periodicamente apenas
quando autenticado, com acompanhamento disponível e a página visível.

O snapshot ERP usa uma versão para impedir que alterações simultâneas sobrescrevam
uma atualização mais recente. A cota do Supabase ainda deve ser acompanhada;
migrar os dados não remove os outros limites do plano gratuito da Vercel.
