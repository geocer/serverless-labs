import boto3

def verificar_instancias_iniciadas(instance_ids):
    """
    Verifica se todas as instâncias em uma lista foram iniciadas.

    Args:
        instance_ids (list): Lista de IDs de instâncias.

    Returns:
        bool: True se todas as instâncias foram iniciadas, False caso contrário.
    """
    try:
        ec2 = boto3.client('ec2')
        response = ec2.describe_instances(InstanceIds=instance_ids)

        instancias_iniciadas = True
        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                if instance['State']['Name'] != 'running':
                    instancias_iniciadas = False
                    print(f"Instância {instance['InstanceId']} não está iniciada.")
                    break
            if not instancias_iniciadas:
                break

        return instancias_iniciadas

    except Exception as e:
        print(f"Erro ao verificar instâncias: {e}")
        return False

# Exemplo de uso
instance_ids = ['i-0123456789abcdef0', 'i-0123456789abcdef1', 'i-0123456789abcdef2']  # Substitua pelos seus IDs de instâncias

if verificar_instancias_iniciadas(instance_ids):
    print("Todas as instâncias foram iniciadas com sucesso!")
else:
    print("Nem todas as instâncias foram iniciadas.")
