# Disponibilidade e recuperação

## Proteções implementadas no código

- `GET /health/live` confirma que a aplicação está respondendo sem depender de serviços externos.
- `GET /health/ready` valida no runtime serverless o snapshot do catálogo, a chave de sessão estável, a existência de ao menos um representante e o acesso ao armazenamento durável do ERP. Responde `503` se faltar qualquer requisito.
- Os índices de fotos usam cache concorrente por chave, limitado a 128 entradas por instância. Uma falha no provedor permite usar o último resultado válido por até 24 horas; a regra vale apenas para leituras de mídia e não para autenticação ou gravação de dados.
- As respostas do catálogo, das integrações e das exportações no runtime Vercel são atualizadas em uma janela máxima de 10 segundos. As escritas locais ERP usam substituição atômica. No S3, atualizações usam ETag condicional e o bucket mantém versões anteriores.
- As tentativas de autenticação na AWS usam contadores DynamoDB compartilhados entre instâncias. Sem tabela compartilhada, o fallback em memória é limitado a 4.096 chaves.

## Estado da implantação

O `vercel.json` ativa Fluid Compute e fixa as funções em `gru1`. A Vercel entrega os arquivos estáticos pela CDN e informa redundância entre zonas para Functions; a redundância entre regiões e o número de regiões disponíveis dependem do plano e da configuração. Consulte [regiões de Functions](https://vercel.com/docs/functions/configuring-functions/region) antes de configurar uma região secundária.

O frontend estático pode continuar disponível mesmo quando a API ou um provedor de imagens falha. A rota `/health/live` serve para monitorar a API; `/health/ready` confirma o catálogo empacotado, a chave de sessão, o cadastro de representantes e o acesso ao armazenamento ERP. Configure um monitor externo para ambas e alerte quando `/health/ready` não retornar `200`.

## Riscos que ainda exigem infraestrutura

1. **No Vercel, configure o Blob privado antes da promoção.** Ele armazena o registro de representantes e o snapshot ERP ativo. A prontidão fica em `503` até haver usuários no registro e acesso válido ao Blob.
2. **No Vercel Blob, gravações concorrentes do ERP não têm comparação condicional entre instâncias.** Evite importações simultâneas; a AWS usa ETag condicional no S3 e retorna conflito para atualização concorrente.
3. **As fotos ainda dependem de provedores externos.** O cache de contingência só existe na instância aquecida que já consultou o provedor. Um início a frio durante uma indisponibilidade pode não ter cópia local. Para garantir a galeria, mantenha cópia versionada da mídia em um storage/CDN controlado pela aplicação.
4. **A API está configurada para uma região primária.** A região secundária precisa ser escolhida conforme o plano e a localização do armazenamento. Alterar regiões sem essa checagem pode aumentar a latência ou impedir o deploy.
5. **Não há monitoramento externo nem metas de recuperação registradas no repositório.** Defina SLO de disponibilidade e latência, RPO/RTO, canal de alerta, responsáveis e procedimento de rollback; depois faça teste de restauração, não apenas de backup.

## Operação de deploy

Antes de publicar:

1. Gere `reports/catalog_runtime.json` a partir das fontes aprovadas e valide hashes e quantidade de produtos.
2. Rode a suíte backend e a build do frontend.
3. Publique como Preview, verifique `/health/live`, `/health/ready`, autenticação, pesquisa, galeria e exportações.
4. Promova o mesmo artefato para produção e confira o domínio e os alertas.
5. Mantenha a implantação anterior disponível para rollback.

A medição local registrada em [segurança e carga](security-and-load-testing.md) encontrou aumento de latência nos PDFs a partir de cinco usuários e duas falhas no estágio de vinte. Não use esse teste local como SLO de produção: repita a carga em Preview com dados equivalentes antes de fixar o limite operacional.
