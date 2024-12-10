import requests
import pandas as pd

def exportar_excel_servicenow(instance, table, query, output_file, user, password):
    """
    Exporta dados do ServiceNow para um arquivo Excel.

    Args:
        instance (str): URL da instância do ServiceNow.
        table (str): Nome da tabela ServiceNow.
        query (str): Query GlideRecord para filtrar os dados.
        output_file (str): Nome do arquivo de saída.
        user (str): Nome de usuário do ServiceNow.
        password (str): Senha do usuário do ServiceNow.
    """

    # URL da API REST
    url = f"{instance}/api/now/table/{table}?sysparm_query={query}"

    # Autenticação básica
    auth = (user, password)

    # Fazer a requisição GET
    response = requests.get(url, auth=auth)
    data = response.json()['result']

    # Criar um DataFrame Pandas
    df = pd.DataFrame(data)

    # Exportar para Excel
    df.to_excel(output_file, index=False)

    print(f"Dados exportados para {output_file}")
