import boto3
import json

def generate_tfvars_from_apigatewayv2(api_gateway_id, region_name='sa-east-1'):
    client = boto3.client('apigatewayv2', region_name=region_name)
    lambda_client = boto3.client('lambda', region_name=region_name)
    tfvars_config = {"api_gateway_config": []}

    print(f"Obtendo rotas para API Gateway ID: {api_gateway_id} na região: {region_name}")
    routes_response = client.get_routes(ApiId=api_gateway_id)
    routes_data = routes_response.get('Items', [])
    print(f"Rotas encontradas: {len(routes_data)}")

    print(f"Obtendo integrações para API Gateway ID: {api_gateway_id} na região: {region_name}")
    integrations_response = client.get_integrations(ApiId=api_gateway_id)
    integrations_data = integrations_response.get('Items', [])
    print(f"Integrações encontradas: {len(integrations_data)}")

    for route in routes_data:
        integration_id = route.get('Target')
        route_path = route.get('RouteKey')
        route_method = route_path.split(' ')[0] if ' ' in route_path else 'ANY'
        print(f"\nProcessando rota: {route_method} {route_path}, Target: {integration_id}")

        integration_info = next((i for i in integrations_data if i['IntegrationId'] == integration_id), None)

        if integration_info:
            print(f"  Detalhes da integração encontrada: {integration_info.get('IntegrationType')}, URI: {integration_info.get('IntegrationUri')}")
            if integration_info['IntegrationType'] == 'AWS_PROXY' and 'arn:aws:lambda' in integration_info['IntegrationUri']:
                lambda_arn = integration_info['IntegrationUri']
                function_name = lambda_arn.split(':function:')[-1]
                try:
                    print(f"  Obtendo configuração da função Lambda: {function_name}")
                    lambda_config = lambda_client.get_function_configuration(FunctionName=function_name)
                    handler = lambda_config.get('Handler')
                    runtime = lambda_config.get('Runtime')
                    # Tentativa de obter a configuração de retenção de logs (pode não ser diretamente acessível assim)
                    # Uma abordagem mais robusta seria verificar as propriedades do grupo de logs associado à função
                    retention_days = "7" # Valor padrão, você pode precisar implementar uma lógica mais complexa

                    integration_config = {
                        "function_name": function_name,
                        "handler": handler,
                        "runtime": runtime,
                        "description": route.get('Description', f"Integration for {route_path}"),
                        "cloudwatch_logs_retention_in_days": retention_days,
                        "routes": [
                            {
                                "path": route_path.split(' ')[1] if ' ' in route_path else '/',
                                "method": route_method,
                                "subroutes": [],
                                "parameters": route.get('RequestParameters', [])
                            }
                        ]
                    }
                    tfvars_config["api_gateway_config"].append(integration_config)
                    print(f"  Configuração adicionada para: {function_name}")

                except lambda_client.exceptions.ResourceNotFoundException:
                    print(f"  Erro: Função Lambda não encontrada: {function_name}")
                except Exception as e:
                    print(f"  Erro ao obter configuração da Lambda {function_name}: {e}")
            else:
                print(f"  Integração não é AWS_PROXY para Lambda, ignorando.")
        else:
            print(f"  Erro: Integração não encontrada para rota.")

    return json.dumps(tfvars_config, indent=2)

if __name__ == "__main__":
    api_gateway_id = "your-api-gateway-id" # Substitua pelo seu ID do API Gateway v2
    tfvars_content = generate_tfvars_from_apigatewayv2(api_gateway_id, region_name='sa-east-1') # Defina a região correta
    print(tfvars_content)

    with open("apigateway.tfvars.json", "w") as f:
        f.write(tfvars_content)

    print("Arquivo 'apigateway.tfvars.json' gerado com sucesso.")
