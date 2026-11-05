"""Generate the representative PDF, editable DOCX and Markdown from conteudo.json.

Requires PyMuPDF for PDF generation. This script never accesses production or credentials.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
import re
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

import fitz


ROOT = Path(__file__).resolve().parent
STEM = "Guia-do-Representante-Nitrolux-Pienza"
DATA = json.loads((ROOT / "conteudo.json").read_text(encoding="utf-8"))
CSS = """body { font-family: sans-serif; color: #25374a; font-size: 10.3pt; line-height: 1.36; }
h1 { font-size: 26pt; line-height: 1.12; color: #102e50; margin: 0 0 10pt; }
h2 { font-size: 13pt; color: #133f6d; margin: 13pt 0 5pt; }
p { margin: 0 0 8pt; }
.eyebrow { color: #24728b; font-weight: bold; font-size: 8pt; letter-spacing: 1pt; margin: 0 0 8pt; }
.lead { font-size: 11.2pt; line-height: 1.4; margin-bottom: 12pt; }
ul, ol { margin: 3pt 0 10pt; padding-left: 18pt; }
li { margin: 0 0 5pt; }
.callout { background: #edf5fa; border-left: 3pt solid #2884a5; padding: 10pt 12pt; margin: 10pt 0; }
.callout p { margin: 4pt 0 0; }
.link { background: #102e50; color: white; padding: 10pt 12pt; margin: 0 0 12pt; }
.link a { color: white; text-decoration: none; font-size: 9.3pt; }
.caption { font-size: 8pt; color: #61758a; margin: 4pt 0 10pt; }
.figure { text-align: center; margin: 8pt 0; }
table { width: 100%; border-collapse: collapse; margin: 7pt 0 12pt; }
th { background: #173f67; color: white; text-align: left; font-size: 10pt; }
th, td { padding: 7pt 8pt; border: 0.5pt solid #d9e5ed; vertical-align: top; }
table.split { margin: 4pt 0 8pt; }
table.split td { border: none; padding: 0; }
table.split td.left { padding-right: 14pt; }
table.split h2:first-child { margin-top: 0; }
"""


def inline(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(text))


def figure(block: dict) -> str:
    width = block.get("width", 510)
    return f'<div class="figure"><img src="imagens/{block["file"]}" width="{width}" alt="{html.escape(block['caption'])}"><p class="caption">{inline(block["caption"])}</p></div>'


def blocks_html(blocks: list[dict]) -> str:
    output = []
    for block in blocks:
        kind = block["kind"]
        if kind == "paragraph":
            output.append(f'<p>{inline(block["text"])}</p>')
        elif kind == "heading":
            output.append(f'<h2>{inline(block["text"])}</h2>')
        elif kind in {"steps", "bullets"}:
            tag = "ol" if kind == "steps" else "ul"
            output.append(f'<{tag}>' + "".join(f"<li>{inline(item)}</li>" for item in block["items"]) + f'</{tag}>')
        elif kind == "link":
            output.append(f'<div class="link"><b>{inline(block["text"])}</b><br><a href="{html.escape(block["url"])}">{html.escape(block["url"])}</a></div>')
        elif kind == "callout":
            output.append(f'<div class="callout"><b>{inline(block["title"])}</b><p>{inline(block["text"])}</p></div>')
        elif kind == "image":
            output.append(figure(block))
        elif kind == "table":
            head = "".join(f"<th>{inline(value)}</th>" for value in block["headers"])
            rows = "".join("<tr>" + "".join(f"<td>{inline(value)}</td>" for value in row) + "</tr>" for row in block["rows"])
            output.append(f'<table><tr>{head}</tr>{rows}</table>')
        elif kind == "split":
            output.append(f'<table class="split"><tr><td class="left">{blocks_html(block["blocks"])}</td><td style="width:185pt">{figure(block)}</td></tr></table>')
        else:
            raise ValueError("Unknown block type: " + kind)
    return "".join(output)


def page_html(page: dict) -> str:
    return f'<div class="eyebrow">{inline(page["eyebrow"])}</div><h1>{inline(page["title"])}</h1><p class="lead">{inline(page["lead"])}</p>{blocks_html(page["blocks"])}'


def make_pdf() -> None:
    document = fitz.open()
    archive = fitz.Archive(str(ROOT))
    navy = (0.063, 0.18, 0.314)
    for number, content in enumerate(DATA["pages"], start=1):
        page = document.new_page(width=595.276, height=841.89)
        page.draw_rect(fitz.Rect(0, 0, page.rect.width, 8), color=None, fill=navy)
        page.insert_text((42, 35), "NITROLUX  /  PIENZA", fontname="hebo", fontsize=10, color=navy)
        page.insert_text((403, 35), "GUIA DO REPRESENTANTE", fontsize=7.5, color=navy)
        spare, scale = page.insert_htmlbox(fitz.Rect(42, 56, 553, 790), page_html(content), css=CSS, archive=archive, scale_low=1)
        if spare < 0 or scale < 0.999:
            raise RuntimeError(f"Content exceeds page {number}; edit the copy instead of shrinking it")
        page.draw_line((42, 806), (553, 806), color=(0.81, 0.87, 0.91), width=0.6)
        page.insert_text((42, 822), f"Guia de uso / Edição {DATA['edition']}", fontsize=8, color=(0.35, 0.43, 0.51))
        page.insert_text((520, 822), f"{number} / {len(DATA['pages'])}", fontsize=8, color=(0.35, 0.43, 0.51))
    document.set_metadata({"title":DATA["title"]+" | Nitrolux e Pienza","author":"Nitrolux","subject":"Guia de uso do catalogo para representantes","keywords":"catalogo, representantes, Nitrolux, Pienza"})
    document.set_toc([[1, p["title"], i] for i,p in enumerate(DATA["pages"],start=1)])
    document.save(ROOT / (STEM+".pdf"),garbage=4,deflate=True)
    document.close()


def markdown_blocks(blocks: list[dict]) -> list[str]:
    lines = []
    for block in blocks:
        kind = block["kind"]
        if kind == "heading":
            lines.append("### " + block["text"])
        elif kind == "paragraph":
            lines.append(block["text"])
        elif kind == "link":
            lines.append(f'[{block["text"]}]({block["url"]})')
        elif kind in {"steps", "bullets"}:
            lines.append("\n".join((f"{i}. " if kind == "steps" else "- ")+text for i,text in enumerate(block["items"],start=1)))
        elif kind == "callout":
            lines.append(f'**{block["title"]}**\n\n{block["text"]}')
        elif kind == "image":
            lines.append(f'![{block["caption"]}](imagens/{block["file"]})')
        elif kind == "table":
            lines.append("| " + " | ".join(block["headers"]) + " |\n| " + " | ".join("---" for _ in block["headers"]) + " |\n" + "\n".join("| " + " | ".join(row) + " |" for row in block["rows"]))
        elif kind == "split":
            lines.extend(markdown_blocks(block["blocks"]))
            lines.append(f'![{block["caption"]}](imagens/{block["file"]})')
    return lines


def make_markdown_and_html() -> None:
    text = f'# {DATA["title"]}\n\n{DATA["subtitle"]} • Edição {DATA["edition"]}\n'
    for page in DATA["pages"]:
        text += "\n\n## " + page["title"] + "\n\n" + page["lead"] + "\n\n" + "\n\n".join(markdown_blocks(page["blocks"]))
    (ROOT / "guia-representantes.md").write_text(text+"\n",encoding="utf-8")
    sheets = "".join('<article>'+page_html(page)+'</article>' for page in DATA["pages"])
    print_css = '@page{size:A4;margin:15mm} body{background:#e8eef5;margin:0} article{background:white;max-width:720px;padding:42px;margin:22px auto} img{max-width:100%;height:auto} @media print{body{background:white}article{margin:0;padding:0;break-after:page;max-width:none}article:last-child{break-after:auto}}'
    (ROOT / "guia-representantes.html").write_text(f'<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Guia do representante | Nitrolux e Pienza</title><style>{CSS}{print_css}</style><body>{sheets}</body></html>',encoding="utf-8")


def runs(text: str) -> str:
    output = []
    for part in re.split(r"(\*\*.*?\*\*)",text):
        bold = part.startswith("**") and part.endswith("**")
        value = part[2:-2] if bold else part
        output.append('<w:r>'+('<w:rPr><w:b/></w:rPr>' if bold else '')+'<w:t xml:space="preserve">'+escape(value)+'</w:t></w:r>')
    return "".join(output)


def paragraph(text: str, style: str = "Normal") -> str:
    return f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr>{runs(text)}</w:p>'


class WordDocument:
    def __init__(self):
        self.images: dict[str,str] = {}
        self.drawing_id = 0

    def image(self, block: dict) -> str:
        filename = block["file"]
        relation = self.images.setdefault(filename,"rIdImage"+str(len(self.images)+1))
        self.drawing_id += 1
        pixmap = fitz.Pixmap(ROOT / "imagens" / filename)
        width = min(block.get("width",510),495)
        height = width * pixmap.height / pixmap.width
        cx,cy = int(width*12700),int(height*12700)
        drawing = f'''<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/><wp:docPr id="{self.drawing_id}" name="{escape(filename)}" descr="{escape(block['caption'])}"/><a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic><pic:nvPicPr><pic:cNvPr id="0" name="{escape(filename)}"/><pic:cNvPicPr/></pic:nvPicPr><pic:blipFill><a:blip r:embed="{relation}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>'''
        return drawing+paragraph(block["caption"],"Caption")

    def table(self, block: dict) -> str:
        rows = []
        for i,row in enumerate([block["headers"]]+block["rows"]):
            cells = []
            for j,value in enumerate(row):
                width = 2550 if j == 0 else 7650
                props = f'<w:tcPr><w:tcW w:w="{width}" w:type="dxa"/>'+('<w:shd w:fill="EAF2FA"/>' if i==0 else '')+'</w:tcPr>'
                cells.append('<w:tc>'+props+paragraph('**'+value+'**' if i==0 else value)+'</w:tc>')
            rows.append('<w:tr>'+('<w:trPr><w:tblHeader/></w:trPr>' if i==0 else '')+''.join(cells)+'</w:tr>')
        return '<w:tbl><w:tblPr><w:tblStyle w:val="GuideTable"/><w:tblW w:w="10200" w:type="dxa"/></w:tblPr><w:tblGrid><w:gridCol w:w="2550"/><w:gridCol w:w="7650"/></w:tblGrid>'+''.join(rows)+'</w:tbl>'+paragraph('')

    def blocks(self, blocks: list[dict]) -> str:
        output = []
        for block in blocks:
            kind = block["kind"]
            if kind == "heading":
                output.append(paragraph(block["text"],"Heading2"))
            elif kind == "paragraph":
                output.append(paragraph(block["text"]))
            elif kind in {"steps","bullets"}:
                output.extend(paragraph((f'{i}. ' if kind == 'steps' else '• ')+value) for i,value in enumerate(block["items"],start=1))
            elif kind == "callout":
                output.extend([paragraph(block["title"],"Callout"),paragraph(block["text"])])
            elif kind == "image":
                output.append(self.image(block))
            elif kind == "link":
                output.append(paragraph(block["text"],"Heading2"))
                output.append('<w:p><w:hyperlink r:id="rIdCatalogLink"><w:r><w:rPr><w:color w:val="1D6488"/><w:u w:val="single"/></w:rPr><w:t>'+escape(block["url"])+'</w:t></w:r></w:hyperlink></w:p>')
            elif kind == "table":
                output.append(self.table(block))
            elif kind == "split":
                output.append('<w:tbl><w:tblPr><w:tblW w:w="10200" w:type="dxa"/></w:tblPr><w:tblGrid><w:gridCol w:w="6300"/><w:gridCol w:w="3900"/></w:tblGrid><w:tr><w:tc><w:tcPr><w:tcW w:w="6300" w:type="dxa"/></w:tcPr>'+self.blocks(block["blocks"])+paragraph('')+'</w:tc><w:tc><w:tcPr><w:tcW w:w="3900" w:type="dxa"/></w:tcPr>'+self.image(block)+'</w:tc></w:tr></w:tbl>'+paragraph(''))
        return ''.join(output)

    def save(self):
        body = []
        for i,page in enumerate(DATA["pages"]):
            if i:
                body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
            body.extend([paragraph(page["eyebrow"],"Subtitle"),paragraph(page["title"],"Title"),paragraph(page["lead"],"Lead"),self.blocks(page["blocks"])])
        body.append('<w:sectPr><w:headerReference w:type="default" r:id="rIdHeader"/><w:footerReference w:type="default" r:id="rIdFooter"/><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="850" w:right="850" w:bottom="850" w:left="850" w:header="360" w:footer="360"/></w:sectPr>')
        namespaces = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"'
        document = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {namespaces}><w:body>'+''.join(body)+'</w:body></w:document>'
        relation_type = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
        relationships = [f'<Relationship Id="rIdStyles" Type="{relation_type}styles" Target="styles.xml"/>',f'<Relationship Id="rIdHeader" Type="{relation_type}header" Target="header1.xml"/>',f'<Relationship Id="rIdFooter" Type="{relation_type}footer" Target="footer1.xml"/>',f'<Relationship Id="rIdCatalogLink" Type="{relation_type}hyperlink" Target="{escape(DATA["url"])}" TargetMode="External"/>']
        relationships.extend(f'<Relationship Id="{relation}" Type="{relation_type}image" Target="media/{filename}"/>' for filename,relation in self.images.items())
        styles = '''<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="21"/><w:lang w:val="pt-BR"/><w:color w:val="25374A"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="110" w:line="270" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:after="150"/></w:pPr><w:rPr><w:b/><w:sz w:val="48"/><w:color w:val="102E50"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="Heading 2"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="180" w:after="70"/><w:outlineLvl w:val="1"/></w:pPr><w:rPr><w:b/><w:sz w:val="25"/><w:color w:val="133F6D"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/><w:rPr><w:b/><w:sz w:val="17"/><w:color w:val="24728B"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Lead"><w:name w:val="Lead"/><w:basedOn w:val="Normal"/><w:rPr><w:sz w:val="23"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Caption"><w:name w:val="Caption"/><w:basedOn w:val="Normal"/><w:rPr><w:sz w:val="17"/><w:color w:val="61758A"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Callout"><w:name w:val="Callout"/><w:pPr><w:keepNext/><w:shd w:fill="EDF5FA"/><w:spacing w:before="120" w:after="60"/></w:pPr><w:rPr><w:b/><w:color w:val="173F67"/></w:rPr></w:style>
<w:style w:type="table" w:styleId="GuideTable"><w:name w:val="Guide Table"/><w:tblPr><w:tblBorders><w:top w:val="single" w:sz="4" w:color="D9E5ED"/><w:left w:val="single" w:sz="4" w:color="D9E5ED"/><w:bottom w:val="single" w:sz="4" w:color="D9E5ED"/><w:right w:val="single" w:sz="4" w:color="D9E5ED"/><w:insideH w:val="single" w:sz="4" w:color="D9E5ED"/><w:insideV w:val="single" w:sz="4" w:color="D9E5ED"/></w:tblBorders><w:tblCellMar><w:top w:w="90" w:type="dxa"/><w:left w:w="100" w:type="dxa"/><w:bottom w:w="90" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tblCellMar></w:tblPr></w:style></w:styles>'''
        content_types = '''<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/><Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/><Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/></Types>'''
        root_relations = '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rIdDocument" Type="'+relation_type+'officeDocument" Target="word/document.xml"/></Relationships>'
        with ZipFile(ROOT/(STEM+'.docx'),'w',ZIP_DEFLATED) as package:
            package.writestr('[Content_Types].xml',content_types)
            package.writestr('_rels/.rels',root_relations)
            package.writestr('word/document.xml',document)
            package.writestr('word/styles.xml',styles)
            package.writestr('word/_rels/document.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(relationships)+'</Relationships>')
            package.writestr('word/header1.xml','<w:hdr '+namespaces+'>'+paragraph('NITROLUX / PIENZA  |  GUIA DO REPRESENTANTE','Subtitle')+'</w:hdr>')
            package.writestr('word/footer1.xml','<w:ftr '+namespaces+'>'+paragraph('Edição '+DATA['edition'],'Caption')+'<w:p><w:pPr><w:jc w:val="right"/></w:pPr><w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText> PAGE </w:instrText></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p></w:ftr>')
            for filename in self.images:
                package.write(ROOT/'imagens'/filename,'word/media/'+filename)


def main():
    make_markdown_and_html()
    make_pdf()
    WordDocument().save()
    print('Generated: PDF (5 pages), editable DOCX, Markdown and HTML.')


if __name__ == '__main__':
    main()
