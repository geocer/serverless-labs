import boto3

def get_specific_tags(instance_ids, tags_to_extract):
    """
    Extrai tags específicas de uma lista de instâncias AWS.

    Args:
        instance_ids: Uma lista de IDs de instâncias.
        tags_to_extract: Uma lista de nomes de tags a serem extraídas.

    Returns:
        Um dicionário onde as chaves são os IDs das instâncias e os valores são dicionários contendo as tags extraídas.
    """

    ec2 = boto3.client('ec2')

    response = ec2.describe_instances(InstanceIds=instance_ids)

    instance_tags = {}
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            instance_id = instance['InstanceId']
            tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', []) if tag['Key'] in tags_to_extract}
            instance_tags[instance_id] = tags

    return instance_tags

# Exemplo de uso
instance_ids = ['i-1234567890abcdef0', 'i-0987654321fedcba']
tags_to_extract = ['Name', 'responsavel']

result = get_specific_tags(instance_ids, tags_to_extract)

print(result)
