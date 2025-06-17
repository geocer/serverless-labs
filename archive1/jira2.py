import jira

# Configurações
JIRA_URL = 'https://your-jira-instance.atlassian.net'  # URL da sua instância Jira
PROJECT_KEY = 'YOUR_PROJECT_KEY'  # Chave do seu projeto Jira
FEATURE_KEY = 'FEATURE-1'  # Chave da Feature onde a task será criada
SUMMARY = 'Título da sua task'  # Título da task
DESCRIPTION = 'Descrição detalhada da sua task'  # Descrição da task
PAT = 'SEU_PERSONAL_ACCESS_TOKEN'  # Seu Personal Access Token

# Autenticação com PAT
options = {'server': JIRA_URL}
jira_instance = jira.JIRA(options, token_auth=PAT)

# Função para criar a task
def create_jira_task(issue, project_key, summary, description, feature_key):
    try:
        # Busca a Feature
        feature = jira_instance.issue(feature_key)

        # Cria a task dentro da Feature
        new_issue = issue.create_issue(
            project=project_key,
            summary=summary,
            description=description,
            parent={'key': feature.key}  # Define a Feature como pai da task
        )

        print(f"Task criada com sucesso: {new_issue.key}")
    except Exception as e:
        print(f"Erro ao criar task: {e}")

# Cria a task
create_jira_task(jira_instance, PROJECT_KEY, SUMMARY, DESCRIPTION, FEATURE_KEY)
