"""
This file contains the code of proxy design pattern that will be hosted on the proxy ec2 machine
"""
from flask import Flask, request, jsonify
from sshtunnel import SSHTunnelForwarder
import random
import time
import json 
import mysql.connector
import ping3

app = Flask(__name__)

# getting the details about mysql cluster machines: workers and manager and setting up the config of database, user and password
with open('cluster_instance_details.json') as file: 
    cluster_data = json.load(file)

workers_config = []
for data in cluster_data:
    if data['Name'] == 'manager':
        master_config = {
            'host': data['PublicDNS'],
            'user': 'root',
            'password': '',
            'database': 'sakila',
        }
    else:
            workers_config.append(
                {
            'host': data['PublicDNS'],
            'user': 'root',
            'password': '',
            'database': 'sakila',
        }
            )



@app.route('/direct_hit', methods=['POST'])
def direct_hit_endpoint():
    """
    Here the implemenation of proxy direct hit startegry: use master node
    1- establish a connection to the manager node of mysql cluster
    2- execute and commit the query
    """
    master_connection = mysql.connector.connect(**master_config)
    master_cursor = master_connection.cursor()
    query = request.json['query']
    master_cursor.execute(query)
    try:
         master_connection.commit() 
    except Exception as e:
        pass
    result = master_cursor.fetchall()
    return jsonify({'result': result})


@app.route('/random', methods=['POST'])
def random_proxy():
    """
    Here the implemenation of random strategy choose a random woker node
    1- establish a tunnel from the random worker to the manager (in order to be able to send sql queries using worker nodes)
    2- establish a connection to the worker node of mysql cluster
    3- execute and commit the query
    """
    selected_slave = random.choice(workers_config)
    tunnel = SSHTunnelForwarder(
        (master_config['host'], 3306), 
    ssh_username ='ubuntu', ssh_pkey="/home/ubuntu/my_key_pair.pem", 
    remote_bind_address =(selected_slave['host'], 3306)
        )
    connection = mysql.connector.connect(
        host= selected_slave['host'], 
        user='root', 
    password= '',
    database= 'sakila'
    )
    cursor = connection.cursor()
    data = request.json
    query = data.get('query')

    cursor.execute(query)
    try:
         connection.commit() 
    except Exception as e:
        pass
    result = cursor.fetchall()
    return jsonify({'result': result})

@app.route('/customized', methods=['POST'])
def customized_proxy():
    """
    Here the implemenation of customized proxy: choose the node bases on the fasted ping time
    1- ping all cluster machines and define the fastest one
    1- establish a tunnel from the fastest machie to the manager (in order to be able to send sql queries using all nodes)
    2- establish a connection to the fastest node of mysql cluster
    2- execute and commit the query
    """
    lowest_ping_time = float('inf')
    for worker in workers_config:
        ping = ping3.ping(worker['host'])
        if ping is not None and ping < lowest_ping_time:
            lowest_ping_time = ping
            selected_server = worker

    ping =ping3.ping(master_config['host'])
    if ping is not None and ping < lowest_ping_time:
        lowest_ping_time = ping
        selected_server = master_config

    tunnel = SSHTunnelForwarder(
        (master_config['host'], 3306), 
    ssh_username ='ubuntu', ssh_pkey="/home/ubuntu/my_key_pair.pem", 
    remote_bind_address =(selected_server['host'], 3306)
        )
    connection = mysql.connector.connect(
        host= selected_server['host'], 
        user='root', 
    password= '',
    database= 'sakila'
    )
    cursor = connection.cursor()
    data = request.json
    query = data.get('query')

    cursor.execute(query)
    try:
         connection.commit() 
    except Exception as e:
        pass

    result = cursor.fetchall()
    return jsonify({'result': result})

    
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

