"""
This file contains the required steps to set up the infrastructure of the proxy pattern
"""
import boto3
import os
import json
import base64
from constants import security_group_name, key_pair_name, ImageId, subnet_id, arn, cluster_details, proxy_source_code, private_key_path, proxy_host_path
import time
from utils import upload_file_to_ec2, send_command, check_command_status



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



# retriving an existing security group (allowing all access from everywhere)
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

# launch  1 ec2 instance  t2.large  for proxy
instance = ec2_resource.create_instances(
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
instance_name = 'proxy'
instance.create_tags(Tags=[{'Key': 'Name', 'Value': instance_name}])
instance_info = {
        'Name': instance_name,
        'InstanceID': instance.id,
        'PublicDNS': instance.public_dns_name,
        'PublicIP': instance.public_ip_address
    }
instance_data = [instance_info]

# Write the instance data to a JSON file
with open('proxy_details.json', 'w') as file:
    json.dump(instance_data, file, indent=4)


# upload provate key file, cluster_instance_details.json and proxy.py to proxy ec2 machine
upload_file_to_ec2(instance, cluster_details, os.path.join(proxy_host_path, os.path.basename(cluster_details)), private_key_path)
upload_file_to_ec2(instance, private_key_path, os.path.join(proxy_host_path, os.path.basename(private_key_path)), private_key_path)
upload_file_to_ec2(instance, proxy_source_code, os.path.join(proxy_host_path, os.path.basename(proxy_source_code)), private_key_path)


# prepare the proxy environment and launch proxy server 
proxy_commands = [
    'sudo apt-get update',
    'sudo apt install python3.8-venv -y', 
    'python3 -m venv venv', 
    'source venv/bin/activate',
    'pip install ping3',
    'pip install paramiko',
    'pip install sshtunnel',
    'pip install mysql-connector-python ',
    'pip install flask',
    'pip install requests',
    'python proxy.py'
]

for i in range(len(proxy_commands)):
    command = proxy_commands[i]
    command_id = send_command([instance], command, ssm_client)
    status = check_command_status(command_id, instance, ssm_client)
    print(f"Status for instance {instance} on command '{command}': {status['Status']}, {status['StatusDetails']}")
    if status['Status'] != 'Success':
        print(f"Command execution failed on instance {instance} for command '{command}'")
        break  


# at this step the proxy server is configured, up and running, to send requests you can use proxy/send_requests.py