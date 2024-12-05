import boto3

def resize_ec2_instances(instances_data):
    """
    Redimensiona instâncias EC2 com base em uma lista de dados.

    Args:
        instances_data: Uma lista de dicionários com os dados da instância.
            Cada dicionário deve conter os seguintes chaves:
            - 'Name': O nome da tag da instância.
            - 'NewSize': O novo tamanho da instância.
    """

    ec2 = boto3.client('ec2')

    for instance in instances_data:
        try:
            # Filtrar as instâncias por nome da tag
            response = ec2.describe_instances(
                Filters=[
                    {
                        'Name': 'tag:Name',
                        'Values': [instance['Name']]
                    }
                ]
            )

            # Obter o ID da primeira instância encontrada
            instance_id = response['Reservations'][0]['Instances'][0]['InstanceId']

            # Desligar a instância
            ec2.stop_instances(InstanceIds=[instance_id])

            # Esperar a instância desligar
            waiter = ec2.get_waiter('instance_stopped')
            waiter.wait(InstanceIds=[instance_id])

            # Modificar o tamanho da instância
            ec2.modify_instance_attribute(
                InstanceId=instance_id,
                Attribute='instanceType',
                Value=instance['NewSize']
            )

            # Ligar a instância
            ec2.start_instances(InstanceIds=[instance_id])

            print(f"Instância {instance['Name']} redimensionada para {instance['NewSize']}")

        except Exception as e:
            print(f"Erro ao redimensionar a instância {instance['Name']}: {str(e)}")

# Exemplo de uso:
instances_data = [
    {'Name': 'minha-instancia-1', 'NewSize': 't2.medium'},
    {'Name': 'minha-instancia-2', 'NewSize': 'm5.large'}
]

resize_ec2_instances(instances_data)
