import boto3
import argparse
import logging
import os
import ipaddress

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Lista de serviços de endpoint a serem criados (excluindo S3 que é Gateway Endpoint)
service_endpoints_to_create = [
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

def get_aws_client(service_name, region_name='sa-east-1',
                   aws_access_key_id=None, aws_secret_access_key=None, aws_session_token=None):
    """
    Retorna um cliente boto3 para o serviço especificado,
    com credenciais explicitamente fornecidas.
    """
    try:
        if aws_access_key_id and aws_secret_access_key:
            client_args = {
                'service_name': service_name,
                'region_name': region_name,
                'aws_access_key_id': aws_access_key_id,
                'aws_secret_access_key': aws_secret_access_key
            }
            if aws_session_token:
                client_args['aws_session_token'] = aws_session_token
            return boto3.client(**client_args)
        else:
            logging.warning("Credenciais AWS não fornecidas explicitamente. Boto3 tentará usar o default (variáveis de ambiente, perfis, roles de instância).")
            return boto3.client(service_name, region_name=region_name)
    except Exception as e:
        logging.error(f"Erro ao obter cliente para {service_name}: {e}")
        raise

def get_aws_resource(service_name, region_name='sa-east-1',
                     aws_access_key_id=None, aws_secret_access_key=None, aws_session_token=None):
    """
    Retorna um recurso boto3 para o serviço especificado,
    com credenciais explicitamente fornecidas.
    """
    try:
        if aws_access_key_id and aws_secret_access_key:
            resource_args = {
                'service_name': service_name,
                'region_name': region_name,
                'aws_access_key_id': aws_access_key_id,
                'aws_secret_access_key': aws_secret_access_key
            }
            if aws_session_token:
                resource_args['aws_session_token'] = aws_session_token
            return boto3.resource(**resource_args)
        else:
            logging.warning("Credenciais AWS não fornecidas explicitamente. Boto3 tentará usar o default (variáveis de ambiente, perfis, roles de instância).")
            return boto3.resource(service_name, region_name=region_name)
    except Exception as e:
        logging.error(f"Erro ao obter recurso para {service_name}: {e}")
        raise

def create_vpc_endpoints(service_names, vpc_id, subnet_ids, security_group_ids, region,
                         aws_access_key_id, aws_secret_access_key, aws_session_token):
    """
    Cria VPC Endpoints para os serviços especificados.
    Assume que os IDs da VPC, Subnets e Security Groups já existem.
    """
    ec2_client = get_aws_client('ec2', region, aws_access_key_id, aws_secret_access_key, aws_session_token)
    logging.info(f"Iniciando a criação de VPC Endpoints na VPC: {vpc_id}")

    created_endpoints = []
    for service_name in service_names:
        try:
            if service_name.endswith('.s3'): # S3 é um Gateway Endpoint
                logging.info(f"Criando VPC Gateway Endpoint para o serviço: {service_name}")
                response = ec2_client.create_vpc_endpoint(
                    VpcId=vpc_id,
                    ServiceName=f'com.amazonaws.{region}.s3', # Nome de serviço para S3 Gateway Endpoint
                    VpcEndpointType='Gateway',
                    RouteTableIds=[], # Gateway Endpoints associam-se a Route Tables, não a Subnets
                    TagSpecifications=[
                        {
                            'ResourceType': 'vpc-endpoint',
                            'Tags': [
                                {'Key': 'Name', 'Value': f"{service_name.split('.')[-1]}-gateway-endpoint"},
                                {'Key': 'ManagedBy', 'Value': 'HarnessPipeline'}
                            ]
                        },
                    ]
                )
                endpoint_id = response['VpcEndpoint']['VpcEndpointId']
                created_endpoints.append(endpoint_id)
                logging.info(f"VPC Gateway Endpoint '{endpoint_id}' para '{service_name}' criado com sucesso.")
            else: # Interface Endpoints
                logging.info(f"Criando VPC Interface Endpoint para o serviço: {service_name}")
                response = ec2_client.create_vpc_endpoint(
                    VpcId=vpc_id,
                    ServiceName=service_name,
                    VpcEndpointType='Interface',
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

def identify_routable_network(vpc_id, region,
                              aws_access_key_id, aws_secret_access_key, aws_session_token):
    """
    Identifica uma tabela de roteamento em uma VPC que tenha uma rota para um Transit Gateway.
    Retorna o ID da tabela de roteamento se encontrada, caso contrário None.
    """
    ec2_client = get_aws_client('ec2', region, aws_access_key_id, aws_secret_access_key, aws_session_token)
    logging.info(f"Identificando tabela de roteamento roteável na VPC: {vpc_id}")

    try:
        response = ec2_client.describe_route_tables(
            Filters=[
                {'Name': 'vpc-id', 'Values': [vpc_id]},
                {'Name': 'route.state', 'Values': ['active']}
            ]
        )

        for rt in response['RouteTables']:
            for route in rt.get('Routes', []):
                if 'TransitGatewayId' in route and route['State'] == 'active':
                    logging.info(f"Tabela de roteamento '{rt['RouteTableId']}' encontrada com rota para Transit Gateway: {route['TransitGatewayId']}")
                    return rt['RouteTableId']
        logging.warning(f"Nenhuma tabela de roteamento com rota para Transit Gateway encontrada na VPC: {vpc_id}")
        return None
    except Exception as e:
        logging.error(f"Erro ao identificar rede roteável: {e}")
        return None

def associate_subnets_to_route_table(route_table_id, subnet_ids, region,
                                     aws_access_key_id, aws_secret_access_key, aws_session_token):
    """
    Associa uma lista de subnets a uma tabela de roteamento específica.
    """
    ec2_client = get_aws_client('ec2', region, aws_access_key_id, aws_secret_access_key, aws_session_token)
    logging.info(f"Associando subnets {subnet_ids} à tabela de roteamento '{route_table_id}'.")
    
    successful_associations = []
    for subnet_id in subnet_ids:
        try:
            # Verifica se a subnet já está explicitamente associada a esta tabela de roteamento
            current_associations = ec2_client.describe_route_tables(
                Filters=[
                    {'Name': 'association.subnet-id', 'Values': [subnet_id]},
                    {'Name': 'route-table-id', 'Values': [route_table_id]}
                ]
            )['RouteTables']

            already_explicitly_associated = False
            for rt in current_associations:
                for assoc in rt.get('Associations', []):
                    if assoc.get('SubnetId') == subnet_id and assoc.get('RouteTableId') == route_table_id and not assoc.get('Main', False):
                        already_explicitly_associated = True
                        break
                if already_explicitly_associated:
                    break

            if not already_explicitly_associated:
                logging.info(f"Associando subnet '{subnet_id}' à tabela de roteamento '{route_table_id}'.")
                ec2_client.associate_route_table(
                    RouteTableId=route_table_id,
                    SubnetId=subnet_id
                )
                logging.info(f"Subnet '{subnet_id}' associada com sucesso à tabela de roteamento '{route_table_id}'.")
                successful_associations.append(subnet_id)
            else:
                logging.info(f"Subnet '{subnet_id}' já está explicitamente associada à tabela de roteamento '{route_table_id}'.")
                successful_associations.append(subnet_id) # Considera sucesso se já estava associada

        except Exception as e:
            logging.error(f"Erro ao associar subnet '{subnet_id}' à tabela de roteamento '{route_table_id}': {e}")
    return successful_associations

def create_private_nat_gateway(subnet_id, region,
                               aws_access_key_id, aws_secret_access_key, aws_session_token):
    """
    Cria um NAT Gateway privado na subnet especificada.
    Retorna o ID do NAT Gateway.
    """
    ec2_client = get_aws_client('ec2', region, aws_access_key_id, aws_secret_access_key, aws_session_token)
    logging.info(f"Criando NAT Gateway privado na subnet: {subnet_id}")

    try:
        response = ec2_client.create_nat_gateway(
            SubnetId=subnet_id,
            ConnectivityType='private',
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

        waiter = ec2_client.get_waiter('nat_gateway_available')
        waiter.wait(NatGatewayIds=[nat_gateway_id])
        logging.info(f"NAT Gateway '{nat_gateway_id}' está agora disponível.")
        return nat_gateway_id
    except Exception as e:
        logging.error(f"Erro ao criar NAT Gateway privado: {e}")
        return None

def get_subnet_for_nat_gateway(vpc_id, main_vpc_cidr, region,
                               aws_access_key_id, aws_secret_access_key, aws_session_token):
    """
    Encontra uma subnet adequada para o NAT Gateway no CIDR principal da VPC.
    Prioriza subnets com 'public' no nome da tag se possível, ou a primeira disponível.
    """
    ec2_client = get_aws_client('ec2', region, aws_access_key_id, aws_secret_access_key, aws_session_token)
    logging.info(f"Buscando subnet para NAT Gateway no CIDR '{main_vpc_cidr}' da VPC '{vpc_id}'")
    
    try:
        # Filtra subnets que estão dentro do main_vpc_cidr
        all_subnets_in_vpc = ec2_client.describe_subnets(
            Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
        )['Subnets']

        main_network = ipaddress.ip_network(main_vpc_cidr)
        candidate_subnets = []

        for subnet in all_subnets_in_vpc:
            subnet_network = ipaddress.ip_network(subnet['CidrBlock'])
            if subnet_network.subnet_of(main_network):
                candidate_subnets.append(subnet)

        if not candidate_subnets:
            logging.warning(f"Nenhuma subnet encontrada dentro do CIDR '{main_vpc_cidr}' na VPC '{vpc_id}'.")
            return None
            
        # Prioriza subnets com tags de nome 'public'
        for subnet in candidate_subnets:
            for tag in subnet.get('Tags', []):
                if tag['Key'] == 'Name' and 'public' in tag['Value'].lower():
                    logging.info(f"Subnet pública ideal para NAT Gateway encontrada: {subnet['SubnetId']}")
                    return subnet['SubnetId']
        
        # Se nenhuma subnet 'public' for encontrada, retorna a primeira candidata
        logging.info(f"Nenhuma subnet 'public' ideal encontrada. Usando a primeira subnet candidata no CIDR '{main_vpc_cidr}': {candidate_subnets[0]['SubnetId']}")
        return candidate_subnets[0]['SubnetId']
    except Exception as e:
        logging.error(f"Erro ao encontrar subnet para NAT Gateway: {e}")
        return None

def create_subnets(vpc_id, base_cidr_block, num_subnets, subnet_prefix_length, tag_name_prefix, region,
                   aws_access_key_id, aws_secret_access_key, aws_session_token):
    """
    Cria um número especificado de subnets em diferentes AZs a partir de um CIDR block base.
    As subnets serão divididas com o subnet_prefix_length.
    Usará somente as AZs 'sa-east-1a' e 'sa-east-1b'.
    Retorna uma lista de IDs das subnets criadas.
    As tags de nome serão 'app-non-routable-[AZ]' e 'database-non-routable-[AZ]'.
    """
    ec2_client = get_aws_client('ec2', region, aws_access_key_id, aws_secret_access_key, aws_session_token)
    logging.info(f"Iniciando a criação de {num_subnets} subnets na VPC '{vpc_id}' a partir do CIDR base '{base_cidr_block}' com prefixo /{subnet_prefix_length}")

    created_subnet_ids = []
    
    # AZs permitidas conforme requisito
    allowed_azs = ['sa-east-1a', 'sa-east-1b']
    
    # Verificar se as AZs permitidas estão disponíveis na região
    available_azs = []
    try:
        response = ec2_client.describe_availability_zones(
            Filters=[
                {'Name': 'state', 'Values': ['available']},
                {'Name': 'region-name', 'Values': [region]}
            ]
        )
        all_available_azs = [az['ZoneName'] for az in response['AvailabilityZones']]
        logging.info(f"Todas as AZs disponíveis na região {region}: {all_available_azs}")
        
        # Filtrar apenas as AZs permitidas e que realmente existem
        available_azs = [az for az in allowed_azs if az in all_available_azs]
        if not available_azs:
            logging.error(f"As AZs '{allowed_azs}' não estão disponíveis na região {region}. Abortando criação de subnets.")
            return []
        logging.info(f"AZs disponíveis e selecionadas para criação de subnets: {available_azs}")

    except Exception as e:
        logging.error(f"Erro ao listar AZs: {e}")
        return []

    # Mapeamento de AZ para sufixo (a, b) para nomes de tags
    az_suffixes = {'sa-east-1a': 'a', 'sa-east-1b': 'b'}
    tag_types = ['app', 'database']

    try:
        # Calcular os blocos CIDR para as novas subnets
        network = ipaddress.ip_network(base_cidr_block)
        subnets_to_create_cidrs = list(network.subnets(new_prefix=subnet_prefix_length))

        if len(subnets_to_create_cidrs) < num_subnets:
            logging.error(f"O CIDR base '{base_cidr_block}' (/{(network.prefixlen)}) não pode ser dividido em {num_subnets} subnets de prefixo /{subnet_prefix_length}. São possíveis apenas {len(subnets_to_create_cidrs)}.")
            return []
        
        # Contador para os CIDRs e para o número de subnets criadas
        cidr_idx = 0
        created_count = 0

        # Loop para criar as subnets, garantindo a alternância de AZ e tipo
        while created_count < num_subnets and cidr_idx < len(subnets_to_create_cidrs):
            for az_name in available_azs:
                if created_count >= num_subnets or cidr_idx >= len(subnets_to_create_cidrs):
                    break # Sair se já criamos o número desejado de subnets ou esgotamos os CIDRs
                
                for tag_type in tag_types:
                    if created_count >= num_subnets or cidr_idx >= len(subnets_to_create_cidrs):
                        break # Sair se já criamos o número desejado de subnets ou esgotamos os CIDRs
                    
                    subnet_cidr = str(subnets_to_create_cidrs[cidr_idx])
                    final_tag_name = f"{tag_name_prefix}-{tag_type}-non-routable-{az_suffixes.get(az_name, az_name.split('-')[-1])}"

                    # Verificar se já existe uma subnet com este CIDR e AZ na VPC
                    existing_subnets = ec2_client.describe_subnets(
                        Filters=[
                            {'Name': 'vpc-id', 'Values': [vpc_id]},
                            {'Name': 'cidr-block', 'Values': [subnet_cidr]},
                            {'Name': 'availability-zone', 'Values': [az_name]} 
                        ]
                    )['Subnets']

                    if existing_subnets:
                        subnet_id = existing_subnets[0]['SubnetId']
                        logging.info(f"Subnet com CIDR '{subnet_cidr}' e AZ '{az_name}' (Tag: {final_tag_name}) já existe na VPC '{vpc_id}' como '{subnet_id}'. Reutilizando.")
                        created_subnet_ids.append(subnet_id)
                    else:
                        logging.info(f"Tentando criar subnet com CIDR '{subnet_cidr}' na AZ '{az_name}' com tag: {final_tag_name}")
                        try:
                            subnet = ec2_client.create_subnet(
                                VpcId=vpc_id,
                                CidrBlock=subnet_cidr,
                                AvailabilityZone=az_name,
                                TagSpecifications=[
                                    {
                                        'ResourceType': 'subnet',
                                        'Tags': [
                                            {'Key': 'Name', 'Value': final_tag_name},
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
                    
                    created_count += 1
                    cidr_idx += 1
                    if created_count >= num_subnets: # Se atingiu o número desejado de subnets, sair
                        break
            if created_count >= num_subnets: # Se atingiu o número desejado de subnets, sair do loop externo
                break

    except Exception as e:
        logging.error(f"Erro geral ao criar subnets: {e}")

    return created_subnet_ids

def create_new_route_table_and_associate(vpc_id, subnet_ids, nat_gateway_id, region,
                                         aws_access_key_id, aws_secret_access_key, aws_session_token):
    """
    Cria uma NOVA tabela de roteamento, adiciona rota para NAT Gateway e associa as subnets fornecidas.
    Esta RT será para as subnets "não roteáveis" (do CIDR 100.99.0.0/16) que usam o NAT Gateway.
    """
    ec2_client = get_aws_client('ec2', region, aws_access_key_id, aws_secret_access_key, aws_session_token)
    logging.info(f"Criando nova tabela de roteamento na VPC '{vpc_id}' para subnets não roteáveis e associando.")

    try:
        response = ec2_client.create_route_table(
            VpcId=vpc_id,
            TagSpecifications=[
                {
                    'ResourceType': 'route-table',
                    'Tags': [
                        {'Key': 'Name', 'Value': 'Harness-Managed-NonRoutable-RT'}, 
                        {'Key': 'ManagedBy', 'Value': 'HarnessPipeline'}
                    ]
                },
            ]
        )
        route_table_id = response['RouteTable']['RouteTableId']
        logging.info(f"Nova tabela de roteamento '{route_table_id}' criada com sucesso para subnets não roteáveis.")

        if nat_gateway_id:
            try:
                ec2_client.create_route(
                    DestinationCidrBlock='0.0.0.0/0',
                    NatGatewayId=nat_gateway_id,
                    RouteTableId=route_table_id
                )
                logging.info(f"Rota '0.0.0.0/0' para NAT Gateway '{nat_gateway_id}' adicionada à nova tabela de roteamento '{route_table_id}'.")
            except Exception as e:
                logging.error(f"Erro ao adicionar rota para NAT Gateway na nova tabela de roteamento: {e}")
        else:
            logging.warning("NAT Gateway ID não fornecido. Nenhuma rota para NAT Gateway será adicionada à nova RT.")

        for subnet_id in subnet_ids:
            try:
                # Verifica se a subnet já está explicitamente associada a esta tabela de roteamento
                current_associations = ec2_client.describe_route_tables(
                    Filters=[
                        {'Name': 'association.subnet-id', 'Values': [subnet_id]},
                        {'Name': 'route-table-id', 'Values': [route_table_id]}
                    ]
                )['RouteTables']

                already_explicitly_associated = False
                for rt in current_associations:
                    for assoc in rt.get('Associations', []):
                        if assoc.get('SubnetId') == subnet_id and assoc.get('RouteTableId') == route_table_id and not assoc.get('Main', False):
                            already_explicitly_associated = True
                            break
                    if already_explicitly_associated:
                        break

                if not already_explicitly_associated:
                    ec2_client.associate_route_table(
                        RouteTableId=route_table_id,
                        SubnetId=subnet_id
                    )
                    logging.info(f"Subnet '{subnet_id}' associada à nova tabela de roteamento '{route_table_id}'.")
                else:
                    logging.info(f"Subnet '{subnet_id}' já estava explicitamente associada à nova tabela de roteamento '{route_table_id}'.")

            except Exception as e:
                logging.error(f"Erro ao associar subnet '{subnet_id}' à nova tabela de roteamento '{route_table_id}': {e}")
        return route_table_id
    except Exception as e:
        logging.error(f"Erro ao criar e associar nova tabela de roteamento: {e}")
        return None

def get_existing_subnets_in_cidr(vpc_id, cidr_block, region,
                                  aws_access_key_id, aws_secret_access_key, aws_session_token):
    """
    Retorna uma lista de IDs de subnets existentes dentro de um bloco CIDR específico na VPC.
    """
    ec2_client = get_aws_client('ec2', region, aws_access_key_id, aws_secret_access_key, aws_session_token)
    logging.info(f"Buscando subnets existentes no CIDR '{cidr_block}' da VPC '{vpc_id}'.")
    
    found_subnet_ids = []
    try:
        target_network = ipaddress.ip_network(cidr_block)
        response = ec2_client.describe_subnets(
            Filters=[
                {'Name': 'vpc-id', 'Values': [vpc_id]},
            ]
        )
        for subnet in response['Subnets']:
            subnet_network = ipaddress.ip_network(subnet['CidrBlock'])
            if subnet_network.subnet_of(target_network):
                found_subnet_ids.append(subnet['SubnetId'])
        logging.info(f"Subnets encontradas no CIDR '{cidr_block}': {found_subnet_ids}")
        return found_subnet_ids
    except Exception as e:
        logging.error(f"Erro ao buscar subnets existentes no CIDR '{cidr_block}': {e}")
        return []

def main():
    parser = argparse.ArgumentParser(description="Script para configurar recursos de rede AWS em uma pipeline Harness.")
    parser.add_argument('--region', type=str, default='sa-east-1', help='Região AWS a ser usada.')
    parser.add_argument('--vpc-id', type=str, required=True, help='ID da VPC onde os recursos serão criados.')
    parser.add_argument('--security-group-ids', nargs='+', required=True, help='IDs dos Security Groups para os VPC Endpoints.')
    parser.add_argument('--num-subnets', type=int, default=4, help='Número de subnets desejadas para o CIDR 100.99.0.0/16 (recomenda-se 2 ou 4 para AZs a e b).')
    parser.add_argument('--subnet-prefix-length', type=int, default=20, help='Comprimento do prefixo das novas subnets do 100.99.0.0/16 (e.g., 20 para /20).')
    parser.add_argument('--new-subnet-tag-name-prefix', type=str, default='Harness', help='Prefixo do Tag Name para as novas subnets criadas (do 100.99.0.0/16). As tags finais serão 'Harness-app-non-routable-[AZ]' ou 'Harness-database-non-routable-[AZ]').')
    parser.add_argument('--non-routable-cidr', type=str, default='100.99.0.0/16', help='CIDR a ser dividido em novas subnets (este será o CIDR "não roteável" via TGW).')
    parser.add_argument('--main-vpc-cidr', type=str, required=True, help='CIDR principal da VPC onde o NAT Gateway deve ser criado e onde as subnets roteáveis existentes estão.')

    args = parser.parse_args()

    aws_access_key_id = os.environ.get('AWS_ACCESS_KEY_ID')
    aws_secret_access_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    aws_session_token = os.environ.get('AWS_SESSION_TOKEN')

    if not aws_access_key_id or not aws_secret_access_key:
        logging.error("Variáveis de ambiente AWS_ACCESS_KEY_ID e/ou AWS_SECRET_ACCESS_KEY não encontradas. Por favor, configure-as na pipeline do Harness.")
        exit(1)

    logging.info(f"Iniciando configuração de rede na VPC '{args.vpc_id}' na região '{args.region}'.")
    
    # 1. Identificar a tabela de roteamento roteável (com TGW)
    logging.info("Passo 1: Identificando tabela de roteamento roteável (com TGW).")
    routable_route_table_id = identify_routable_network(args.vpc_id, args.region,
                                                        aws_access_key_id, aws_secret_access_key, aws_session_token)
    
    if not routable_route_table_id:
        logging.error("Nenhuma tabela de roteamento com rota para Transit Gateway encontrada. Não é possível configurar a rede roteável. Abortando.")
        exit(1)

    # 2. Identificar uma subnet existente para o NAT Gateway (no main_vpc_cidr)
    logging.info(f"Passo 2: Identificando uma subnet para o NAT Gateway no CIDR '{args.main_vpc_cidr}'.")
    nat_gateway_subnet_id = get_subnet_for_nat_gateway(args.vpc_id, args.main_vpc_cidr, args.region,
                                                       aws_access_key_id, aws_secret_access_key, aws_session_token)
    
    if not nat_gateway_subnet_id:
        logging.error(f"Nenhuma subnet adequada encontrada no CIDR '{args.main_vpc_cidr}' para criar o NAT Gateway. Abortando.")
        exit(1)
    
    # 3. Criar NAT Gateway privado
    logging.info("Passo 3: Criando NAT Gateway privado.")
    nat_gateway_id = create_private_nat_gateway(nat_gateway_subnet_id, args.region,
                                                aws_access_key_id, aws_secret_access_key, aws_session_token)

    if not nat_gateway_id:
        logging.error("Falha ao criar NAT Gateway privado. Abortando.")
        exit(1)

    # 4. Criar as novas subnets (do non-routable-cidr, e.g., 100.99.0.0/16)
    logging.info(f"Passo 4: Criando as novas subnets a partir do CIDR '{args.non_routable_cidr}' (somente AZs 'a' e 'b').")
    created_subnets = create_subnets(
        args.vpc_id,
        args.non_routable_cidr,
        args.num_subnets,
        args.subnet_prefix_length,
        args.new_subnet_tag_name_prefix,
        args.region,
        aws_access_key_id, aws_secret_access_key, aws_session_token
    )

    if not created_subnets:
        logging.error("Nenhuma subnet foi criada com sucesso a partir do CIDR 100.99.0.0/16. Abortando a execução.")
        exit(1)

    # 5. Criar uma NOVA Tabela de Roteamento para as Novas Subnets e associá-las, com rota para NAT GW
    logging.info("Passo 5: Criando uma NOVA tabela de roteamento para as subnets recém-criadas (do 100.99.0.0/16) e associando-as com rota para NAT Gateway.")
    new_non_routable_rt_id = create_new_route_table_and_associate(
        args.vpc_id,
        created_subnets,
        nat_gateway_id,
        args.region,
        aws_access_key_id, aws_secret_access_key, aws_session_token
    )

    if not new_non_routable_rt_id:
        logging.error("Falha ao criar e configurar a nova tabela de roteamento para as subnets 100.99.0.0/16. Abortando.")
        exit(1)
    
    # 6. Associar subnets EXISTENTES do main_vpc_cidr à Tabela de Roteamento do TGW
    logging.info(f"Passo 6: Verificando e associando subnets existentes do CIDR '{args.main_vpc_cidr}' à Tabela de Roteamento do TGW ('{routable_route_table_id}').")
    
    existing_main_cidr_subnets = get_existing_subnets_in_cidr(
        args.vpc_id,
        args.main_vpc_cidr, 
        args.region,
        aws_access_key_id, aws_secret_access_key, aws_session_token
    )

    if existing_main_cidr_subnets:
        logging.info(f"Subnets existentes no CIDR '{args.main_vpc_cidr}' encontradas: {existing_main_cidr_subnets}. Associando-as à RT do TGW.")
        associate_subnets_to_route_table(
            routable_route_table_id,
            existing_main_cidr_subnets,
            args.region,
            aws_access_key_id, aws_secret_access_key, aws_session_token
        )
    else:
        logging.warning(f"Nenhuma subnet existente encontrada no CIDR '{args.main_vpc_cidr}' para associação à RT do TGW.")

    # 7. Criar VPC Endpoints (nas novas subnets do 100.99.0.0/16)
    logging.info("Passo 7: Criando VPC Endpoints nas subnets recém-criadas (do 100.99.0.0/16) e Gateway Endpoints.")
    
    # Lidar com S3 Gateway Endpoint
    s3_service_name = 'com.amazonaws.sa-east-1.s3'
    create_vpc_endpoints(
        [s3_service_name], # S3 tratado separadamente como Gateway
        args.vpc_id,
        [], # Subnet IDs não são usadas para Gateway Endpoints
        [], # Security Group IDs não são usadas para Gateway Endpoints
        args.region,
        aws_access_key_id, aws_secret_access_key, aws_session_token
    )

    # Lidar com Interface Endpoints
    create_vpc_endpoints(
        service_endpoints_to_create, # Lista de Interface Endpoints
        args.vpc_id,
        created_subnets, # Usar as subnets do 100.99.0.0/16 para os endpoints de interface
        args.security_group_ids,
        args.region,
        aws_access_key_id, aws_secret_access_key, aws_session_token
    )

    logging.info("Configuração de rede AWS concluída através do script Python.")

if __name__ == "__main__":
    main()

