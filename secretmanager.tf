# No seu arquivo que chama o módulo secrets_manager

module "secrets_manager_docker_credentials" {
  source = "terraform-aws-modules/secrets-manager/aws" # Confirme o source do seu módulo

  name        = "docker/fmh-nexus-onefiserv-net-credentials"
  description = "Credenciais para o Docker Registry fmh.nexus.onefiserv.net"

  # Você precisa passar o secret_string como um input para o MÓDULO,
  # não tentar configurá-lo como um argumento de um 'resource' dentro do seu código chamador.
  # O nome da variável de input depende do módulo. A maioria dos módulos usa 'secret_string'.
  secret_string = jsonencode({
    username = "svc-bra-fts-eng-clou",
    password = var.docker_nexus_password # Use uma variável ou outra fonte segura
  })

  # As configurações de política devem ser passadas como input para o módulo,
  # ou gerenciadas por um recurso aws_secretsmanager_secret_policy separado,
  # conforme discutimos anteriormente para maior flexibilidade.

  # Se o módulo suporta a criação de política:
  create_policy       = true # Se o módulo criar a política, mantenha true
  block_public_policy = true
  policy_statements = [
    {
      sid    = "AllowEcsTaskExecutionRolesToReadSecret"
      effect = "Allow"
      principals = [
        # Se module.ecs_main.task_exec_iam_role_arn for uma lista, use a sintaxe abaixo:
        {
          type = "AWS"
          identifiers = [for arn in module.ecs_main.task_exec_iam_role_arn : arn]
        }
      ]
      actions   = ["secretsmanager:GetSecretValue"]
      resources = ["*"] # O ARN específico do segredo é tratado pelo módulo se policy_statements estiver no módulo
    }
  ]

  # Se o módulo NÃO suportar a criação de política, ou você preferir gerenciar separadamente:
  # create_policy = false # Desabilite a criação de política pelo módulo
  # E então, crie o resource aws_secretsmanager_secret_policy *fora* deste módulo block,
  # como detalhado na resposta anterior, usando aws_secretsmanager_secret_policy.docker_credentials_policy.

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
