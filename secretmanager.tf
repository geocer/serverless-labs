module "secrets_manager_docker_credentials" {
  # Assumindo que este é o caminho do seu módulo do Secrets Manager
  source = "terraform-aws-modules/secrets-manager/aws" # ou o caminho local se for um módulo customizado

  # Nome do segredo no Secrets Manager
  # É uma boa prática incluir o nome do registro para fácil identificação
  name = "docker/fmh-nexus-onefiserv-net-credentials" 
  description = "Credenciais para o Docker Registry fmh.nexus.onefiserv.net"

  # Recovery window em dias (padrão 30, mas pode ajustar)
  recovery_window_in_days = 7

  # Política para permitir que a Task Execution Role do ECS leia este segredo
  create_policy       = true
  block_public_policy = true
  policy_statements = [
    {
      sid    = "AllowEcsTaskExecutionRoleToReadSecret"
      effect = "Allow"
      principals = [
        {
          type        = "AWS"
          identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/your_ecs_task_execution_role_name"] # <-- MUITO IMPORTANTE: Substitua pela Task Execution Role do seu ECS
        }
      ]
      actions   = ["secretsmanager:GetSecretValue"]
      resources = ["*"] # Ou use o ARN específico do segredo se quiser ser mais restritivo: ["${module.secrets_manager_docker_credentials.arn}"]
    }
  ]

  # Conteúdo do segredo (username e password)
  # ATENÇÃO: Nunca coloque sua senha diretamente no código Terraform em produção!
  # Use variáveis de ambiente, ferramentas como AWS Parameter Store, ou injete via CI/CD.
  # Para este exemplo, estamos mostrando a sintaxe, mas considere alternativas seguras.
  secret_string = jsonencode({
    username = "svc-bra-fts-eng-clou",
    password = "SUA_SENHA_DO_DOCKER_NEXUS_AQUI" # <<-- SUBSTITUA PELA SENHA REAL
  })

  # Não precisamos de senha randômica para este caso, pois estamos fornecendo uma
  create_random_password = false
  # random_password_length       = 64
  # random_password_override_special = "!@#$%^&*()_+"

  tags = {
    Environment = "Development"
    Project     = "DockerIntegration"
    ManagedBy   = "Terraform"
  }
}

# Data source para obter o ID da conta AWS, necessário para o ARN da política
data "aws_caller_identity" "current" {}


# No seu arquivo que chama o módulo secrets_manager

resource "aws_secretsmanager_secret" "docker_credentials" {
  name        = "docker/fmh-nexus-onefiserv-net-credentials"
  description = "Credenciais para o Docker Registry fmh.nexus.onefiserv.net"
  secret_string = jsonencode({
    username = "svc-bra-fts-eng-clou",
    password = var.docker_nexus_password # Use uma variável ou outra fonte segura
  })
}

resource "aws_secretsmanager_secret_policy" "docker_credentials_policy" {
  secret_arn = aws_secretsmanager_secret.docker_credentials.arn
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowEcsTaskExecutionRolesToReadSecret"
        Effect = "Allow"
        Principal = {
          # Crie uma lista de ARNs para o Principal.AWS
          AWS = [for arn in module.ecs_main.task_exec_iam_role_arn : arn] 
        }
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = aws_secretsmanager_secret.docker_credentials.arn
      }
    ]
  })
}

# No seu módulo secrets_manager_docker_credentials (mesma lógica do cenário 1)
module "secrets_manager_docker_credentials" {
  source = "terraform-aws-modules/secrets-manager/aws"
  name = "docker/fmh-nexus-onefiserv-net-credentials" 
  description = "Credenciais para o Docker Registry fmh.nexus.onefiserv.net"
  recovery_window_in_days = 7
  
  create_policy       = false 
  block_public_policy = true 

  secret_string = jsonencode({
    username = "svc-bra-fts-eng-clou",
    password = var.docker_nexus_password
  })

  tags = {
    Environment = "Development"
    Project     = "DockerIntegration"
    ManagedBy   = "Terraform"
  }
}

# No seu arquivo que chama o módulo secrets_manager

resource "aws_secretsmanager_secret" "docker_credentials" {
  name        = "docker/fmh-nexus-onefiserv-net-credentials"
  description = "Credenciais para o Docker Registry fmh.nexus.onefiserv.net"
  secret_string = jsonencode({
    username = "svc-bra-fts-eng-clou",
    password = var.docker_nexus_password # Use uma variável ou outra fonte segura
  })
}

# Criar a política separadamente para ter mais controle sobre a iteração
# (isso assume que o módulo secrets_manager não tem a opção de policy_statements diretamente iterável para cada role)

resource "aws_secretsmanager_secret_policy" "docker_credentials_policy" {
  secret_arn = aws_secretsmanager_secret.docker_credentials.arn
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # Iterar sobre o mapa de ARNs de roles e criar um statement para cada
      for role_name, role_arn in module.ecs_main.task_exec_iam_role_arn : {
        Sid       = "AllowEcsTaskExecutionRoleToReadSecret-${role_name}"
        Effect    = "Allow"
        Principal = {
          AWS = role_arn
        }
        Action    = ["secretsmanager:GetSecretValue"]
        Resource  = aws_secretsmanager_secret.docker_credentials.arn # Ou "*" se a política for para o segredo diretamente no módulo
      }
    ]
  })
}

# No seu módulo secrets_manager_docker_credentials (se ele permitir apenas uma política padrão)
# Certifique-se de que o módulo secrets_manager NÃO esteja criando sua própria política
# Se o módulo criar uma política padrão, você precisará desativá-la ou ajustá-la.
module "secrets_manager_docker_credentials" {
  source = "terraform-aws-modules/secrets-manager/aws"
  name = "docker/fmh-nexus-onefiserv-net-credentials" 
  description = "Credenciais para o Docker Registry fmh.nexus.onefiserv.net"
  recovery_window_in_days = 7
  
  # Certifique-se de que estas flags não criem uma política que entre em conflito
  create_policy       = false # Desativar a criação de política pelo módulo, pois estamos criando separadamente
  block_public_policy = true 

  secret_string = jsonencode({
    username = "svc-bra-fts-eng-clou",
    password = var.docker_nexus_password
  })

  tags = {
    Environment = "Development"
    Project     = "DockerIntegration"
    ManagedBy   = "Terraform"
  }
}


