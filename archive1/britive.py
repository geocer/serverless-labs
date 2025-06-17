import requests
import json

# Configurações
BRITIVE_AUTH_URL = "https://api.britive.com/v1/auth/token"
BRITIVE_CREDENTIALS_URL = "https://api.britive.com/v1/aws/credentials"
USERNAME = "seu_usuario"
PASSWORD = "sua_senha"
AWS_ACCOUNT_ID = "123456789012"  # Substitua pelo ID da conta AWS

# Função para autenticar no Britive e obter o token de acesso
def authenticate_britive(username, password):
    headers = {
        "Content-Type": "application/json"
    }
    payload = {
        "username": username,
        "password": password
    }
    response = requests.post(BRITIVE_AUTH_URL, headers=headers, json=payload)
    if response.status_code == 200:
        return response.json().get("access_token")
    else:
        raise Exception(f"Falha na autenticação: {response.status_code} - {response.text}")

# Função para obter as credenciais da AWS
def get_aws_credentials(access_token, aws_account_id):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    response = requests.get(f"{BRITIVE_CREDENTIALS_URL}/{aws_account_id}", headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Falha ao obter credenciais: {response.status_code} - {response.text}")

# Função principal
def main():
    try:
        # Autenticar no Britive
        access_token = authenticate_britive(USERNAME, PASSWORD)
        print("Autenticação no Britive bem-sucedida!")

        # Obter credenciais da AWS
        aws_credentials = get_aws_credentials(access_token, AWS_ACCOUNT_ID)
        print("Credenciais da AWS obtidas com sucesso!")
        print(json.dumps(aws_credentials, indent=4))

        # Aqui você pode usar as credenciais da AWS para autenticar em serviços AWS
        # Exemplo: boto3.client('s3', aws_access_key_id=aws_credentials['AccessKeyId'],
        #                      aws_secret_access_key=aws_credentials['SecretAccessKey'],
        #                      aws_session_token=aws_credentials['SessionToken'])

    except Exception as e:
        print(f"Erro: {e}")

if __name__ == "__main__":
    main()