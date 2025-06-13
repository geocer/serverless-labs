import boto3
import argparse
import logging
import os
import ipaddress # Importar a biblioteca ipaddress para manipulação de CIDRs

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
                {'Name': 'vpc-id', 'Values': [vpc_id]},
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
                        {'Key': 'Name', 'Value': f'PrivateNATGateway-{subnet_id}'}, # Nome mais específico
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
        logging.error(f"Erro ao criar NAT Gateway privado na subnet {subnet_id}: {e}")
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
            # Verifica o CIDR principal da VPC
            if vpc['CidrBlock'].startswith(target_cidr_prefix.split('/')[0]):
                cidrs.append(vpc['CidrBlock'])
            # Verifica os CIDR blocks associados (secundários)
            for association in vpc.get('CidrBlockAssociations', []):
                if association['CidrBlock'].startswith(target_cidr_prefix.split('/')[0]):
                    cidrs.append(association['CidrBlock'])
        logging.info(f"CIDRs encontrados na VPC '{vpc_id}' com prefixo '{target_cidr_prefix}': {list(set(cidrs))}")
        return list(set(cidrs)) # Remove duplicatas
    except Exception as e:
        logging.error(f"Erro ao listar CIDRs da VPC: {e}")
        return []

def create_subnets(vpc_id, base_cidr_block, num_subnets, tag_name, region='sa-east-1'):
    """
    Cria um número especificado de subnets em diferentes AZs dentro de um CIDR block base.
    Utiliza a biblioteca ipaddress para subdividir o CIDR block de forma robusta.
    Retorna uma lista de dicionários contendo {'SubnetId': 'id', 'AvailabilityZone': 'az'}
    """
    ec2_client = get_aws_client('ec2', region)
    logging.info(f"Iniciando a criação de {num_subnets} subnets na VPC '{vpc_id}' usando CIDR base '{base_cidr_block}'")

    created_subnets_info = []
    available_azs = []
    try:
        response = ec2_client.describe_availability_zones(
            Filters=[
                {'Name': 'state', 'Values': ['available']},
                {'Name': 'region-name', 'Values': [region]}
            ]
        )
        available_azs = [az['ZoneName'] for az in response['AvailabilityZones']]
        if not available_azs:
            logging.error(f"Nenhuma AZ disponível na região {region}. Não é possível criar subnets.")
            return []
        logging.info(f"AZs disponíveis na região {region}: {available_azs}")

    except Exception as e:
        logging.error(f"Erro ao listar AZs: {e}")
        return []

    # Mapeia os índices de AZ para os sufixos desejados (a, b, c...)
    az_suffixes = ['a', 'b', 'c', 'd', 'e', 'f'] # Para cobrir mais AZs se necessário
    az_map = {az_name: az_suffixes[i] for i, az_name in enumerate(available_azs) if i < len(az_suffixes)}

    try:
        # Usar ipaddress para subdividir o CIDR principal em sub-CIDRs /24
        network = ipaddress.ip_network(base_cidr_block)
        # Assumimos que queremos subnets /24. Você pode ajustar o prefixlen aqui.
        new_prefixlen = 24
        subnets_iter = network.subnets(new_prefixlen=new_prefixlen)

        for i in range(num_subnets):
            try:
                subnet_cidr_block = str(next(subnets_iter))
            except StopIteration:
                logging.warning(f"Não há CIDRs suficientes no bloco '{base_cidr_block}' para criar {num_subnets} subnets de /{new_prefixlen}. Reutilizando CIDRs se possível.")
                # Se acabarem os CIDRs, uma abordagem seria parar ou reutilizar,
                # mas para criação de novas subnets, é melhor garantir CIDRs únicos.
                break # Sai do loop se não houver mais CIDRs disponíveis

            az_index = i % len(available_azs)
            az_name = available_azs[az_index]
            az_suffix = az_map.get(az_name, az_name.split('-')[-1]) # Fallback para o sufixo original da AZ

            logging.info(f"Tentando criar subnet com CIDR '{subnet_cidr_block}' na AZ '{az_name}'")
            try:
                subnet = ec2_client.create_subnet(
                    VpcId=vpc_id,
                    CidrBlock=subnet_cidr_block,
                    AvailabilityZone=az_name,
                    TagSpecifications=[
                        {
                            'ResourceType': 'subnet',
                            'Tags': [
                                {'Key': 'Name', 'Value': f"{tag_name}-{az_suffix}-{subnet_cidr_block.split('.')[-2]}"}, # Ex: myapp-subnet-a-0
                                {'Key': 'ManagedBy', 'Value': 'HarnessPipeline'}
                            ]
                        },
                    ]
                )
                subnet_id = subnet['Subnet']['SubnetId']
                created_subnets_info.append({'SubnetId': subnet_id, 'AvailabilityZone': az_name})
                logging.info(f"Subnet '{subnet_id}' com CIDR '{subnet_cidr_block}' criada na AZ '{az_name}'.")
            except Exception as e:
                logging.error(f"Erro ao criar subnet '{subnet_cidr_block}' na AZ '{az_name}': {e}")
                # Em caso de erro, continua para a próxima subnet.
    except Exception as e:
        logging.error(f"Erro geral ao iterar e criar subnets: {e}")

    return created_subnets_info


def create_and_associate_route_table(vpc_id, subnet_id, nat_gateway_id, region='sa-east-1'):
    """
    Cria uma nova tabela de roteamento, associa uma subnet e adiciona uma rota para o NAT Gateway.
    Esta função é chamada para cada subnet.
    """
    ec2_client = get_aws_client('ec2', region)
    logging.info(f"Criando nova tabela de roteamento na VPC '{vpc_id}' e associando subnet '{subnet_id}'.")

    try:
        # 1. Criar nova tabela de roteamento
        response = ec2_client.create_route_table(
            VpcId=vpc_id,
            TagSpecifications=[
                {
                    'ResourceType': 'route-table',
                    'Tags': [
                        {'Key': 'Name', 'Value': f'Harness-Managed-RouteTable-{subnet_id}'}, # Nome mais específico
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
                logging.error(f"Erro ao adicionar rota para NAT Gateway '{nat_gateway_id}' na RT '{route_table_id}': {e}")
        else:
            logging.warning("NAT Gateway ID não fornecido. Nenhuma rota para NAT Gateway será adicionada.")

        # 3. Associar a subnet à nova tabela de roteamento
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
        logging.error(f"Erro ao criar e associar tabela de roteamento para subnet '{subnet_id}': {e}")
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

    # Lista de endpoints de serviço da AWS
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
        'com.amazonaws.sa-east-1.ec2instanceconnect'
    ]

    # 1. Listar CIDRs associados à VPC com 100.99.0.0/16 e criar subnets
    logging.info("Passo 1: Listando CIDRs e criando subnets...")
    vpc_cidrs = get_vpc_cidrs(args.vpc_id, args.target_vpc_cidr, args.region)
    created_subnets_info = [] # Esta lista agora conterá dicionários {'SubnetId': 'id', 'AvailabilityZone': 'az'}
    if vpc_cidrs:
        target_cidr_for_subnets = vpc_cidrs[0] # Usar o primeiro CIDR encontrado
        logging.info(f"CIDR alvo para criação de subnets: {target_cidr_for_subnets}")
        created_subnets_info = create_subnets(
            args.vpc_id,
            target_cidr_for_subnets,
            args.num_subnets,
            args.subnet_tag_name,
            args.region
        )
    else:
        logging.error(f"Nenhum CIDR associado à VPC '{args.vpc_id}' encontrado com o prefixo '{args.target_vpc_cidr}'.")
        exit(1) # Abortar se não puder criar as subnets

    if not created_subnets_info:
        logging.error("Nenhuma subnet foi criada. Não é possível prosseguir com a criação de NAT Gateways ou VPC Endpoints.")
        exit(1)

    # Coletar apenas os IDs das subnets para outras funções que os exigem
    created_subnet_ids = [s['SubnetId'] for s in created_subnets_info]


    # 2. Criar NAT Gateway privado para CADA subnet criada
    logging.info("Passo 2: Criando NAT Gateways privados em cada subnet criada...")
    nat_gateway_ids = []
    for subnet_info in created_subnets_info:
        subnet_id = subnet_info['SubnetId']
        nat_gateway_id = create_private_nat_gateway(subnet_id, args.region)
        if nat_gateway_id:
            nat_gateway_ids.append(nat_gateway_id)
        else:
            logging.error(f"Falha ao criar NAT Gateway para subnet: {subnet_id}. Continuar com as demais.")
            # Dependendo da sua tolerância a falhas, você pode optar por sair aqui.

    if not nat_gateway_ids:
        logging.error("Nenhum NAT Gateway privado foi criado. Não é possível prosseguir com a configuração de tabelas de roteamento.")
        exit(1)

    # 3. Criar VPC Endpoints (usando as subnets recém-criadas)
    logging.info(f"Passo 3: Criando VPC Endpoints usando as subnets: {created_subnet_ids}")
    create_vpc_endpoints(
        service_endpoints_to_create,
        args.vpc_id,
        created_subnet_ids, # Usando todas as subnets criadas
        args.security_group_ids,
        args.region
    )

    # 4. Criar nova tabela de roteamento e associar para CADA subnet com seu respectivo NAT Gateway
    # Esta lógica assume que cada subnet privada terá sua própria tabela de roteamento
    # apontando para o NAT Gateway *naquela mesma subnet/AZ*.
    logging.info("Passo 4: Criando e configurando tabelas de roteamento para cada subnet...")
    for i, subnet_info in enumerate(created_subnets_info):
        subnet_id = subnet_info['SubnetId']
        # Assumindo que a ordem dos NAT Gateways corresponde à ordem das subnets para simplicidade.
        # Em um ambiente de produção, você pode querer mapear isso explicitamente por AZ.
        if i < len(nat_gateway_ids):
            nat_gateway_to_associate = nat_gateway_ids[i]
            create_and_associate_route_table(args.vpc_id, subnet_id, nat_gateway_to_associate, args.region)
        else:
            logging.warning(f"Não há NAT Gateway correspondente para a subnet {subnet_id}. Pulando a configuração da rota.")

    logging.info("Configuração de rede AWS concluída através do script Python.")

if __name__ == "__main__":
    main()
