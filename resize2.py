import boto3

def change_instance_family(instance_ids, new_instance_type):
    """
    Muda a família de instâncias EC2.

    Args:
        instance_ids: Uma lista de IDs de instâncias.
        new_instance_type: O novo tipo de instância.

    Returns:
        None
    """

    ec2 = boto3.client('ec2')

    for instance_id in instance_ids:
        try:
            response = ec2.stop_instances(InstanceIds=[instance_id])
            waiter = ec2.get_waiter('instance_stopped')
            waiter.wait(InstanceIds=[instance_id])

            response = ec2.modify_instance_attribute(
                InstanceId=instance_id,
                Attribute='instanceType',
                Value=new_instance_type
            )

            response = ec2.start_instances(InstanceIds=[instance_id])
            waiter = ec2.get_waiter('instance_running')
            waiter.wait(InstanceIds=[instance_id])

            print(f"Instância {instance_id} atualizada para {new_instance_type}")
        except Exception as e:
            print(f"Erro ao atualizar instância {instance_id}: {e}")

# Exemplo de uso
instance_ids = ['i-1234567890abcdef0', 'i-0987654321fedcba']
new_instance_type = 't3.medium'

change_instance_family(instance_ids, new_instance_type)
