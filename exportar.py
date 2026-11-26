"""Exportação das notas lidas: planilha CSV e PDF (resumo de uma nota ou relatório geral).

O PDF de uma nota é um RESUMO para conferência, não substitui a DANFE
oficial. A geração de PDF usa a biblioteca reportlab.
"""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

from nfe import NotaFiscal, formatar_chave, formatar_cnpj_cpf


def reais(valor: Decimal) -> str:
    texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def quantidade(valor: Decimal) -> str:
    """10.0000 -> "10", 2.5000 -> "2,5" (sem notação científica)."""
    texto = format(valor.normalize(), "f")
    return texto.replace(".", ",")


def status(nota: NotaFiscal) -> str:
    if nota.problemas:
        return "Com erros"
    if nota.avisos:
        return "Atenção"
    return "OK"


def exportar_csv(notas: list[NotaFiscal], destino: str | Path) -> None:
    """Uma linha por item, com os dados da nota repetidos (fácil de filtrar no Excel)."""
    with open(destino, "w", newline="", encoding="utf-8-sig") as arquivo:
        escritor = csv.writer(arquivo, delimiter=";")
        escritor.writerow(["Chave", "Número", "Série", "Emissão", "Emitente", "CNPJ emitente", "Destinatário",
                           "Situação", "Status", "Item", "Código", "Descrição", "EAN", "NCM", "CFOP", "Quantidade",
                           "Valor unitário", "Valor item", "Total da nota", "Conferida"])
        for nota in notas:
            base = [nota.chave, nota.numero, nota.serie,
                    nota.emissao.strftime("%d/%m/%Y") if nota.emissao else "", nota.emitente_nome,
                    formatar_cnpj_cpf(nota.emitente_doc), nota.destinatario_nome, nota.situacao, status(nota)]
            fim = [str(nota.valor_total).replace(".", ","), "Sim" if nota.conferida else "Não"]
            if not nota.itens:
                escritor.writerow(base + [""] * 9 + fim)
            for item in nota.itens:
                escritor.writerow(base + [item.numero, item.codigo, item.descricao, item.ean, item.ncm, item.cfop,
                                          quantidade(item.quantidade),
                                          str(item.valor_unitario).replace(".", ","),
                                          str(item.valor_total).replace(".", ",")] + fim)


def _estilos():
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    base = getSampleStyleSheet()
    return {
        "titulo": ParagraphStyle("titulo", parent=base["Title"], fontSize=16, alignment=0, spaceAfter=4),
        "sub": ParagraphStyle("sub", parent=base["Normal"], fontSize=8.5, textColor=colors.HexColor("#555555")),
        "secao": ParagraphStyle("secao", parent=base["Heading3"], fontSize=11, spaceBefore=10, spaceAfter=4),
        "normal": ParagraphStyle("normal", parent=base["Normal"], fontSize=9, leading=12),
        "pequeno": ParagraphStyle("pequeno", parent=base["Normal"], fontSize=8, leading=10),
        "erro": ParagraphStyle("erro", parent=base["Normal"], fontSize=9, textColor=colors.HexColor("#b3261e")),
        "aviso": ParagraphStyle("aviso", parent=base["Normal"], fontSize=9, textColor=colors.HexColor("#8a5a00")),
    }


def _tabela(dados, larguras, alinhar_direita=()):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    tabela = Table(dados, colWidths=larguras, repeatRows=1)
    estilo = [
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for coluna in alinhar_direita:
        estilo.append(("ALIGN", (coluna, 0), (coluna, -1), "RIGHT"))
    tabela.setStyle(TableStyle(estilo))
    return tabela


def pdf_nota(nota: NotaFiscal, destino: str | Path) -> None:
    from reportlab.graphics.barcode import code128
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    e = _estilos()
    doc = SimpleDocTemplate(str(destino), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm, title=f"NF-e {nota.numero}")
    largura = A4[0] - 30 * mm
    emissao = nota.emissao.strftime("%d/%m/%Y %H:%M") if nota.emissao else "-"
    partes = [
        Paragraph(f"Resumo da NF-e nº {nota.numero} · série {nota.serie}", e["titulo"]),
        Paragraph("Documento auxiliar para conferência. Não substitui a DANFE oficial.", e["sub"]),
        Spacer(1, 6),
        code128.Code128(nota.chave, barHeight=12 * mm, barWidth=0.26 * mm, humanReadable=False),
        Paragraph(f"<b>Chave de acesso:</b> {formatar_chave(nota.chave)}", e["normal"]),
        Spacer(1, 4),
        _tabela([["Emissão", "Situação", "Protocolo", "Natureza da operação"],
                 [emissao, nota.situacao, nota.protocolo or "-", Paragraph(nota.natureza or "-", e["pequeno"])]],
                [32 * mm, 30 * mm, 38 * mm, largura - 100 * mm]),
        Paragraph("Emitente e destinatário", e["secao"]),
        _tabela([["", "Nome", "CNPJ/CPF"],
                 ["Emitente", Paragraph(nota.emitente_nome, e["pequeno"]), formatar_cnpj_cpf(nota.emitente_doc)],
                 ["Destinatário", Paragraph(nota.destinatario_nome or "-", e["pequeno"]),
                  formatar_cnpj_cpf(nota.destinatario_doc)]],
                [26 * mm, largura - 70 * mm, 44 * mm]),
        Paragraph("Itens", e["secao"]),
    ]
    linhas = [["#", "Descrição", "EAN", "Qtd", "Unitário", "Total"]]
    for item in nota.itens:
        linhas.append([item.numero, Paragraph(item.descricao, e["pequeno"]), item.ean,
                       quantidade(item.quantidade), reais(item.valor_unitario),
                       reais(item.valor_total)])
    linhas.append(["", "", "", "", "Total da nota", reais(nota.valor_total)])
    partes.append(_tabela(linhas, [8 * mm, largura - 112 * mm, 30 * mm, 16 * mm, 28 * mm, 30 * mm],
                          alinhar_direita=(3, 4, 5)))
    partes.append(Paragraph("Validações", e["secao"]))
    if not nota.problemas and not nota.avisos:
        partes.append(Paragraph("Nenhum problema encontrado: chave, CNPJ, códigos de barras e totais conferem.",
                                e["normal"]))
    partes += [Paragraph(f"ERRO: {p}", e["erro"]) for p in nota.problemas]
    partes += [Paragraph(f"ATENÇÃO: {a}", e["aviso"]) for a in nota.avisos]
    doc.build(partes)


def pdf_relatorio(notas: list[NotaFiscal], destino: str | Path) -> None:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    e = _estilos()
    pagina = landscape(A4)
    doc = SimpleDocTemplate(str(destino), pagesize=pagina, leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm, title="Relatório de NF-e")
    total = sum((n.valor_total for n in notas if n.situacao == "Autorizada"), Decimal("0"))
    com_erro = sum(1 for n in notas if n.problemas)
    conferidas = sum(1 for n in notas if n.conferida)
    linhas = [["Número", "Emissão", "Emitente", "Destinatário", "Situação", "Valor", "Status", "Conferida"]]
    for n in notas:
        linhas.append([n.numero, n.emissao.strftime("%d/%m/%Y") if n.emissao else "-",
                       Paragraph(n.emitente_nome, e["pequeno"]), Paragraph(n.destinatario_nome or "-", e["pequeno"]),
                       n.situacao, reais(n.valor_total), status(n), "Sim" if n.conferida else "Não"])
    largura = pagina[0] - 24 * mm
    partes = [
        Paragraph("Relatório de notas fiscais", e["titulo"]),
        Paragraph(f"{len(notas)} nota(s) · {com_erro} com erros · {conferidas} conferida(s) · "
                  f"total autorizado {reais(total)}", e["sub"]),
        Spacer(1, 8),
        _tabela(linhas, [20 * mm, 24 * mm, largura - 192 * mm, 60 * mm, 26 * mm, 28 * mm, 22 * mm, 20 * mm],
                alinhar_direita=(5,)),
    ]
    problemas = [(n, p) for n in notas for p in n.problemas]
    if problemas:
        partes.append(Paragraph("Erros encontrados", e["secao"]))
        partes += [Paragraph(f"NF-e {n.numero}: {p}", e["erro"]) for n, p in problemas]
    doc.build(partes)
