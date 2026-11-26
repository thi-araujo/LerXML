import csv
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import exemplos_nfe as ex  # noqa: E402
import exportar as xp  # noqa: E402
import nfe  # noqa: E402

try:
    import reportlab  # noqa: F401
    TEM_REPORTLAB = True
except ImportError:
    TEM_REPORTLAB = False


class TestDigitos(unittest.TestCase):
    def test_chave_do_manual(self):
        # Exemplo do Manual de Orientação do Contribuinte da NF-e.
        self.assertEqual(nfe.dv_chave("5206043300991100250655012000000780026730161"), 5)
        self.assertEqual(nfe.validar_chave("52060433009911002506550120000007800267301615"), [])

    def test_chave_invalida(self):
        self.assertIn("dígito verificador", nfe.validar_chave("52060433009911002506550120000007800267301614")[0])
        self.assertIn("44 dígitos", nfe.validar_chave("123")[0])
        problemas = nfe.validar_chave("99" + "1313" + "0" * 37 + "0")
        self.assertTrue(any("UF" in p for p in problemas))
        self.assertTrue(any("mês" in p for p in problemas))

    def test_analisar_chave(self):
        partes = nfe.analisar_chave("5206 0433 0099 1100 2506 5501 2000 0007 8002 6730 1615")
        self.assertEqual((partes.uf, partes.ano_mes, partes.modelo, partes.serie, partes.numero),
                         ("52", "0604", "55", "012", "000000780"))
        self.assertEqual(partes.documento, "33009911002506")

    def test_cnpj_cpf(self):
        self.assertTrue(nfe.validar_cnpj("11.222.333/0001-81"))
        self.assertFalse(nfe.validar_cnpj("11.222.333/0001-82"))
        self.assertFalse(nfe.validar_cnpj("00000000000000"))
        self.assertTrue(nfe.validar_cpf("529.982.247-25"))
        self.assertFalse(nfe.validar_cpf("529.982.247-24"))
        self.assertFalse(nfe.validar_cpf("111.111.111-11"))

    def test_gtin(self):
        self.assertTrue(nfe.validar_gtin("7891000315507"))   # EAN-13
        self.assertTrue(nfe.validar_gtin("96385074"))        # EAN-8
        self.assertTrue(nfe.validar_gtin("036000291452"))    # UPC-A
        self.assertFalse(nfe.validar_gtin("7891000315508"))
        self.assertFalse(nfe.validar_gtin("SEM GTIN"))
        self.assertFalse(nfe.validar_gtin("12345"))

    def test_formatacao(self):
        self.assertEqual(nfe.formatar_cnpj_cpf("11222333000181"), "11.222.333/0001-81")
        self.assertEqual(nfe.formatar_cnpj_cpf("52998224725"), "529.982.247-25")
        self.assertEqual(nfe.formatar_chave("1" * 8), "1111 1111")


class TestLeitura(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.TemporaryDirectory()
        ex.gerar(Path(cls.pasta.name))
        cls.resultado = nfe.ler_pasta(cls.pasta.name)
        cls.notas = {n.numero: n for n in cls.resultado.notas}

    @classmethod
    def tearDownClass(cls):
        cls.pasta.cleanup()

    def test_le_todas(self):
        self.assertEqual(self.resultado.erros, [])
        self.assertEqual(sorted(self.notas), ["1", "2", "3", "310", "4"])

    def test_nota_valida(self):
        nota = self.notas["1"]
        self.assertTrue(nota.valida, nota.problemas)
        self.assertEqual(nota.avisos, [])
        self.assertEqual(nota.situacao, "Autorizada")
        self.assertEqual(nota.valor_total, Decimal("998.70"))
        self.assertEqual(len(nota.itens), 3)
        self.assertEqual(nota.emitente_uf, "SP")
        self.assertEqual(nota.emissao.strftime("%d/%m/%Y"), "15/10/2026")
        self.assertIsNone(nota.itens[2].ean_valido)  # SEM GTIN
        self.assertTrue(nota.itens[0].ean_valido)

    def test_nota_com_erros(self):
        problemas = " | ".join(self.notas["3"].problemas)
        self.assertIn("dígito verificador inválido", problemas)
        self.assertIn("soma dos itens", problemas)
        self.assertIn("EAN inválido", problemas)

    def test_cancelada(self):
        nota = self.notas["4"]
        self.assertEqual(nota.situacao, "Cancelada")
        self.assertTrue(nota.valida)
        self.assertIn("cancelada", nota.avisos[0])

    def test_localizar(self):
        nota = self.notas["2"]
        self.assertEqual(nfe.localizar(self.resultado.notas, nfe.formatar_chave(nota.chave)), (nota, None))
        achado = nfe.localizar(self.resultado.notas, nota.itens[0].ean)
        self.assertEqual(achado[1].descricao, "Mochila escolar")
        self.assertIsNone(nfe.localizar(self.resultado.notas, "0" * 44))
        self.assertIsNone(nfe.localizar(self.resultado.notas, "7891000315507"))


class TestCoerencia(unittest.TestCase):
    def ler(self, conteudo: str) -> nfe.NotaFiscal:
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "nota.xml"
            caminho.write_text(conteudo, encoding="utf-8")
            return nfe.ler_nfe(caminho)

    def test_numero_diferente_da_chave(self):
        xml = ex.montar_xml(7, ex.EMITENTE, [ex.ItemExemplo("A", "Item", "SEM GTIN", "00000000", Decimal(1),
                                                            Decimal(10))])
        xml = xml.replace("<nNF>7</nNF>", "<nNF>8</nNF>")
        self.assertTrue(any("número da chave" in p for p in self.ler(xml).problemas))

    def test_sem_protocolo(self):
        xml = ex.montar_xml(9, ex.EMITENTE, [ex.ItemExemplo("A", "Item", "SEM GTIN", "0", Decimal(2), Decimal(5))])
        inicio, fim = xml.index("<protNFe"), xml.index("</protNFe>") + len("</protNFe>")
        nota = self.ler(xml[:inicio] + xml[fim:])
        self.assertEqual(nota.situacao, "Sem protocolo")
        self.assertIn("protocolo", nota.avisos[0])

    def test_recusa_xml_perigoso(self):
        bomba = ('<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]>'
                 '<nfeProc>&b;</nfeProc>')
        with self.assertRaises(nfe.ErroNFe) as contexto:
            self.ler(bomba)
        self.assertIn("segurança", str(contexto.exception))

    def test_nao_e_nfe(self):
        with self.assertRaises(nfe.ErroNFe):
            self.ler("<pedido><numero>1</numero></pedido>")
        with self.assertRaises(nfe.ErroNFe):
            self.ler("<nfeProc><NFe>")


class TestExportar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.TemporaryDirectory()
        ex.gerar(Path(cls.pasta.name) / "xml")
        cls.notas = nfe.ler_pasta(Path(cls.pasta.name) / "xml").notas

    @classmethod
    def tearDownClass(cls):
        cls.pasta.cleanup()

    def test_csv(self):
        destino = Path(self.pasta.name) / "notas.csv"
        self.notas[0].conferida = True
        xp.exportar_csv(self.notas, destino)
        with open(destino, encoding="utf-8-sig") as arquivo:
            linhas = list(csv.DictReader(arquivo, delimiter=";"))
        self.assertEqual(len(linhas), sum(len(n.itens) for n in self.notas))
        self.assertEqual(linhas[0]["Conferida"], "Sim")
        self.assertEqual(linhas[0]["CNPJ emitente"], nfe.formatar_cnpj_cpf(self.notas[0].emitente_doc))

    def test_quantidade(self):
        self.assertEqual(xp.quantidade(Decimal("10.0000")), "10")
        self.assertEqual(xp.quantidade(Decimal("2.5000")), "2,5")

    def test_reais(self):
        self.assertEqual(xp.reais(Decimal("1234.5")), "R$ 1.234,50")

    @unittest.skipUnless(TEM_REPORTLAB, "reportlab não instalado")
    def test_pdfs(self):
        nota_pdf = Path(self.pasta.name) / "nota.pdf"
        relatorio = Path(self.pasta.name) / "relatorio.pdf"
        xp.pdf_nota(next(n for n in self.notas if n.problemas), nota_pdf)
        xp.pdf_relatorio(self.notas, relatorio)
        for arquivo in (nota_pdf, relatorio):
            self.assertTrue(arquivo.read_bytes().startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
