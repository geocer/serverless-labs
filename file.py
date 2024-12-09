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

def comparar_planilhas(arquivo1, coluna1, arquivo2, coluna2, status, sufixo):
    """
    Compara duas colunas de duas planilhas Excel, filtrando por status e ignorando case e sufixo.

    Args:
        arquivo1 (str): Nome do arquivo da primeira planilha.
        coluna1 (str): Nome da coluna a ser comparada na primeira planilha.
        arquivo2 (str): Nome do arquivo da segunda planilha.
        coluna2 (str): Nome da coluna a ser comparada na segunda planilha.
        status (str): Valor do status para filtrar.
        sufixo (str): Sufixo a ser removido das strings da segunda coluna.

    Returns:
        list: Lista de tuplas (valor da coluna 1, valor da coluna 2) para os itens encontrados.
    """

    # Carregar os dados das planilhas
    df1 = pd.read_excel(arquivo1)
    df2 = pd.read_excel(arquivo2)

    # Filtrar os dados da primeira planilha pelo status
    df1_filtrado = df1[df1['status'] == status]

    # Remover o sufixo da coluna 2 da segunda planilha e converter para minúsculas
    df2[coluna2] = df2[coluna2].str.replace(sufixo, '').str.lower()

    # Comparar as strings e retornar os resultados
    resultados = []
    for valor1 in df1_filtrado[coluna1]:
        for valor2 in df2[coluna2]:
            if valor1.lower() == valor2:
                resultados.append((valor1, valor2))

    return resultados

# Exemplo de uso
arquivo1 = 'planilha1.xlsx'
coluna1 = 'nome_equipamento'
arquivo2 = 'planilha2.xlsx'
coluna2 = 'nome_host'
status = 'Power On'
sufixo = '.dominio.com'

resultados = comparar_planilhas(arquivo1, coluna1, arquivo2, coluna2, status, sufixo)

# Imprimir os resultados
for resultado in resultados:
    print(resultado)



import pandas as pd

def comparar_planilhas(arquivo1, coluna1, arquivo2, coluna2, coluna_status, status, sufixo):
    """
    Compara duas colunas de duas planilhas, filtrando por status e ignorando sufixo e caixa.

    Args:
        arquivo1 (str): Nome do arquivo da primeira planilha.
        coluna1 (str): Nome da coluna a ser comparada na primeira planilha.
        arquivo2 (str): Nome do arquivo da segunda planilha.
        coluna2 (str): Nome da coluna a ser comparada na segunda planilha.
        coluna_status (str): Nome da coluna de status na primeira planilha.
        status (str): Valor do status para filtrar.
        sufixo (str): Sufixo a ser removido da segunda coluna.
    """

    # Carregar os dados das planilhas
    df1 = pd.read_excel(arquivo1)
    df2 = pd.read_excel(arquivo2)

    # Filtrar os dados da primeira planilha por status
    df1_filtrado = df1[df1[coluna_status] == status]

    # Remover o sufixo da segunda coluna e converter para minúsculas
    df2[coluna2] = df2[coluna2].str.replace(sufixo, '').str.lower()

    # Converter a coluna a ser comparada na primeira planilha para minúsculas
    df1_filtrado[coluna1] = df1_filtrado[coluna1].str.lower()

    # Encontrar os valores únicos da primeira planilha que não estão na segunda
    valores_unicos = df1_filtrado[~df1_filtrado[coluna1].isin(df2[coluna2])][coluna1]

    print(valores_unicos)

# Exemplo de uso
comparar_planilhas('planilha1.xlsx', 'Nome', 'planilha2.xlsx', 'Hostname', 'Status', 'Power On', '.dominio.com')
