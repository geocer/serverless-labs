import boto3
import json

def document_api_integrations(api_id, region_name='sa-east-1', output_file='api_integrations_documentation.json'):
    """
    Gera um arquivo JSON contendo detalhes das integrações de cada método em cada recurso de um API Gateway.

    Args:
        api_id (str): O ID do API Gateway.
        region_name (str): A região AWS onde o API Gateway está localizado.
        output_file (str): O nome do arquivo JSON onde a documentação será salva.
    """
    try:
        client = boto3.client('apigateway', region_name=region_name)
        documentation = {"api_id": api_id, "region": region_name, "resources": {}}

        # 1. Obter todos os recursos da API
        resources_response = client.get_resources(restApiId=api_id, limit=500)
        resources = resources_response.get('items', [])

        for resource in resources:
            resource_id = resource['id']
            resource_path = resource.get('path', '')
            documentation["resources"][resource_id] = {"path": resource_path, "methods": {}}

            # 2. Obter os métodos de cada recurso
            methods = resource.get('resourceMethods', {})
            for method in methods:
                documentation["resources"][resource_id]["methods"][method] = {"integration": None}

                # 3. Obter detalhes da integração para cada método
                try:
                    integration_response = client.get_integration(
                        restApiId=api_id,
                        resourceId=resource_id,
                        httpMethod=method
                    )
                    documentation["resources"][resource_id]["methods"][method]["integration"] = integration_response
                except client.exceptions.NotFoundException:
                    documentation["resources"][resource_id]["methods"][method]["integration"] = "No integration configured"
                except Exception as e:
                    print(f"Erro ao obter integração para {resource_path} - {method}: {e}")

        # Salvar a documentação em um arquivo JSON
        with open(output_file, 'w') as f:
            json.dump(documentation, f, indent=4)

        print(f"Documentação das integrações da API '{api_id}' salva em '{output_file}'")

    except Exception as e:
        print(f"Ocorreu um erro ao processar a API '{api_id}': {e}")

if __name__ == "__main__":
    api_id_to_document = input("Digite o ID do API Gateway que você deseja documentar: ")
    region = input("Digite a região AWS do API Gateway (padrão: sa-east-1): ") or 'sa-east-1'
    output_filename = input("Digite o nome do arquivo para salvar a documentação (padrão: api_integrations_documentation.json): ") or 'api_integrations_documentation.json'

    document_api_integrations(api_id_to_document, region, output_filename)
