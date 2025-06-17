import boto3
import json
import sys

def get_all_items(client, method, key, **kwargs):
    """Helper to handle pagination for Boto3 list/get methods."""
    items = []
    paginator = client.get_paginator(method)
    for page in paginator.paginate(**kwargs):
        items.extend(page.get(key, []))
    return items

def get_lambda_name_from_arn(lambda_arn):
    """Extracts the Lambda function name from its ARN."""
    # ARN format: arn:aws:lambda:region:account-id:function:function-name
    parts = lambda_arn.split(':')
    if len(parts) > 6 and parts[5] == 'function':
        return parts[6]
    return None

def extract_apigw_config(api_gateway_name):
    """
    Extracts API Gateway v2 configuration (routes and Lambda integrations)
    and formats it for Terraform tfvars.
    """
    apigw_client = boto3.client('apigatewayv2')
    lambda_client = boto3.client('lambda')

    try:
        # 1. Find the API Gateway ID by name
        # List APIs and find the one with the matching name
        apis = get_all_items(apigw_client, 'get_apis', 'Items')
        api_id = None
        for api in apis:
            if api.get('Name') == api_gateway_name:
                api_id = api['ApiId']
                break

        if not api_id:
            print(f"Error: API Gateway with name '{api_gateway_name}' not found.")
            return None

        print(f"Found API Gateway '{api_gateway_name}' with ID: {api_id}")

        # 2. Get all routes for the API
        routes = get_all_items(apigw_client, 'get_routes', 'Items', ApiId=api_id)
        print(f"Found {len(routes)} routes.")

        # 3. Get all integrations for the API
        integrations = get_all_items(apigw_client, 'get_integrations', 'Items', ApiId=api_id)
        print(f"Found {len(integrations)} integrations.")

        # 4. Create a map from IntegrationId to integration details
        integration_id_to_details = {intg['IntegrationId']: intg for intg in integrations}

        # 5. Group routes by IntegrationId
        integration_id_to_routes = {}
        for route in routes:
            integration_id = route.get('IntegrationId')
            if integration_id:
                if integration_id not in integration_id_to_routes:
                    integration_id_to_routes[integration_id] = []
                integration_id_to_routes[integration_id].append(route)

        # 6. Build the api_gateway_config structure
        api_gateway_config_map = {} # Use a map to group by Lambda ARN initially

        for integration_id, route_list in integration_id_to_routes.items():
            integration_details = integration_id_to_details.get(integration_id)

            if not integration_details:
                print(f"Warning: Integration ID '{integration_id}' not found for routes: {[r['RouteKey'] for r in route_list]}")
                continue

            # Check if it's an AWS_PROXY integration targeting Lambda
            if (integration_details.get('IntegrationType') == 'AWS_PROXY' and
                'lambda' in integration_details.get('IntegrationUri', '')):

                integration_uri = integration_details['IntegrationUri']
                lambda_arn = integration_uri # For AWS_PROXY Lambda, the URI is the ARN
                lambda_name = get_lambda_name_from_arn(lambda_arn)

                if not lambda_name:
                    print(f"Warning: Could not extract Lambda name from ARN: {lambda_arn} for integration ID: {integration_id}")
                    continue

                # If this Lambda ARN is not yet in our config map, get Lambda details
                if lambda_arn not in api_gateway_config_map:
                    try:
                        lambda_details = lambda_client.get_function(FunctionName=lambda_name)
                        config = lambda_details.get('Configuration', {})
                        # Note: Getting CloudWatch Log retention directly is not trivial via get_function
                        # Assuming a default or requiring manual check. Using a placeholder.
                        log_retention_days = 7 # Placeholder

                        api_gateway_config_map[lambda_arn] = {
                            "function_name": config.get('FunctionName', lambda_name),
                            "handler": config.get('Handler', 'index.handler'), # Default handler if not found
                            "runtime": config.get('Runtime', 'python3.9'),    # Default runtime if not found
                            "description": config.get('Description', f"Lambda function {lambda_name}"),
                            "cloudwatch_logs_retention_in_days": log_retention_days,
                            "routes": [] # Initialize the list of routes for this lambda
                        }
                        print(f"Processing Lambda: {lambda_name}")

                    except lambda_client.exceptions.ResourceNotFoundException:
                        print(f"Warning: Lambda function '{lambda_name}' not found. Skipping routes associated with it.")
                        continue
                    except Exception as e:
                        print(f"Error fetching details for Lambda '{lambda_name}': {e}")
                        continue

                # Add routes associated with this Lambda
                for route in route_list:
                    route_key = route.get('RouteKey')
                    if not route_key:
                        print(f"Warning: Skipping route with no RouteKey for integration {integration_id}.")
                        continue

                    route_attributes = {
                        "authorization_type": route.get('AuthorizationType'),
                        "authorizer_id": route.get('AuthorizerId'), # This ID needs mapping in Terraform
                        "detailed_metrics_enabled": route.get('DetailedMetricsEnabled', False), # Default to False
                        "api_key_required": route.get('ApiKeyRequired'),
                        "integration": {
                            "uri": integration_uri,
                            "payload_format_version": integration_details.get('PayloadFormatVersion'),
                            "timeout_milliseconds": integration_details.get('TimeoutMilliseconds')
                        }
                    }

                    # Handle RouteSettings for throttling if they exist
                    route_settings = route.get('RouteSettings', {})
                    if route_settings:
                         route_attributes["throttling_rate_limit"] = route_settings.get('ThrottlingRateLimit')
                         route_attributes["throttling_burst_limit"] = route_settings.get('ThrottlingBurstLimit')


                    # Clean up None values to match JSON null or omit in Terraform
                    # Using dict comprehension to filter out None values recursively might be too complex
                    # Let's rely on json.dump handling None as null and Terraform's lookup handling null

                    api_gateway_config_map[lambda_arn]['routes'].append({
                        "route_key": route_key,
                        "attributes": route_attributes
                    })
                    print(f"  - Added route: {route_key}")

            # You can add handling for other integration types here if needed
            # elif integration_details.get('IntegrationType') == 'HTTP_PROXY':
            #     print(f"Skipping HTTP_PROXY integration for ID {integration_id}. Not supported by current tfvars structure.")
            # ... handle other types ...

    except Exception as e:
        print(f"An error occurred: {e}")
        return None

    # Convert the map values to a list for the final tfvars structure
    api_gateway_config_list = list(api_gateway_config_map.values())

    # Final structure for tfvars
    tfvars_data = {
        "api_gateway_config": api_gateway_config_list
        # Add other variables needed in terraform.tfvars.json if any
        # "api_gateway_name": api_gateway_name # You could also include the name here if it's a variable
    }

    return tfvars_data

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python extract_apigw_config.py <api_gateway_name>")
        sys.exit(1)

    api_gateway_name = sys.argv[1]
    config_data = extract_apigw_config(api_gateway_name)

    if config_data:
        tfvars_file = "terraform.tfvars.json"
        with open(tfvars_file, 'w') as f:
            json.dump(config_data, f, indent=2)
        print(f"Successfully generated {tfvars_file}")
    else:
        print("Failed to generate configuration.")

