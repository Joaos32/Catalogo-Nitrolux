# Testes de segurança e carga do catálogo

Há dois recursos para validar o acesso ao catálogo e estimar o comportamento da API sob acessos simultâneos:

- `tests/test_security_load_contract.py` verifica que os dados do catálogo e os downloads exigem autenticação quando ela está configurada, rejeitam token inválido e usam cabeçalhos de cache privados associados à identidade da requisição.
- `scripts/load_test_catalog.py` simula níveis crescentes de usuários: cada usuário carrega o catálogo, faz três pesquisas locais por ciclo e baixa um formato de exportação. O relatório registra latências p50/p95/p99, erros HTTP, volume transferido e tempo das pesquisas locais.

## Como executar os testes de segurança

Na raiz do projeto:

```powershell
python -m pytest tests/test_security.py tests/test_security_load_contract.py tests/test_integration_api.py
```

## Como medir concorrência local

Inicie a API em modo local e, em outro terminal, rode o medidor:

```powershell
$env:VERCEL = "true"
$env:CATALOG_MEDIA_CDN_BASE_URL = ""
$env:CATALOG_MEDIA_BLOB_ENABLED = "false"
python -m uvicorn app:app --host 127.0.0.1 --port 8765
```

```powershell
python scripts/load_test_catalog.py --base-url http://127.0.0.1:8765 --users 1,5,10,20 --duration 10 --think-time 1 --formats csv,pdf --json-output .codex-tmp/load-report.json
```

Se a autenticação de representantes estiver habilitada, forneça um token por variável de ambiente. O token não é mostrado nem gravado no relatório:

```powershell
$env:CATALOG_LOAD_TOKEN = "<token de acesso>"
python scripts/load_test_catalog.py --base-url http://127.0.0.1:8765
```

Também é possível usar `CATALOG_LOAD_EMAIL` e `CATALOG_LOAD_PASSWORD`; nesse caso, o script autentica uma vez antes da medição. Os usuários virtuais compartilham a credencial, enquanto cada um mantém sua própria cadência de requisições.

O medidor aceita no máximo 200 usuários para testes locais. Alvos remotos são bloqueados por padrão; para habilitá-los, o destino precisa usar HTTPS e exige `--allow-remote`. Mais de 20 usuários remotos requerem `--allow-high-load`, e ZIP remoto — que pode consultar provedores externos de mídia — requer também `--allow-remote-zip`. Faça uma medição remota apenas com janela e autorização operacional definidas.

## Como interpretar

A busca digitada no catálogo roda no navegador depois do carregamento dos produtos. Por isso, o medidor calcula o custo dessa busca localmente e mede separadamente as requisições da API para carregar o catálogo e baixar arquivos. Ele não gera tráfego de busca por tecla para o servidor.

O maior estágio sem erros e com latência aceitável é uma referência para a máquina, a rede, os dados e a cadência usados naquela execução. Não é um limite universal de usuários simultâneos nem uma garantia de capacidade de produção: o runtime, a concorrência por instância, o cache e os provedores de mídia do deploy podem diferir. O mesmo token é compartilhado entre usuários simulados e o teste não mede uma onda de logins simultâneos.

Compare p95, erros 4xx/5xx, requisições por segundo e bytes por operação em cada nível. Considere a capacidade aprovada apenas se os critérios operacionais do ambiente forem cumpridos em uma medição controlada no próprio ambiente.

## Referência local

Em 28/09/2026, foi feita uma execução local com 2.247 produtos, cinco segundos por estágio, intervalo de um segundo entre downloads e formatos CSV/PDF:

| Usuários simultâneos | Requisições HTTP | Erros | p95 carregar catálogo | p95 pesquisa local | p95 CSV | p95 PDF |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 5 | 0 | 29 ms | 15 ms | 323 ms | 2,4 s |
| 5 | 18 | 0 | 289 ms | 23 ms | 4,7 s | 5,2 s |
| 10 | 31 | 0 | 634 ms | 16 ms | 5,3 s | 5,4 s |
| 20 | 53 | 2 | 1,3 s | 19 ms | 15,0 s | 15,1 s |

Nesse equipamento, 10 usuários completaram a amostra sem erros, com p95 dos downloads acima de cinco segundos; a amostra de 20 atingiu o timeout de 15 segundos e teve duas falhas de transporte. Isso indica degradação clara em 20 usuários e não estabelece um número aprovado para produção.
