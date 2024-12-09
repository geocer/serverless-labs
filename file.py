import pandas as pd
import matplotlib.pyplot as plt

def comparar_servidores(arquivo1, coluna1, arquivo2, coluna2, status="Power On"):
    """
    Compara duas planilhas para identificar servidores não descobertos.

    Args:
        arquivo1: Nome do arquivo da planilha com o inventário completo.
        coluna1: Nome da coluna com os hostnames na primeira planilha.
        arquivo2: Nome do arquivo da planilha com os servidores descobertos.
        coluna2: Nome da coluna com os hostnames na segunda planilha.
        status: Status dos servidores a serem considerados.

    Returns:
        Um DataFrame com a contagem de servidores descobertos e não descobertos.
    """

    # Carregar os dados das planilhas
    df1 = pd.read_excel(arquivo1)
    df2 = pd.read_excel(arquivo2)

    # Filtrar os servidores com status "Power On"
    df1 = df1[df1['Status'] == status]

    # Converter os hostnames para minúsculas para comparação
    df1[coluna1] = df1[coluna1].str.lower()
    df2[coluna2] = df2[coluna2].str.lower()

    # Encontrar os servidores não descobertos
    nao_descobertos = df1[~df1[coluna1].isin(df2[coluna2])]

    # Contar os servidores descobertos e não descobertos
    total_servidores = len(df1)
    descobertos = len(df2)
    nao_descobertos = len(nao_descobertos)

    # Criar um DataFrame com os resultados
    resultados = pd.DataFrame({'Status': ['Descobertos', 'Não Descobertos'],
                               'Quantidade': [descobertos, nao_descobertos]})

    # Criar um gráfico de pizza
    plt.pie(resultados['Quantidade'], labels=resultados['Status'], autopct='%1.1f%%')
    plt.title('Cobertura de Servidores')
    plt.show()

    return resultados

# Exemplo de uso
comparar_servidores('inventario.xlsx', 'hostname', 'descobertos.xlsx', 'Human Name')
