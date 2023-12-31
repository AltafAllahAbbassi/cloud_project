import requests
import json
import argparse


## Example of read and write sql queries
read_query = 'select first_name, last_name, last_update from actor where actor_id=100;'
write_query ="INSERT INTO actor (first_name, last_name, last_update) VALUES ('Altaaf', 'Abbassi', NOW());"

url_template = "http://{}:{}" # gatekeeper url template
port = 5000 # port on which gatekeeper is running


## get the gatekeeper machine details
gatekeepr_instances_details = 'gatekeeper/gatekeeper_instance_details.json'
with open(gatekeepr_instances_details) as file: 
    gate_trusted_instance_details = json.load(file)

for detail in gate_trusted_instance_details:
    if detail['Name'] == 'gatekeeper':
        gatekeeper = detail
        break



# this methos serve to send a query to the gatekeeper
def send_request(query, host=gatekeeper['PublicIP']):
    headers = {'Content-Type': 'application/json'} 
    data = {'query': query}
    url = url_template.format(host, port)
    response = requests.post(url, json=data,headers=headers)
    print(response)
    return response.text


if __name__== "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--query', default='read', type=str) 
    args = parser.parse_args()

    if args.query == 'read':
        query = read_query
    else:
        query = write_query
    
    response = send_request(query)
    print(response)
