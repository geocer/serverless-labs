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
                    # Verifica se é uma associação explícita (não a associação principal da VPC)
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

def create_private_nat_gateway(subnet_id, az_suffix, region,
                               aws_access_key_id, aws_secret_access_key, aws_session_token):
    """
    Cria um NAT Gateway privado na subnet especificada.
    Retorna o ID do NAT Gateway.
    """
    ec2_client = get_aws_client('ec2', region, aws_access_key_id, aws_secret_access_key, aws_session_token)
    logging.info(f"Criando NAT Gateway privado na subnet: {subnet_id} para AZ {az_suffix}")

    try:
        # Verificar se já existe um NAT Gateway na subnet
        existing_nat_gateways = ec2_client.describe_nat_gateways(
            Filters=[
                {'Name': 'subnet-id', 'Values': [subnet_id]},
                {'Name': 'state', 'Values': ['pending', 'available']}
            ]
        )['NatGateways']

        if existing_nat_gateways:
            nat_gateway_id = existing_nat_gateways[0]['NatGatewayId']
            logging.info(f"NAT Gateway '{nat_gateway_id}' já existe na subnet '{subnet_id}'. Reutilizando.")
            return nat_gateway_id

        response = ec2_client.create_nat_gateway(
            SubnetId=subnet_id,
            ConnectivityType='private',
            TagSpecifications=[
                {
                    'ResourceType': 'natgateway',
                    'Tags': [
                        {'Key': 'Name', 'Value': f'PrivateNATGateway-{az_suffix}'},
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
        logging.error(f"Erro ao criar NAT Gateway privado na subnet {subnet_id}: {e}")
        return None

def get_subnets_for_nat_gateway(vpc_id, main_vpc_cidr, region,
                               aws_access_key_id, aws_secret_access_key, aws_session_token):
    """
    Encontra subnets adequadas para os NAT Gateways, uma em cada AZ permitida (sa-east-1a, sa-east-1b).
    Prioriza subnets com 'public' no nome da tag se possível, ou a primeira disponível.
    Retorna um dicionário {az_name: subnet_id}.
    """
    ec2_client = get_aws_client('ec2', region, aws_access_key_id, aws_secret_access_key, aws_session_token)
    logging.info(f"Buscando subnets para NAT Gateways no CIDR '{main_vpc_cidr}' da VPC '{vpc_id}'")
    
    allowed_azs = ['sa-east-1a', 'sa-east-1b']
    nat_gateway_subnets = {}

    try:
        # Filtra subnets que estão dentro do main_vpc_cidr
        all_subnets_in_vpc = ec2_client.describe_subnets(
            Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
        )['Subnets']

        main_network = ipaddress.ip_network(main_vpc_cidr)
        
        for az_name in allowed_azs:
            candidate_subnets_in_az = []
            for subnet in all_subnets_in_vpc:
                if subnet['AvailabilityZone'] == az_name:
                    subnet_network = ipaddress.ip_network(subnet['CidrBlock'])
                    if subnet_network.subnet_of(main_network):
                        candidate_subnets_in_az.append(subnet)
            
            if not candidate_subnets_in_az:
                logging.warning(f"Nenhuma subnet encontrada dentro do CIDR '{main_vpc_cidr}' na AZ '{az_name}' da VPC '{vpc_id}'.")
                continue

            found_subnet = None
            # Prioriza subnets com tags de nome 'public'
            for subnet in candidate_subnets_in_az:
                for tag in subnet.get('Tags', []):
                    if tag['Key'] == 'Name' and 'public' in tag['Value'].lower():
                        found_subnet = subnet
                        logging.info(f"Subnet pública ideal para NAT Gateway encontrada na AZ '{az_name}': {subnet['SubnetId']}")
                        break
                if found_subnet:
                    break
            
            if not found_subnet:
                # Se nenhuma subnet 'public' for encontrada, retorna a primeira candidata
                found_subnet = candidate_subnets_in_az[0]
                logging.info(f"Nenhuma subnet 'public' ideal encontrada na AZ '{az_name}'. Usando a primeira subnet candidata: {found_subnet['SubnetId']}")
            
            nat_gateway_subnets[az_name] = found_subnet['SubnetId']

        if not nat_gateway_subnets:
            logging.error(f"Nenhuma subnet adequada encontrada para NAT Gateway nas AZs {allowed_azs} dentro do CIDR '{main_vpc_cidr}'.")
        return nat_gateway_subnets
    except Exception as e:
        logging.error(f"Erro ao encontrar subnets para NAT Gateway: {e}")
        return {}

def create_subnets(vpc_id, base_cidr_block, subnet_prefix_length, region,
                   aws_access_key_id, aws_secret_access_key, aws_session_token):
    """
    Cria um número especificado de subnets em diferentes AZs a partir de um CIDR block base.
    As subnets serão divididas com o subnet_prefix_length.
    Usará somente as AZs 'sa-east-1a' e 'sa-east-1b'.
    Retorna um dicionário de IDs de subnets criadas, mapeado por nome fixo.
    As tags de nome serão 'app-non-routable-1a', 'app-non-routable-1b', 'database-non-routable-1a', 'database-non-routable-1b'.
    """
    ec2_client = get_aws_client('ec2', region, aws_access_key_id, aws_secret_access_key, aws_session_token)
    logging.info(f"Iniciando a criação de subnets na VPC '{vpc_id}' a partir do CIDR base '{base_cidr_block}' com prefixo /{subnet_prefix_length}")

    created_subnet_ids = {}
    
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
            return {}
        logging.info(f"AZs disponíveis e selecionadas para criação de subnets: {available_azs}")

    except Exception as e:
        logging.error(f"Erro ao listar AZs: {e}")
        return {}

    # Mapeamento de AZ para sufixo (a, b) para nomes de tags
    az_suffixes = {'sa-east-1a': '1a', 'sa-east-1b': '1b'}
    tag_types = ['app', 'database']
    expected_num_subnets = len(allowed_azs) * len(tag_types) # Deve ser 4

    try:
        # Calcular os blocos CIDR para as novas subnets
        network = ipaddress.ip_network(base_cidr_block)
        subnets_to_create_cidrs = list(network.subnets(new_prefix=subnet_prefix_length))

        if len(subnets_to_create_cidrs) < expected_num_subnets:
            logging.error(f"O CIDR base '{base_cidr_block}' (/{(network.prefixlen)}) não pode ser dividido em {expected_num_subnets} subnets de prefixo /{subnet_prefix_length}. São possíveis apenas {len(subnets_to_create_cidrs)}.")
            return {}
        
        cidr_idx = 0
        
        for tag_type in tag_types:
            for az_name in available_azs:
                if cidr_idx >= len(subnets_to_create_cidrs):
                    logging.warning("Não há mais CIDRs disponíveis para alocar. Saindo da criação de subnets.")
                    break
                
                subnet_cidr = str(subnets_to_create_cidrs[cidr_idx])
                final_tag_name = f"{tag_type}-non-routable-{az_suffixes.get(az_name)}"

                # Verificar se já existe uma subnet com este CIDR e AZ na VPC
                existing_subnets = ec2_client.describe_subnets(
                    Filters=[
                        {'Name': 'vpc-id', 'Values': [vpc_id]},
                        {'Name': 'cidr-block', 'Values': [subnet_cidr]},
                        {'Name': 'availability-zone', 'Values': [az_name]} 
                    ]
                )['Subnets']

                subnet_id = None
                if existing_subnets:
                    subnet_id = existing_subnets[0]['SubnetId']
                    logging.info(f"Subnet com CIDR '{subnet_cidr}' e AZ '{az_name}' (Tag: {final_tag_name}) já existe na VPC '{vpc_id}' como '{subnet_id}'. Reutilizando.")
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
                        logging.info(f"Subnet '{subnet_id}' com CIDR '{subnet_cidr}' criada na AZ '{az_name}'.")
                    except Exception as e:
                        logging.error(f"Erro ao criar subnet '{subnet_cidr}' na AZ '{az_name}': {e}")
                        continue # Continuar para a próxima iteração se houver um erro na criação

                if subnet_id:
                    created_subnet_ids[final_tag_name] = subnet_id
                cidr_idx += 1

    except Exception as e:
        logging.error(f"Erro geral ao criar subnets: {e}")

    return created_subnet_ids

def create_new_route_table_and_associate(vpc_id, subnet_ids_map, nat_gateway_ids_map, region,
                                         aws_access_key_id, aws_secret_access_key, aws_session_token):
    """
    Cria DUAS novas tabelas de roteamento (uma para 'a', outra para 'b'),
    adiciona rota para o NAT Gateway correspondente à sua AZ, e associa as subnets fornecidas.
    Esta RT será para as subnets "não roteáveis" (do CIDR 100.99.0.0/16) que usam o NAT Gateway.
    subnet_ids_map é um dicionário {nome_da_tag: subnet_id}.
    nat_gateway_ids_map é um dicionário {az_name: nat_gateway_id}.
    Retorna um dicionário {az_name: route_table_id}.
    """
    ec2_client = get_aws_client('ec2', region, aws_access_key_id, aws_secret_access_key, aws_session_token)
    logging.info(f"Criando novas tabelas de roteamento na VPC '{vpc_id}' para subnets não roteáveis e associando.")

    new_non_routable_rts = {}
    allowed_azs = ['sa-east-1a', 'sa-east-1b']
    az_suffixes = {'sa-east-1a': '1a', 'sa-east-1b': '1b'}

    for az_name in allowed_azs:
        rt_name = f'Harness-Managed-NonRoutable-RT-{az_suffixes.get(az_name)}'
        nat_gateway_id = nat_gateway_ids_map.get(az_name)

        if not nat_gateway_id:
            logging.error(f"NAT Gateway ID não encontrado para AZ '{az_name}'. Não será possível configurar a tabela de roteamento para esta AZ.")
            continue

        try:
            # Verificar se a tabela de roteamento já existe pelo nome da tag
            existing_rts = ec2_client.describe_route_tables(
                Filters=[
                    {'Name': 'vpc-id', 'Values': [vpc_id]},
                    {'Name': 'tag:Name', 'Values': [rt_name]}
                ]
            )['RouteTables']

            route_table_id = None
            if existing_rts:
                route_table_id = existing_rts[0]['RouteTableId']
                logging.info(f"Tabela de roteamento '{rt_name}' já existe como '{route_table_id}'. Reutilizando.")
            else:
                response = ec2_client.create_route_table(
                    VpcId=vpc_id,
                    TagSpecifications=[
                        {
                            'ResourceType': 'route-table',
                            'Tags': [
                                {'Key': 'Name', 'Value': rt_name}, 
                                {'Key': 'ManagedBy', 'Value': 'HarnessPipeline'}
                            ]
                        },
                    ]
                )
                route_table_id = response['RouteTable']['RouteTableId']
                logging.info(f"Nova tabela de roteamento '{route_table_id}' ('{rt_name}') criada com sucesso para subnets não roteáveis.")

            new_non_routable_rts[az_name] = route_table_id

            # Adicionar rota para NAT Gateway (se não existir)
            routes_in_rt = ec2_client.describe_route_tables(RouteTableIds=[route_table_id])['RouteTables'][0]['Routes']
            nat_route_exists = any(r.get('NatGatewayId') == nat_gateway_id and r.get('DestinationCidrBlock') == '0.0.0.0/0' for r in routes_in_rt)

            if not nat_route_exists:
                try:
                    ec2_client.create_route(
                        DestinationCidrBlock='0.0.0.0/0',
                        NatGatewayId=nat_gateway_id,
                        RouteTableId=route_table_id
                    )
                    logging.info(f"Rota '0.0.0.0/0' para NAT Gateway '{nat_gateway_id}' adicionada à tabela de roteamento '{route_table_id}'.")
                except Exception as e:
                    logging.error(f"Erro ao adicionar rota para NAT Gateway na tabela de roteamento '{route_table_id}': {e}")
            else:
                logging.info(f"Rota '0.0.0.0/0' para NAT Gateway '{nat_gateway_id}' já existe na tabela de roteamento '{route_table_id}'.")


            # Associar as subnets criadas nesta AZ à RT
            subnets_for_this_az = [
                subnet_id for tag_name, subnet_id in subnet_ids_map.items()
                if tag_name.endswith(az_suffixes.get(az_name)) and ('app' in tag_name or 'database' in tag_name)
            ]
            
            for subnet_id in subnets_for_this_az:
                try:
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

        except Exception as e:
            logging.error(f"Erro ao criar e configurar tabela de roteamento para AZ '{az_name}': {e}")
    return new_non_routable_rts

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
    # num-subnets e new-subnet-tag-name-prefix serão controlados internamente para nomes fixos e 4 subnets
    parser.add_argument('--subnet-prefix-length', type=int, default=20, help='Comprimento do prefixo das novas subnets do 100.99.0.0/16 (e.g., 20 para /20).')
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
    
    # 1. Identificar a tabela de roteamento roteável (com TGW) - OK
    logging.info("Passo 1: Identificando tabela de roteamento roteável (com TGW).")
    routable_route_table_id = identify_routable_network(args.vpc_id, args.region,
                                                        aws_access_key_id, aws_secret_access_key, aws_session_token)
    
    if not routable_route_table_id:
        logging.error("Nenhuma tabela de roteamento com rota para Transit Gateway encontrada. Não é possível configurar a rede roteável. Abortando.")
        exit(1)

    # 2. Identificar uma subnet existente para o NAT Gateway (no main_vpc_cidr)
    logging.info(f"Passo 2: Identificando subnets para os NAT Gateways no CIDR '{args.main_vpc_cidr}' nas AZs 'sa-east-1a' e 'sa-east-1b'.")
    nat_gateway_subnets = get_subnets_for_nat_gateway(args.vpc_id, args.main_vpc_cidr, args.region,
                                                       aws_access_key_id, aws_secret_access_key, aws_session_token)
    
    if not nat_gateway_subnets or len(nat_gateway_subnets) < 2:
        logging.error(f"Não foi possível encontrar subnets adequadas em ambas as AZs ('sa-east-1a', 'sa-east-1b') no CIDR '{args.main_vpc_cidr}' para criar os NAT Gateways. Abortando.")
        exit(1)
    
    # 3. Criar NAT Gateways privados (um em cada AZ)
    logging.info("Passo 3: Criando NAT Gateways privados (um em cada AZ).")
    nat_gateway_ids = {}
    for az_name, subnet_id in nat_gateway_subnets.items():
        az_suffix = az_name.split('-')[-1] # 'a' or 'b'
        nat_gw_id = create_private_nat_gateway(subnet_id, az_suffix, args.region,
                                            aws_access_key_id, aws_secret_access_key, aws_session_token)
        if nat_gw_id:
            nat_gateway_ids[az_name] = nat_gw_id
        else:
            logging.error(f"Falha ao criar NAT Gateway privado na AZ '{az_name}'. Abortando.")
            exit(1)

    if len(nat_gateway_ids) < 2:
        logging.error("Não foi possível criar NAT Gateways em ambas as AZs. Abortando.")
        exit(1)

    # 4. Criar as novas subnets (do non-routable-cidr, e.g., 100.99.0.0/16)
    logging.info(f"Passo 4: Criando as novas subnets a partir do CIDR '{args.non_routable_cidr}' (nomes fixos e AZs '1a' e '1b').")
    created_subnets_map = create_subnets(
        args.vpc_id,
        args.non_routable_cidr,
        args.subnet_prefix_length,
        args.region,
        aws_access_key_id, aws_secret_access_key, aws_session_token
    )

    if not created_subnets_map or len(created_subnets_map) < 4:
        logging.error("Não foi possível criar todas as 4 subnets esperadas com os nomes fixos. Abortando a execução.")
        exit(1)
    
    logging.info(f"Subnets criadas/reutilizadas com sucesso: {created_subnets_map}")

    # 5. Criar uma NOVA Tabela de Roteamento para as Novas Subnets e associá-las, com rota para NAT GW
    logging.info("Passo 5: Criando NOVAS tabelas de roteamento para as subnets recém-criadas (do 100.99.0.0/16) e associando-as com rota para NAT Gateway.")
    new_non_routable_rts_map = create_new_route_table_and_associate(
        args.vpc_id,
        created_subnets_map,
        nat_gateway_ids,
        args.region,
        aws_access_key_id, aws_secret_access_key, aws_session_token
    )

    if not new_non_routable_rts_map or len(new_non_routable_rts_map) < 2:
        logging.error("Falha ao criar e configurar as novas tabelas de roteamento para as subnets 100.99.0.0/16. Abortando.")
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
    logging.info("Passo 7: Criando VPC Endpoints nas subnets 'app-non-routable-1a' e 'app-non-routable-1b' e Gateway Endpoints.")
    
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

    # Filtrar as subnets para os VPC Endpoints de Interface
    app_non_routable_subnets_for_endpoints = []
    if 'app-non-routable-1a' in created_subnets_map:
        app_non_routable_subnets_for_endpoints.append(created_subnets_map['app-non-routable-1a'])
    if 'app-non-routable-1b' in created_subnets_map:
        app_non_routable_subnets_for_endpoints.append(created_subnets_map['app-non-routable-1b'])

    if len(app_non_routable_subnets_for_endpoints) < 2:
        logging.error("Não foi possível encontrar as subnets 'app-non-routable-1a' e 'app-non-routable-1b' para criar os VPC Endpoints de interface. Abortando.")
        exit(1)
    
    # Lidar com Interface Endpoints
    create_vpc_endpoints(
        service_endpoints_to_create, # Lista de Interface Endpoints
        args.vpc_id,
        app_non_routable_subnets_for_endpoints, # Usar as subnets 'app' de diferentes AZs
        args.security_group_ids,
        args.region,
        aws_access_key_id, aws_secret_access_key, aws_session_token
    )

    logging.info("Configuração de rede AWS concluída através do script Python.")

if __name__ == "__main__":
    main()