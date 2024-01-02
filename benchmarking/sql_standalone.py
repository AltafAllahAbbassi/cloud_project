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



# retriving an existing security group 
response = ec2_client.describe_security_groups(
    Filters=[
        {
            'Name': 'group-name',
            'Values': [security_group_name]
        }
    ]
)
security_group = response['SecurityGroups'][0]



# user data script to install and start amazon-ssm-agent in ec2 intstances, so we can send requests
user_data_script = """#!/bin/bash
sudo snap install amazon-ssm-agent --classic
sudo systemctl enable amazon-ssm-agent
sudo systemctl start amazon-ssm-agent
"""
user_data_encoded = base64.b64encode(user_data_script.encode()).decode()

# launch  an ec2 instance, latter we will be installing sql server standalone here
instance = ec2_resource.create_instances(
    ImageId=ImageId,
    InstanceType='t2.micro',
    MaxCount=1,
    MinCount=1,
    KeyName=key_pair_name,
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

# Write the instance data to a JSON file
instance = instance[0]
instance.wait_until_running()
instance.load()
instance_name = 'standalone'
instance.create_tags(Tags=[{'Key': 'Name', 'Value': instance_name}])
instance_info = {
        'Name': instance_name,
        'InstanceID': instance.id,
        'PublicDNS': instance.public_dns_name,
        'PublicIP': instance.public_ip_address
    }
instance_data = [instance_info]

# Write the instance data to a JSON file
with open('standalone_details.json', 'w') as file:
    json.dump(instance_data, file, indent=4)


# set up commands to install mysqlserver standalone
commands =[

    'sudo apt-get update',
    'sudo apt-get install mysql-server -y'
]

for i in range(len(commands)):
    command = commands[i]
    command_id = send_command([instance], command, ssm_client)
    status = check_command_status(command_id, instance, ssm_client)
    print(f"Status for instance {instance} on command '{command}': {status['Status']}, {status['StatusDetails']}")
    if status['Status'] != 'Success':
        print(f"Command execution failed on instance {instance} for command '{command}'")
        break  



# installing sakila database, insralling sysbench and preparing a dataset for benchamrking 
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
    'sudo mysql -u root  -p   < sakila-schema.sql ', 
    'sudo mysql -u root  -p sakila < sakila-data.sql', 
    'sudo apt-get install sysbench -y', 
    'sudo sysbench --table-size=1000000 --db-driver=mysql --mysql-user=root --mysql-password=root --mysql-db=sakila --threads=1 --rand-type=uniform /usr/share/sysbench/oltp_read_only.lua prepare',
]

for i in range(len(sakila_commands)):
    command = sakila_commands[i]
    command_id = send_command([instance], command, ssm_client)
    status = check_command_status(command_id, instance, ssm_client)
    print(f"Status for instance {instance} on command '{command}': {status['Status']}, {status['StatusDetails']}")
    if status['Status'] != 'Success':
        print(f"Command execution failed on instance {instance} for command '{command}'")
        break  

# at this step teh sql standalone server is installing up and running, sakila is ready and configured, sysbench is installed and a benchmarking dataset is prepared
