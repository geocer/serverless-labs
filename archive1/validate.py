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
    
    import boto3

def validate_ec2_stopped(ec2_stopped):
    notify = []
    ec2 = boto3.client('ec2')

    for instance_ids in ec2_stopped:
        response = ec2.describe_instances(InstanceIds=[instance_ids])

        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                instance_id = instance['InstanceId']
                status_checks = ec2.describe_instance_status(InstanceIds=[instance_id])

                if status_checks['InstanceStatuses']:  # Verifica se há status checks
                    instance_status = status_checks['InstanceStatuses'][0]
                    system_status = instance_status['SystemStatus']['Status']
                    instance_status_check = instance_status['InstanceStatus']['Status']

                    print(f"Instance {instance_id}: System Status - {system_status}, Instance Status - {instance_status_check}")

                    if system_status != 'ok' or instance_status_check != 'ok':
                        print(f"Instance {instance_id} has status checks failing.")
                        notify.append(f" {instance_ids} : System Status - {system_status}, Instance Status - {instance_status_check} ")
                        continue
                else:
                    print(f"Instance {instance_id} has no status checks.")
                    notify.append(f" {instance_ids} : No status checks available. ")
                    continue

    if len(notify) > 0:
        topico_arn = "arn:aws:sns:sa-east-1:650501285453:cloud-latam-topic"
        assunto = "WARN|EC2AutoStopLowers|fdaws-brazil-se-dc1homolog-prod"
        c_mensagem = "".join(map(str, notify))
        mensagem = f"Some instance(s) has status checks failing: {c_mensagem}"
        sent_email_sns(topico_arn, assunto, mensagem)
    else:
        topico_arn = "arn:aws:sns:sa-east-1:650501285453:cloud-latam-topic"
        # Adicione aqui o código para enviar uma mensagem de sucesso, se necessário

    
    notify.append("" + instance_ids + ":" + instance['State']['Name'] + " - Responsável: " + next((tag['Value'] for tag in instance['Tags'] if tag['Key'] == 'responsável'), 'Não encontrado') + "")

print(f"Instance {instance_id}: System Status {system_status}, Instance Status {instance_status_check}, Responsável: {next((tag['Value'] for tag in status_checks['InstanceStatuses'][0]['Tags'] if tag['Key'] == 'Responsavel'), 'Não encontrado')}")
