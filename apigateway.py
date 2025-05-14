import boto3
import json
import re

def generate_tfvars_json(api_id):
    """
    Generates a terraform.tfvars.json file for an API Gateway based on its routes
    and integrations, matching the specified Terraform variable structure.

    Args:
        api_id (str): The ID of the API Gateway.

    Returns:
        None: Creates or overwrites the terraform.tfvars.json file.
    """
    apigatewayv2_client = boto3.client('apigatewayv2')
    lambda_client = boto3.client('lambda')

    api_config_list = []

    try:
        # Get routes for the API Gateway
        routes_response = apigatewayv2_client.get_routes(ApiId=api_id)
        routes = routes_response.get('Items', [])

        # Structure to hold routes for this API
        api_routes_config = []

        # Placeholder for Lambda details - assuming one set of Lambda details
        # per API config entry for simplicity, though a real scenario might
        # have different Lambdas for different routes.
        # We'll try to get details from the first Lambda integration found.
        lambda_function_name = None
        lambda_handler = "placeholder_handler"
        lambda_runtime = "placeholder_runtime"
        lambda_description = "placeholder_description"
        cloudwatch_logs_retention_in_days = 30 # Placeholder

        for route in routes:
            route_path = route.get('RouteKey', '').split(' ')[-1] # e.g., "GET /my/path" -> "/my/path"
            route_method = route.get('RouteKey', '').split(' ')[0] # e.g., "GET /my/path" -> "GET"
            integration_target = route.get('Target')

            # Attempt to get integration details and derive Lambda function name
            if integration_target and integration_target.startswith('integrations/'):
                integration_id = integration_target.split('/')[-1]
                try:
                    integration_response = apigatewayv2_client.get_integration(
                        ApiId=api_id,
                        IntegrationId=integration_id
                    )
                    integration_uri = integration_response.get('IntegrationUri')

                    # Parse Lambda function name from IntegrationUri ARN
                    # Example ARN: arn:aws:apigateway:region:lambda:path/2015-03-31/functions/arn:aws:lambda:region:account-id:function:function-name/invocations
                    if integration_uri and ':lambda:path' in integration_uri:
                        match = re.search(r'function:([^/]+)/invocations', integration_uri)
                        if match:
                            function_name = match.group(1)
                            if not lambda_function_name: # Get details from the first one found
                                lambda_function_name = function_name
                                try:
                                    lambda_response = lambda_client.get_function(FunctionName=lambda_function_name)
                                    lambda_config = lambda_response.get('Configuration', {})
                                    lambda_handler = lambda_config.get('Handler', lambda_handler)
                                    lambda_runtime = lambda_config.get('Runtime', lambda_runtime)
                                    lambda_description = lambda_config.get('Description', lambda_description)
                                    # Note: cloudwatch_logs_retention_in_days is not directly in get_function response
                                except Exception as e:
                                    print(f"Warning: Could not get details for Lambda function {lambda_function_name}: {e}")


                except Exception as e:
                    print(f"Warning: Could not get integration details for integration ID {integration_id}: {e}")

            # Construct the route object for the tfvars structure
            # Simplifying subroutes and parameters as they are not directly
            # available from get_routes in this nested format.
            api_routes_config.append({
                "path": route_path,
                "method": route_method,
                "subroutes": [], # Placeholder: API GW v2 has flat routes, this structure implies nesting
                "parameters": [] # Placeholder: Parameters would need to be parsed from path or definition
            })

        # Construct the main object for this API Gateway in the list
        api_config_list.append({
            "function_name": lambda_function_name if lambda_function_name else "unknown_lambda_function",
            "handler": lambda_handler,
            "runtime": lambda_runtime,
            "description": lambda_description,
            "cloudwatch_logs_retention_in_days": cloudwatch_logs_retention_in_days,
            "routes": api_routes_config
        })

        # Final structure for the tfvars.json file
        tfvars_data = {
            "api_gateway_config": api_config_list
        }

        # Write to terraform.tfvars.json
        with open("terraform.tfvars.json", "w") as f:
            json.dump(tfvars_data, f, indent=2)

        print("Successfully generated terraform.tfvars.json")

    except Exception as e:
        print(f"An error occurred: {e}")

# --- How to use the script ---
# Replace 'YOUR_API_GATEWAY_ID' with the actual ID of your API Gateway
# You can find the API ID in the AWS Management Console or by using list_apis()
api_id_to_process = 'YOUR_API_GATEWAY_ID'

# Run the function
generate_tfvars_json(api_id_to_process)
