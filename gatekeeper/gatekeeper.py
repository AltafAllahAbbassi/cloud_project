"""
This file contains the flasp application for the gatekeeper, that will be copied to the gatekeeper ec2 machine
"""
from flask import Flask, request, jsonify
import sqlvalidator
import json
import requests

app = Flask(__name__)


TRUSTED_HOST_PORT = 5000 # the port on which the trusted app is running
TRSUTED_URL_TEMPLATE = "http://{}:{}" # template of the url of the trust app


# getting deatil of the machine where the trusted is running
gatekeepr_instances_details = 'gatekeeper_instance_details.json'
with open(gatekeepr_instances_details) as file: 
    gate_trusted_instance_details = json.load(file)
for detail in gate_trusted_instance_details:
    if detail['Name'] == 'trusted_host':
        trusted_detail = detail
        break



@app.route('/', methods=['POST'])
def gatekeeper():
    """
    Our proposed gatekeeper checks the requests in two steps:
    1- check if the body of the request contains a query 
    2- validate the query using sql validator library
    If these two tests are passed, then forward the request to the trusted host 
    """
    data = request.json
    query = data.get('query')
    if query is None:
        return jsonify({'error': 'Query not provided'}), 400
    if not sqlvalidator.parse(query).is_valid():
        return jsonify({'error': 'Query not valid'}), 400
    headers = {'Content-Type': 'application/json'}
    data = {'query': query}
    url = TRSUTED_URL_TEMPLATE.format(trusted_detail['PrivateIP'], TRUSTED_HOST_PORT)
    response = requests.post(url, json=data, headers=headers)
    print(url)
    return jsonify(response.json()), response.status_code


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
