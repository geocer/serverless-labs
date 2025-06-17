import boto3
import argparse
import logging
import os

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_aws_client(service_name, region_name='sa-east-1'):
    """Retorna um cliente boto3 para o serviço especificado."""
    try:
        return boto3.client(service_name, region_name=region_name)
    except Exception as e:
        logging.error(f"Erro ao obter cliente para {service_name}: {e}")
        raise

def get_aws_resource(service_name, region_name='sa-east-1'):
    """Retorna um recurso boto3 para o serviço especificado."""
    try:
        return boto3.resource(service_name, region_name=region_name)
    except Exception as e:
        logging.error(f"Erro ao obter recurso para {service_name}: {e}")
        raise

def create_vpc_endpoints(service_names, vpc_id, subnet_ids, security_group_ids, region='sa-east-1'):
    """
    Cria VPC Endpoints para os serviços especificados.
    Assume que os IDs da VPC, Subnets e Security Groups já existem.
    """
    ec2_client = get_aws_client('ec2', region)
    logging.info(f"Iniciando a criação de VPC Endpoints na VPC: {vpc_id}")

    created_endpoints = []
    for service_name in service_names:
        try:
            logging.info(f"Criando VPC Endpoint para o serviço: {service_name}")
            response = ec2_client.create_vpc_endpoint(
                VpcId=vpc_id,
                ServicePrivateDnsName=service_name, # Para endpoints de interface, o nome do serviço geralmente é o privado
                VpcEndpointType='Interface', # Ou 'Gateway' para S3 e DynamoDB
                SubnetIds=subnet_ids,
                SecurityGroupIds=security_group_ids,
                PrivateDnsEnabled=True,
                TagSpecifications=[
                    {
                        'ResourceType': 'vpc-endpoint',
                        'Tags': [
                            {'Key': 'Name', 'Value': f"{service_name.split('.')[-2]}-endpoint"},
                            {'Key': 'ManagedBy', 'Value': 'HarnessPipeline'}
                        ]
                    },
                ]
            )
            endpoint_id = response['VpcEndpoint']['VpcEndpointId']
            created_endpoints.append(endpoint_id)
            logging.info(f"VPC Endpoint '{endpoint_id}' para '{service_name}' criado com sucesso.")
        except Exception as e:
            logging.error(f"Erro ao criar VPC Endpoint para '{service_name}': {e}")
    return created_endpoints

def identify_routable_network(vpc_id, region='sa-east-1'):
    """
    Identifica uma subnet roteável em uma VPC que tenha uma tabela de roteamento
    com uma rota para um Transit Gateway.
    Retorna o ID da subnet.
    """
    ec2_client = get_aws_client('ec2', region)
    logging.info(f"Identificando subnet roteável na VPC: {vpc_id}")

    try:
        response = ec2_client.describe_route_tables(
            Filters=[
                {'Name': 'vpc-id', 'Value': vpc_id},
                {'Name': 'route.state', 'Values': ['active']}
            ]
        )

        for rt in response['RouteTables']:
            for route in rt.get('Routes', []):
                # Procura por uma rota para um Transit Gateway
                if 'TransitGatewayId' in route and route['State'] == 'active':
                    logging.info(f"Tabela de roteamento '{rt['RouteTableId']}' encontrada com rota para Transit Gateway: {route['TransitGatewayId']}")

                    # Encontra uma associação de subnet para esta tabela de roteamento
                    for association in rt.get('Associations', []):
                        if 'SubnetId' in association and association['SubnetId']:
                            logging.info(f"Subnet '{association['SubnetId']}' associada a uma tabela de roteamento com rota para TGW. Considerada roteável.")
                            return association['SubnetId']
        logging.warning(f"Nenhuma subnet roteável com rota para Transit Gateway encontrada na VPC: {vpc_id}")
        return None
    except Exception as e:
        logging.error(f"Erro ao identificar rede roteável: {e}")
        return None

def create_private_nat_gateway(subnet_id, region='sa-east-1'):
    """
    Cria um NAT Gateway privado na subnet especificada.
    Retorna o ID do NAT Gateway.
    """
    ec2_client = get_aws_client('ec2', region)
    logging.info(f"Criando NAT Gateway privado na subnet: {subnet_id}")

    try:
        response = ec2_client.create_nat_gateway(
            SubnetId=subnet_id,
            ConnectivityType='private', # NAT Gateway privado
            TagSpecifications=[
                {
                    'ResourceType': 'natgateway',
                    'Tags': [
                        {'Key': 'Name', 'Value': 'PrivateNATGateway'},
                        {'Key': 'ManagedBy', 'Value': 'HarnessPipeline'}
                    ]
                },
            ]
        )
        nat_gateway_id = response['NatGateway']['NatGatewayId']
        logging.info(f"NAT Gateway privado '{nat_gateway_id}' criado. Aguardando status 'available'...")

        # Esperar até que o NAT Gateway esteja disponível
        waiter = ec2_client.get_waiter('nat_gateway_available')
        waiter.wait(NatGatewayIds=[nat_gateway_id])
        logging.info(f"NAT Gateway '{nat_gateway_id}' está agora disponível.")
        return nat_gateway_id
    except Exception as e:
        logging.error(f"Erro ao criar NAT Gateway privado: {e}")
        return None

def get_vpc_cidrs(vpc_id, target_cidr_prefix='100.99.0.0/16', region='sa-east-1'):
    """
    Lista os CIDRs associados à VPC com um prefixo específico.
    Retorna uma lista de CIDRs.
    """
    ec2_client = get_aws_client('ec2', region)
    logging.info(f"Buscando CIDRs associados à VPC '{vpc_id}' com prefixo: {target_cidr_prefix}")
    cidrs = []
    try:
        response = ec2_client.describe_vpcs(VpcIds=[vpc_id])
        for vpc in response['Vpcs']:
            for association in vpc.get('CidrBlockAssociations', []):
                if association['CidrBlock'].startswith(target_cidr_prefix.split('/')[0]):
                    cidrs.append(association['CidrBlock'])
            # Inclui também o CIDR principal da VPC se ele corresponder
            if vpc['CidrBlock'].startswith(target_cidr_prefix.split('/')[0]):
                cidrs.append(vpc['CidrBlock'])
        logging.info(f"CIDRs encontrados na VPC '{vpc_id}' com prefixo '{target_cidr_prefix}': {cidrs}")
        return list(set(cidrs)) # Remove duplicatas
    except Exception as e:
        logging.error(f"Erro ao listar CIDRs da VPC: {e}")
        return []

def create_subnets(vpc_id, cidr_block, num_subnets, tag_name, region='sa-east-1'):
    """
    Cria um número especificado de subnets em diferentes AZs dentro de um CIDR block.
    Retorna uma lista de IDs das subnets criadas.
    """
    ec2_client = get_aws_client('ec2', region)
    ec2_resource = get_aws_resource('ec2', region)
    logging.info(f"Iniciando a criação de {num_subnets} subnets na VPC '{vpc_id}' usando CIDR '{cidr_block}'")

    created_subnet_ids = []
    available_azs = []
    try:
        response = ec2_client.describe_availability_zones(
            Filters=[
                {'Name': 'state', 'Values': ['available']},
                {'Name': 'region-name', 'Values': [region]}
            ]
        )
        available_azs = [az['ZoneName'] for az in response['AvailabilityZones']]
        logging.info(f"AZs disponíveis na região {region}: {available_azs}")

    except Exception as e:
        logging.error(f"Erro ao listar AZs: {e}")
        return []

    # Mapeia os índices de AZ para os sufixos desejados (1a, 1b)
    az_suffixes = ['a', 'b', 'c', 'd', 'e', 'f'] # Para cobrir mais AZs se necessário
    az_mapping = {}
    for i, az_name in enumerate(available_azs):
        if i < len(az_suffixes):
            az_mapping[az_name] = az_suffixes[i]

    # Implementação simplificada de subnets consecutivas dentro do CIDR principal da VPC
    # Para uma criação mais robusta, uma biblioteca como `ipaddress` seria recomendada
    # para submeter o CIDR e dividir em sub-CIDRs.
    # Neste exemplo, vamos assumir /24 para cada subnet dentro de um /16, ajustando o terceiro octeto.

    # Exemplo: Se cidr_block for '100.99.0.0/16', subnets seriam 100.99.0.0/24, 100.99.1.0/24, etc.
    # Esta lógica é simplificada e pode precisar ser ajustada para blocos CIDR maiores ou mais complexos.
    try:
        base_ip = int(cidr_block.split('.')[2]) # Obtém o terceiro octeto se for um /16
        network_prefix = ".".join(cidr_block.split('.')[:2])

        for i in range(num_subnets):
            if i >= len(available_azs):
                logging.warning(f"Não há AZs suficientes disponíveis para criar {num_subnets} subnets. Criando em AZs repetidas.")
                az_index = i % len(available_azs) # Reutiliza AZs se não houver o suficiente
            else:
                az_index = i

            az_name = available_azs[az_index]
            subnet_cidr = f"{network_prefix}.{base_ip + i}.0/24" # Exemplo: 100.99.0.0/24, 100.99.1.0/24

            # Se o CIDR block de entrada não for /16, ou precisar de uma lógica de subdivisão mais inteligente
            # você precisaria de uma biblioteca como `ipaddress` para calcular os CIDRs das subnets
            # de forma programática.

            if not os.path.exists('/tmp/subnet_allocation.txt'):
                with open('/tmp/subnet_allocation.txt', 'w') as f:
                    f.write("0\n") # Initialize with 0

            with open('/tmp/subnet_allocation.txt', 'r+') as f:
                current_offset = int(f.read().strip())
                new_offset = current_offset + 1
                f.seek(0)
                f.write(str(new_offset))
                f.truncate()

            # Usar o offset para calcular o terceiro octeto
            subnet_cidr = f"{network_prefix}.{base_ip + current_offset}.0/24"

            logging.info(f"Tentando criar subnet com CIDR '{subnet_cidr}' na AZ '{az_name}'")
            try:
                subnet = ec2_client.create_subnet(
                    VpcId=vpc_id,
                    CidrBlock=subnet_cidr,
                    AvailabilityZone=az_name,
                    TagSpecifications=[
                        {
                            'ResourceType': 'subnet',
                            'Tags': [
                                {'Key': 'Name', 'Value': f"{tag_name}-subnet-{az_mapping.get(az_name, az_name.split('-')[-1])}-{current_offset}"}, # Ex: myapp-subnet-1a-0
                                {'Key': 'ManagedBy', 'Value': 'HarnessPipeline'}
                            ]
                        },
                    ]
                )
                subnet_id = subnet['Subnet']['SubnetId']
                created_subnet_ids.append(subnet_id)
                logging.info(f"Subnet '{subnet_id}' com CIDR '{subnet_cidr}' criada na AZ '{az_name}'.")
            except Exception as e:
                logging.error(f"Erro ao criar subnet '{subnet_cidr}' na AZ '{az_name}': {e}")
                # Em caso de erro, talvez seja bom tentar a próxima AZ ou abortar.
                # Aqui, continuamos para a próxima subnet para tentar criar as restantes.
    except Exception as e:
        logging.error(f"Erro geral ao criar subnets: {e}")

    return created_subnet_ids


def create_and_associate_route_table(vpc_id, subnet_ids, nat_gateway_id, region='sa-east-1'):
    """
    Cria uma nova tabela de roteamento, associa as subnets e adiciona uma rota para o NAT Gateway.
    """
    ec2_client = get_aws_client('ec2', region)
    logging.info(f"Criando nova tabela de roteamento na VPC '{vpc_id}' e associando subnets.")

    try:
        # 1. Criar nova tabela de roteamento
        response = ec2_client.create_route_table(
            VpcId=vpc_id,
            TagSpecifications=[
                {
                    'ResourceType': 'route-table',
                    'Tags': [
                        {'Key': 'Name', 'Value': 'Harness-Managed-RouteTable'},
                        {'Key': 'ManagedBy', 'Value': 'HarnessPipeline'}
                    ]
                },
            ]
        )
        route_table_id = response['RouteTable']['RouteTableId']
        logging.info(f"Tabela de roteamento '{route_table_id}' criada com sucesso.")

        # 2. Adicionar rota para o NAT Gateway
        if nat_gateway_id:
            try:
                ec2_client.create_route(
                    DestinationCidrBlock='0.0.0.0/0',
                    NatGatewayId=nat_gateway_id,
                    RouteTableId=route_table_id
                )
                logging.info(f"Rota '0.0.0.0/0' para NAT Gateway '{nat_gateway_id}' adicionada à tabela de roteamento '{route_table_id}'.")
            except Exception as e:
                logging.error(f"Erro ao adicionar rota para NAT Gateway: {e}")
        else:
            logging.warning("NAT Gateway ID não fornecido. Nenhuma rota para NAT Gateway será adicionada.")

        # 3. Associar as subnets criadas à nova tabela de roteamento
        for subnet_id in subnet_ids:
            try:
                ec2_client.associate_route_table(
                    RouteTableId=route_table_id,
                    SubnetId=subnet_id
                )
                logging.info(f"Subnet '{subnet_id}' associada à tabela de roteamento '{route_table_id}'.")
            except Exception as e:
                logging.error(f"Erro ao associar subnet '{subnet_id}' à tabela de roteamento '{route_table_id}': {e}")
        return route_table_id
    except Exception as e:
        logging.error(f"Erro ao criar e associar tabela de roteamento: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Script para configurar recursos de rede AWS em uma pipeline Harness.")
    parser.add_argument('--region', type=str, default='sa-east-1', help='Região AWS a ser usada.')
    parser.add_argument('--vpc-id', type=str, required=True, help='ID da VPC onde os recursos serão criados.')
    parser.add_argument('--security-group-ids', nargs='+', required=True, help='IDs dos Security Groups para os VPC Endpoints.')
    parser.add_argument('--num-subnets', type=int, default=2, help='Número de subnets desejadas (min 2 para AZs diferentes).')
    parser.add_argument('--subnet-tag-name', type=str, default='Harness-Managed-Subnet', help='Tag Name para as subnets criadas.')
    parser.add_argument('--target-vpc-cidr', type=str, default='100.99.0.0/16', help='Prefixo CIDR da VPC para identificar os blocos.')

    args = parser.parse_args()

    # Credenciais AWS devem ser configuradas via variáveis de ambiente ou ~/.aws/credentials
    # boto3 automaticamente buscará por elas.

    # Lista de endpoints de serviço da AWS que você mencionou na imagem
    service_endpoints_to_create = [
        'com.amazonaws.sa-east-1.s3',
        'com.amazonaws.sa-east-1.ssm',
        'com.amazonaws.sa-east-1.ssmmessages',
        'com.amazonaws.sa-east-1.ec2messages',
        'com.amazonaws.sa-east-1.logs',
        'com.amazonaws.sa-east-1.ecr.api',
        'com.amazonaws.sa-east-1.sts',
        'com.amazonaws.sa-east-1.elasticloadbalancing',
        'com.amazonaws.sa-east-1.autoscaling',
        'com.amazonaws.sa-east-1.ec2',
        'com.amazonaws.sa-east-1.ecr.dkr',
        # O endpoint eice-0ca614a2e456d94d7.eb8c576e.ec2-instance-connect-endpoint.sa-east-1.amazonaws.com
        # parece ser um endpoint de instância conectada, que é um pouco diferente dos endpoints de serviço padrão.
        # Ele geralmente é um Private DNS Name para um serviço existente ou um endpoint privado customizado.
        # Para criar endpoints de serviço, geralmente usamos o ServicePrivateDnsName.
        # Se for um endpoint de interface EC2 Instance Connect, o nome do serviço é 'com.amazonaws.sa-east-1.ec2instanceconnect'.
        'com.amazonaws.sa-east-1.ec2instanceconnect'
    ]

    # 1. Criar os endpoints da foto
    logging.info("Passo 1: Criando VPC Endpoints...")
    # Para criar os endpoints, precisamos de IDs de subnets existentes e Security Groups.
    # Neste exemplo, estamos usando os IDs passados como argumento.
    # Na sua pipeline, você precisaria de subnets e SGs pré-existentes ou criá-los antes.
    # Para simplificar, vou usar um placeholder para `subnet_ids_for_endpoints`.
    # Você pode querer usar as subnets criadas no passo 3 para os endpoints,
    # ou ter subnets dedicadas para endpoints.
    # Para este exemplo, vamos assumir que as subnets para endpoints são as mesmas criadas no passo 3.
    # Ou que args.subnet_ids_for_endpoints seja um argumento separado.
    # Por enquanto, vou deixar como um placeholder.
    # Para o passo 1, se você não tem as subnets prontas, não consigo criar os endpoints.
    # Vou reajustar para que as subnets criadas no passo 3 sejam usadas.
    # Portanto, este passo será executado depois do passo 3.

    # 2. Identificar a rede roteável e criar NAT Gateway privado
    logging.info("Passo 2: Identificando rede roteável e criando NAT Gateway privado...")
    routable_subnet_id = identify_routable_network(args.vpc_id, args.region)
    nat_gateway_id = None
    if routable_subnet_id:
        nat_gateway_id = create_private_nat_gateway(routable_subnet_id, args.region)
    else:
        logging.error("Não foi possível encontrar uma subnet roteável para criar o NAT Gateway privado.")
        exit(1) # Abortar se não puder criar o NAT GW

    # 3. Listar CIDRs associados à VPC com 100.99.0.0/16 e criar subnets
    logging.info("Passo 3: Listando CIDRs e criando subnets...")
    vpc_cidrs = get_vpc_cidrs(args.vpc_id, args.target_vpc_cidr, args.region)
    created_subnets = []
    if vpc_cidrs:
        # Para este exemplo, vou usar o primeiro CIDR encontrado que corresponde ao prefixo
        # Se precisar de lógica mais complexa para selecionar o CIDR, ajuste aqui.
        target_cidr_for_subnets = vpc_cidrs[0]
        logging.info(f"CIDR alvo para criação de subnets: {target_cidr_for_subnets}")
        created_subnets = create_subnets(
            args.vpc_id,
            target_cidr_for_subnets,
            args.num_subnets,
            args.subnet_tag_name,
            args.region
        )
    else:
        logging.error(f"Nenhum CIDR associado à VPC '{args.vpc_id}' encontrado com o prefixo '{args.target_vpc_cidr}'.")
        exit(1) # Abortar se não puder criar as subnets

    # Agora que as subnets foram criadas no passo 3, podemos usá-las para os endpoints do passo 1.
    if created_subnets:
        logging.info(f"Usando as subnets recém-criadas para VPC Endpoints: {created_subnets}")
        create_vpc_endpoints(
            service_endpoints_to_create,
            args.vpc_id,
            created_subnets, # Usando as subnets criadas no passo 3
            args.security_group_ids,
            args.region
        )
    else:
        logging.warning("Nenhuma subnet foi criada, pulando a criação de VPC Endpoints que dependem de subnets.")


    # 4. Criar nova tabela de roteamento, incluir subnets e NAT Gateway
    logging.info("Passo 4: Criando e configurando nova tabela de roteamento...")
    if created_subnets and nat_gateway_id:
        create_and_associate_route_table(args.vpc_id, created_subnets, nat_gateway_id, args.region)
    else:
        logging.error("Não foi possível criar a tabela de roteamento e associar subnets/NAT Gateway devido a recursos ausentes.")
        exit(1)


    logging.info("Configuração de rede AWS concluída através do script Python.")

if __name__ == "__main__":
    main()

