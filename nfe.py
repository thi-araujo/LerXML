"""Leitura e validação de XML de Nota Fiscal Eletrônica (NF-e, modelo 55 / NFC-e, modelo 65).

Valida, sem precisar de internet:
- a chave de acesso (44 dígitos, dígito verificador e coerência com os dados da nota);
- CNPJ/CPF do emitente e do destinatário;
- os códigos de barras EAN/GTIN dos produtos;
- a soma dos itens contra o total da nota;
- a situação do protocolo de autorização (cStat 100 = autorizada).

Segurança: XML recebido de terceiros pode trazer ataques como "billion laughs"
ou entidades externas (XXE). Uma NF-e nunca tem DOCTYPE, então arquivos com
DOCTYPE/ENTITY são recusados antes da leitura, e há limite de tamanho.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

NS = {"nfe": "http://www.portalfiscal.inf.br/nfe"}
TAMANHO_MAXIMO = 5 * 1024 * 1024  # 5 MB: uma NF-e grande tem poucas centenas de KB

UFS = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO", "21": "MA", "22": "PI",
    "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL", "28": "SE", "29": "BA", "31": "MG", "32": "ES",
    "33": "RJ", "35": "SP", "41": "PR", "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}
SITUACOES = {"100": "Autorizada", "101": "Cancelada", "110": "Denegada", "135": "Cancelada", "150": "Autorizada"}


class ErroNFe(Exception):
    pass


# --------------------------------------------------------------------------
# Dígitos verificadores
# --------------------------------------------------------------------------

def so_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


def dv_chave(chave43: str) -> int:
    """Dígito verificador da chave de acesso (módulo 11, pesos 2 a 9 da direita para a esquerda)."""
    soma = sum(int(d) * (2 + i % 8) for i, d in enumerate(reversed(chave43)))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def validar_cnpj(cnpj: str) -> bool:
    cnpj = so_digitos(cnpj)
    if len(cnpj) != 14 or len(set(cnpj)) == 1:
        return False
    for tamanho in (12, 13):
        pesos = list(range(tamanho - 7, 1, -1)) + list(range(9, 1, -1))
        soma = sum(int(d) * p for d, p in zip(cnpj[:tamanho], pesos))
        digito = 0 if soma % 11 < 2 else 11 - soma % 11
        if int(cnpj[tamanho]) != digito:
            return False
    return True


def validar_cpf(cpf: str) -> bool:
    cpf = so_digitos(cpf)
    if len(cpf) != 11 or len(set(cpf)) == 1:
        return False
    for tamanho in (9, 10):
        soma = sum(int(d) * p for d, p in zip(cpf[:tamanho], range(tamanho + 1, 1, -1)))
        digito = (soma * 10) % 11 % 10
        if int(cpf[tamanho]) != digito:
            return False
    return True


def validar_gtin(codigo: str) -> bool:
    """EAN-8, UPC-A (12), EAN-13 e GTIN-14: o último dígito confere os demais."""
    codigo = (codigo or "").strip()
    if not codigo.isdigit() or len(codigo) not in (8, 12, 13, 14):
        return False
    corpo, digito = codigo[:-1], int(codigo[-1])
    soma = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(corpo)))
    return (10 - soma % 10) % 10 == digito


def formatar_cnpj_cpf(numero: str) -> str:
    n = so_digitos(numero)
    if len(n) == 14:
        return f"{n[:2]}.{n[2:5]}.{n[5:8]}/{n[8:12]}-{n[12:]}"
    if len(n) == 11:
        return f"{n[:3]}.{n[3:6]}.{n[6:9]}-{n[9:]}"
    return numero or "-"


def formatar_chave(chave: str) -> str:
    return " ".join(chave[i:i + 4] for i in range(0, len(chave), 4))


# --------------------------------------------------------------------------
# Chave de acesso
# --------------------------------------------------------------------------

@dataclass
class PartesChave:
    uf: str
    ano_mes: str
    documento: str  # CNPJ (ou CPF com zeros à esquerda)
    modelo: str
    serie: str
    numero: str
    tipo_emissao: str
    codigo: str
    dv: str


def analisar_chave(chave: str) -> PartesChave:
    c = so_digitos(chave)
    if len(c) != 44:
        raise ErroNFe(f"a chave precisa ter 44 dígitos (tem {len(c)})")
    return PartesChave(c[0:2], c[2:6], c[6:20], c[20:22], c[22:25], c[25:34], c[34], c[35:43], c[43])


def validar_chave(chave: str) -> list[str]:
    """Problemas encontrados na chave (lista vazia = chave válida)."""
    try:
        partes = analisar_chave(chave)
    except ErroNFe as erro:
        return [str(erro)]
    problemas = []
    c = so_digitos(chave)
    if dv_chave(c[:43]) != int(partes.dv):
        problemas.append(f"dígito verificador inválido (esperado {dv_chave(c[:43])}, veio {partes.dv})")
    if partes.uf not in UFS:
        problemas.append(f"código de UF inexistente: {partes.uf}")
    if not 1 <= int(partes.ano_mes[2:]) <= 12:
        problemas.append(f"mês inválido na chave: {partes.ano_mes[2:]}")
    if partes.modelo not in ("55", "65"):
        problemas.append(f"modelo {partes.modelo} não é NF-e (55) nem NFC-e (65)")
    return problemas


# --------------------------------------------------------------------------
# Leitura do XML
# --------------------------------------------------------------------------

@dataclass
class Item:
    numero: int
    codigo: str
    descricao: str
    ean: str
    ncm: str
    cfop: str
    unidade: str
    quantidade: Decimal
    valor_unitario: Decimal
    valor_total: Decimal

    @property
    def ean_valido(self) -> bool | None:
        """None quando o produto não tem código de barras ("SEM GTIN")."""
        if not self.ean or self.ean.upper() == "SEM GTIN":
            return None
        return validar_gtin(self.ean)


@dataclass
class NotaFiscal:
    arquivo: Path
    chave: str
    modelo: str
    serie: str
    numero: str
    emissao: datetime | None
    natureza: str
    emitente_nome: str
    emitente_doc: str
    emitente_uf: str
    destinatario_nome: str
    destinatario_doc: str
    valor_produtos: Decimal
    valor_total: Decimal
    situacao: str
    protocolo: str
    itens: list[Item] = field(default_factory=list)
    problemas: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    conferida: bool = False

    @property
    def valida(self) -> bool:
        return not self.problemas


def _texto(no: ET.Element | None, caminho: str) -> str:
    if no is None:
        return ""
    achado = no.find(caminho, NS)
    return (achado.text or "").strip() if achado is not None else ""


def _decimal(texto: str) -> Decimal:
    try:
        return Decimal(texto) if texto else Decimal("0")
    except InvalidOperation:
        return Decimal("0")


def _data(texto: str) -> datetime | None:
    if not texto:
        return None
    try:
        return datetime.fromisoformat(texto)
    except ValueError:
        try:
            return datetime.strptime(texto[:10], "%Y-%m-%d")
        except ValueError:
            return None


def ler_xml_seguro(caminho: Path) -> ET.Element:
    if caminho.stat().st_size > TAMANHO_MAXIMO:
        raise ErroNFe("arquivo grande demais para ser uma NF-e")
    conteudo = caminho.read_bytes()
    cabecalho = conteudo[:4096].upper()
    if b"<!DOCTYPE" in cabecalho or b"<!ENTITY" in conteudo.upper():
        raise ErroNFe("XML com DOCTYPE/ENTITY recusado por segurança (uma NF-e não usa isso)")
    try:
        return ET.fromstring(conteudo)
    except ET.ParseError as erro:
        raise ErroNFe(f"XML malformado: {erro}") from None


def ler_nfe(caminho: str | Path) -> NotaFiscal:
    caminho = Path(caminho)
    raiz = ler_xml_seguro(caminho)
    inf = raiz.find(".//nfe:infNFe", NS)
    if inf is None:
        raise ErroNFe("não é um XML de NF-e (tag infNFe não encontrada)")
    ide, emit, dest = inf.find("nfe:ide", NS), inf.find("nfe:emit", NS), inf.find("nfe:dest", NS)
    prot = raiz.find(".//nfe:protNFe/nfe:infProt", NS)

    chave = so_digitos(inf.get("Id", ""))
    situacao_codigo = _texto(prot, "nfe:cStat")
    nota = NotaFiscal(
        arquivo=caminho, chave=chave,
        modelo=_texto(ide, "nfe:mod"), serie=_texto(ide, "nfe:serie"), numero=_texto(ide, "nfe:nNF"),
        emissao=_data(_texto(ide, "nfe:dhEmi") or _texto(ide, "nfe:dEmi")), natureza=_texto(ide, "nfe:natOp"),
        emitente_nome=_texto(emit, "nfe:xNome"),
        emitente_doc=_texto(emit, "nfe:CNPJ") or _texto(emit, "nfe:CPF"),
        emitente_uf=_texto(emit, "nfe:enderEmit/nfe:UF"),
        destinatario_nome=_texto(dest, "nfe:xNome"),
        destinatario_doc=_texto(dest, "nfe:CNPJ") or _texto(dest, "nfe:CPF") or _texto(dest, "nfe:idEstrangeiro"),
        valor_produtos=_decimal(_texto(inf, "nfe:total/nfe:ICMSTot/nfe:vProd")),
        valor_total=_decimal(_texto(inf, "nfe:total/nfe:ICMSTot/nfe:vNF")),
        situacao=SITUACOES.get(situacao_codigo, f"Situação {situacao_codigo}" if situacao_codigo else "Sem protocolo"),
        protocolo=_texto(prot, "nfe:nProt"),
    )
    for det in inf.findall("nfe:det", NS):
        prod = det.find("nfe:prod", NS)
        nota.itens.append(Item(
            numero=int(det.get("nItem", len(nota.itens) + 1)), codigo=_texto(prod, "nfe:cProd"),
            descricao=_texto(prod, "nfe:xProd"), ean=_texto(prod, "nfe:cEAN"), ncm=_texto(prod, "nfe:NCM"),
            cfop=_texto(prod, "nfe:CFOP"), unidade=_texto(prod, "nfe:uCom"),
            quantidade=_decimal(_texto(prod, "nfe:qCom")), valor_unitario=_decimal(_texto(prod, "nfe:vUnCom")),
            valor_total=_decimal(_texto(prod, "nfe:vProd")),
        ))
    verificar(nota, _texto(ide, "nfe:cUF"), _texto(ide, "nfe:cDV"))
    return nota


def verificar(nota: NotaFiscal, cuf: str = "", cdv: str = "") -> None:
    """Preenche nota.problemas (erros) e nota.avisos (pontos de atenção)."""
    problemas, avisos = nota.problemas, nota.avisos
    problemas.extend(validar_chave(nota.chave))
    if len(nota.chave) == 44:
        partes = analisar_chave(nota.chave)
        comparacoes = [("número", partes.numero, nota.numero.zfill(9)), ("série", partes.serie, nota.serie.zfill(3)),
                       ("modelo", partes.modelo, nota.modelo),
                       ("CNPJ/CPF do emitente", partes.documento, so_digitos(nota.emitente_doc).zfill(14))]
        if cuf:
            comparacoes.append(("UF", partes.uf, cuf))
        if cdv:
            comparacoes.append(("dígito verificador (cDV)", partes.dv, cdv))
        if nota.emissao:
            comparacoes.append(("ano/mês de emissão", partes.ano_mes, nota.emissao.strftime("%y%m")))
        for nome, na_chave, na_nota in comparacoes:
            if na_chave != na_nota:
                problemas.append(f"{nome} da chave ({na_chave}) não confere com a nota ({na_nota})")

    documento = so_digitos(nota.emitente_doc)
    if documento and not (validar_cnpj(documento) if len(documento) == 14 else validar_cpf(documento)):
        problemas.append(f"CNPJ/CPF do emitente inválido: {formatar_cnpj_cpf(documento)}")
    destino = so_digitos(nota.destinatario_doc)
    if destino and len(destino) in (11, 14) and not (validar_cnpj(destino) if len(destino) == 14 else validar_cpf(destino)):
        problemas.append(f"CNPJ/CPF do destinatário inválido: {formatar_cnpj_cpf(destino)}")

    soma = sum((item.valor_total for item in nota.itens), Decimal("0"))
    if nota.itens and abs(soma - nota.valor_produtos) > Decimal("0.01"):
        problemas.append(f"soma dos itens (R$ {soma:.2f}) diferente do total de produtos (R$ {nota.valor_produtos:.2f})")
    for item in nota.itens:
        if item.ean_valido is False:
            problemas.append(f"item {item.numero}: código de barras EAN inválido ({item.ean})")
        esperado = (item.quantidade * item.valor_unitario).quantize(Decimal("0.01"))
        if abs(esperado - item.valor_total) > Decimal("0.01"):
            avisos.append(f"item {item.numero}: quantidade × valor unitário = R$ {esperado}, "
                          f"mas o total do item é R$ {item.valor_total}")
    if not nota.itens:
        avisos.append("a nota não tem itens")
    if nota.situacao == "Cancelada":
        avisos.append("nota cancelada: não tem validade fiscal")
    elif nota.situacao == "Sem protocolo":
        avisos.append("arquivo sem protocolo de autorização da SEFAZ (pode ser só o XML assinado, não autorizado)")
    elif nota.situacao != "Autorizada":
        avisos.append(f"situação: {nota.situacao}")


@dataclass
class ResultadoPasta:
    notas: list[NotaFiscal]
    erros: list[tuple[str, str]]  # (arquivo, motivo) dos XMLs que não puderam ser lidos


def ler_pasta(pasta: str | Path) -> ResultadoPasta:
    notas, erros = [], []
    for arquivo in sorted(Path(pasta).glob("*.xml")):
        try:
            notas.append(ler_nfe(arquivo))
        except (ErroNFe, OSError) as erro:
            erros.append((arquivo.name, str(erro)))
    return ResultadoPasta(notas, erros)


def localizar(notas: list[NotaFiscal], codigo: str) -> tuple[NotaFiscal, Item | None] | None:
    """Procura um código lido pelo leitor: chave de acesso (44 dígitos) ou EAN de um produto."""
    digitos = so_digitos(codigo)
    if len(digitos) == 44:
        return next(((n, None) for n in notas if n.chave == digitos), None)
    for nota in notas:
        for item in nota.itens:
            if item.ean and item.ean == codigo.strip():
                return nota, item
    return None
