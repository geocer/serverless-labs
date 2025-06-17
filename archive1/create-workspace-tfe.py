import requests
import json
import os

# Configurações
TERRAFORM_CLOUD_TOKEN = os.environ.get("TERRAFORM_CLOUD_TOKEN")
ORGANIZATION_NAME = "your-organization-name"  # Substitua pelo nome da sua organização
PROJECT_ID = "your-project-id"  # Substitua pelo ID do seu projeto

if not TERRAFORM_CLOUD_TOKEN:
    raise EnvironmentError("A variável de ambiente TERRAFORM_CLOUD_TOKEN não está definida.")

headers = {
    "Authorization": f"Bearer {TERRAFORM_CLOUD_TOKEN}",
    "Content-Type": "application/vnd.api+json",
}

def create_terraform_cloud_workspace(workspace_name, description=None, vcs_repo=None):
    """
    Cria um novo workspace no Terraform Cloud dentro de um projeto específico.

    Args:
        workspace_name (str): O nome desejado para o novo workspace.
        description (str, optional): Uma descrição para o workspace. Defaults to None.
        vcs_repo (dict, optional): Detalhes do repositório VCS a ser conectado. Defaults to None.
                                     Exemplo:
                                     {
                                         "identifier": "your-vcs-org/your-repo",
                                         "oauth_token_id": "ot-xxxxxxxxxxxxxxxxx",
                                         "branch": "main",
                                         "ingress_submodules": False
                                     }

    Returns:
        dict or None: Os dados do workspace criado em caso de sucesso, None em caso de falha.
    """
    api_url = f"https://app.terraform.io/api/v2/projects/{PROJECT_ID}/workspaces"

    payload = {
        "data": {
            "type": "workspaces",
            "attributes": {
                "name": workspace_name,
                "description": description,
                "operations": True,  # Habilita operações no workspace
                "allow-empty-apply": False, # Impede applies vazios por padrão
                "execution-mode": "remote" # Define o modo de execução como remoto (Terraform Cloud)
            }
        }
    }

    if vcs_repo:
        payload["data"]["relationships"] = {
            "vcs-repo": {
                "data": {
                    "type": "vcs-repos",
                    "id": vcs_repo["oauth_token_id"]  # O ID aqui é o OAuth Token ID
                }
            }
        }
        payload["included"] = [
            {
                "type": "vcs-repos",
                "id": vcs_repo["oauth_token_id"],
                "attributes": {
                    "identifier": vcs_repo["identifier"],
                    "branch": vcs_repo.get("branch", "main"),
                    "ingress-submodules": vcs_repo.get("ingress_submodules", False)
                }
            }
        ]

    try:
        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status()  # Levanta uma exceção para códigos de status de erro
        return response.json()["data"]
    except requests.exceptions.RequestException as e:
        print(f"Erro ao criar o workspace '{workspace_name}': {e}")
        if response is not None:
            print(f"Detalhes da resposta: {response.status_code} - {response.text}")
        return None

if __name__ == "__main__":
    new_workspace_name = "my-new-workspace"
    workspace_description = "Este é um workspace criado via script Python."

    # Exemplo sem conexão VCS
    created_workspace = create_terraform_cloud_workspace(new_workspace_name, workspace_description)
    if created_workspace:
        print(f"Workspace '{created_workspace['attributes']['name']}' criado com sucesso!")
        print(f"ID do Workspace: {created_workspace['id']}")

    print("-" * 30)

    # Exemplo com conexão VCS (substitua com suas informações)
    vcs_configuration = {
        "identifier": "your-github-org/your-repo-name",
        "oauth_token_id": "ot-xxxxxxxxxxxxxxxxx",  # Obtenha este ID nas configurações da sua organização
        "branch": "develop",
        "ingress_submodules": True
    }
    new_workspace_with_vcs_name = "my-workspace-with-vcs"
    created_workspace_vcs = create_terraform_cloud_workspace(new_workspace_with_vcs_name, "Workspace com VCS conectado.", vcs_configuration)
    if created_workspace_vcs:
        print(f"Workspace '{created_workspace_vcs['attributes']['name']}' criado com sucesso com VCS!")
        print(f"ID do Workspace: {created_workspace_vcs['id']}")
