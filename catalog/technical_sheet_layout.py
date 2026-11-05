"""Column contract for the recurring Nitrolux product registration workbook."""

# Row 3 of teste.xlsx; row 2 groups the repeated measurement headers.
NITROLUX_HEADERS = (
    "CATEGORIA", "CÓDIGO", "DESCRIÇÃO", "NCM", "IPI", "CEST", "CÓDIGO INMETRO",
    "TITULO E-COMMERCE", "DESCRIÇÃO E-COMMERCE", "PALAVRAS CHAVE",
    "DESCRIÇÃO COMERCIAL", "FICHA TÉCNICA", "POTÊNCIA (W)", "TEMP. COR (K)",
    "TENSÃO (V)", "INDICE DE PROTEÇÃO (IP)", "IRC", "FLUXO LUMINOSO (lm)",
    "FATOR DE POTÊNCIA", "BASE", "VIDA ÚTIL (Horas)", "GARANTIA", "COR", "MATERIAIS",
    "LARGURA (cm)", "ALTURA (cm)", "COMP. (cm)", "DIAMETRO BASE", "PESO LÍQUIDO (Kg)",
    "PESO BRUTO (Kg)", "ALTURA (cm)", "LARGURA (cm)", "COMP (cm)", "COD BARRAS (EAN)",
    "PESO BRUTO (Kg)", "PESO LÍQUIDO (Kg)", "QTD UNID", "COMP (cm)", "LARGURA (cm)",
    "ALTURA (cm)", "COD BARRAS (DUN)", "FOTO 1", "FOTO 2", "FOTO 3", "CUBAGEM",
)

# Zero-based indexes. Structured fields precede the free-form technical sheet,
# so current column values take precedence when the presentation deduplicates them.
NITROLUX_TECHNICAL_COLUMNS = {
    6: "Código Inmetro",
    12: "Potência (W)", 13: "Temperatura de cor (K)", 14: "Tensão (V)",
    15: "Índice de proteção (IP)", 16: "IRC", 17: "Fluxo luminoso (lm)",
    18: "Fator de potência", 19: "Base", 20: "Vida útil (horas)",
    21: "Garantia", 22: "Cor", 23: "Material",
    24: "Produto - Largura (cm)", 25: "Produto - Altura (cm)",
    26: "Produto - Comprimento (cm)", 27: "Produto - Diâmetro da base",
    28: "Produto - Peso líquido (kg)",
    29: "Embalagem - Peso bruto (kg)", 30: "Embalagem - Altura (cm)",
    31: "Embalagem - Largura (cm)", 32: "Embalagem - Comprimento (cm)",
    33: "Código de barras EAN",
    34: "Caixa master - Peso bruto (kg)", 35: "Caixa master - Peso líquido (kg)",
    36: "Caixa master - Quantidade de unidades", 37: "Caixa master - Comprimento (cm)",
    38: "Caixa master - Largura (cm)", 39: "Caixa master - Altura (cm)",
    40: "Código de barras DUN", 44: "Cubagem",
    11: None,
}
