import requests
import json
import os

# --- Configurações da API do Harness ---
# É altamente recomendável usar variáveis de ambiente ou um sistema de gerenciamento de segredos
# para armazenar sua chave de API e outras informações sensíveis.
HARNESS_API_KEY = os.getenv("HARNESS_API_KEY") # Exemplo: "YOUR_HARNESS_API_KEY"
HARNESS_BASE_URL = "https://app.harness.io/gateway/ng/api" # URL base da API do Harness (pode variar para outras regiões/instâncias)

# --- Informações do seu Ambiente Harness ---
ORG_ID = "YOUR_ORGANIZATION_ID" # Substitua pelo ID da sua organização
PROJECT_ID = "YOUR_PROJECT_ID"   # Substitua pelo ID do seu projeto

# --- Detalhes do Segredo a Ser Criado ---
SECRET_NAME = "my_new_secret_text"           # Nome do segredo
SECRET_IDENTIFIER = "my_new_secret_text_id"   # Identificador único para o segredo (usado em referências)
SECRET_VALUE = "this_is_my_super_secret_value" # O valor real do segredo
DESCRIPTION = "This is a text secret created via Python script." # Descrição opcional

def create_harness_secret_text(
    api_key: str,
    base_url: str,
    org_id: str,
    project_id: str,
    secret_name: str,
    secret_identifier: str,
    secret_value: str,
    description: str = ""
) -> dict:
    """
    Cria um segredo de texto no Harness.

    Args:
        api_key (str): Sua chave de API do Harness.
        base_url (str): A URL base da API do Harness (ex: "https://app.harness.io/gateway/ng/api").
        org_id (str): O ID da sua organização Harness.
        project_id (str): O ID do seu projeto Harness.
        secret_name (str): O nome que será exibido para o segredo.
        secret_identifier (str): O identificador único para o segredo.
        secret_value (str): O valor do segredo.
        description (str, optional): Uma descrição para o segredo. Defaults to "".

    Returns:
        dict: A resposta da API do Harness (JSON parseado).
    """
    if not api_key:
        raise ValueError("A chave de API do Harness não foi fornecida. Defina a variável de ambiente HARNESS_API_KEY.")

    url = f"{base_url}/v2/secrets"
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json"
    }

    payload = {
        "secret": {
            "type": "SecretText",
            "name": secret_name,
            "identifier": secret_identifier,
            "description": description,
            "orgIdentifier": org_id,
            "projectIdentifier": project_id,
            "spec": {
                "secretManagerIdentifier": "harnessSecretManager", # Geralmente é o gerenciador padrão
                "valueType": "Inline",
                "value": secret_value
            }
        }
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        response.raise_for_status() # Lança uma exceção para códigos de status HTTP 4xx/5xx
        return response.json()
    except requests.exceptions.HTTPError as err:
        print(f"Erro HTTP ao criar o segredo: {err}")
        print(f"Resposta do servidor: {response.text}")
        return {"error": str(err), "response_text": response.text}
    except requests.exceptions.RequestException as err:
        print(f"Erro ao conectar ou enviar a requisição: {err}")
        return {"error": str(err)}

if __name__ == "__main__":
    print("Tentando criar segredo de texto no Harness...")
    result = create_harness_secret_text(
        api_key=HARNESS_API_KEY,
        base_url=HARNESS_BASE_URL,
        org_id=ORG_ID,
        project_id=PROJECT_ID,
        secret_name=SECRET_NAME,
        secret_identifier=SECRET_IDENTIFIER,
        secret_value=SECRET_VALUE,
        description=DESCRIPTION
    )

    if "error" in result:
        print("\nFalha ao criar o segredo.")
        print(result)
    else:
        print("\nSegredo criado com sucesso!")
        print(json.dumps(result, indent=4))
