import boto3
import jira
import pandas as pd

def get_aws_recommendations(client, resource_type):
    response = client.get_recommendations()
    recommendations = response['Recommendations']
    return [rec for rec in recommendations if rec['Finding'] == resource_type]

def create_jira_card(issue, project_key, summary, description):
    try:
        new_issue = issue.create_issue(project=project_key, summary=summary, description=description)
        print(f"Card criado com sucesso: {new_issue.key}")
    except Exception as e:
        print(f"Erro ao criar card: {e}")

def main():
    # Configuração das credenciais AWS e Jira
    # ... (Substitua pelas suas credenciais)

    # Conectar ao Jira
    options = {'server': 'https://your-jira-instance.atlassian.net'}
    jira_instance = jira.JIRA(options, basic_auth=(username, password))

    # Listar as contas AWS
    accounts = ['account1', 'account2', ...]

    for account in accounts:
        # Assumir a role na conta AWS
        sts = boto3.client('sts')
        assumed_role_object = sts.assume_role(
            RoleArn="arn:aws:iam::your-role-arn",
            RoleSessionName="AssumeRoleSession1"
        )
        credentials = assumed_role_object['Credentials']

        # Criar um cliente para o Compute Optimizer
        client = boto3.client('compute-optimizer',
                             aws_access_key_id=credentials['AccessKeyId'],
                             aws_secret_access_key=credentials['SecretAccessKey'],
                             aws_session_token=credentials['SessionToken'])

        # Obter recomendações para EC2
        ec2_recommendations = get_aws_recommendations(client, 'OverProvisioned')
        for rec in ec2_recommendations:
            summary = f"Instância EC2 OverProvisioned"
            description = f"""
            Instance ID: {rec['Recommendation']['ResourceDetails']['EC2Instance']['InstanceId']}
            Recommended Instance Type: {rec['Recommendation']['RecommendationDetails']['EC2Instance']['RecommendedInstanceType']}
            Account ID: {account}
            """
            create_jira_card(jira_instance, 'YOUR_PROJECT_KEY', summary, description)

        # Obter recomendações para EBS
        ebs_recommendations = get_aws_recommendations(client, 'NotOptimized')
        for rec in ebs_recommendations:
            summary = f"Volume EBS Not Optimized"
            description = f"""
            Volume ID: {rec['Recommendation']['ResourceDetails']['EBSVolume']['VolumeId']}
            Recommended Volume Type: {rec['Recommendation']['RecommendationDetails']['EBSVolume']['RecommendedVolumeType']}
            Recommended IOPS: {rec['Recommendation']['RecommendationDetails']['EBSVolume']['RecommendedIOPS']}
            Account ID: {account}
            """
            create_jira_card(jira_instance, 'YOUR_PROJECT_KEY', summary, description)

if __name__ == "__main__":
    main()
