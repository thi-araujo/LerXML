"""Para ler um código de barras de um arquivo XML em Python usando um leitor de código de barras,
 Podemos usar a biblioteca xml.etree.ElementTree
para analisar o XML e a biblioteca keyboard para detectar a entrada do teclado do leitor.
Aqui está um exemplo de código que mostra como fazer isso"""

import xml.etree.ElementTree as ET
import os

def ler_codigo_de_barras(xml_file):
    tree = ET.parse(xml_file)
    root = tree.getroot()


# Encontre o elemento que contém o código de barras
    codigo_de_barras = root.find('CodigoDeBarras').text

# Validação do código de barras

    return codigo_de_barras

def validar_codigos_de_barras_em_pasta(pasta):
    arquivos_xml = [f for f in os.listdir(pasta) if f.endswith('.xml')]

    for arquivo_xml in arquivos_xml:
        caminho_arquivo = os.path.join(pasta, arquivo_xml)
        codigo_de_barras = ler_codigo_de_barras(caminho_arquivo)


