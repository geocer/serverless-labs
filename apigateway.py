import boto3
import json
import re

def generate_tfvars_json_from_integrations(api_id):
    """
    Generates a terraform.tfvars.json file for an API Gateway by inspecting
    its integrations, matching the specified Terraform variable structure
    partially.

    Note: This function uses get_integrations and cannot fully determine
    route paths and methods from its output alone. The 'routes' and
    'subroutes' lists will be generated as empty placeholders.

    Args:
        api_id (str): The ID of the API Gateway.

    Returns:
        None: Creates or overwrites the terraform.tfvars.json file.
    """
    apigatewayv2_client = boto3.client('apigatewayv2')
    lambda_client = boto3.client('lambda')

    # We will group configurations by the backend Lambda function
    api_configs_by_lambda = {}

    try:
        paginator = apigatewayv2_client.get_paginator('get_integrations')
        pages = paginator.paginate(ApiId=api_id)

        for page in pages:
            integrations = page.get('Items', [])

            for integration in integrations:
                integration_id = integration.get('IntegrationId')
                integration_type = integration.get('IntegrationType')
                integration_uri = integration.get('IntegrationUri')

                lambda_function_name = None

                # Try to extract Lambda function name from IntegrationUri for AWS and AWS_PROXY types
                if integration_type in ['AWS_PROXY', 'AWS'] and integration_uri:
                    # Example Lambda IntegrationUri format:
                    # arn:aws:apigateway:region:lambda:path/2015-03-31/functions/arn:aws:lambda:region:account-id:function:function-name/invocations
                    match = re.search(r'function:([^/]+)/invocations', integration_uri)
                    if match:
                        lambda_function_name = match.group(1)

                if lambda_function_name:
                    if lambda_function_name not in api_configs_by_lambda:
                        # Fetch Lambda details if this is the first time we see this function
                        lambda_handler = "placeholder_handler"
                        lambda_runtime = "placeholder_runtime"
                        lambda_description = "placeholder_description"
                        cloudwatch_logs_retention_in_days = 30 # Placeholder

                        try:
                            lambda_response = lambda_client.get_function(FunctionName=lambda_function_name)
                            lambda_config = lambda_response.get('Configuration', {})
                            lambda_handler = lambda_config.get('Handler', lambda_handler)
                            lambda_runtime = lambda_config.get('Runtime', lambda_runtime)
                            lambda_description = lambda_config.get('Description', lambda_description)
                            # cloudwatch_logs_retention_in_days is not directly available here
                        except Exception as e:
                            print(f"Warning: Could not get details for Lambda function {lambda_function_name}: {e}")
                            # If Lambda details cannot be fetched, use placeholders

                        # Initialize the structure for this Lambda backend
                        api_configs_by_lambda[lambda_function_name] = {
                            "function_name": lambda_function_name,
                            "handler": lambda_handler,
                            "runtime": lambda_runtime,
                            "description": lambda_description,
                            "cloudwatch_logs_retention_in_days": cloudwatch_logs_retention_in_days,
                            "routes": [] # Placeholder: Cannot determine routes from get_integrations
                        }
                    # Note: We are not adding routes here because get_integrations doesn't provide route info.
                    # If you had a way to map integration IDs to routes, you would add that logic here.

        # Convert the dictionary of configs into the list format expected by tfvars
        api_gateway_config_list = list(api_configs_by_lambda.values())

        # Final structure for the tfvars.json file
        tfvars_data = {
            "api_gateway_config": api_gateway_config_list
        }

        # Write to terraform.tfvars.json
        with open("terraform.tfvars.json", "w") as f:
            json.dump(tfvars_data, f, indent=2)

        print("Successfully generated terraform.tfvars.json. Note: 'routes' and 'subroutes' are placeholders.")

    except Exception as e:
        print(f"An error occurred: {e}")

# --- How to use the script ---
# Replace 'YOUR_API_GATEWAY_ID' with the actual ID of your API Gateway
# You can find the API ID in the AWS Management Console or by using list_apis()
api_id_to_process = 'YOUR_API_GATEWAY_ID'

# Run the function
generate_tfvars_json_from_integrations(api_id_to_process)
