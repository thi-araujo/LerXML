"""Leitor de NF-e: abre XMLs de notas fiscais, valida e confere com leitor de código de barras.

    python leitor_nfe.py

O leitor de código de barras funciona como um teclado: clique no campo de
conferência e leia o código de barras da DANFE (chave de acesso) ou de um
produto (EAN). A geração de PDF requer reportlab (pip install -r requirements.txt).
"""

from __future__ import annotations

import platform
import tempfile
import tkinter as tk
from decimal import Decimal
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import exemplos_nfe
import exportar as xp
import nfe

CORES = {
    "fundo": "#0f172a",
    "painel": "#1e293b",
    "borda": "#334155",
    "texto": "#e2e8f0",
    "texto_suave": "#94a3b8",
    "destaque": "#38bdf8",
    "verde": "#22c55e",
    "vermelho": "#ef4444",
    "ambar": "#f59e0b",
}
ROTULO_STATUS = {"OK": "✔ OK", "Atenção": "⚠ Atenção", "Com erros": "✖ Erros"}
TAG_STATUS = {"OK": "", "Atenção": "atencao", "Com erros": "erro"}

WINDOWS = platform.system() == "Windows"
FONTE = "Segoe UI" if WINDOWS else "Helvetica"
FONTE_MONO = "Consolas" if WINDOWS else "DejaVu Sans Mono"


def configurar_estilo(raiz: tk.Tk) -> None:
    estilo = ttk.Style(raiz)
    estilo.theme_use("clam")
    sem_borda = dict(bordercolor=CORES["painel"], lightcolor=CORES["painel"], darkcolor=CORES["painel"])
    estilo.configure(".", background=CORES["fundo"], foreground=CORES["texto"], font=(FONTE, 10))
    estilo.configure("Painel.TFrame", background=CORES["painel"])
    estilo.configure("Suave.TLabel", foreground=CORES["texto_suave"])
    estilo.configure("TButton", background=CORES["borda"], foreground=CORES["texto"], borderwidth=0,
                     padding=(12, 6), font=(FONTE, 10, "bold"))
    estilo.map("TButton", background=[("disabled", CORES["painel"]), ("active", "#475569")],
               foreground=[("disabled", CORES["texto_suave"])])
    estilo.configure("Destaque.TButton", background=CORES["destaque"], foreground=CORES["fundo"])
    estilo.map("Destaque.TButton", background=[("disabled", CORES["painel"]), ("active", "#0ea5e9")])
    estilo.configure("TEntry", fieldbackground=CORES["fundo"], foreground=CORES["texto"], insertcolor=CORES["texto"],
                     bordercolor=CORES["destaque"], lightcolor=CORES["fundo"], darkcolor=CORES["fundo"])
    estilo.configure("Treeview", background=CORES["painel"], fieldbackground=CORES["painel"],
                     foreground=CORES["texto"], borderwidth=0, rowheight=26, **sem_borda)
    estilo.configure("Treeview.Heading", background=CORES["borda"], foreground=CORES["texto_suave"],
                     borderwidth=0, font=(FONTE, 9, "bold"))
    estilo.map("Treeview.Heading", background=[("active", CORES["borda"])])
    estilo.map("Treeview", background=[("selected", CORES["borda"])])
    estilo.configure("Vertical.TScrollbar", background=CORES["borda"], troughcolor=CORES["painel"], borderwidth=0,
                     arrowcolor=CORES["texto_suave"], **sem_borda)
    estilo.map("Vertical.TScrollbar", background=[("disabled", CORES["painel"])],
               arrowcolor=[("disabled", CORES["painel"])])
    estilo.configure("Sash", sashthickness=8, background=CORES["fundo"])


def tabela(pai, colunas, altura) -> ttk.Treeview:
    quadro = ttk.Frame(pai)
    quadro.pack(fill="both", expand=True)
    arvore = ttk.Treeview(quadro, columns=[c[0] for c in colunas], show="headings", height=altura,
                          selectmode="browse")
    for chave, titulo, largura, ancora in colunas:
        arvore.heading(chave, text=titulo, anchor=ancora)
        arvore.column(chave, width=largura, anchor=ancora, stretch=chave in ("emitente", "descricao"))
    for tag, cor in (("ok", CORES["verde"]), ("atencao", CORES["ambar"]), ("erro", CORES["vermelho"])):
        arvore.tag_configure(tag, foreground=cor)
    barra = ttk.Scrollbar(quadro, orient="vertical", command=arvore.yview)
    arvore.configure(yscrollcommand=barra.set)
    arvore.pack(side="left", fill="both", expand=True)
    barra.pack(side="right", fill="y")
    return arvore


class Aplicativo(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Leitor de NF-e")
        self.geometry("1180x760")
        self.minsize(1040, 680)
        self.configure(bg=CORES["fundo"])
        configurar_estilo(self)
        self.notas: list[nfe.NotaFiscal] = []
        self._montar()

    # ------------------------------------------------------------------ tela

    def _montar(self) -> None:
        topo = ttk.Frame(self, padding=(16, 14, 16, 6))
        topo.pack(fill="x")
        tk.Label(topo, text="🧾  Leitor de NF-e", font=(FONTE, 15, "bold"), bg=CORES["fundo"],
                 fg=CORES["destaque"]).pack(side="left")
        ttk.Button(topo, text="Usar exemplos", command=self.usar_exemplos).pack(side="right")
        ttk.Button(topo, text="Abrir arquivos...", command=self.abrir_arquivos).pack(side="right", padx=8)
        ttk.Button(topo, text="Abrir pasta...", style="Destaque.TButton", command=self.abrir_pasta).pack(side="right")

        self.lbl_resumo = ttk.Label(self, text="Abra a pasta com os XMLs das notas fiscais.", style="Suave.TLabel",
                                    padding=(16, 0))
        self.lbl_resumo.pack(fill="x")

        conferencia = tk.Frame(self, bg=CORES["painel"], padx=16, pady=12)
        conferencia.pack(fill="x", padx=16, pady=10)
        tk.Label(conferencia, text="Conferência", font=(FONTE, 11, "bold"), bg=CORES["painel"],
                 fg=CORES["destaque"]).pack(side="left")
        self.var_codigo = tk.StringVar()
        self.entrada_codigo = ttk.Entry(conferencia, textvariable=self.var_codigo, font=(FONTE_MONO, 13), width=50)
        self.entrada_codigo.pack(side="left", padx=12, ipady=3)
        self.entrada_codigo.bind("<Return>", lambda _e: self.conferir())
        self.entrada_codigo.bind("<KP_Enter>", lambda _e: self.conferir())
        self.lbl_conferencia = tk.Label(conferencia, text="Leia o código de barras da DANFE (chave) ou de um produto (EAN)",
                                        font=(FONTE, 10), bg=CORES["painel"], fg=CORES["texto_suave"], anchor="w")
        self.lbl_conferencia.pack(side="left", fill="x", expand=True)

        rodape = ttk.Frame(self, padding=(16, 6, 16, 12))
        rodape.pack(side="bottom", fill="x")
        self.lbl_status = ttk.Label(rodape, text="", style="Suave.TLabel")
        self.lbl_status.pack(side="left")
        self.botoes_exportar = [
            ttk.Button(rodape, text="Relatório PDF", command=self.relatorio_pdf),
            ttk.Button(rodape, text="PDF da nota", command=self.nota_pdf),
            ttk.Button(rodape, text="Exportar planilha (CSV)", command=self.exportar_csv),
        ]
        for botao in self.botoes_exportar:
            botao.pack(side="right", padx=(8, 0))
            botao.state(["disabled"])

        divisor = ttk.PanedWindow(self, orient="vertical")
        divisor.pack(fill="both", expand=True, padx=16)
        parte_notas = ttk.Frame(divisor)
        self.tbl_notas = tabela(parte_notas, [
            ("status", "Status", 100, "w"), ("numero", "Nº", 70, "e"), ("emissao", "Emissão", 90, "center"),
            ("emitente", "Emitente", 300, "w"), ("situacao", "Situação", 100, "w"), ("valor", "Valor", 120, "e"),
            ("conferida", "Conferida", 80, "center")], altura=7)
        self.tbl_notas.bind("<<TreeviewSelect>>", lambda _e: self._mostrar_detalhes())
        divisor.add(parte_notas, weight=1)

        detalhes = tk.Frame(divisor, bg=CORES["painel"], padx=14, pady=10)
        self.lbl_cabecalho = tk.Label(detalhes, text="", font=(FONTE, 12, "bold"), bg=CORES["painel"],
                                      fg=CORES["texto"], anchor="w", justify="left")
        self.lbl_cabecalho.pack(fill="x")
        self.lbl_info = tk.Label(detalhes, text="", font=(FONTE_MONO, 9), bg=CORES["painel"], fg=CORES["texto_suave"],
                                 anchor="w", justify="left")
        self.lbl_info.pack(fill="x", pady=(2, 8))
        meio = tk.Frame(detalhes, bg=CORES["painel"])
        meio.pack(fill="both", expand=True)
        quadro_itens = tk.Frame(meio, bg=CORES["painel"])
        quadro_itens.pack(side="left", fill="both", expand=True)
        self.tbl_itens = tabela(quadro_itens, [
            ("n", "#", 36, "center"), ("descricao", "Descrição", 260, "w"), ("ean", "EAN", 150, "w"),
            ("qtd", "Qtd", 60, "e"), ("unitario", "Unitário", 100, "e"), ("total", "Total", 100, "e")], altura=6)
        self.txt_validacao = tk.Text(meio, width=46, bg=CORES["fundo"], fg=CORES["texto"], relief="flat",
                                     font=(FONTE, 9), wrap="word", padx=10, pady=8, highlightthickness=0,
                                     state="disabled")
        for nome in ("verde", "vermelho", "ambar", "texto_suave"):
            self.txt_validacao.tag_configure(nome, foreground=CORES[nome])
        self.txt_validacao.tag_configure("titulo", font=(FONTE, 10, "bold"), foreground=CORES["destaque"])
        self.txt_validacao.pack(side="left", fill="y", padx=(12, 0))
        divisor.add(detalhes, weight=1)

    def status(self, texto: str, cor: str = "texto_suave") -> None:
        self.lbl_status.configure(text=texto, foreground=CORES[cor])

    # ------------------------------------------------------------------ carregar

    def abrir_pasta(self) -> None:
        pasta = filedialog.askdirectory(parent=self, title="Pasta com os XMLs das notas")
        if pasta:
            self.carregar(nfe.ler_pasta(pasta), Path(pasta).name)

    def abrir_arquivos(self) -> None:
        caminhos = filedialog.askopenfilenames(parent=self, title="XMLs de NF-e", filetypes=[("XML", "*.xml")])
        if not caminhos:
            return
        notas, erros = [], []
        for caminho in caminhos:
            try:
                notas.append(nfe.ler_nfe(caminho))
            except (nfe.ErroNFe, OSError) as erro:
                erros.append((Path(caminho).name, str(erro)))
        self.carregar(nfe.ResultadoPasta(notas, erros), f"{len(caminhos)} arquivo(s)")

    def usar_exemplos(self) -> None:
        pasta = Path(tempfile.mkdtemp(prefix="nfe_exemplos_"))
        exemplos_nfe.gerar(pasta)
        self.carregar(nfe.ler_pasta(pasta), "exemplos fictícios")

    def carregar(self, resultado: nfe.ResultadoPasta, origem: str) -> None:
        self.notas = sorted(resultado.notas, key=lambda n: (n.emissao is None, n.emissao, n.numero))
        self.tbl_notas.delete(*self.tbl_notas.get_children())
        for i, nota in enumerate(self.notas):
            self.tbl_notas.insert("", "end", iid=str(i), values=self._linha(nota),
                                  tags=(TAG_STATUS[xp.status(nota)],))
        autorizadas = [n for n in self.notas if n.situacao == "Autorizada"]
        total = sum((n.valor_total for n in autorizadas), Decimal("0"))
        com_erros = sum(1 for n in self.notas if n.problemas)
        self.lbl_resumo.configure(text=f"{origem}: {len(self.notas)} nota(s) · {com_erros} com erros · "
                                       f"{len(autorizadas)} autorizada(s) somando {xp.reais(total)}")
        for botao in self.botoes_exportar:
            botao.state(["!disabled"] if self.notas else ["disabled"])
        if resultado.erros:
            lista = "\n".join(f"• {nome}: {motivo}" for nome, motivo in resultado.erros[:15])
            messagebox.showwarning("Arquivos ignorados", f"{len(resultado.erros)} arquivo(s) não puderam ser lidos:"
                                                         f"\n\n{lista}", parent=self)
        if self.notas:
            self.tbl_notas.selection_set("0")
        self.status(f"{len(self.notas)} nota(s) carregada(s).", "verde" if self.notas else "ambar")
        self.entrada_codigo.focus_set()

    def _linha(self, nota: nfe.NotaFiscal) -> tuple:
        return (ROTULO_STATUS[xp.status(nota)], nota.numero,
                nota.emissao.strftime("%d/%m/%Y") if nota.emissao else "-", nota.emitente_nome, nota.situacao,
                xp.reais(nota.valor_total), "✔" if nota.conferida else "")

    # ------------------------------------------------------------------ detalhes

    def _nota_selecionada(self) -> nfe.NotaFiscal | None:
        selecao = self.tbl_notas.selection()
        return self.notas[int(selecao[0])] if selecao else None

    def _mostrar_detalhes(self, item_destacado: nfe.Item | None = None) -> None:
        nota = self._nota_selecionada()
        if nota is None:
            return
        emissao = nota.emissao.strftime("%d/%m/%Y %H:%M") if nota.emissao else "-"
        self.lbl_cabecalho.configure(text=f"NF-e nº {nota.numero} · série {nota.serie} · {emissao} · {nota.situacao}")
        self.lbl_info.configure(text=(
            f"Chave        {nfe.formatar_chave(nota.chave)}\n"
            f"Emitente     {nota.emitente_nome}  ({nfe.formatar_cnpj_cpf(nota.emitente_doc)}, {nota.emitente_uf})\n"
            f"Destinatário {nota.destinatario_nome or '-'}  ({nfe.formatar_cnpj_cpf(nota.destinatario_doc)})\n"
            f"Arquivo      {nota.arquivo.name}"))
        self.tbl_itens.delete(*self.tbl_itens.get_children())
        for item in nota.itens:
            marca = {True: "✔", False: "✖", None: "—"}[item.ean_valido]
            tag = {True: (), False: ("erro",), None: ()}[item.ean_valido]
            self.tbl_itens.insert("", "end", iid=str(item.numero), tags=tag, values=(
                item.numero, item.descricao, f"{marca} {item.ean}", xp.quantidade(item.quantidade),
                xp.reais(item.valor_unitario), xp.reais(item.valor_total)))
        if item_destacado is not None:
            self.tbl_itens.selection_set(str(item_destacado.numero))
            self.tbl_itens.see(str(item_destacado.numero))

        caixa = self.txt_validacao
        caixa.configure(state="normal")
        caixa.delete("1.0", "end")
        caixa.insert("end", "Validações\n", "titulo")
        if not nota.problemas and not nota.avisos:
            caixa.insert("end", "✔ Chave de acesso, CNPJ, códigos de barras e totais conferem.\n", "verde")
        for problema in nota.problemas:
            caixa.insert("end", f"✖ {problema}\n", "vermelho")
        for aviso in nota.avisos:
            caixa.insert("end", f"⚠ {aviso}\n", "ambar")
        caixa.insert("end", f"\nTotal da nota: {xp.reais(nota.valor_total)}\n", "texto_suave")
        if nota.conferida:
            caixa.insert("end", "✔ Conferida pelo leitor de código de barras\n", "verde")
        caixa.configure(state="disabled")

    # ------------------------------------------------------------------ conferência

    def conferir(self) -> None:
        codigo = self.var_codigo.get().strip()
        self.var_codigo.set("")
        if not codigo:
            return
        if not self.notas:
            self._resultado_conferencia("Abra as notas antes de conferir.", "ambar")
            return
        achado = nfe.localizar(self.notas, codigo)
        if achado is None:
            digitos = nfe.so_digitos(codigo)
            motivo = ""
            if len(digitos) == 44 and nfe.validar_chave(digitos):
                motivo = f" (chave inválida: {nfe.validar_chave(digitos)[0]})"
            elif len(digitos) in (8, 12, 13, 14) and not nfe.validar_gtin(digitos):
                motivo = " (EAN inválido: leia de novo)"
            curto = codigo if len(codigo) <= 16 else f"{codigo[:6]}…{codigo[-6:]}"
            self._resultado_conferencia(f"✖ {curto} não está nas notas abertas{motivo}", "vermelho")
            self.bell()
            return
        nota, item = achado
        indice = self.notas.index(nota)
        self.tbl_notas.selection_set(str(indice))
        self.tbl_notas.see(str(indice))
        if item is None:
            ja = nota.conferida
            nota.conferida = True
            self.tbl_notas.item(str(indice), values=self._linha(nota))
            texto = f"NF-e {nota.numero} já estava conferida" if ja else f"✔ NF-e {nota.numero} conferida"
            self._resultado_conferencia(f"{texto} · {nota.emitente_nome} · {xp.reais(nota.valor_total)}",
                                        "ambar" if ja else "verde")
        else:
            self._resultado_conferencia(f"✔ Produto na NF-e {nota.numero}: {item.descricao} "
                                        f"({xp.quantidade(item.quantidade)} {item.unidade})", "verde")
        self._mostrar_detalhes(item)
        conferidas = sum(1 for n in self.notas if n.conferida)
        self.status(f"{conferidas} de {len(self.notas)} nota(s) conferida(s).")

    def _resultado_conferencia(self, texto: str, cor: str) -> None:
        self.lbl_conferencia.configure(text=texto, fg=CORES[cor])
        self.entrada_codigo.focus_set()

    # ------------------------------------------------------------------ exportação

    def exportar_csv(self) -> None:
        destino = filedialog.asksaveasfilename(parent=self, title="Salvar planilha", defaultextension=".csv",
                                               initialfile="notas_fiscais.csv", filetypes=[("CSV", "*.csv")])
        if destino:
            xp.exportar_csv(self.notas, destino)
            self.status(f"Planilha salva em {destino}", "verde")

    def _pdf(self, gerar, nome_sugerido: str) -> None:
        destino = filedialog.asksaveasfilename(parent=self, title="Salvar PDF", defaultextension=".pdf",
                                               initialfile=nome_sugerido, filetypes=[("PDF", "*.pdf")])
        if not destino:
            return
        try:
            gerar(destino)
        except ImportError:
            messagebox.showerror("Falta o reportlab", "Para gerar PDF, instale:\n\npip install -r requirements.txt",
                                 parent=self)
            return
        self.status(f"PDF salvo em {destino}", "verde")

    def nota_pdf(self) -> None:
        nota = self._nota_selecionada()
        if nota:
            self._pdf(lambda destino: xp.pdf_nota(nota, destino), f"nfe_{nota.numero}.pdf")

    def relatorio_pdf(self) -> None:
        self._pdf(lambda destino: xp.pdf_relatorio(self.notas, destino), "relatorio_nfe.pdf")


def main() -> None:
    Aplicativo().mainloop()


if __name__ == "__main__":
    main()
