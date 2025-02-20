import boto3

def adicionar_tags_em_instancias(regiao, lista_ids_instancias):
    """
    Adiciona tags em instâncias EC2 especificadas em uma lista.

    Args:
        regiao: A região da AWS a ser consultada (ex: 'us-east-1').
        lista_ids_instancias: Uma lista com os IDs das instâncias EC2.
    """

    ec2 = boto3.client('ec2', region_name=regiao)
    tags = [
        {'Key': 'tag1', 'Value': 'valor1'},
        {'Key': 'tag2', 'Value': 'valor2'},
        {'Key': 'tag3', 'Value': 'valor3'}
    ]

    try:
        for id_instancia in lista_ids_instancias:
            ec2.create_tags(
                Resources=[id_instancia],
                Tags=tags
            )
            print(f"Tags adicionadas à instância {id_instancia}")

    except Exception as e:
        print(f"Erro ao adicionar tags: {e}")

# Exemplo de uso
regiao = 'us-east-1'  # Substitua pela sua região
lista_ids_instancias = ['i-xxxxxxxxxxxxxxxxx', 'i-yyyyyyyyyyyyyyyyy']  # Substitua pelos IDs das suas instâncias

adicionar_tags_em_instancias(regiao, lista_ids_instancias)
