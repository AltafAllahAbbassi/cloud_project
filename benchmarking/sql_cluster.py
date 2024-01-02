"""
This file contains the implementation of sql cluster infrastructure
"""
import boto3
import json
import base64
from .constants import security_group_name, key_pair_name, ImageId, subnet_id, arn
from .utils import send_command, check_command_status



# instanciating aws services
ec2_resource = boto3.resource('ec2')
ec2_client = boto3.client('ec2')
iam = boto3.client('iam')
ssm_client = boto3.client('ssm')

# retriving and then configuring the VPC
vpc = ec2_client.describe_vpcs()['Vpcs'][0]
vpc_resource = ec2_resource.Vpc(vpc['VpcId'])
vpc_resource.modify_attribute(EnableDnsHostnames={'Value': True})
vpc_resource.modify_attribute(EnableDnsSupport={'Value': True})



# retriving an existing security group that was configured to allow all the trafic, this security group will be used for the gatekeeper host
response = ec2_client.describe_security_groups(
    Filters=[
        {
            'Name': 'group-name',
            'Values': [security_group_name]
        }
    ]
)
security_group = response['SecurityGroups'][0]

# retriving an existing key pair 
response = ec2_client.describe_key_pairs()
matching_key_pairs = [key_pair for key_pair in response['KeyPairs'] if key_pair['KeyName'] == key_pair_name]
key_pair = matching_key_pairs[0]


# user data script to install and start amazon-ssm-agent in ec2 intstances, so we can send requests
user_data_script = """#!/bin/bash
sudo snap install amazon-ssm-agent --classic
sudo systemctl enable amazon-ssm-agent
sudo systemctl start amazon-ssm-agent
"""
user_data_encoded = base64.b64encode(user_data_script.encode()).decode()

# launch  4 ec2 instances for sql cluster: 1 manager (data management node) and 3 workers (data nodes)
instances = ec2_resource.create_instances(
    ImageId=ImageId,
    InstanceType='t2.micro',
    MaxCount=4,
    MinCount=1,
    KeyName='my_key_pair',
    UserData=user_data_encoded,
    IamInstanceProfile={'Arn': arn},
    NetworkInterfaces=[{
        'SubnetId': subnet_id,
        'DeviceIndex': 0,
        'AssociatePublicIpAddress': True,
        'Groups': [security_group['GroupId']]
    }],
    BlockDeviceMappings=[
        {   'DeviceName': '/dev/sda1',
            'Ebs': {
                'VolumeSize': 16,  # Size in GB
                'DeleteOnTermination': True,
                'VolumeType': 'gp2',  # General Purpose SSD
            },
        },
    ],
)

# Adding tags to EC2 instances: name of each node either worker or manager
instance_data = []
for i, instance in enumerate(instances, start=1):
    instance.wait_until_running()
    instance.load()

    if i <= 3:
        instance_name = f'worker{i}'
    else:
        instance_name = 'manager'

    instance.create_tags(Tags=[{'Key': 'Name', 'Value': instance_name}])

    instance_info = {
        'Name': instance_name,
        'InstanceID': instance.id,
        'PublicDNS': instance.public_dns_name,
        'PublicIP': instance.public_ip_address
    }
    instance_data.append(instance_info)

# Write the sql cluster instances details to a JSON file
with open('cluster_instance_details.json', 'w') as file:
    json.dump(instance_data, file, indent=4)


# retriving  manager and workers details (instance id and DNS)
all_instance_ids = []
worker_instances_ids = []
manager_instance_id = []
workers_dns=[]
manager_dns = []
for data in instance_data:
    all_instance_ids.append(data['InstanceID'])
    if 'worker' in data['Name']:
        worker_instances_ids.append(data['InstanceID'])
        workers_dns.append(data['PublicDNS'])
    else: 
        manager_instance_id.append(data['InstanceID'])
        manager_dns.append(data['PublicDNS'])



# the common steps to be excutes on both manger and worker nodes: 
# Create Directory for MySQL Cluster
# Download MySQL Cluster
# Extract MySQL Cluster Package
# Create Symbolic Link to sql cluster
# Configure Environment Variables for MySQL Cluster functionality
# Update Package Information Again and Install Dependency: libncurses5
common_steps = [
    'sudo apt-get update',
    'sudo mkdir -p /opt/mysqlcluster/home',
    'cd /opt/mysqlcluster/home',
    'sudo wget http://dev.mysql.com/get/Downloads/MySQL-Cluster-7.2/mysql-cluster-gpl-7.2.1-linux2.6-x86_64.tar.gz',
    'sudo tar xvf mysql-cluster-gpl-7.2.1-linux2.6-x86_64.tar.gz',
    'sudo ln -s mysql-cluster-gpl-7.2.1-linux2.6-x86_64 mysqlc',
    'sudo sh -c \'echo "export MYSQLC_HOME=/opt/mysqlcluster/home/mysqlc" > /etc/profile.d/mysqlc.sh && echo "export PATH=$MYSQLC_HOME/bin:$PATH" >> /etc/profile.d/mysqlc.sh\'',
    'source /etc/profile.d/mysqlc.sh',
    'source /etc/profile.d/mysqlc.sh step',
    'sudo apt-get update && sudo apt-get -y install libncurses5'
]

# exeucting the common steps on manager and all worker nodes
for i in range(len(common_steps)):
    command = common_steps[i]
    command_id = send_command(all_instance_ids, command, ssm_client)
    for instance_id in all_instance_ids:
        status = check_command_status(command_id, instance_id, ssm_client)
        print(f"Status for instance {instance_id} on command '{command}': {status['Status']}, {status['StatusDetails']}")
        if status['Status'] != 'Success':
            print(f"Command execution failed on instance {instance_id} for command '{command}'")
            break  


# defining the steps specifc to manager node
# Create Deployment Directory
# Create Configuration Subdirectorie (conf, mysqld_data ndb_data)
# create and configure MySQL Configuration File: my.cnf
# Configure NDB Management Daemon (ndb_mgmd): by specifying the host and worker node ids with their respective host
# Start NDB Management Daemon
# Start MySQL Server
manager_steps = [

    'sudo mkdir -p /opt/mysqlcluster/deploy ',
    'cd /opt/mysqlcluster/deploy',
    'sudo mkdir conf',
    'sudo mkdir mysqld_data',
    'sudo mkdir ndb_data',
    'cd conf',
    'echo -e \"[mysqld]\nndbcluster\ndatadir=/opt/mysqlcluster/deploy/mysqld_data\nbasedir=/opt/mysqlcluster/home/mysqlc\nport=3306\" | sudo tee -a my.cnf',
    'truncate -s 0 /opt/mysqlcluster/deploy/conf/config.ini',
    'echo [ndb_mgmd] >> /opt/mysqlcluster/deploy/conf/config.ini',
    f'echo hostname={manager_dns[0]} >> /opt/mysqlcluster/deploy/conf/config.ini',
    'echo [ndbd default] >> /opt/mysqlcluster/deploy/conf/config.ini',
    'echo noofreplicas=3 >> /opt/mysqlcluster/deploy/conf/config.ini',
    'echo datadir=/opt/mysqlcluster/deploy/ndb_data>> /opt/mysqlcluster/deploy/conf/config.ini',
    'echo [ndbd] >> /opt/mysqlcluster/deploy/conf/config.ini',
    f'echo hostname={workers_dns[0]} >> /opt/mysqlcluster/deploy/conf/config.ini',
    'echo nodeid=3 >> /opt/mysqlcluster/deploy/conf/config.ini',
    'echo [ndbd] >> /opt/mysqlcluster/deploy/conf/config.ini',
    f'echo hostname={workers_dns[1]} >> /opt/mysqlcluster/deploy/conf/config.ini',
    'echo nodeid=4 >> /opt/mysqlcluster/deploy/conf/config.ini',
    'echo [ndbd] >> /opt/mysqlcluster/deploy/conf/config.ini',
   f'echo hostname={workers_dns[2]} >> /opt/mysqlcluster/deploy/conf/config.ini',
    'echo nodeid=5 >> /opt/mysqlcluster/deploy/conf/config.ini',
    'echo [mysqld] >> /opt/mysqlcluster/deploy/conf/config.ini',
    'echo nodeid=50 >> /opt/mysqlcluster/deploy/conf/config.ini', 
    'cd /opt/mysqlcluster/home/mysqlc',
    'sudo scripts/mysql_install_db --defaults-file=/dev/null --datadir=/opt/mysqlcluster/deploy/mysqld_data --user root &',
    'sudo ./bin/ndb_mgmd -f /opt/mysqlcluster/deploy/conf/config.ini --initial --configdir=/opt/mysqlcluster/deploy/conf', 
    'sudo /opt/mysqlcluster/home/mysql-cluster-gpl-7.2.1-linux2.6-x86_64/bin/mysqld --defaults-file=/opt/mysqlcluster/deploy/conf/my.cnf --user=root &'
]
# executing steps specic to manager node
for i in range(len(manager_steps)):
    command = manager_steps[i]
    command_id = send_command(manager_instance_id, command, ssm_client)
    for instance_id in manager_instance_id:
        status = check_command_status(command_id, instance_id, ssm_client)
        print(f"Status for instance {instance_id} on command '{command}': {status['Status']}, {status['StatusDetails']}")
        if status['Status'] != 'Success':
            print(f"Command execution failed on instance {instance_id} for command '{command}'")
            any_command_failed = True
            break  


# defining steps specific to data node (worker)
# create a directory for deployment and bind the data node to the managament node
worker_steps = [
    'sudo mkdir -p /opt/mysqlcluster/deploy/ndb_data', 
    'cd /opt/mysqlcluster/home/', 
    f'sudo /opt/mysqlcluster/home/mysql-cluster-gpl-7.2.1-linux2.6-x86_64/bin/ndbd -c {manager_dns[0]}:1186'
]

# executing steps specic to data node (worker)
for i in range(len(worker_steps)):
    command = worker_steps[i]
    command_id = send_command(manager_instance_id, command, ssm_client)
    for instance_id in manager_instance_id:
        status = check_command_status(command_id, instance_id, ssm_client)
        print(f"Status for instance {instance_id} on command '{command}': {status['Status']}, {status['StatusDetails']}")
        if status['Status'] != 'Success':
            print(f"Command execution failed on instance {instance_id} for command '{command}'")
            any_command_failed = True
            break  



# setup sakila commands and installing sysbench  on manager node of the sql cluster
# downloading the sakila database (as tar)
# extarct the database
# mount the database to sql server
# install sysbench: the benchmarking tool
# parepre a bemchmarking dataset using sysbench prepare
sakila_commands = [
    'wget https://downloads.mysql.com/docs/sakila-db.tar.gz', 
    'tar -xzvf sakila-db.tar.gz',
    'cd sakila-db',
    '/opt/mysqlcluster/home/mysqlc/bin/mysql -u root  -p   < sakila-schema.sql', 
    '/opt/mysqlcluster/home/mysqlc/bin/mysql -u root  -p   sakila < sakila-data.sql', 
    'sudo apt-get install sysbench -y', 
    f'sudo sysbench --table-size=1000000 --db-driver=mysql --mysql-user=root  --mysql-db=sakila --threads=1  --mysql-host={manager_dns[0]}  --rand-type=uniform /usr/share/sysbench/oltp_read_only.lua prepare'
]


for i in range(len(sakila_commands)):
    command = sakila_commands[i]
    command_id = send_command(manager_instance_id, command, ssm_client)
    for instance_id in manager_instance_id:
        status = check_command_status(command_id, instance_id, ssm_client)
        print(f"Status for instance {instance_id} on command '{command}': {status['Status']}, {status['StatusDetails']}")
        if status['Status'] != 'Success':
            print(f"Command execution failed on instance {instance_id} for command '{command}'")
            any_command_failed = True
            break  




## at this step, the sql cluster is set, sakila database is ready to use and sysbench is installed and benchmarking dataset is prepared
## thus the sql cluster is ready for use