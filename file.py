import pandas as pd
import matplotlib.pyplot as plt

def analisar_servidores(arquivo1, coluna_hostname1, coluna_status1, arquivo2, coluna_hostname2):
    """
    Compara duas planilhas para identificar servidores não descobertos.

    Args:
        arquivo1 (str): Nome do arquivo da primeira planilha.
        coluna_hostname1 (str): Nome da coluna com os hostnames na primeira planilha.
        coluna_status1 (str): Nome da coluna com o status na primeira planilha.
        arquivo2 (str): Nome do arquivo da segunda planilha.
        coluna_hostname2 (str): Nome da coluna com os hostnames na segunda planilha.
    """

    # Carregar os dados das planilhas
    df1 = pd.read_excel(arquivo1)
    df2 = pd.read_excel(arquivo2)

    # Filtrar os servidores com status "Power On" na primeira planilha
    df1_power_on = df1[df1[coluna_status1] == 'Power On']

    # Converter os hostnames para minúsculas para comparação
    df1_power_on[coluna_hostname1] = df1_power_on[coluna_hostname1].str.lower()
    df2[coluna_hostname2] = df2[coluna_hostname2].str.lower()

    # Encontrar os servidores não descobertos
    servidores_nao_descobertos = df1_power_on[~df1_power_on[coluna_hostname1].isin(df2[coluna_hostname2])]

    # Calcular o número de servidores descobertos e não descobertos
    total_servidores = len(df1_power_on)
    descobertos = len(df2)
    nao_descobertos = len(servidores_nao_descobertos)

    # Criar um gráfico de pizza
    labels = ['Descobertos', 'Não Descobertos']
    sizes = [descobertos, nao_descobertos]
    plt.pie(sizes, labels=labels, autopct='%1.1f%%')
    plt.title('Cobertura de Servidores')
    plt.show()

    # Imprimir os servidores não descobertos
    print("Servidores não descobertos:")
    print(servidores_nao_descobertos[coluna_hostname1])

# Exemplo de uso
analisar_servidores('inventario_completo.xlsx', 'Hostname', 'Status', 'servidores_descobertos.xlsx', 'HumanName')
