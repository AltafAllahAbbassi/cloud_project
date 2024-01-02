"""
This file conatains the script to run the benchmark
"""
import boto3
import paramiko
import json
from constants import private_key_path, cluster_instance_file, standalone_details

# retriving the stanalone server and manager node (of sql cluser) dns 
with open(cluster_instance_file) as file:
    cluster_instance_details = json.load(file)
with open(standalone_details) as file:
    standalone_details = json.load(file)
standalone_dns = standalone_details[0]['PublicDNS']
for detail in cluster_instance_details:
    if detail['Name'] =='manager':
        cluster_manager_node_dns = detail['PublicDNS']
        break


# defining benchmarking commands on both standalone and manager node
# we have defined three requests: read oly, write only and read_and_write
# the result of benchmark is saved in files
standalone_commands = [
    'sudo sysbench --db-driver=mysql --mysql-user=root    --mysql-db=sakila --range_size=100   --table_size=1000000 --tables=1 --threads=1 --events=0 --time=60   --rand-type=uniform /usr/share/sysbench/oltp_read_only.lua run > read_only_standalone.txt',
    'sudo sysbench --db-driver=mysql --mysql-user=root    --mysql-db=sakila --range_size=100   --table_size=1000000 --tables=1 --threads=1 --events=0 --time=60   --rand-type=uniform /usr/share/sysbench/oltp_write_only.lua run > write_only_standalone.txt ', 
    'sudo sysbench --db-driver=mysql --mysql-user=root    --mysql-db=sakila --range_size=100   --table_size=1000000 --tables=1 --threads=1 --events=0 --time=60   --rand-type=uniform /usr/share/sysbench/oltp_read_write.lua run > read_write_standalone.txt'
]

cluster_commands = [
    f'sudo sysbench --db-driver=mysql --mysql-user=root    --mysql-db=sakila --range_size=100   --table_size=1000000 --tables=1 --threads=1  --mysql-host={cluster_manager_node_dns}  --events=0 --time=60   --rand-type=uniform /usr/share/sysbench/oltp_read_only.lua run > read_only_cluster.txt',
    f'sudo sysbench --db-driver=mysql --mysql-user=root    --mysql-db=sakila --range_size=100   --table_size=1000000 --tables=1 --threads=1  --mysql-host={cluster_manager_node_dns}  --events=0 --time=60   --rand-type=uniform /usr/share/sysbench/oltp_write_only.lua run > write_only_cluster.txt',
    f'sudo sysbench --db-driver=mysql --mysql-user=root    --mysql-db=sakila --range_size=100   --table_size=1000000 --tables=1 --threads=1  --mysql-host={cluster_manager_node_dns}  --events=0 --time=60   --rand-type=uniform /usr/share/sysbench/oltp_read_write.lua run > read_write_cluster.txt',

]

## seting ssh  on stand alone server 
ssh_standalone = paramiko.SSHClient()
ssh_standalone.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh_standalone.connect(standalone_dns, username='ubuntu', key_filename=private_key_path)

## seting ssh  on cluster server 
ssh_manager = paramiko.SSHClient()
ssh_manager.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh_manager.connect(cluster_manager_node_dns, username='ubuntu', key_filename=private_key_path)

# run benchmarking commands on stadlone, result files will be generated 
for command in standalone_commands:
    print("Running on standalone", command)
    _,stdout, stderr = ssh_standalone.exec_command(command)
    print(stdout.read().decode('utf-8'))
    print(stderr.read().decode('utf-8'))

# run benchmarking commands on cluster, result files will be generated   
for command in cluster_commands: 
    print("Running on standalone", command)
    _,stdout, stderr = ssh_manager.exec_command(command)  
    print(stdout.read().decode('utf-8'))
    print(stderr.read().decode('utf-8'))


# setting sftp on standaloen server to copy benchmark result files locally
sftp_standalone = ssh_standalone.open_sftp()
# copy standalone readonly benchmark results
sftp_standalone.get("read_only_standalone.txt", "read_only_standalone.txt")
# copy standalone write only benchmark results
sftp_standalone.get("write_only_standalone.txt", "write_only_standalone.txt")
# copy standalone read and wirtw benchmark results
sftp_standalone.get("read_only_standalone.txt", "read_write_standalone.txt")
# close teh sftp on standaloen server
sftp_standalone.close()

# setting sftp on cluster server to copy benchmark result files locally
sftp_cluster = ssh_standalone.open_sftp()
# copy cluster read only benchmark result file
sftp_cluster.get("read_only_cluster.txt", "read_only_cluster.txt")
# copy cluster write only benchmark result file
sftp_cluster.get("write_only_cluster.txt", "write_only_cluster.txt")
# copy cluster read write benchmark result file
sftp_cluster.get("read_write_cluster.txt", "read_write_cluster.txt")
# close teh sftp on cluster 
sftp_cluster.close()