from flask import Flask, request, jsonify
import mysql.connector
import json 

app = Flask(__name__)

# get the details about the ec2 machine where the manager of mysql cluster is deployed
with open('cluster_instances_details.json') as file: 
    cluster_data = json.load(file)
for data in cluster_data:
    if data['Name'] == 'manager':
        master_config = {
            'host': data['PublicDNS'],
            'user': 'root',
            'password': '',
            'database': 'sakila',
        }
        break


@app.route('/', methods=['POST'])
def direct_hit_endpoint():
    """
    initilalize a connection with the manager of mysql cluster
    Then execute mysql query
    Return the response
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

