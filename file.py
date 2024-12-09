import pandas as pd
import difflib
import pygal

def compare_and_plot(file1, column1, file2, column2, similarity_threshold=0.5):
    """
    Compara duas colunas de duas planilhas Excel e gera um gráfico com os valores únicos da primeira coluna que não possuem correspondência na segunda com pelo menos a similaridade especificada.

    Args:
        file1: Nome do arquivo da primeira planilha.
        column1: Nome da coluna a ser comparada na primeira planilha.
        file2: Nome do arquivo da segunda planilha.
        column2: Nome da coluna a ser comparada na segunda planilha.
        similarity_threshold: Limiar de similaridade (valor entre 0 e 1).

    Returns:
        Nenhum. Gera um gráfico Pygal.
    """

    # Carregar os dados das planilhas
    df1 = pd.read_excel(file1, usecols=[column1])
    df2 = pd.read_excel(file2, usecols=[column2])

    # Converter os dados para listas
    list1 = df1[column1].tolist()
    list2 = df2[column2].tolist()

    # Encontrar os valores únicos da primeira lista que não possuem correspondência na segunda
    unique_values = []
    for value1 in list1:
        found = False
        for value2 in list2:
            if difflib.SequenceMatcher(None, value1, value2).ratio() >= similarity_threshold:
                found = True
                break
        if not found:
            unique_values.append(value1)

    # Criar um gráfico de barras com os valores únicos
    chart = pygal.Bar(title='Valores Únicos')
    chart.add('Valores Únicos', unique_values)
    chart.render_to_file('grafico_diferencas.svg')

# Exemplo de uso
compare_and_plot('planilha1.xlsx', 'ColunaA', 'planilha2.xlsx', 'ColunaB', 0.7)



import pandas as pd

def comparar_strings(arquivo1, coluna1, arquivo2, coluna2, sufixo):
    """
    Compara as strings de duas colunas, ignorando o sufixo e a case.

    Args:
        arquivo1 (str): Nome do arquivo da primeira planilha.
        coluna1 (str): Nome da coluna a ser comparada na primeira planilha.
        arquivo2 (str): Nome do arquivo da segunda planilha.
        coluna2 (str): Nome da coluna a ser comparada na segunda planilha.
        sufixo (str): Sufixo a ser removido da segunda coluna.

    Returns:
        list: Lista de strings da primeira coluna que não foram encontradas na segunda.
    """

    # Carregar os dados das planilhas
    df1 = pd.read_excel(arquivo1)
    df2 = pd.read_excel(arquivo2)

    # Remover o sufixo da segunda coluna e converter para minúsculas
    df2[coluna2] = df2[coluna2].str.replace(sufixo, '').str.lower()

    # Converter a primeira coluna para minúsculas
    df1[coluna1] = df1[coluna1].str.lower()

    # Criar um conjunto para verificar a existência de cada string na segunda coluna de forma eficiente
    conjunto_strings2 = set(df2[coluna2])

    # Comparar as strings e retornar as que não foram encontradas
    nao_encontradas = []
    for string in df1[coluna1]:
        if string not in conjunto_strings2:
            nao_encontradas.append(string)

    return nao_encontradas

# Exemplo de uso
arquivo1 = 'planilha1.xlsx'
coluna1 = 'ColunaA'
arquivo2 = 'planilha2.xlsx'
coluna2 = 'ColunaB'
sufixo = '.dominio.com'

resultados = comparar_strings(arquivo1, coluna1, arquivo2, coluna2, sufixo)
print(resultados)
