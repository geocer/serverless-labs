import pandas as pd
import matplotlib.pyplot as plt

def analisar_servidores(arquivo1, coluna_hostname, coluna_status, coluna_modelo, coluna_tipo, status, modelo, tipo, arquivo2, coluna_hostname_aws):
    """
    Analisa os dados de duas planilhas e identifica os servidores que ainda não foram descobertos.

    Args:
        arquivo1 (str): Nome do arquivo da primeira planilha.
        coluna_hostname (str): Nome da coluna de hostname na primeira planilha.
        coluna_status (str): Nome da coluna de status na primeira planilha.
        coluna_modelo (str): Nome da coluna de modelo na primeira planilha.
        coluna_tipo (str): Nome da coluna de tipo na primeira planilha.
        status (str): Valor do status para filtrar.
        modelo (str): Valor do modelo para filtrar.
        tipo (str): Valor do tipo para filtrar.
        arquivo2 (str): Nome do arquivo da segunda planilha.
        coluna_hostname_aws (str): Nome da coluna de hostname na segunda planilha.
    """

    # Carregar os dados das planilhas
    df1 = pd.read_excel(arquivo1)
    df2 = pd.read_excel(arquivo2)

    # Filtrar os dados da primeira planilha
    df1_filtrado = df1[(df1[coluna_status] == status) &
                     (df1[coluna_modelo] == modelo) &
                     (df1[coluna_tipo] == tipo)]

    # Encontrar os servidores que não foram descobertos
    servidores_nao_descobertos = df1_filtrado[~df1_filtrado[coluna_hostname].isin(df2[coluna_hostname_aws])][coluna_hostname]

    # Calcular o número de servidores descobertos e não descobertos
    total_servidores = len(df1_filtrado)
    descobertos = len(df2)
    nao_descobertos = len(servidores_nao_descobertos)

    # Criar um gráfico de pizza
    labels = ['Descobertos', 'Não Descobertos']
    sizes = [descobertos, nao_descobertos]
    plt.pie(sizes, labels=labels, autopct='%1.1f%%')
    plt.title('Servidores Descobertos vs. Não Descobertos')
    plt.show()

    # Imprimir os servidores não descobertos
    print("Servidores ainda não descobertos:")
    print(servidores_nao_descobertos)

# Exemplo de uso
analisar_servidores('inventario.xlsx', 'Hostname', 'Status', 'Modelo', 'Type', 'Power On', 'Hyper-V', 'Virtual', 'descobertos_aws.xlsx', 'Human Name')
