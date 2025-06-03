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
