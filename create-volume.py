service: ec2-volume-creation-monitor

frameworkVersion: '3'

provider:
  name: aws
  runtime: python3.9
  region: sa-east-1 # Substitua pela sua região AWS
  iam:
    role:
      statements:
        - Effect: Allow
          Action:
            - ec2:DescribeVolumes
            - ec2:DescribeInstances
            - logs:CreateLogGroup
            - logs:CreateLogStream
            - logs:PutLogEvents
          Resource: "*"

functions:
  volume_creation_handler:
    handler: handler.volume_created
    events:
      - eventBridge:
          pattern:
            source:
              - aws.ec2
            detail-type:
              - AWS API Call via CloudTrail
            detail:
              eventSource:
                - ec2.amazonaws.com
              eventName:
                - CreateVolume

import boto3
import json
from datetime import datetime, timezone, timedelta

ec2 = boto3.client('ec2')

def volume_created(event, context):
    print(f"Evento recebido: {json.dumps(event)}")

    try:
        volume_id = event['detail']['responseElements']['volumeId']
        create_time_str = event['detail']['responseElements']['createTime']

        # Converter a string de tempo de criação do volume para um objeto datetime
        volume_create_time = datetime.fromisoformat(create_time_str.replace('Z', '+00:00'))

        # Obter informações sobre o volume para encontrar a instância anexada
        volume_response = ec2.describe_volumes(VolumeIds=[volume_id])

        if volume_response and volume_response['Volumes']:
            volume = volume_response['Volumes'][0]
            if 'Attachments' in volume and volume['Attachments']:
                attachment = volume['Attachments'][0]
                instance_id = attachment['InstanceId']
                print(f"Volume {volume_id} anexado à instância: {instance_id}")

                # Obter informações sobre a instância EC2
                instance_response = ec2.describe_instances(InstanceIds=[instance_id])

                if instance_response and instance_response['Reservations'] and instance_response['Reservations'][0]['Instances']:
                    instance = instance_response['Reservations'][0]['Instances'][0]
                    instance_launch_time = instance['LaunchTime'].replace(tzinfo=timezone.utc)

                    # Calcular a diferença de tempo
                    time_difference = volume_create_time - instance_launch_time
                    time_difference_minutes = time_difference.total_seconds() / 60

                    print(f"Hora de criação do volume (UTC): {volume_create_time}")
                    print(f"Hora de lançamento da instância (UTC): {instance_launch_time}")
                    print(f"Diferença de tempo em minutos: {time_difference_minutes}")

                    if 0 <= time_difference_minutes <= 5:
                        print(f"A data de criação do volume está dentro da janela de 5 minutos do lançamento da instância.")
                        # Adicione aqui qualquer lógica adicional que você precise executar
                    else:
                        print(f"A data de criação do volume NÃO está dentro da janela de 5 minutos do lançamento da instância.")
                else:
                    print(f"Não foi possível encontrar informações para a instância {instance_id}.")
            else:
                print(f"O volume {volume_id} não está anexado a nenhuma instância.")
        else:
            print(f"Não foi possível encontrar informações para o volume {volume_id}.")

    except Exception as e:
        print(f"Erro ao processar o evento de criação de volume: {e}")

