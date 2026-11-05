# Vercel com Blob privado

A configuracao escolhida usa a Vercel para o site e um Blob **privado** para
usuarios e ERP. `vercel.json` define `CATALOG_STATE_BACKEND=blob`: conexoes
PostgreSQL e credenciais S3 antigas nao selecionam outro armazenamento.
As fotos continuam na fonte de midia ja configurada.

## Configurar o projeto da empresa

O endereco informado e `https://catalogo-nitrolux-ten.vercel.app`.
Antes de publicar, confirme a equipe e o projeto: a vinculacao local anterior
apontava para o projeto pessoal `catalogo`.

```powershell
npx.cmd vercel login
npx.cmd vercel teams list
npx.cmd vercel link --scope <ESCOPO_EMPRESA> --project <PROJETO_EMPRESA>
```

Em Storage, crie ou conecte um Blob privado ao projeto correto e selecione
Production. A conexao fornece `BLOB_READ_WRITE_TOKEN` ao servidor. Configure
tambem os segredos de sessao/JWT e as credenciais administrativas descritos
em [vercel.md](vercel.md). Nao envie tokens no chat nem use nomes `VITE_*`.

```text
CATALOG_STATE_BACKEND=blob
CATALOG_ERP_BLOB_ENABLED=true
CATALOG_MEDIA_BLOB_ENABLED=false
CATALOG_REPRESENTATIVE_BLOB_PATH=catalogo/representative_users.json
CATALOG_ERP_BLOB_PATH=catalogo/erp_products.json
```

Essas configuracoes precisam estar presentes no novo deployment. Grave tambem
as opcoes de `env` do `vercel.json` em Production no painel da Vercel para que
republicacoes pela CLI conservem login obrigatorio, ERP no Blob e demais opcoes. Um Blob
vazio nao transfere os usuarios ou o ERP do projeto anterior.

## Preservar os dados recentes

Se o mesmo Blob continuar conectado, mantenha os objetos atuais. Nao execute
a copia entre stores nesse caso. Se houver um novo Blob, prepare os dois tokens
somente no arquivo local ignorado `.env.local`:

```text
CATALOG_SOURCE_BLOB_READ_WRITE_TOKEN=<token do Blob antigo>
BLOB_READ_WRITE_TOKEN=<token do Blob novo>
```

Os caminhos de origem podem ser alterados por
`CATALOG_SOURCE_REPRESENTATIVE_BLOB_PATH` e `CATALOG_SOURCE_ERP_BLOB_PATH`.
O utilitario le exatamente esses dois objetos, valida os dados e verifica ambos
os destinos antes de gravar. Nao lista fotos, apaga a origem ou sobrescreve o destino.
Senhas, hashes, permissoes e demais campos existentes sao preservados.

```powershell
python scripts/migrate_blob_store.py
python scripts/migrate_blob_store.py --apply
```

O primeiro comando so verifica; o segundo envia os objetos ausentes. Se uma
gravacao for interrompida, execute novamente: objetos identicos sao ignorados,
enquanto dados diferentes interrompem a copia. A transferencia de dois objetos
nao e uma transacao atomica. Execute durante uma pausa nas alteracoes de usuarios
e ERP, e so publique apontando ao novo Blob depois de concluir ambos.

O Blob antigo estava bloqueado por cota. Enquanto a leitura estiver bloqueada,
a transferencia dos dados recentes tambem fica bloqueada. As copias locais de
setembro nao substituem os dados recentes. Criar outro deploy nao recupera esses
objetos nem garante reinicio da cota.

## Reduzir operacoes avancadas

Nao ha gravacoes de presenca online no Blob; na Vercel sem um backend de
presenca separado, o painel informa que esse acompanhamento esta indisponivel.
Navegar e validar sessoes usa leituras; gravacoes de usuarios e ativacoes de ERP
continuam consumindo operacoes avancadas. Leituras tambem possuem limites.

### Cache das consultas

O servidor reutiliza os snapshots privados de usuarios e ERP por ate 300
segundos em memoria. Cada objeto, inclusive um objeto ausente, e lido uma vez
por janela e por instancia ativa. Chamadas simultaneas compartilham a mesma
leitura. Tokens e caminhos diferentes usam entradas separadas; o token nao e
armazenado nas chaves do cache.

Antes de alterar usuarios, senhas ou ERP, o backend ignora o cache e busca a
versao atual. Uma gravacao bem-sucedida atualiza imediatamente o snapshot da
instancia que gravou. Outras instancias podem levar ate cinco minutos para
perceber alteracoes de credenciais, exclusoes ou permissoes. Expirado o cache,
um erro de leitura nao permite usar credenciais antigas.

O navegador compartilha uma unica consulta de sessao entre login e catalogo.
Sem acompanhamento online, consulta novamente no vencimento do JWT e ao voltar
a uma tela com sessao desatualizada; o polling fixo a cada dois minutos foi
removido. A expiracao e a autorizacao continuam verificadas pelo servidor nas
requisicoes protegidas.

Em teste, 1.000 leituras do cadastro e 1.000 do ERP na mesma janela geraram
apenas duas chamadas de leitura ao Blob (uma por objeto). Isso nao representa
um limite garantido de usuarios: novas instancias, reinicios, expiracoes e
operacoes administrativas continuam gerando leituras. Nao ha cache global
compartilhado nem acesso ilimitado no plano gratuito.

A Vercel contabiliza `put`, `copy` e `list` como operacoes avancadas. O plano
Hobby inclui 2.000 e bloqueia o acesso ao Blob ao exceder a cota. Consulte os
[limites oficiais](https://vercel.com/docs/vercel-blob/usage-and-pricing).

Depois da configuracao e da transferencia, publique no projeto confirmado e
verifique `/health/ready`, login de representante e o ERP atual antes de liberar
o acesso aos usuarios.


## JSONs enviados para revisão

Com o armazenamento compartilhado do ERP habilitado, os arquivos enviados pelo painel são gravados como objetos privados e imutáveis em `catalogo/erp_inbox/<identificador>/<arquivo>.json`. O painel usa uma referência interna `erp-inbox://...` para consultar a prévia e implantar o arquivo selecionado. Não há gravação em `reports/erp_inbox` na função da Vercel, nem dependência de arquivos temporários locais entre requisições.

Envios com o mesmo nome recebem identificadores diferentes. O envio para revisão não muda o catálogo ativo; a substituição continua ocorrendo somente na ação de implantação. Os mesmos controles de acesso administrativo, origem da requisição e tamanho do upload permanecem ativos.

A caixa de revisão acompanha o backend de estado do ERP (Blob privado, S3 ou PostgreSQL). Instalações locais sem armazenamento remoto continuam usando a pasta configurada. Na Vercel, a ausência de armazenamento compartilhado retorna uma mensagem de configuração com status 503.
