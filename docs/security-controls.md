# Controles de segurança

## Identidade e sessões

O cadastro privado de representantes é autoritativo para alterações e exclusões. Contas de ambiente continuam disponíveis quando o cadastro pode ser consultado; não são usadas como contingência quando o provedor falha. Exclusões persistem um registro `disabled` para impedir que uma conta reapareça por outra fonte. Reativação requer senha nova.

As sessões possuem identificador aleatório. O logout persiste o SHA-256 desse identificador e sua expiração em `revoked_sessions` no mesmo documento privado, com bloqueio local ou compare-and-swap no provedor. Outros dispositivos permanecem ativos. Atualizações de usuários preservam as revogações. Se não for possível gravar a revogação, o logout retorna 503 e a interface informa o erro. Nenhum token ou cookie é gravado em texto nesse mapa.

Tokens de representantes possuem prazo absoluto de 12 horas, além do prazo de inatividade. A renovação mantém identificador e prazo absoluto. Entradas de revogação expiradas são removidas em novas gravações de logout. Sessões administrativas mantêm o prazo absoluto configurado em `CATALOG_ADMIN_SESSION_ABSOLUTE_MAX_SECONDS`.

Validações de autenticação leem o cadastro e as revogações sem cache compartilhado entre requisições. Isso fornece revogação entre instâncias, mas aumenta as leituras do Blob. Um PostgreSQL compartilhado pode reduzir a dependência das cotas do Blob; não foi provisionado um serviço nesta correção. Não reduza a frequência dessas leituras sem definir explicitamente uma janela aceitável de revogação.

A implantação desta versão exige novo login para sessões antigas, que não possuem o novo identificador. Não requer migração manual do documento existente: os novos campos são adicionados nas operações normais. Ao migrar o armazenamento, preserve o documento inteiro, incluindo exclusões e revogações.

## Requisições de navegador

Mutações de navegador em `/auth/` e `/catalog/` exigem origem permitida e o cabeçalho `X-Catalog-Request: 1`. Em produção, a origem da própria requisição é permitida. Origens adicionais devem ser explicitamente configuradas em `CATALOG_TRUSTED_ORIGINS` e na configuração CORS; não utilize curingas. As origens locais de desenvolvimento só são admitidas automaticamente fora da Vercel.

Clientes de serviço sem `Origin` e sem Fetch Metadata continuam usando sua autenticação própria. O cabeçalho do frontend não substitui autenticação. Uploads ERP recusam tipos simples como `text/plain`; o frontend envia `application/json`.

## Entrega e dependências

A rota protegida de imagens do Drive usa `private, no-store`. As páginas estáticas recebem cabeçalhos de segurança pelo `vercel.json`; a API recebe a mesma CSP pelo middleware. Scripts são limitados à própria origem, sem `unsafe-eval`. Fontes Google e imagens/downloads HTTPS permanecem permitidos para manter os recursos do catálogo.

`requirements.txt` lista diretamente as versões fixadas das dependências diretas e transitivas para compatibilidade com a Vercel. `requirements.lock` mantém o mesmo inventário para auditoria. O frontend usa `package-lock.json`. A CI audita os dois conjuntos, além de executar testes e build. Atualize os arquivos juntos e confirme compatibilidade com o Python de produção.

O limitador de login compartilhado por DynamoDB continua opcional via `CATALOG_AUTH_RATE_LIMIT_TABLE`. Na ausência dele, o contador é local ao processo. WAF/IAM e retenção de logs precisam de revisão operacional própria; não foram modificados nesta entrega.
