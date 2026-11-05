# Material de uso para representantes

Edição: **16/10/2026**. Conteúdo baseado na interface do catálogo Nitrolux/Pienza
e em capturas reais dessa versão, sem credenciais ou informações administrativas.

Arquivos para distribuição:

- `Guia-do-Representante-Nitrolux-Pienza.pdf`: guia ilustrado de cinco páginas, com link de acesso clicável.
- `Guia-do-Representante-Nitrolux-Pienza.docx`: versão editável, com as imagens incorporadas.
- `mensagem-divulgacao-whatsapp.txt`: mensagem pronta para acompanhar o PDF.

Fontes de edição:

- `conteudo.json`: conteúdo único usado para gerar os documentos.
- `guia-representantes.md`: versão em Markdown.
- `guia-representantes.html`: versão para leitura no navegador; mantenha a pasta `imagens` junto dela.
- `imagens/`: telas reais de acesso, filtros, informações de um produto e comandos da galeria.

Para atualizar o material, edite `conteudo.json` e execute na raiz do projeto:

```powershell
python docs/representantes/gerar_documentos.py
```

A geração do PDF requer PyMuPDF no ambiente de documentação. O gerador não
acessa a produção, não lê senhas e não altera o aplicativo. Revise os arquivos
gerados antes de compartilhar uma nova edição.
