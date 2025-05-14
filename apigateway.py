import boto3
import json

def generate_tfvars_from_apigatewayv2(api_gateway_id, region_name='us-east-1'):
    client = boto3.client('apigatewayv2', region_name=region_name)
    lambda_client = boto3.client('lambda', region_name=region_name)
    tfvars_config = {"api_gateway_config": []}

    # 1. Obter as rotas da API Gateway v2
    routes_response = client.get_routes(ApiId=api_gateway_id)
    routes_data = routes_response.get('Items', [])

    # 2. Obter as integrações da API Gateway v2
    integrations_response = client.get_integrations(ApiId=api_gateway_id)
    integrations_data = integrations_response.get('Items', [])

    # 3. Mapear rotas para integrações e extrair informações relevantes
    for route in routes_data:
        integration_id = route.get('Target') # O Target geralmente é o ID da integração
        route_path = route.get('RouteKey')
        route_method = route_path.split(' ')[0] if ' ' in route_path else 'ANY'
        integration_info = next((i for i in integrations_data if i['IntegrationId'] == integration_id), None)

        if integration_info and integration_info['IntegrationType'] == 'AWS_PROXY' and 'arn:aws:lambda' in integration_info['IntegrationUri']:
            lambda_arn = integration_info['IntegrationUri'].split(':function:')[0] + ':function:' + integration_info['IntegrationUri'].split(':function:')[1].split(':')[0]
            try:
                lambda_config = lambda_client.get_function_configuration(FunctionName=lambda_arn)
                function_name = lambda_config.get('FunctionName')
                handler = lambda_config.get('Handler')
                runtime = lambda_config.get('Runtime')
                log_config = lambda_config.get('LoggingConfig')
                retention_days = str(log_config.get('LogGroupArn', '').split(':log-group:')[-1].split(':')[0]) if log_config else "7" # Tentativa de obter retenção, pode precisar ajuste

                # Construir o objeto de configuração para esta integração
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
                            "subroutes": [], # API Gateway v2 não tem sub-rotas explícitas como v1
                            "parameters": route.get('RequestParameters', []) # Adapte como os parâmetros são extraídos
                        }
                    ],
                    # Adicione mais campos da integração conforme necessário
                }
                tfvars_config["api_gateway_config"].append(integration_config)

            except lambda_client.exceptions.ResourceNotFoundException:
                print(f"Lambda function not found: {lambda_arn}")
            except Exception as e:
                print(f"Error getting Lambda config for {lambda_arn}: {e}")

        # Adicione lógica para outros tipos de integração (HTTP, MOCK, etc.) conforme necessário

    return json.dumps(tfvars_config, indent=2)

if __name__ == "__main__":
    api_gateway_id = "your-api-gateway-id" # Substitua pelo ID do seu API Gateway v2
    tfvars_content = generate_tfvars_from_apigatewayv2(api_gateway_id)
    print(tfvars_content)

    with open("apigateway.tfvars.json", "w") as f:
        f.write(tfvars_content)

    print("Arquivo 'apigateway.tfvars.json' gerado com sucesso.")
