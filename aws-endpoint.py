import boto3
import argparse
import logging
import os

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
            current_associations = ec2_client.describe_route_tables(
                Filters=[
                    {'Name': 'association.subnet-id', 'Values': [subnet_id]}
                ]
            )['RouteTables']

            already_associated = False
            for current_rt in current_associations:
                for assoc in current_rt.get('Associations', []):
                    if assoc.get('SubnetId') == subnet_id and assoc.get('RouteTableId') == route_table_id:
                        logging.info(f"Subnet '{subnet_id}' já está associada à tabela de roteamento '{route_table_id}'.")
                        already_associated = True
                        break
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
                successful_associations.append(subnet_id)

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

def get_vpc_cidrs(vpc_id, target_cidr_prefix, region,
                  aws_access_key_id, aws_secret_access_key, aws_session_token):
    """
    Lista os CIDRs associados à VPC com um prefixo específico.
    Retorna uma lista de CIDRs.
    """
    ec2_client = get_aws_client('ec2', region, aws_access_key_id, aws_secret_access_key, aws_session_token)
    logging.info(f"Buscando CIDRs associados à VPC '{vpc_id}' com prefixo: {target_cidr_prefix}")
    cidrs = []
    try:
        response = ec2_client.describe_vpcs(VpcIds=[vpc_id])
        for vpc in response['Vpcs']:
            for association in vpc.get('CidrBlockAssociations', []):
                if association['CidrBlock'].startswith(target_cidr_prefix.split('/')[0]):
                    cidrs.append(association['CidrBlock'])
            if vpc['CidrBlock'].startswith(target_cidr_prefix.split('/')[0]):
                cidrs.append(vpc['CidrBlock'])
        logging.info(f"CIDRs encontrados na VPC '{vpc_id}' com prefixo '{target_cidr_prefix}': {cidrs}")
        return list(set(cidrs))
    except Exception as e:
        logging.error(f"Erro ao listar CIDRs da VPC: {e}")
        return []

def create_subnets(vpc_id, cidr_block, num_subnets, tag_name, region,
                   aws_access_key_id, aws_secret_access_key, aws_session_token):
    """
    Cria um número especificado de subnets em diferentes AZs dentro de um CIDR block.
    Retorna uma lista de IDs das subnets criadas.
    """
    ec2_client = get_aws_client('ec2', region, aws_access_key_id, aws_secret_access_key, aws_session_token)
    ec2_resource = get_aws_resource('ec2', region, aws_access_key_id, aws_secret_access_key, aws_session_token)
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

    az_suffixes = ['a', 'b', 'c', 'd', 'e', 'f']
    az_mapping = {}
    for i, az_name in enumerate(available_azs):
        if i < len(az_suffixes):
            az_mapping[az_name] = az_suffixes[i]

    try:
        base_ip_part = int(cidr_block.split('.')[2])
        network_prefix = ".".join(cidr_block.split('.')[:2])

        for i in range(num_subnets):
            if i >= len(available_azs):
                logging.warning(f"Não há AZs suficientes disponíveis para criar {num_subnets} subnets. Reutilizando AZs.")
                az_index = i % len(available_azs)
            else:
                az_index = i

            az_name = available_azs[az_index]
            subnet_cidr = f"{network_prefix}.{base_ip_part + i}.0/24"

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
                                {'Key': 'Name', 'Value': f"{tag_name}-subnet-{az_mapping.get(az_name, az_name.split('-')[-1])}-{i}"},
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

def create_and_associate_route_table(vpc_id, subnet_ids, nat_gateway_id, region,
                                     aws_access_key_id, aws_secret_access_key, aws_session_token):
    """
    Cria uma nova tabela de roteamento, associa as subnets e adiciona uma rota para o NAT Gateway.
    """
    ec2_client = get_aws_client('ec2', region, aws_access_key_id, aws_secret_access_key, aws_session_token)
    logging.info(f"Criando nova tabela de roteamento na VPC '{vpc_id}' e associando subnets.")

    try:
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

    # **Obter credenciais AWS das variáveis de ambiente injetadas pelo Harness**
    aws_access_key_id = os.environ.get('AWS_ACCESS_KEY_ID')
    aws_secret_access_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    aws_session_token = os.environ.get('AWS_SESSION_TOKEN') # Opcional, para credenciais temporárias

    if not aws_access_key_id or not aws_secret_access_key:
        logging.error("Variáveis de ambiente AWS_ACCESS_KEY_ID e/ou AWS_SECRET_ACCESS_KEY não encontradas. Por favor, configure-as na pipeline do Harness.")
        exit(1)


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
    vpc_cidrs = get_vpc_cidrs(args.vpc_id, args.target_vpc_cidr, args.region,
                              aws_access_key_id, aws_secret_access_key, aws_session_token)
    created_subnets = []
    if vpc_cidrs:
        target_cidr_for_subnets = vpc_cidrs[0]
        logging.info(f"CIDR alvo para criação de subnets: {target_cidr_for_subnets}")
        created_subnets = create_subnets(
            args.vpc_id,
            target_cidr_for_subnets,
            args.num_subnets,
            args.subnet_tag_name,
            args.region,
            aws_access_key_id, aws_secret_access_key, aws_session_token
        )
    else:
        logging.error(f"Nenhum CIDR associado à VPC '{args.vpc_id}' encontrado com o prefixo '{args.target_vpc_cidr}'.")
        exit(1)

    if not created_subnets:
        logging.error("Nenhuma subnet foi criada com sucesso. Abortando a execução.")
        exit(1)

    # 2. Identificar a tabela de roteamento roteável (com TGW)
    logging.info("Passo 2: Identificando tabela de roteamento roteável...")
    routable_route_table_id = identify_routable_network(args.vpc_id, args.region,
                                                      aws_access_key_id, aws_secret_access_key, aws_session_token)
    
    if routable_route_table_id:
        logging.info(f"Tabela de roteamento roteável '{routable_route_table_id}' encontrada. Associando subnets recém-criadas a ela.")
        associate_subnets_to_route_table(routable_route_table_id, created_subnets, args.region,
                                         aws_access_key_id, aws_secret_access_key, aws_session_token)
    else:
        logging.warning("Nenhuma tabela de roteamento com rota para Transit Gateway encontrada. Subnets não serão associadas a uma RT de TGW.")

    # 3. Criar NAT Gateway privado (usando a primeira subnet criada para hospedá-lo)
    logging.info("Passo 3: Criando NAT Gateway privado...")
    nat_gateway_id = None
    if created_subnets:
        nat_gateway_subnet_id = created_subnets[0]
        nat_gateway_id = create_private_nat_gateway(nat_gateway_subnet_id, args.region,
                                                    aws_access_key_id, aws_secret_access_key, aws_session_token)
    else:
        logging.error("Não foi possível criar NAT Gateway privado pois nenhuma subnet foi criada.")
        exit(1)

    # 4. Criar VPC Endpoints
    logging.info("Passo 4: Criando VPC Endpoints...")
    create_vpc_endpoints(
        service_endpoints_to_create,
        args.vpc_id,
        created_subnets,
        args.security_group_ids,
        args.region,
        aws_access_key_id, aws_secret_access_key, aws_session_token
    )

    logging.info("Passo 5: Configuração final das tabelas de roteamento para as subnets criadas.")
    if routable_route_table_id:
        if nat_gateway_id:
            try:
                ec2_client_for_check = get_aws_client('ec2', args.region, aws_access_key_id, aws_secret_access_key, aws_session_token)
                rt_details = ec2_client_for_check.describe_route_tables(RouteTableIds=[routable_route_table_id])['RouteTables'][0]
                nat_route_exists = any(
                    route['DestinationCidrBlock'] == '0.0.0.0/0' and route.get('NatGatewayId') == nat_gateway_id
                    for route in rt_details.get('Routes', [])
                )
                if not nat_route_exists:
                    ec2_client_for_check.create_route(
                        DestinationCidrBlock='0.0.0.0/0',
                        NatGatewayId=nat_gateway_id,
                        RouteTableId=routable_route_table_id
                    )
                    logging.info(f"Rota '0.0.0.0/0' para NAT Gateway '{nat_gateway_id}' adicionada à tabela de roteamento '{routable_route_table_id}'.")
                else:
                    logging.info(f"Rota '0.0.0.0/0' para NAT Gateway '{nat_gateway_id}' já existe na tabela de roteamento '{routable_route_table_id}'.")
            except Exception as e:
                logging.error(f"Erro ao verificar/adicionar rota para NAT Gateway na RT do TGW: {e}")
    else:
        logging.info("Nenhuma tabela de roteamento com rota para Transit Gateway encontrada. Criando uma nova tabela de roteamento para as subnets e associando o NAT Gateway.")
        if created_subnets and nat_gateway_id:
            create_and_associate_route_table(args.vpc_id, created_subnets, nat_gateway_id, args.region,
                                             aws_access_key_id, aws_secret_access_key, aws_session_token)
        else:
            logging.error("Não foi possível criar e associar nova tabela de roteamento devido a recursos ausentes (subnets ou NAT Gateway).")

    logging.info("Configuração de rede AWS concluída através do script Python.")

if __name__ == "__main__":
    main()
