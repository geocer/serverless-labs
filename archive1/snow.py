import requests
import pandas as pd

def exportar_dados_servicenow_para_excel(instance, user, password, table_name, output_file):
    """
    Exporta dados de uma tabela do ServiceNow para um arquivo Excel.

    Args:
        instance (str): URL da instância do ServiceNow.
        user (str): Nome de usuário para autenticação.
        password (str): Senha para autenticação.
        table_name (str): Nome da tabela (ou view) a ser consultada.
        output_file (str): Nome do arquivo Excel de saída.
    """

    # Construir a URL da API
    url = f"{instance}/api/now/table/{table_name}"

    # Cabeçalho de autenticação básica
    auth = (user, password)

    # Fazer a requisição GET à API
    response = requests.get(url, auth=auth)
    data = response.json()

    # Converter os dados para um DataFrame do pandas
    df = pd.DataFrame(data['result'])

    # Exportar os dados para um arquivo Excel
    df.to_excel(output_file, index=False)

    print(f"Dados exportados com sucesso para {output_file}")

# Exemplo de uso:
instance = "https://your_instance.service-now.com"
user = "seu_usuario"
password = "sua_senha"
table_name = "your_table_name"
output_file = "dados_servicenow.xlsx"

exportar_dados_servicenow_para_excel(instance, user, password, table_name, output_file)
