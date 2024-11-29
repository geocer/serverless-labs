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
