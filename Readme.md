This project is organzied as follow:
- Benchmarking: to benchmark the perfomance of MySQL cluster and standalone servers. 
- Proxy: contains the implementation of proxy design pattern.
- Gatekeeper: conatins the implemenation of gatekeeper design pattern. 

------------


To reproduce the results please follow the follwoing instructions: 

**Common:**

1- Put your aws credentails into ~/.aws/credentials.

2- Pull the repository 
```bash
git clone https://github.com/AltafAllahAbbassi/cloud_project
```
3- install the dependenices:
```bash
pip install requirements.txt
```
**Benchamrking:**
1- rename contants_template.py to constants,py and configure your constants.
2- prepare the infrastructure:
```bash
cd benchmarking 
python sql_cluster.py
python sql_standalone.py
```
3- Run the benchmark: 
```bash
python benchmark.py
```
After running these commands you will find results under benchmarking folder.
**Proxy:**
1- rename contants_template.py to constants,py and configure your constants.
2- prepare the infrastructure:
```bash
cd proxy 
python infrastructure.py
```
2- send requests: 
```bash
python send_requests.py --query SQL_QUERY --strategy STRATEGY
```
PS: supported startegies: random, customized, direct_hit
**Gatekeeper:**
1- rename contants_template.py to constants,py and configure your constants.
2- prepare the infrastructure:
```bash
cd gatekeeper
python infrastructure.py
```
2- send requests: 
```bash
python send_requests.py --query SQL_QUERY 
```
