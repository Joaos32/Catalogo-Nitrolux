# Segurança e limites operacionais do backend

As correções de 28/10/2026 mantêm os adaptadores de armazenamento existentes e tratam os nove achados principais da revisão. Não exigem migração dos dados atuais.

## Sessões administrativas

Cada ação administrativa com sessão revalida a existência da conta, sua permissão e a versão das credenciais. No Blob, essa consulta força atualização, independentemente do cache de cinco minutos utilizado nas leituras comuns. Isso acrescenta acesso ao armazenamento em ações administrativas para garantir a revogação entre instâncias. Erros de revalidação negam acesso.

Sessões antigas sem a versão das credenciais exigem novo login. Alterar senha, remover o usuário ou retirar seu papel administrativo invalida a sessão. Retirar e devolver o papel não reativa a sessão anterior.

O login Microsoft usa a identidade retornada pelo MSAL e exige que o mesmo e-mail esteja autorizado no cadastro administrativo. Antes de usar esse provedor, cadastre o usuário como administrador; contas Microsoft sem esse cadastro recebem 403.

`CATALOG_SESSION_MAX_AGE_SECONDS` continua controlando a duração do cookie. `CATALOG_ADMIN_SESSION_ABSOLUTE_MAX_SECONDS` limita a duração total da autenticação, mesmo com renovação do cookie; seu padrão é 43.200 segundos, ou 12 horas.

## Gravações e conflitos

ERP e representantes transportam a versão lida até a gravação remota. PostgreSQL usa comparação de versão e S3 usa condições de ETag/criação. Blob usa a escrita condicional da API oficial, porque o SDK Python instalado ainda não expõe `if_match` em `put`. O adaptador está isolado em `catalog/blob_versioning.py`; não existe fallback para sobrescrita incondicional.

O contrato segue o [código oficial da Vercel](https://github.com/vercel/storage/blob/main/packages/blob/src/put-helpers.ts). Alteração concorrente resulta em HTTP 409. O cliente deve recarregar o cadastro e reaplicar a alteração; repetir cegamente um snapshot antigo não resolve o conflito. Um timeout de gravação deve ser seguido de releitura, pois o provedor pode ter confirmado a alteração antes da interrupção.

Arquivos locais usam bloqueio entre processos e substituição atômica. Arquivos de representantes corrompidos produzem erro de armazenamento, em vez de serem substituídos por um cadastro vazio.

## Entradas, fotos e planilhas

O cadastro de representantes exige booleanos reais para `is_admin`, limita o tamanho dos campos e rejeita campos inesperados. Login e recuperação aceitam somente strings com comprimentos limitados, preservando os aliases existentes.

Operações síncronas de armazenamento e mídia são executadas fora do event loop. Falhas de consulta de fotos recebem 503 e `Cache-Control: no-store`; ausência confirmada de imagem continua sendo um resultado válido. O cliente divide consultas em lotes de até 30 códigos e propaga falhas, sem registrar sucesso vazio.

CSV e manifesto ZIP neutralizam prefixos de fórmulas nos campos textuais; números reais mantêm seu valor. No XLSX, campos textuais e cabeçalhos são gravados como texto explícito.

## Exportações e uploads

| Configuração | Padrão no código | Comportamento |
| --- | --- | --- |
| `CATALOG_ERP_MAX_UPLOAD_BYTES` | 10 MiB | Na Vercel, limitado adicionalmente a 4 MiB. A leitura para ao exceder o limite, mesmo sem `Content-Length`. |
| `CATALOG_EXPORT_MAX_BYTES` | 64 MiB | Na Vercel, limitado adicionalmente a 4 MiB. |
| `CATALOG_EXPORT_MAX_SECONDS` | 45 segundos | Orçamento cooperativo de geração e download; na Vercel, configurações maiores continuam limitadas a 45 segundos. |
| `CATALOG_EXPORT_MAX_PDF_PRODUCTS` | 150 | Rejeita seleção maior antes de renderizar. |
| `CATALOG_EXPORT_MAX_PDF_PAGES` | 10 | Limita páginas complementares de uma ficha técnica. |
| `CATALOG_EXPORT_MAX_ZIP_PRODUCTS` | 20 | Rejeita seleção maior antes de baixar as imagens. |
| `CATALOG_MEDIA_MAX_IMAGE_BYTES` | 5 MiB | Na Vercel, limitado adicionalmente a 4 MiB; aplica-se durante o download do Drive. |

Há duas vagas simultâneas para geração de exportações por processo. Excesso de trabalho retorna 503 com `Retry-After`; a vaga é liberada mesmo em erro. Isso limita o trabalho de cada instância, sem pretender substituir um limite compartilhado da infraestrutura.

Os limites excedidos retornam 413 com orientação para filtrar menos produtos. O orçamento de tempo é cooperativo: não interrompe arbitrariamente uma chamada nativa em andamento. Páginas rasterizadas são fechadas depois da geração do PDF.

A margem de 4 MiB fica abaixo do [limite documentado de 4,5 MB da Vercel](https://vercel.com/docs/functions/limitations). `.env.production.example` usa 4 MiB para uploads, exportações e imagens. As variáveis já configuradas em produção não foram alteradas.

Arquivos maiores e exportações completas com muitas imagens exigem uma etapa futura de geração em trabalho separado e entrega pelo armazenamento. A implementação atual rejeita essas operações de forma controlada; não foi criada uma fila nem um worker.

## Melhorias complementares ainda abertas

A limitação de login compartilhada depende de `CATALOG_AUTH_RATE_LIMIT_TABLE` ou proteção equivalente da infraestrutura; sem isso, o limite continua local ao processo. Um login bem-sucedido agora limpa apenas as falhas da própria identidade, preservando o contador compartilhado por IP. A configuração remota e o WAF não foram consultados.

Arquivos preparados pelo fluxo `stage-file` continuam locais. Para sobreviver à troca de instância, esse fluxo precisa armazenar o arquivo preparado de forma privada e durável, com identificador opaco e expiração. Não confundir a correção da gravação do ERP ativo com a persistência dessa etapa intermediária.

Continuam como evolução: versões reproduzíveis das dependências e auditoria automática, medição/pool e timeout de consultas PostgreSQL, política de atualização das leituras comuns entre instâncias e trilha de auditoria administrativa. Não houve migração ou alteração de serviços externos nesta correção.

## Verificação

- `python -m pytest -q --disable-warnings`: 269 testes aprovados, incluindo 59 novos cenários de regressão.
- `node scripts/check_photo_batches.mjs`: cliente TypeScript real consultando 71 códigos com API simulada; verifica lotes, combinação, duplicatas, entrada vazia e propagação de falha.
- `npm.cmd run lint` e `npm.cmd run build`, em `frontend`: aprovados.
- A CI executa também a verificação do contrato de lotes de fotos.

Os testes usam dados fictícios e provedores simulados. O contrato remoto de escrita condicional foi conferido no código oficial; não houve teste de gravação em dados de produção nem deploy nesta etapa.
