import boto3
import time
import datetime

def validate_ec2_stopped(ec2_stopped):
    notify =
    ec2 = boto3.client('ec2')
    lambda_start_time = datetime.datetime.now()
    lambda_timeout = datetime.timedelta(minutes=14)  # Deixa 1 minuto de folga

    instances_to_retry = {}  # Armazena instâncias para retentar

    for instance_ids in ec2_stopped:
        response = ec2.describe_instances(InstanceIds=[instance_ids])

        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                instance_id = instance['InstanceId']

                # Verifica se a instância já estava em retentativa
                if instance_id in instances_to_retry:
                    wait_time = instances_to_retry[instance_id]
                else:
                    wait_time = 0

                status_checks_ok = False
                start_time = datetime.datetime.now()
                max_wait_time = 60  # 1 minuto

                while (datetime.datetime.now() - start_time).seconds < max_wait_time:
                    status_checks = ec2.describe_instance_status(InstanceIds=[instance_id])

                    if status_checks['InstanceStatuses']:
                        instance_status = status_checks['InstanceStatuses'][0]
                        system_status = instance_status['SystemStatus']['Status']
                        instance_status_check = instance_status['InstanceStatus']['Status']

                        print(
                            f"Instance {instance_id}: System Status - {system_status}, "
                            f"Instance Status - {instance_status_check}"
                        )

                        if system_status == 'ok' and instance_status_check == 'ok':
                            status_checks_ok = True
                            break  # Status checks OK, sai do loop
                        else:
                            print(f"Instance {instance_id} has status checks failing. Waiting...")
                            time.sleep(5)  # Espera antes de verificar novamente
                    else:
                        print(f"Instance {instance_id} has no status checks. Waiting...")
                        time.sleep(5)  # Espera antes de verificar novamente

                    # Verifica o tempo restante do Lambda
                    if datetime.datetime.now() - lambda_start_time > lambda_timeout:
                        print(
                            f"Lambda timeout reached. Saving instance {instance_id} for retry."
                        )
                        instances_to_retry[instance_id] = (datetime.datetime.now() - start_time).seconds
                        break  # Sai do loop while
                
                # Se status checks OK ou timeout do Lambda
                if status_checks_ok:
                    print(f"Instance {instance_id} status checks are OK.")
                else:
                    if instance_id not in instances_to_retry:
                        notify.append(
                            f" {instance_ids} : System Status - {system_status}, "
                            f"Instance Status - {instance_status_check} "
                        )

        # Se timeout do Lambda, sai do loop for
        if instances_to_retry:
            break

    if len(notify) > 0 or instances_to_retry:
        topico_arn = "arn:aws:sns:sa-east-1:650501285453:cloud-latam-topic"
        assunto = "WARN|EC2AutoStopLowers|fdaws-brazil-se-dc1homolog-prod"
        c_mensagem = "".join(map(str, notify))
        mensagem = f"Some instance(s) has status checks failing: {c_mensagem}"
        if instances_to_retry:
            mensagem += f" Instances to retry: {list(instances_to_retry.keys())}"
        sent_email_sns(topico_arn, assunto, mensagem)
    else:
        topico_arn = "arn:aws:sns:sa-east-1:650501285453:cloud-latam-topic"
        # Adicione aqui o código para enviar uma mensagem de sucesso, se necessário
