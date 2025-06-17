import boto3

def enviar_email_sns(topico_arn, assunto, mensagem):
    """
    Envia um e-mail para os inscritos em um tópico SNS.

    Args:
        topico_arn (str): ARN do tópico SNS.
        assunto (str): Assunto do e-mail.
        mensagem (str): Corpo do e-mail.
    """
    try:
        sns_client = boto3.client('sns')

        # Publica a mensagem no tópico SNS
        response = sns_client.publish(
            TopicArn=topico_arn,
            Subject=assunto,
            Message=mensagem
        )

        print(f"E-mail enviado com sucesso! MessageId: {response['MessageId']}")

    except Exception as e:
        print(f"Erro ao enviar e-mail: {e}")

# Substitua pelos seus valores
topico_arn = "arn:aws:sns:sua-regiao:sua-conta:nome-do-seu-topico"
assunto = "Assunto do seu e-mail"
mensagem = "Corpo do seu e-mail."

enviar_email_sns(topico_arn, assunto, mensagem)
