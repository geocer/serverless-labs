import boto3

def adicionar_tags_em_instancias(regiao, lista_ids_excluidas):
    """
    Adiciona tags em todas as instâncias EC2 em uma região, exceto as da lista.

    Args:
        regiao: A região da AWS a ser consultada (ex: 'us-east-1').
        lista_ids_excluidas: Uma lista com os IDs das instâncias a serem excluídas.
    """

    ec2 = boto3.client('ec2', region_name=regiao)
    tags = [
        {'Key': 'tag1', 'Value': 'valor1'},
        {'Key': 'tag2', 'Value': 'valor2'},
        {'Key': 'tag3', 'Value': 'valor3'}
    ]

    try:
        resposta = ec2.describe_instances()
        for reserva in resposta['Reservations']:
            for instancia in reserva['Instances']:
                id_instancia = instancia['InstanceId']

                # Verifica se a instância está na lista de exclusão
                if id_instancia not in lista_ids_excluidas:
                    ec2.create_tags(
                        Resources=[id_instancia],
                        Tags=tags
                    )
                    print(f"Tags adicionadas à instância {id_instancia}")

    except Exception as e:
        print(f"Erro ao adicionar tags: {e}")

# Exemplo de uso
regiao = 'us-east-1'  # Substitua pela sua região
lista_ids_excluidas = ['i-xxxxxxxxxxxxxxxxx', 'i-yyyyyyyyyyyyyyyyy']  # Substitua pelos IDs das instâncias a serem excluídas

adicionar_tags_em_instancias(regiao, lista_ids_excluidas)
