"""
This file helps to send requests to proxy machine
"""

import requests
import json
import argparse
from urllib.parse import urljoin
from constants import proxy_details, port


# example of  a read and write request to be sent to mysql cluster
read_query = 'select first_name, last_name, last_update from actor where actor_id=100;'
write_query = "insert into actor (first_name, last_name, last_update) VALUES (' Altaaf', 'Abbassi', NOW());"
# a url template for the proxt maxhie
url_template = "http://{}:{}/{}"

# get proxy machine details
with open(proxy_details) as file:
    proxy_detail = json.load(file)



def send_request(query, host=proxy_detail[0]['PublicIP'], uri='direct_hit'):
    """
    INput:  query (SQL qery)
            stategy: proxy strategy
    method to send post request and put the query in the body of the request

    """
    headers = {'Content-Type': 'application/json'} 
    data = {'query': query}
    url = url_template.format(host, port,uri)
    response = requests.post(url, json=data,headers=headers)
    print(response)
    return response.text


if __name__== "__main__":
    """
    Main method to send the requests to proxy
    1- retrive the qeuery from args 
    2- retrieve the strategy
    3- send the query to the gatekeeper
    """
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--query', default='read', type=str) 
    parser.add_argument('--strategy', default='customized')
    args = parser.parse_args()

    if args.query == 'read':
        query = read_query
    else:
        query = write_query
    
    assert args.strategy in ['random', 'direct_hit', 'customized']
    response = send_request(query, uri=args.strategy)
    print(response)
