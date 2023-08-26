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

# Faça a validação do código de barras aqui

print(f'Arquivo: {arquivo_xml}, Código de Barras: {codigo_de_barras}, Validação: {validacao}')

# Exemplo de uso
pasta_xml = '/caminho/para/a/pasta/xml' # aqui vc informa o caminho do arquivo
validar_codigos_de_barras_em_pasta(pasta_xml)



"""Nesse exemplo, a função ler_codigo_de_barras recebe o caminho de um arquivo XML e retorna o código de barras contido nele. Você deve implementar a validação do código de barras nessa função.

A função validar_codigos_de_barras_em_pasta recebe o caminho para uma pasta contendo arquivos XML e itera sobre eles, chamando a função ler_codigo_de_barras para cada arquivo e realizando a validação desejada.

Certifique-se de substituir /caminho/para/a/pasta/xml pelo caminho real da pasta que contém seus arquivos XML.

Lembre-se de adaptar esse exemplo de acordo com a estrutura do seu XML e as regras específicas de validação do código de barras.""""

import xml.etree.ElementTree as ET
import keyboard

def read_barcode():
    barcode = ""
    keyboard.on_release_key("enter", lambda _: keyboard.write("\n"))
    keyboard.wait("esc")
    return barcode

def read_xml_barcode(xml_file):
    tree = ET.parse(xml_file)
