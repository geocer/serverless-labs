# variables.tf

variable "api_gateway_name" {
  description = "Name of the API Gateway to extract configuration from."
  type        = string
}

variable "api_gateway_config" {
  description = "Configuration extracted from an existing API Gateway for use in the module."
  type = list(object({
    # Lambda function details (as per the image structure)
    function_name                   = string
    handler                         = string
    runtime                         = string
    description                     = string
    cloudwatch_logs_retention_in_days = number # Assuming number of days

    # List of routes associated with this Lambda function
    routes = list(object({
      route_key = string # e.g., "ANY /", "GET /some-route"

      # Attributes for the route block value in the Terraform module
      attributes = object({
        authorization_type       = string  # e.g., "NONE", "JWT" - use null for optional
        authorizer_id            = string  # Authorizer ID - will need mapping in Terraform
        throttling_rate_limit    = number  # Use null for optional
        throttling_burst_limit   = number  # Use null for optional
        detailed_metrics_enabled = bool    # Default to false if not present

        # Integration details for this route
        integration = object({
          uri                    = string # The integration endpoint (e.g., Lambda ARN)
          payload_format_version = string # e.g., "2.0", "1.0"
          timeout_milliseconds   = number # Use null for optional
          # Add other relevant integration parameters here if needed
        })
        # Add other top-level route parameters here if needed (e.g., api_key_required)
        api_key_required = bool # Use null for optional
      })
    }))
  }))
}
# main.tf

locals {
  # Flatten the list of routes from api_gateway_config
  # We create a map where the key is the route_key for easy iteration in the dynamic block
  flattened_routes = {
    for route in flatten([for lambda_conf in var.api_gateway_config : lambda_conf.routes]) :
    route.route_key => route.attributes # Map route_key to its attributes
  }
}

module "api_gateway" {
  source = "terraform-Aws-modules/apigateway-v2/aws"

  cors_configuration = {
    allow_headers = ["content-type", "x-amz-date", "authorization", "x-api-key", "x-amz-security-token", "x-amz-user-agent"]
    allow_methods = ["*"]
    allow_origins = ["*"]
  }

  description      = "My awesome HTTP API Gateway"
  fail_on_warnings = false
  name             = var.api_gateway_name # Use the input variable for name

  # Dynamic block to create routes from the flattened_routes local
  dynamic "routes" {
    for_each = local.flattened_routes # Iterate over the map of route_key => attributes

    content {
      # The content of the dynamic block instance is the 'attributes' object
      # extracted from the flattened_routes map.
      # Use lookup to handle optional attributes gracefully.

      # Route Attributes
      authorization_type       = lookup(routes.value, "authorization_type", null)
      authorizer_id            = lookup(routes.value, "authorizer_id", null) # Requires mapping old ID to new ID
      throttling_rate_limit    = lookup(routes.value, "throttling_rate_limit", null)
      throttling_burst_limit   = lookup(routes.value, "throttling_burst_limit", null)
      detailed_metrics_enabled = lookup(routes.value, "detailed_metrics_enabled", false) # Default to false if missing
      api_key_required         = lookup(routes.value, "api_key_required", null) # Default to null if missing

      # Integration Block within the route
      integration = {
        uri                    = routes.value.integration.uri
        payload_format_version = routes.value.integration.payload_format_version
        timeout_milliseconds   = lookup(routes.value.integration, "timeout_milliseconds", null)
        # Add other integration parameters using lookups
      }
    }
  }

  # ... potentially define authorizers here and reference their IDs in the dynamic block ...

  # If the Lambda function should also be managed by Terraform based on the config,
  # you might use another dynamic block or separate resource blocks here,
  # iterating over var.api_gateway_config.
  # However, the original module usage shows a separate lambda_function module.
  # You will need to decide if the script should also output data to configure Lambdas.
  # Based on the variable structure and requirement to output lambda name, routes, and integrations,
  # it seems the intent is to capture the relationship.
}

# Example of defining an authorizer if needed
/*
resource "aws_apigatewayv2_authorizer" "external" {
  # ... authorizer configuration ...
  api_id = module.api_gateway.api_id
  # You would need to map the extracted authorizer_id from the existing API
  # to the ID of this new authorizer resource in your Terraform code.
  # This mapping logic is outside the scope of the Python script generating tfvars.
}
*/

# The lambda_function module as in your original example
# You might need to adjust how it gets inputs based on api_gateway_config,
# or keep it separate and ensure the extracted Lambda ARNs match.
/*
module "lambda_function" {
  source  = "terraform-aws-modules/lambda/aws"
  version = "~> 7.0"

  # If you want to define Lambdas from the config:
  # Iterate over var.api_gateway_config or a filtered version
  # For simplicity in this example, keeping the original module block.
  # function_name = local.name # This would likely change if configuring multiple lambdas

  # ... other lambda module parameters ...
}
*/
