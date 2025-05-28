import boto3
import argparse
import logging
import os
import ipaddress # Importar para manipulação de CIDR

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
            logging.info(f"Criando VPC Endpoint para o serviço: {service_name}")
            response = ec2_client.create_vpc_endpoint(
                VpcId=vpc_id,
                ServicePrivateDnsName=service_name,
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
            # Verifica se a subnet já está associada a esta tabela de roteamento
            current_associations = ec2_client.describe_route_tables(
                Filters=[
                    {'Name': 'association.subnet-id', 'Values': [subnet_id]},
                    {'Name': 'route-table-id', 'Values': [route_table_id]}
                ]
            )['RouteTables']

            already_associated = False
            if current_associations:
                for current_rt in current_associations:
                    for assoc in current_rt.get('Associations', []):
                        # Verifica se a associação explícita existe
                        if assoc.get('SubnetId') == subnet_id and assoc.get('RouteTableId') == route_table_id and assoc.get('Main', False) is False:
                            logging.info(f"Subnet '{subnet_id}' já está explicitamente associada à tabela de roteamento '{route_table_id}'.")
                            already_associated = True
                            break
                        # Se for uma associação principal, a subnet já está associada à RT principal da VPC
                        elif assoc.get('SubnetId') == subnet_id and assoc.get('Main', False) is True:
                             logging.info(f"Subnet '{subnet_id}' está associada à tabela de roteamento principal da VPC.")
                             # Precisamos desassociar da principal se for associar a uma nova RT não principal.
                             # No contexto deste script, se estamos associando explicitamente a uma RT do TGW,
                             # a associação principal não impede a associação explícita.
                             # Não precisamos desassociar da principal para associar a uma RT explícita.

                    if already_associated:
                        break

            if not already_associated:
                logging.info(f"Associando subnet '{subnet_id}' à tabela de roteamento '{route_table_id}'.")
                ec2_client.associate_route_table(
                    RouteTableId=route_table_id,
                    SubnetId=subnet_id
                )
                logging.info(f"Subnet '{subnet_id}' associada com sucesso à tabela de roteamento '{route_table_id}'.")
                successful_associations.append(subnet_id)
            else:
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

def get_vpc_cidrs(vpc_id, region, aws_access_key_id, aws_secret_access_key, aws_session_token):
    """
    Lista todos os CIDRs associados a uma VPC.
    Retorna uma lista de CIDRs.
    """
    ec2_client = get_aws_client('ec2', region, aws_access_key_id, aws_secret_access_key, aws_session_token)
    logging.info(f"Buscando todos os CIDRs associados à VPC '{vpc_id}'")
    cidrs = []
    try:
        response = ec2_client.describe_vpcs(VpcIds=[vpc_id])
        for vpc in response['Vpcs']:
            cidrs.append(vpc['CidrBlock'])
            for association in vpc.get('CidrBlockAssociations', []):
                if association['CidrBlockState']['State'] == 'associated':
                    cidrs.append(association['CidrBlock'])
        logging.info(f"CIDRs encontrados na VPC '{vpc_id}': {list(set(cidrs))}")
        return list(set(cidrs)) # Retorna apenas CIDRs únicos
    except Exception as e:
        logging.error(f"Erro ao listar CIDRs da VPC: {e}")
        return []

def get_subnets_by_cidr_prefix(vpc_id, cidr_prefix, region,
                               aws_access_key_id, aws_secret_access_key, aws_session_token):
    """
    Retorna IDs de subnets em uma VPC que começam com um determinado prefixo CIDR.
    """
    ec2_client = get_aws_client('ec2', region, aws_access_key_id, aws_secret_access_key, aws_session_token)
    logging.info(f"Buscando subnets na VPC '{vpc_id}' com CIDR prefixo '{cidr_prefix}'")
    found_subnet_ids = []
    try:
        response = ec2_client.describe_subnets(
            Filters=[
                {'Name': 'vpc-id', 'Values': [vpc_id]},
                {'Name': 'cidr-block', 'Values': [f'{cidr_prefix}*']} # Filtra por prefixo
            ]
        )
        for subnet in response['Subnets']:
            # Verificação adicional para garantir que o CIDR realmente começa com o prefixo
            if subnet['CidrBlock'].startswith(cidr_prefix.split('/')[0]):
                 found_subnet_ids.append(subnet['SubnetId'])
        logging.info(f"Subnets encontradas para CIDR prefixo '{cidr_prefix}': {found_subnet_ids}")
        return found_subnet_ids
    except Exception as e:
        logging.error(f"Erro ao buscar subnets por prefixo CIDR: {e}")
        return []

def get_subnet_for_nat_gateway(vpc_id, main_vpc_cidr, region,
                               aws_access_key_id, aws_secret_access_key, aws_session_token):
    """
    Encontra uma subnet adequada para o NAT Gateway no CIDR principal da VPC.
    Prioriza subnets com 'public' no nome da tag se possível, ou a primeira disponível.
    """
    ec2_client = get_aws_client('ec2', region, aws_access_key_id, aws_secret_access_key, aws_session_token)
    logging.info(f"Buscando subnet para NAT Gateway no CIDR '{main_vpc_cidr}' da VPC '{vpc_id}'")
    
    try:
        response = ec2_client.describe_subnets(
            Filters=[
                {'Name': 'vpc-id', 'Values': [vpc_id]},
                {'Name': 'cidr-block', 'Values': [main_vpc_cidr]} # Filtra estritamente pelo CIDR principal
            ]
        )
        
        candidate_subnets = []
        for subnet in response['Subnets']:
            # Tenta encontrar uma subnet que seja pública (AutoAssignPublicIp) e tenha um nome público
            if subnet.get('MapPublicIpOnLaunch', False):
                for tag in subnet.get('Tags', []):
                    if tag['Key'] == 'Name' and 'public' in tag['Value'].lower():
                        logging.info(f"Subnet pública ideal para NAT Gateway encontrada: {subnet['SubnetId']}")
                        return subnet['SubnetId']
                candidate_subnets.append(subnet['SubnetId'])
            else:
                candidate_subnets.append(subnet['SubnetId'])
        
        if candidate_subnets:
            logging.info(f"Nenhuma subnet 'public' ideal encontrada. Usando a primeira subnet candidata no CIDR '{main_vpc_cidr}': {candidate_subnets[0]}")
            return candidate_subnets[0]
        else:
            logging.warning(f"Nenhuma subnet encontrada no CIDR '{main_vpc_cidr}' na VPC '{vpc_id}'.")
            return None
    except Exception as e:
        logging.error(f"Erro ao encontrar subnet para NAT Gateway: {e}")
        return None

def create_subnets(vpc_id, base_cidr_block, num_subnets, subnet_prefix_length, tag_name, region,
                   aws_access_key_id, aws_secret_access_key, aws_session_token):
    """
    Cria um número especificado de subnets em diferentes AZs a partir de um CIDR block base.
    As subnets serão divididas com o subnet_prefix_length.
    Usará somente as AZs 'sa-east-1a' e 'sa-east-1b'.
    Retorna uma lista de IDs das subnets criadas.
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

    try:
        # Calcular os blocos CIDR para as novas subnets
        network = ipaddress.ip_network(base_cidr_block)
        subnets_to_create_cidrs = list(network.subnets(new_prefix=subnet_prefix_length))

        if len(subnets_to_create_cidrs) < num_subnets:
            logging.error(f"O CIDR base '{base_cidr_block}' (/{(network.prefixlen)}) não pode ser dividido em {num_subnets} subnets de prefixo /{subnet_prefix_length}. São possíveis apenas {len(subnets_to_create_cidrs)}.")
            return []

        for i in range(num_subnets):
            if i >= len(subnets_to_create_cidrs):
                logging.warning(f"Não há mais CIDRs disponíveis para criar a subnet {i+1}. Criadas {len(created_subnet_ids)} subnets.")
                break

            az_index = i % len(available_azs) # Cicla entre as AZs disponíveis e permitidas
            az_name = available_azs[az_index]
            
            subnet_cidr = str(subnets_to_create_cidrs[i])
            
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
                logging.info(f"Subnet com CIDR '{subnet_cidr}' e AZ '{az_name}' já existe na VPC '{vpc_id}' como '{subnet_id}'. Reutilizando.")
                created_subnet_ids.append(subnet_id)
            else:
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
                                    {'Key': 'Name', 'Value': f"{tag_name}-subnet-{az_suffixes.get(az_name, az_name.split('-')[-1])}-{i}"},
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
                # Verifica se a subnet já está associada a esta tabela de roteamento
                current_associations = ec2_client.describe_route_tables(
                    Filters=[
                        {'Name': 'association.subnet-id', 'Values': [subnet_id]},
                        {'Name': 'route-table-id', 'Values': [route_table_id]}
                    ]
                )['RouteTables']

                already_associated = False
                if current_associations:
                    for current_rt in current_associations:
                        for assoc in current_rt.get('Associations', []):
                            if assoc.get('SubnetId') == subnet_id and assoc.get('RouteTableId') == route_table_id:
                                logging.info(f"Subnet '{subnet_id}' já está associada à nova tabela de roteamento '{route_table_id}'.")
                                already_associated = True
                                break
                        if already_associated:
                            break

                if not already_associated:
                    ec2_client.associate_route_table(
                        RouteTableId=route_table_id,
                        SubnetId=subnet_id
                    )
                    logging.info(f"Subnet '{subnet_id}' associada à nova tabela de roteamento '{route_table_id}'.")
                else:
                    logging.info(f"Subnet '{subnet_id}' já estava associada à nova tabela de roteamento '{route_table_id}'.")

            except Exception as e:
                logging.error(f"Erro ao associar subnet '{subnet_id}' à nova tabela de roteamento '{route_table_id}': {e}")
        return route_table_id
    except Exception as e:
        logging.error(f"Erro ao criar e associar nova tabela de roteamento: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Script para configurar recursos de rede AWS em uma pipeline Harness.")
    parser.add_argument('--region', type=str, default='sa-east-1', help='Região AWS a ser usada.')
    parser.add_argument('--vpc-id', type=str, required=True, help='ID da VPC onde os recursos serão criados.')
    parser.add_argument('--security-group-ids', nargs='+', required=True, help='IDs dos Security Groups para os VPC Endpoints.')
    parser.add_argument('--num-subnets', type=int, default=4, help='Número de subnets desejadas para o CIDR 100.99.0.0/16 (recomenda-se 2 ou 4 para AZs a e b).')
    parser.add_argument('--subnet-prefix-length', type=int, default=20, help='Comprimento do prefixo das novas subnets do 100.99.0.0/16 (e.g., 20 para /20).') # Mudado para 20
    parser.add_argument('--new-subnet-tag-name', type=str, default='Harness-Managed-Private', help='Tag Name para as novas subnets criadas (do 100.99.0.0/16).') # Renomeado para clareza
    parser.add_argument('--new-routable-cidr', type=str, default='100.99.0.0/16', help='CIDR a ser dividido em novas subnets (este será o CIDR "não roteável" via TGW).') # Renomeado para clareza
    parser.add_argument('--main-vpc-cidr', type=str, required=True, help='CIDR principal da VPC onde o NAT Gateway deve ser criado e onde as subnets roteáveis existentes estão.') # NOVO ARGUMENTO

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

    # 4. Criar as novas subnets (do new_routable_cidr, e.g., 100.99.0.0/16)
    logging.info(f"Passo 4: Criando as novas subnets a partir do CIDR '{args.new_routable_cidr}' (somente AZs 'a' e 'b').")
    created_subnets = create_subnets(
        args.vpc_id,
        args.new_routable_cidr,
        args.num_subnets,
        args.subnet_prefix_length,
        args.new_subnet_tag_name,
        args.region,
        aws_access_key_id, aws_secret_access_key, aws_session_token
    )

    if not created_subnets:
        logging.error("Nenhuma subnet foi criada com sucesso a partir do CIDR 100.99.0.0/16. Abortando a execução.")
        exit(1)

    # 5. Criar uma NOVA Tabela de Roteamento para as Novas Subnets e associá-las, com rota para NAT GW
    logging.info("Passo 5: Criando uma NOVA tabela de roteamento para as subnets recém-criadas (100.99.0.0/16) e associando-as com rota para NAT Gateway.")
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
    
    existing_main_cidr_subnets = get_subnets_by_cidr_prefix(
        args.vpc_id,
        args.main_vpc_cidr.split('/')[0], # Pega apenas o prefixo do IP para a busca
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
    logging.info("Passo 7: Criando VPC Endpoints nas subnets recém-criadas (do 100.99.0.0/16).")
    create_vpc_endpoints(
        service_endpoints_to_create,
        args.vpc_id,
        created_subnets, # Usar as subnets do 100.99.0.0/16 para os endpoints
        args.security_group_ids,
        args.region,
        aws_access_key_id, aws_secret_access_key, aws_session_token
    )

    logging.info("Configuração de rede AWS concluída através do script Python.")

if __name__ == "__main__":
    main()
