# Planilha recorrente de dados técnicos

O formato de referência é o arquivo `teste.xlsx` fornecido pelo usuário em
04/11/2026. O reconhecimento usa o conteúdo dos cabeçalhos e suas posições,
independentemente do nome do arquivo ou da aba.

- Linha 1: título do cadastro.
- Linha 2: grupos Produto, Embalagem e Caixa master.
- Linha 3: cabeçalhos de A a AS, nas posições originais.
- Linha 4 em diante: um produto por linha; B identifica o produto no catálogo.
- Linhas vazias e células que só possuem formatação são desconsideradas.

| Colunas | Uso na leitura |
| --- | --- |
| A e C | Categoria e descrição de referência; preserva os campos do catálogo. |
| B | Código do produto. |
| D a F | NCM, IPI e CEST; não fazem parte das especificações. |
| G | Código Inmetro. |
| H a K | Conteúdo comercial; preserva os campos do catálogo. |
| L | Texto da ficha técnica. |
| M a X | Potência, temperatura de cor, tensão, proteção IP, IRC, fluxo luminoso, fator de potência, base, vida útil, garantia, cor e material. |
| Y a AC | Largura, altura, comprimento, diâmetro da base e peso líquido do produto. |
| AD a AH | Peso bruto, altura, largura e comprimento da embalagem; código EAN. |
| AI a AO | Pesos bruto e líquido, quantidade, comprimento, largura e altura da caixa master; código DUN. |
| AP a AR | Fotos: células, fórmulas e erros são ignorados pelo importador técnico. |
| AS | Cubagem. |

Os rótulos de medidas e pesos incluem seu grupo para distinguir produto,
embalagem e caixa master. As colunas estruturadas são apresentadas antes do
texto da ficha técnica. Campos com `***`, `-` ou `--` são tratados como ausentes.
Não é necessário remover nem renomear as colunas com cabeçalhos repetidos.

A prévia mantém o número original de cada linha. Códigos repetidos ou ausentes
no catálogo e erros/fórmulas nas células efetivamente importadas ficam marcados
para correção; somente linhas válidas podem atualizar as especificações.
A aplicação exige a prévia e preserva nomes, descrições, categorias e fotos.
Não executa fórmulas e não importa automaticamente ao selecionar o arquivo.

O modelo público contém apenas os cabeçalhos, sem produtos do arquivo original.
Para regenerá-lo: `python scripts/build_technical_sheet_template.py`.

Planilhas simples com Código/SKU/Referência e Especificações ou outras colunas
técnicas continuam aceitas. Fora do modelo Nitrolux, os cabeçalhos devem ser únicos.
