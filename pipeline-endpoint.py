import boto3
import os

# Configuração da AWS (preferencialmente via variáveis de ambiente ou ~/.aws/credentials)
# Se estiver rodando em uma instância EC2 com um IAM Role, não é necessário configurar as credenciais explicitamente.
# region_name = os.getenv("AWS_DEFAULT_REGION", "sa-east-1") # Exemplo: sa-east-1
# boto3.setup_default_session(region_name=region_name)

ec2_client = boto3.client('ec2')
ec2_resource = boto3.resource('ec2')

# Lista de nomes de serviço de endpoint da imagem
# IMPORTANTE: Confirme se estes são os nomes de serviço corretos para a sua região.
# Nomes de serviço para PrivateLink seguem o padrão com.<region>.<service>
# Os da imagem parecem já estar no formato correto para sa-east-1.
# Por exemplo: com.amazonaws.sa-east-1.s3
# com.amazonaws.sa-east-1.ssm
# com.amazonaws.sa-east-1.ssmmessages
# com.amazonaws.sa-east-1.ec2messages
# com.amazonaws.sa-east-1.logs
# com.amazonaws.sa-east-1.ecr.api
# com.amazonaws.sa-east-1.sts
# com.amazonaws.sa-east-1.elasticloadbalancing
# com.amazonaws.sa-east-1.autoscaling
# com.amazonaws.sa-east-1.ec2
# com.amazonaws.sa-east-1.ecr.dkr
# eice-0ca614a2e456d94d7.eb8c576e.ec2-instance-connect-endpoint.sa-east-1.amazonaws.com # Este parece ser um endpoint específico, não um serviço padrão

SERVICE_NAMES_TO_CREATE = [
    "com.amazonaws.sa-east-1.s3",
    "com.amazonaws.sa-east-1.ssm",
    "com.amazonaws.sa-east-1.ssmmessages",
    "com.amazonaws.sa-east-1.ec2messages",
    "com.amazonaws.sa-east-1.logs",
    "com.amazonaws.sa-east-1.ecr.api",
    "com.amazonaws.sa-east-1.sts",
    "com.amazonaws.sa-east-1.elasticloadbalancing",
    "com.amazonaws.sa-east-1.autoscaling",
    "com.amazonaws.sa-east-1.ec2",
    "com.amazonaws.sa-east-1.ecr.dkr",
    # Adicionar o endpoint de instância connect se necessário.
    # Para o endpoint de instância connect, você provavelmente precisaria de informações como o VPC ID.
    # "eice-0ca614a2e456d94d7.eb8c576e.ec2-instance-connect-endpoint.sa-east-1.amazonaws.com"
]

# --- Variáveis que você pode precisar ajustar ---
# Se você souber o ID da sua VPC, defina-o aqui. Caso contrário, o script tentará encontrar uma.
TARGET_VPC_ID = "vpc-0abcdef1234567890" # Substitua pelo ID da sua VPC, se souber

# --- 1. Identificar a Rede Roteável (Subnet com rota para Transit Gateway) ---
def find_subnet_for_tgw(vpc_id=None):
    print("\n--- Procurando subnet com rota para Transit Gateway ---")
    subnets_with_tgw_route = []

    filters = []
    if vpc_id:
        filters.append({'Name': 'vpc-id', 'Values': [vpc_id]})

    response = ec2_client.describe_route_tables(Filters=filters)

    found_tgw_route = False
    target_route_table_id = None
    target_subnet_id = None
    target_availability_zone = None

    for rt in response['RouteTables']:
        for route in rt['Routes']:
            if 'TransitGatewayId' in route and route['State'] == 'active':
                print(f"Tabela de Roteamento '{rt['RouteTableId']}' tem uma rota ativa para Transit Gateway '{route['TransitGatewayId']}'.")
                found_tgw_route = True
                target_route_table_id = rt['RouteTableId']

                # Encontrar a subnet associada a esta Route Table
                if rt['Associations']:
                    for assoc in rt['Associations']:
                        if 'SubnetId' in assoc and assoc['SubnetId']:
                            target_subnet_id = assoc['SubnetId']
                            print(f"Subnet '{target_subnet_id}' está associada a esta Tabela de Roteamento.")
                            # Obter a AZ da subnet
                            subnet_info = ec2_resource.Subnet(target_subnet_id)
                            target_availability_zone = subnet_info.availability_zone
                            print(f"Disponibilidade da Subnet: {target_availability_zone}")
                            return target_subnet_id, target_availability_zone, target_route_table_id

    if not found_tgw_route:
        print("Nenhuma rota ativa para Transit Gateway encontrada em nenhuma Tabela de Roteamento na VPC especificada (ou em todas as VPCs).")
        return None, None, None


# --- 2. Criar Interface Endpoints (PrivateLink) ---
def create_vpc_endpoints(subnet_id, vpc_id):
    print("\n--- Criando Interface Endpoints (PrivateLink) ---")
    if not subnet_id or not vpc_id:
        print("Subnet ID ou VPC ID não fornecidos. Não é possível criar endpoints.")
        return

    for service_name in SERVICE_NAMES_TO_CREATE:
        try:
            print(f"Verificando se o endpoint para '{service_name}' já existe...")
            existing_endpoints = ec2_client.describe_vpc_endpoints(
                Filters=[
                    {'Name': 'service-name', 'Values': [service_name]},
                    {'Name': 'vpc-id', 'Values': [vpc_id]}
                ]
            )

            if existing_endpoints['VpcEndpoints']:
                print(f"Endpoint para '{service_name}' já existe: {existing_endpoints['VpcEndpoints'][0]['VpcEndpointId']}")
            else:
                print(f"Criando endpoint para o serviço: {service_name} na subnet: {subnet_id}")
                response = ec2_client.create_vpc_endpoint(
                    VpcEndpointType='Interface',
                    VpcId=vpc_id,
                    ServiceName=service_name,
                    SubnetIds=[subnet_id],
                    PrivateDnsEnabled=True # Habilitar DNS privado é uma boa prática
                )
                endpoint_id = response['VpcEndpoint']['VpcEndpointId']
                print(f"Endpoint '{service_name}' criado com ID: {endpoint_id}. Status: {response['VpcEndpoint']['State']}")
        except Exception as e:
            print(f"Erro ao criar endpoint para '{service_name}': {e}")


# --- 3. Criar NAT Gateway Privado ---
def create_private_nat_gateway(subnet_id, route_table_id, availability_zone):
    print("\n--- Criando NAT Gateway Privado ---")
    if not subnet_id or not route_table_id or not availability_zone:
        print("Informações da subnet, rota ou AZ incompletas. Não é possível criar NAT Gateway.")
        return

    # 1. Alocar um Elastic IP privado
    try:
        print("Alocando Elastic IP (EIP) privado...")
        eip_response = ec2_client.allocate_address(
            Domain='vpc',
            TagSpecifications=[
                {
                    'ResourceType': 'elastic-ip',
                    'Tags': [
                        {'Key': 'Name', 'Value': f'Private-NAT-EIP-{subnet_id}'}
                    ]
                }
            ]
        )
        allocation_id = eip_response['AllocationId']
        print(f"EIP privado alocado com Allocation ID: {allocation_id}")

        # 2. Criar o NAT Gateway
        print(f"Criando NAT Gateway na subnet: {subnet_id} com EIP Allocation ID: {allocation_id}")
        nat_gateway_response = ec2_client.create_nat_gateway(
            SubnetId=subnet_id,
            AllocationId=allocation_id,
            ConnectivityType='private', # NAT Gateway Privado
            TagSpecifications=[
                {
                    'ResourceType': 'natgateway',
                    'Tags': [
                        {'Key': 'Name', 'Value': f'Private-NAT-Gateway-{subnet_id}'}
                    ]
                }
            ]
        )
        nat_gateway_id = nat_gateway_response['NatGateway']['NatGatewayId']
        print(f"NAT Gateway privado criado com ID: {nat_gateway_id}. Status: {nat_gateway_response['NatGateway']['State']}")

        # Opcional: Esperar o NAT Gateway ficar disponível
        print("Aguardando o NAT Gateway ficar disponível...")
        waiter = ec2_client.get_waiter('nat_gateway_available')
        waiter.wait(NatGatewayIds=[nat_gateway_id])
        print("NAT Gateway privado está disponível.")

        # 3. Adicionar rota na tabela de roteamento para o NAT Gateway (se necessário)
        # Normalmente, um NAT Gateway é usado para permitir que instâncias em subnets privadas
        # acessem a internet ou outros serviços fora da VPC.
        # Para um NAT Gateway "privado", ele pode ser usado para rotear tráfego para outros
        # serviços dentro da VPC ou para redes conectadas via Transit Gateway/VPN.
        # Se você precisa que instâncias usem este NAT Gateway para acessar a rota do TGW,
        # você precisaria de uma rota default (0.0.0.0/0) apontando para o NAT Gateway
        # nas Route Tables das subnets privadas que o utilizarão.
        # A subnet onde o NAT Gateway está não precisa de uma rota apontando para ele.

        print(f"NAT Gateway privado '{nat_gateway_id}' criado com sucesso na subnet '{subnet_id}'.")
        print("Lembre-se de adicionar rotas nas tabelas de roteamento das subnets que precisam usar este NAT Gateway.")

    except Exception as e:
        print(f"Erro ao criar NAT Gateway privado: {e}")
        # Tentar liberar o EIP se o NAT Gateway falhar
        if 'allocation_id' in locals():
            try:
                print(f"Tentando liberar o EIP alocado: {allocation_id}")
                ec2_client.release_address(AllocationId=allocation_id)
            except Exception as e_release:
                print(f"Erro ao liberar EIP: {e_release}")


# --- Função Principal ---
if __name__ == "__main__":
    if not TARGET_VPC_ID:
        print("AVISO: TARGET_VPC_ID não definido. O script tentará encontrar a primeira VPC.")
        try:
            vpcs = ec2_client.describe_vpcs()['Vpcs']
            if vpcs:
                TARGET_VPC_ID = vpcs[0]['VpcId']
                print(f"Usando a primeira VPC encontrada: {TARGET_VPC_ID}")
            else:
                print("Nenhuma VPC encontrada na conta. Por favor, especifique um TARGET_VPC_ID.")
                exit()
        except Exception as e:
            print(f"Erro ao descrever VPCs: {e}")
            exit()

    subnet_id, availability_zone, route_table_id = find_subnet_for_tgw(TARGET_VPC_ID)

    if subnet_id:
        print(f"\nSubnet identificada para operações: {subnet_id} na AZ {availability_zone}")
        print(f"Tabela de Roteamento associada: {route_table_id}")

        create_vpc_endpoints(subnet_id, TARGET_VPC_ID)
        create_private_nat_gateway(subnet_id, route_table_id, availability_zone)
    else:
        print("Não foi possível identificar uma subnet com rota para Transit Gateway. Operações abortadas.")
