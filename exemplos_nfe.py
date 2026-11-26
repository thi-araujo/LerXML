"""Gera XMLs de NF-e FICTÍCIOS para demonstração e testes.

As empresas, produtos e valores são inventados. Os CNPJs, chaves e códigos
EAN são montados com dígitos verificadores corretos só para passar nas
validações; não correspondem a empresas ou notas reais. Os XMLs gerados
seguem a estrutura da NF-e 4.00, mas não têm assinatura digital.

    python exemplos_nfe.py            # recria a pasta exemplos/
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape

from nfe import dv_chave

PASTA_EXEMPLOS = Path(__file__).resolve().parent / "exemplos"


def cnpj_com_dv(base12: str) -> str:
    numero = base12
    for tamanho in (12, 13):
        pesos = list(range(tamanho - 7, 1, -1)) + list(range(9, 1, -1))
        soma = sum(int(d) * p for d, p in zip(numero, pesos))
        numero += str(0 if soma % 11 < 2 else 11 - soma % 11)
    return numero


def ean13_com_dv(base12: str) -> str:
    soma = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(base12)))
    return base12 + str((10 - soma % 10) % 10)


EMITENTE = ("Distribuidora Exemplo Ltda (FICTÍCIA)", cnpj_com_dv("112223330001"), "SP", "35")
EMITENTE_2 = ("Papelaria Modelo S.A. (FICTÍCIA)", cnpj_com_dv("445556660001"), "MG", "31")
DESTINATARIO = ("Loja Demonstração ME (FICTÍCIA)", cnpj_com_dv("778889990001"))


@dataclass
class ItemExemplo:
    codigo: str
    descricao: str
    ean: str
    ncm: str
    quantidade: Decimal
    unitario: Decimal


def montar_xml(numero: int, emitente, itens: list[ItemExemplo], data: str = "2026-10-15T09:30:00-03:00",
               serie: int = 1, codigo: str = "10203040", cstat: str = "100", quebrar: dict | None = None) -> str:
    """Monta o XML. `quebrar` estraga dados de propósito para demonstrar as validações."""
    quebrar = quebrar or {}
    nome, cnpj, uf, cuf = emitente
    aamm = data[2:4] + data[5:7]
    chave43 = f"{cuf}{aamm}{cnpj}55{serie:03d}{numero:09d}1{codigo}"
    dv = dv_chave(chave43)
    if quebrar.get("dv"):
        dv = (dv + 1) % 10
    chave = f"{chave43}{dv}"
    totais = [(i.quantidade * i.unitario).quantize(Decimal("0.01")) for i in itens]
    v_prod = sum(totais, Decimal("0")) + quebrar.get("diferenca_total", Decimal("0"))
    dets = []
    for n, (item, total) in enumerate(zip(itens, totais), start=1):
        dets.append(f"""
      <det nItem="{n}">
        <prod>
          <cProd>{item.codigo}</cProd><cEAN>{item.ean}</cEAN><xProd>{escape(item.descricao)}</xProd>
          <NCM>{item.ncm}</NCM><CFOP>5102</CFOP><uCom>UN</uCom><qCom>{item.quantidade:.4f}</qCom>
          <vUnCom>{item.unitario:.2f}</vUnCom><vProd>{total:.2f}</vProd><cEANTrib>{item.ean}</cEANTrib>
          <uTrib>UN</uTrib><qTrib>{item.quantidade:.4f}</qTrib><vUnTrib>{item.unitario:.2f}</vUnTrib><indTot>1</indTot>
        </prod>
      </det>""")
    motivo = {"100": "Autorizado o uso da NF-e", "101": "Cancelamento de NF-e homologado"}.get(cstat, "")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe>
    <infNFe Id="NFe{chave}" versao="4.00">
      <ide>
        <cUF>{cuf}</cUF><cNF>{codigo}</cNF><natOp>Venda de mercadoria (EXEMPLO FICTÍCIO)</natOp><mod>55</mod>
        <serie>{serie}</serie><nNF>{numero}</nNF><dhEmi>{data}</dhEmi><tpNF>1</tpNF><tpEmis>1</tpEmis>
        <cDV>{dv}</cDV><tpAmb>2</tpAmb>
      </ide>
      <emit>
        <CNPJ>{cnpj}</CNPJ><xNome>{escape(nome)}</xNome>
        <enderEmit><xLgr>Rua Fictícia</xLgr><nro>100</nro><xMun>Cidade Exemplo</xMun><UF>{uf}</UF></enderEmit>
      </emit>
      <dest>
        <CNPJ>{DESTINATARIO[1]}</CNPJ><xNome>{escape(DESTINATARIO[0])}</xNome>
      </dest>{"".join(dets)}
      <total>
        <ICMSTot><vProd>{v_prod:.2f}</vProd><vNF>{v_prod:.2f}</vNF></ICMSTot>
      </total>
    </infNFe>
  </NFe>
  <protNFe versao="4.00">
    <infProt><tpAmb>2</tpAmb><chNFe>{chave}</chNFe><dhRecbto>{data}</dhRecbto><nProt>135{numero:012d}</nProt>
      <cStat>{cstat}</cStat><xMotivo>{motivo}</xMotivo></infProt>
  </protNFe>
</nfeProc>
"""


def gerar(pasta: Path = PASTA_EXEMPLOS) -> list[Path]:
    pasta.mkdir(parents=True, exist_ok=True)
    caneta = ItemExemplo("CAN-001", "Caneta esferográfica azul (cx 50)", ean13_com_dv("789000000001"), "96081000",
                         Decimal("10"), Decimal("42.90"))
    caderno = ItemExemplo("CAD-010", "Caderno universitário 10 matérias", ean13_com_dv("789000000002"), "48202000",
                          Decimal("24"), Decimal("18.75"))
    grampeador = ItemExemplo("GRP-200", "Grampeador de mesa", "SEM GTIN", "84729010", Decimal("3"), Decimal("39.90"))
    mochila = ItemExemplo("MOC-777", "Mochila escolar", ean13_com_dv("789000000003"), "42029200",
                          Decimal("5"), Decimal("129.00"))
    ean_errado = ItemExemplo("LAP-005", "Lápis preto nº 2 (cx 144)", "7890000000049", "96091000",
                             Decimal("2"), Decimal("55.00"))
    arquivos = {
        "nfe_000001_ok.xml": montar_xml(1, EMITENTE, [caneta, caderno, grampeador]),
        "nfe_000002_ok.xml": montar_xml(2, EMITENTE, [mochila, caneta], data="2026-10-20T14:05:00-03:00",
                                        codigo="55667788"),
        "nfe_000310_ok.xml": montar_xml(310, EMITENTE_2, [caderno, mochila, grampeador],
                                        data="2026-11-03T11:00:00-03:00", serie=2, codigo="99001122"),
        "nfe_000003_com_erros.xml": montar_xml(3, EMITENTE, [ean_errado, caneta], data="2026-10-28T08:15:00-03:00",
                                               codigo="13579246",
                                               quebrar={"dv": True, "diferenca_total": Decimal("10.00")}),
        "nfe_000004_cancelada.xml": montar_xml(4, EMITENTE, [caderno], data="2026-11-05T16:40:00-03:00",
                                               codigo="24681357", cstat="101"),
    }
    caminhos = []
    for nome, conteudo in arquivos.items():
        caminho = pasta / nome
        caminho.write_text(conteudo, encoding="utf-8")
        caminhos.append(caminho)
    return caminhos


if __name__ == "__main__":
    for caminho in gerar():
        print(f"Gerado: {caminho}")
