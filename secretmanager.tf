# No seu arquivo que chama o módulo secrets_manager

module "secrets_manager_docker_credentials" {
  source = "terraform-aws-modules/secrets-manager/aws" # Confirme o source do seu módulo

  name        = "docker/fmh-nexus-onefiserv-net-credentials"
  description = "Credenciais para o Docker Registry fmh.nexus.onefiserv.net"

  secret_string = jsonencode({
    username = "svc-bra-fts-eng-clou",
    password = var.docker_nexus_password # Use uma variável ou outra fonte segura
  })

  create_policy       = true # Mantenha true se o módulo for criar a política
  block_public_policy = true

  # AQUI ESTÁ A MUDANÇA PRINCIPAL: Transforme a lista de declarações em um MAPA
  policy_statements = {
    # A chave aqui será o SID da declaração.
    # Se você tiver múltiplas roles e quiser uma declaração para cada,
    # precisaria de um 'for' para criar chaves únicas e statements únicos.
    # Se todas as roles podem estar em um único statement 'Principal', use a sintaxe abaixo:
    "AllowEcsTaskExecutionRolesToReadSecret" = { # Esta é a chave do mapa, deve ser o SID
      effect = "Allow"
      principals = [
        {
          type = "AWS"
          # Assumindo que module.ecs_main.task_exec_iam_role_arn é uma lista de ARNs
          identifiers = [for arn in module.ecs_main.task_exec_iam_role_arn : arn]
        }
      ]
      actions   = ["secretsmanager:GetSecretValue"]
      # O resource "*" geralmente é tratado pelo módulo se policy_statements estiver no módulo
      # Caso contrário, você pode precisar de:
      # resources = [module.secrets_manager_docker_credentials.arn]
    }

    # Se você precisar de statements separados para cada ARN de role (menos comum para essa permissão):
    /*
    for role_name, role_arn in module.ecs_main.task_exec_iam_role_arn : "Allow${role_name}ToReadSecret" => {
      effect = "Allow"
      principals = [
        {
          type = "AWS"
          identifiers = [role_arn]
        }
      ]
      actions = ["secretsmanager:GetSecretValue"]
      resources = ["*"]
    }
    */
  }

  recovery_window_in_days = 7

  create_random_password = false

  tags = {
    Environment = "Development"
    Project     = "DockerIntegration"
    ManagedBy   = "Terraform"
  }
}

# Certifique-se de que o output de module.ecs_main.task_exec_iam_role_arn
# é uma lista de strings (ARNs) ou um mapa para que a iteração funcione corretamente.

# Exemplo para MÚLTIPLAS ROLES (se elas forem acessíveis de forma similar)
policy_statements = {
  for service_name, service_module in module.ecs_main.module.service :
  "Allow${title(service_name)}ToReadSecret" => {
    effect = "Allow"
    principals = [
      {
        type        = "AWS"
        identifiers = [service_module.aws_iam_role.task_exec[0].arn] # Ajuste se a estrutura for diferente
      }
    ]
    actions   = ["secretsmanager:GetSecretValue"]
    resources = ["*"] # Ou o ARN específico do segredo do Secrets Manager
  }
}


{
  "containerDefinitions": [
    {
      "name": "my-app-container",
      "image": "your_external_registry_hostname/your_image_name:your_tag",
      "cpu": 256,
      "memory": 512,
      "essential": true,
      "portMappings": [
        {
          "containerPort": 80,
          "protocol": "tcp"
        }
      ],
      "repositoryCredentials": {
        "credentialsParameter": "arn:aws:secretsmanager:REGION:ACCOUNT_ID:secret:your_secret_name_in_secrets_manager"
      },
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/my-app",
          "awslogs-region": "REGION",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ],
  "family": "my-app-task-definition",
  "networkMode": "awsvpc",
  "requiresCompatibilities": [
    "FARGATE"
  ],
  "cpu": "256",
  "memory": "512",
  "executionRoleArn": "arn:aws:iam::ACCOUNT_ID:role/your_task_execution_role_name"
}

