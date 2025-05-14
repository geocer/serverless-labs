import boto3
import json

def generate_tfvars_from_apigatewayv2(api_gateway_id, region_name='sa-east-1'):
    client = boto3.client('apigatewayv2', region_name=region_name)
    lambda_client = boto3.client('lambda', region_name=region_name)
    tfvars_config = {"api_gateway_config": []}

    print(f"Obtendo integrações para API Gateway ID: {api_gateway_id} na região: {region_name}")
    integrations_response = client.get_integrations(ApiId=api_gateway_id)
    integrations_data = integrations_response.get('Items', [])
    print(f"Integrações encontradas: {len(integrations_data)}")
    # print(json.dumps(integrations_data, indent=2)) # Descomente para ver os dados brutos das integrações

    print(f"Obtendo rotas para API Gateway ID: {api_gateway_id} na região: {region_name}")
    routes_response = client.get_routes(ApiId=api_gateway_id)
    routes_data = routes_response.get('Items', [])
    print(f"Rotas encontradas: {len(routes_data)}")
    # print(json.dumps(routes_data, indent=2)) # Descomente para ver os dados brutos das rotas

    for integration in integrations_data:
        integration_id = integration.get('IntegrationId')
        integration_type = integration.get('IntegrationType')
        integration_uri = integration.get('IntegrationUri')

        if integration_type == 'AWS_PROXY' and 'arn:aws:lambda' in integration_uri:
            lambda_arn = integration_uri
            function_name = lambda_arn.split(':function:')[-1]
            try:
                print(f"\nProcessando integração Lambda: {function_name} (ID: {integration_id})")
                lambda_config = lambda_client.get_function_configuration(FunctionName=function_name)
                handler = lambda_config.get('Handler')
                runtime = lambda_config.get('Runtime')
                retention_days = "7"  # Valor padrão, pode precisar de lógica mais complexa

                # Encontrar rotas associadas a esta integração
                associated_routes = [
                    r for r in routes_data
                    if r.get('Target') == integration_id
                ]
                routes_config = []
                for route in associated_routes:
                    route_path = route.get('RouteKey')
                    route_method = route_path.split(' ')[0] if ' ' in route_path else 'ANY'
                    routes_config.append({
                        "path": route_path.split(' ')[1] if ' ' in route_path else '/',
                        "method": route_method,
                        "subroutes": [],  # API Gateway v2 não tem sub-rotas explícitas como v1
                        "parameters": route.get('RequestParameters', [])
                    })

                integration_config = {
                    "function_name": function_name,
                    "handler": handler,
                    "runtime": runtime,
                    "description": integration.get('Description', f"Lambda integration {integration_id}"),
                    "cloudwatch_logs_retention_in_days": retention_days,
                    "routes": routes_config
                }
                tfvars_config["api_gateway_config"].append(integration_config)
                print(f"  Configuração adicionada para: {function_name}")

            except lambda_client.exceptions.ResourceNotFoundException:
                print(f"  Erro: Função Lambda não encontrada: {function_name}")
            except Exception as e:
                print(f"  Erro ao obter configuração da Lambda {function_name}: {e}")
        else:
            print(f"  Integração {integration_id} não é AWS_PROXY para Lambda, ignorando.")

    return json.dumps(tfvars_config, indent=2)

if __name__ == "__main__":
    api_gateway_id = "your-api-gateway-id"  # Substitua pelo seu ID do API Gateway v2
    tfvars_content = generate_tfvars_from_apigatewayv2(api_gateway_id, region_name='sa-east-1')
    print(tfvars_content)

    with open("apigateway.tfvars.json", "w") as f:
        f.write(tfvars_content)

    print("Arquivo 'apigateway.tfvars.json' gerado com sucesso.")
