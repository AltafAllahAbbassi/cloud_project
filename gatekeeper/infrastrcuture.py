"""
This file contains the implemenation of gatekeeper design pattern infrastructure
"""

from posixpath import basename
import boto3
import os
import json
import base64
from constants import security_group_name, key_pair_name, ImageId, subnet_id, arn, cluster_details, gatekeper_trusted_details
from constants import private_key_path, gatekeeper_host_path, trusted_host_path, gatekeeper_source_code, trusted_host_source_code
import time
from utils import upload_file_to_ec2, check_command_status, send_command


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
gatekeeper_security_group = response['SecurityGroups'][0]

# we need to have another security group for the trusted host machine that will allow only internal incoming requests 
# initially this security group dont allow any traffic
trusted_hosted_security_group= ec2_resource.create_security_group(
    GroupName='internal_use_sec_group',
    Description='Security group for internal machines',
    VpcId=vpc_resource.id, 
)
# we allow ssh traffic here, to copy code files to the trusted machine
ec2_client.authorize_security_group_ingress(GroupId = trusted_hosted_security_group.id, 
        IpProtocol = 'tcp', 
        FromPort = 22, 
        ToPort = 22, 
        CidrIp = '0.0.0.0/0')


# Also we need to allow internal communication from gatekeeper to the trusted host, here we allowed instances appartenning to the security group of gatekeeper
ec2_client.authorize_security_group_ingress(
    GroupId=trusted_hosted_security_group.id,
    IpPermissions=[
        {
            'IpProtocol': 'tcp',
            'FromPort': 5000,  # Adjust the port range as needed
            'ToPort': 5000,
            'UserIdGroupPairs': [{'GroupId': gatekeeper_security_group['GroupId']}]
        }
    ]
)


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


# launch  1 ec2 instance  t2.large  for gatekeeper, wait untul launch and assign a name
gatekeeper_instance = ec2_resource.create_instances(
    ImageId=ImageId,
    InstanceType='t2.large',
    MaxCount=1,
    MinCount=1,
    KeyName='my_key_pair',
    UserData=user_data_encoded,
    IamInstanceProfile={'Arn': arn},
    NetworkInterfaces=[{
        'SubnetId': subnet_id,
        'DeviceIndex': 0,
        'AssociatePublicIpAddress': True,
        'Groups': [gatekeeper_security_group['GroupId']]
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

gatekeeper_instance = gatekeeper_instance[0]
gatekeeper_instance.wait_until_running()
gatekeeper_instance.load()
instance_name = 'gatekeeper'
gatekeeper_instance.create_tags(Tags=[{'Key': 'Name', 'Value': instance_name}])
gatekeeper_instance_instance_info = {
        'Name': instance_name,
        'InstanceID': gatekeeper_instance.id,
        'PublicDNS': gatekeeper_instance.public_dns_name,
        'PublicIP': gatekeeper_instance.public_ip_address
    }


# lanch 1 ec2 instance t2.large for trsuted host, wait until lunch and assign a name
trusted_instance = ec2_resource.create_instances(
    ImageId=ImageId,
    InstanceType='t2.large',
    MaxCount=1,
    MinCount=1,
    KeyName='my_key_pair',
    UserData=user_data_encoded,
    IamInstanceProfile={'Arn': arn},
    NetworkInterfaces=[{
        'SubnetId': subnet_id,
        'DeviceIndex': 0,
        'AssociatePublicIpAddress': True,
        'Groups': [trusted_hosted_security_group.id]
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

trusted_instance = trusted_instance[0]
trusted_instance.wait_until_running()
trusted_instance.load()
instance_name = 'trusted_host'
trusted_instance.create_tags(Tags=[{'Key': 'Name', 'Value': instance_name}])
trusted_instance_info = {
        'Name': instance_name,
        'InstanceID': trusted_instance.id,
        'PrivateIP': trusted_instance.private_ip_address,
        'PublicDNS': trusted_instance.public_dns_name,
        'PublicIP': trusted_instance.public_ip_address
    }

# save instances data: trsuted host and gatekeeper
with open('gatekeeper_instance_details.json', 'w') as file:
    json.dump([trusted_instance_info, gatekeeper_instance_instance_info], file, indent=4)


# copying gatekeeper and trusted host source code as well as cluster instance details and gatekeeper as well as trusted host details

upload_file_to_ec2(trusted_instance, cluster_details, os.path.join(trusted_host_path, os.path,basename(cluster_details)), private_key_path)
upload_file_to_ec2(trusted_instance, trusted_host_source_code, os.path.join(trusted_host_path, os.path,basename(trusted_host_source_code)), private_key_path)

upload_file_to_ec2(gatekeeper_instance, gatekeper_trusted_details, os.path.join(gatekeeper_host_path, os.path.basename(gatekeper_trusted_details)), private_key_path)
upload_file_to_ec2(gatekeeper_instance, gatekeeper_source_code, os.path.join(gatekeeper_host_path, os.path.basename(gatekeeper_source_code)), private_key_path)


# preparing and installing dependencies for gatekeeper and run the application 
gatekeeper_commands = [
    'sudo apt-get update', 
    'sudo apt install python3.8-venv -y', 
    'python3 -m venv venv', 
    'source venv/bin/activate',
    'pip install Flask', 
    'pip install sqlvalidator', 
    'pip install requests', 
    'python gatekeeper.py'

]
for i in range(len(gatekeeper_commands)):
    command = gatekeeper_commands[i]
    command_id = send_command([gatekeeper_instance], command, ssm_client)
    status = check_command_status(command_id, gatekeeper_instance, ssm_client)
    print(f"Status for instance {gatekeeper_instance} on command '{command}': {status['Status']}, {status['StatusDetails']}")
    if status['Status'] != 'Success':
        print(f"Command execution failed on instance {gatekeeper_instance} for command '{command}'")
        break  

# preparing and installing dependencies for the trusted host and run the application 
trsuted_host_commands = [
    'sudo apt-get update', 
    'sudo apt install python3.8-venv -y', 
    'python3 -m venv venv', 
    'source venv/bin/activate',
    'pip install flask', 
    'pip install mysql-connector-python', 
    'pip install requests', 
    'python trusted_host.py'
]

for i in range(len(trsuted_host_commands)):
    command = trsuted_host_commands[i]
    command_id = send_command([trusted_instance], command, ssm_client)
    status = check_command_status(command_id, trusted_instance, ssm_client)
    print(f"Status for instance {trusted_instance} on command '{command}': {status['Status']}, {status['StatusDetails']}")
    if status['Status'] != 'Success':
        print(f"Command execution failed on instance {trusted_instance} for command '{command}'")
        break  

## At this the infrastructure is set, configured, trusted machine and gatekeeper machine and up and running
## To test and send requests, we use the script: gatekeeper/send_requests.py 