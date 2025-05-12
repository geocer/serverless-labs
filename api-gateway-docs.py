import boto3
import json

def get_api_integrations_documentation(api_id, region_name='us-east-1'):
    """
    Gera a documentação das integrações de um API Gateway.

    Args:
        api_id (str): O ID do API Gateway (ex: 'abcdef123').
        region_name (str): A região AWS onde o API Gateway está localizado.

    Returns:
        dict: Um dicionário contendo a estrutura da API e detalhes de integração.
    """
    client = boto3.client('apigateway', region_name=region_name)
    documentation = {}

    try:
        # 1. Obter recursos (caminhos/endpoints) da API
        resources_response = client.get_resources(restApiId=api_id, limit=500) # Ajuste o limite conforme necessário
        resources = resources_response.get('items', [])

        # Loop através de cada recurso
        for resource in resources:
            resource_path = resource.get('path')
            resource_id = resource.get('id')
            
            documentation[resource_path] = {}
            
            # 2. Obter métodos para cada recurso
            # 'resourceMethods' contém um dicionário de métodos HTTP (GET, POST, etc.)
            if 'resourceMethods' in resource:
                for http_method, method_details in resource['resourceMethods'].items():
                    documentation[resource_path][http_method] = {}
                    
                    # 3. Obter detalhes da integração para cada método
                    try:
                        method_response = client.get_method(
                            restApiId=api_id,
                            resourceId=resource_id,
                            httpMethod=http_method
                        )
                        
                        integration = method_response.get('methodIntegration')
                        if integration:
                            integration_type = integration.get('type')
                            integration_uri = integration.get('uri')
                            integration_method = integration.get('httpMethod') # Método HTTP da integração (backend)
                            
                            documentation[resource_path][http_method]['integration_type'] = integration_type
                            documentation[resource_path][http_method]['integration_uri'] = integration_uri
                            documentation[resource_path][http_method]['integration_method'] = integration_method
                            documentation[resource_path][http_method]['request_templates'] = integration.get('requestTemplates')
                            documentation[resource_path][http_method]['passthrough_behavior'] = integration.get('passthroughBehavior')
                            documentation[resource_path][http_method]['connection_type'] = integration.get('connectionType')
                            documentation[resource_path][http_method]['connection_id'] = integration.get('connectionId')

                            # Exemplo: Para integração com Lambda, você pode extrair o nome da função
                            if integration_type == 'AWS_PROXY' and integration_uri and 'lambda' in integration_uri:
                                # Ex: arn:aws:apigateway:us-east-1:lambda:path/2015-03-31/functions/arn:aws:lambda:us-east-1:ACCOUNT_ID:function:FunctionName/invocations
                                # Ou arn:aws:lambda:us-east-1:ACCOUNT_ID:function:FunctionName
                                if "/functions/" in integration_uri:
                                    lambda_function_name = integration_uri.split("/functions/")[-1].split("/")[0]
                                elif "function:" in integration_uri: # Direct Lambda ARN
                                    lambda_function_name = integration_uri.split("function:")[-1].split(":")[0]
                                else:
                                    lambda_function_name = "N/A (parse error)"
                                documentation[resource_path][http_method]['lambda_function_name'] = lambda_function_name
                            
                            # Adicione mais campos da integração conforme necessário
                        else:
                            documentation[resource_path][http_method]['integration_details'] = "No integration found for this method."
                            
                        # Você também pode querer extrair method_response, method_request, etc.
                        documentation[resource_path][http_method]['method_request_parameters'] = method_response.get('requestParameters')
                        documentation[resource_path][http_method]['method_responses'] = method_response.get('methodResponses')


                    except client.exceptions.NotFoundException:
                        documentation[resource_path][http_method]['integration_details'] = "Method not found or not configured."
                    except Exception as e:
                        documentation[resource_path][http_method]['integration_details'] = f"Error getting method details: {e}"

    except client.exceptions.NotFoundException:
        print(f"API Gateway with ID '{api_id}' not found in region '{region_name}'.")
        return {}
    except Exception as e:
        print(f"An error occurred: {e}")
        return {}

    return documentation

# --- Como usar o script ---
if __name__ == "__main__":
    # Substitua pelo seu ID do API Gateway e a região
    YOUR_API_GATEWAY_ID = 'YOUR_API_GATEWAY_ID_HERE' # Ex: 'abcdef123'
    YOUR_AWS_REGION = 'us-east-1' # Ex: 'sa-east-1' para São Paulo

    if YOUR_API_GATEWAY_ID == 'YOUR_API_GATEWAY_ID_HERE':
        print("Por favor, substitua 'YOUR_API_GATEWAY_ID_HERE' pelo ID real do seu API Gateway.")
        print("Você pode encontrar o ID na console do API Gateway, na URL ou na coluna ID.")
    else:
        print(f"Gerando documentação para API Gateway ID: {YOUR_API_GATEWAY_ID} na região: {YOUR_AWS_REGION}...")
        api_doc = get_api_integrations_documentation(YOUR_API_GATEWAY_ID, YOUR_AWS_REGION)

        if api_doc:
            # Exemplo de como imprimir a documentação em JSON formatado
            print("\n--- Documentação da API ---")
            print(json.dumps(api_doc, indent=2))

            # Você pode então processar 'api_doc' para gerar outros formatos
            # Por exemplo, para gerar um arquivo Markdown simples:
            with open('api_integrations_doc.md', 'w') as f:
                f.write(f"# Documentação da API Gateway: {YOUR_API_GATEWAY_ID}\n\n")
                for path, methods in api_doc.items():
                    f.write(f"## Caminho: `{path}`\n\n")
                    for method, details in methods.items():
                        f.write(f"### Método: `{method}`\n")
                        f.write(f"- **Tipo de Integração:** {details.get('integration_type', 'N/A')}\n")
                        f.write(f"- **URI de Integração:** `{details.get('integration_uri', 'N/A')}`\n")
                        f.write(f"- **Método HTTP da Integração:** {details.get('integration_method', 'N/A')}\n")
                        if 'lambda_function_name' in details:
                            f.write(f"- **Função Lambda (estimado):** `{details['lambda_function_name']}`\n")
                        f.write(f"- **Templates de Requisição:**\n")
                        request_templates = details.get('request_templates')
                        if request_templates:
                            for content_type, template in request_templates.items():
                                f.write(f"  - `{content_type}`:\n")
                                f.write(f"    ```\n{template}\n    ```\n")
                        else:
                            f.write("  Nenhum.\n")
                        f.write("\n")
            print("\nDocumentação Markdown salva em 'api_integrations_doc.md'")
        else:
            print("Nenhuma documentação gerada.")

