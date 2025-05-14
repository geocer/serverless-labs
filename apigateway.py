import boto3
import json

def list_api_gateway_integrations_with_details(api_gateway_id, region_name='sa-east-1'):
    client = boto3.client('apigatewayv2', region_name=region_name)
    all_integration_details = []

    try:
        print(f"Listando integrações para API Gateway ID: {api_gateway_id} na região: {region_name}")
        paginator = client.get_paginator('get_integrations')
        pages = paginator.paginate(ApiId=api_gateway_id)

        integration_ids = []
        for page in pages:
            integrations = page.get('Items', [])
            for integration in integrations:
                integration_ids.append(integration.get('IntegrationId'))

        print(f"\nEncontradas {len(integration_ids)} integrações. Obtendo detalhes:")

        for integration_id in integration_ids:
            print(f"\nObtendo detalhes da integração com ID: {integration_id}")
            integration_details = client.get_integration(
                ApiId=api_gateway_id,
                IntegrationId=integration_id
            )
            all_integration_details.append(integration_details)
            # Você pode imprimir os detalhes de cada integração aqui, se desejar:
            # print(json.dumps(integration_details, indent=2))

        print("\nDetalhes de todas as integrações obtidos.")
        return all_integration_details

    except Exception as e:
        print(f"Erro ao listar e obter detalhes das integrações: {e}")
        return None

if __name__ == "__main__":
    api_gateway_id = "your-api-gateway-id"  # Substitua pelo ID da sua API Gateway v2
    region_name = "sa-east-1"

    all_details = list_api_gateway_integrations_with_details(api_gateway_id, region_name)

    if all_details:
        print("\n--- Detalhes de Todas as Integrações (Formato de Lista de Dicionários): ---")
        print(json.dumps(all_details, indent=2))

        # Você pode agora processar a lista 'all_details' conforme necessário
        # para gerar o seu arquivo tfvars.json

    if all_details:
        tfvars_output = {"api_gateway_config": []}
        for integration_detail in all_details:
            if integration_detail.get('IntegrationType') == 'AWS_PROXY' and 'arn:aws:lambda' in integration_detail.get('IntegrationUri', ''):
                lambda_arn = integration_detail['IntegrationUri']
                function_name = lambda_arn.split(':function:')[-1]
                # ... extrair handler, runtime (você pode precisar chamar get_function_configuration da Lambda)
                # ... encontrar rotas associadas (como no script anterior)

                integration_config = {
                    "function_name": function_name,
                    "handler": "...",
                    "runtime": "...",
                    "description": integration_detail.get('Description', f"Lambda integration {integration_detail.get('IntegrationId')}"),
                    "cloudwatch_logs_retention_in_days": "7", # Valor padrão, pode precisar de mais lógica
                    "routes": [] # Preencher com as rotas associadas
                }
                tfvars_output["api_gateway_config"].append(integration_config)

        print("\n--- Conteúdo para apigateway.tfvars.json: ---")
        print(json.dumps(tfvars_output, indent=2))

        with open("apigateway.tfvars.json", "w") as f:
            f.write(json.dumps(tfvars_output, indent=2))
        print("\nArquivo 'apigateway.tfvars.json' gerado com sucesso.")
