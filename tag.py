import boto3

def get_instance_tags(instance_ids):
    """
    Extrai as tags de uma lista de instâncias AWS.

    Args:
        instance_ids: Uma lista de IDs de instâncias.

    Returns:
        Um dicionário onde as chaves são os IDs das instâncias e os valores são listas de dicionários representando as tags.
    """

    ec2 = boto3.client('ec2')

    response = ec2.describe_instances(InstanceIds=instance_ids)

    instance_tags = {}
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            instance_id = instance['InstanceId']
            tags = instance.get('Tags', [])
            instance_tags[instance_id] = tags

    return instance_tags

# Exemplo de uso
instance_ids = ['i-1234567890abcdef0', 'i-0987654321fedcba']
result = get_instance_tags(instance_ids)

print(result)
