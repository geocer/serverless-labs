import boto3
import json

def document_api_integrations_v2(api_id, region_name='sa-east-1', output_file='api_integrations_v2_documentation.json'):
    """
    Gera um arquivo JSON contendo detalhes das integrações de cada rota de um API Gateway V2.

    Args:
        api_id (str): O ID do API Gateway V2.
        region_name (str): A região AWS onde o API Gateway V2 está localizado.
        output_file (str): O nome do arquivo JSON onde a documentação será salva.
    """
    try:
        client = boto3.client('apigatewayv2', region_name=region_name)
        documentation = {"api_id": api_id, "region": region_name, "routes": {}}

        # 1. Obter todas as rotas da API
        routes_response = client.get_routes(ApiId=api_id, MaxResults='500')
        routes = routes_response.get('Items', [])

        while routes_response.get('NextToken'):
            routes_response = client.get_routes(ApiId=api_id, NextToken=routes_response['NextToken'], MaxResults='500')
            routes.extend(routes_response.get('Items', []))

        for route in routes:
            route_id = route['RouteId']
            route_key = route.get('RouteKey', '')
            documentation["routes"][route_id] = {"route_key": route_key, "integration": None}

            # 2. Obter detalhes da integração para cada rota
            try:
                integration_response = client.get_integration(ApiId=api_id, IntegrationId=route.get('Target'))
                documentation["routes"][route_id]["integration"] = integration_response
            except client.exceptions.NotFoundException:
                documentation["routes"][route_id]["integration"] = "No integration configured"
            except Exception as e:
                print(f"Erro ao obter integração para rota '{route_key}': {e}")

        # Salvar a documentação em um arquivo JSON
        with open(output_file, 'w') as f:
            json.dump(documentation, f, indent=4)

        print(f"Documentação das integrações da API V2 '{api_id}' salva em '{output_file}'")

    except Exception as e:
        print(f"Ocorreu um erro ao processar a API V2 '{api_id}': {e}")

if __name__ == "__main__":
    api_id_to_document = input("Digite o ID do API Gateway V2 que você deseja documentar: ")
    region = input("Digite a região AWS do API Gateway V2 (padrão: sa-east-1): ") or 'sa-east-1'
    output_filename = input("Digite o nome do arquivo para salvar a documentação (padrão: api_integrations_v2_documentation.json): ") or 'api_integrations_v2_documentation.json'

    document_api_integrations_v2(api_id_to_document, region, output_filename)
