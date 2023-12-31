import paramiko
import time 

def upload_file_to_ec2(instance, local_path, remote_path, key_file_path):
    # Connect to EC2 instance using paramiko
    public_ip = instance.public_ip_address

    # Establish an SFTP connection
    transport = paramiko.Transport((public_ip, 22))
    transport.connect(username='ubuntu', pkey=paramiko.RSAKey(filename=key_file_path))

    sftp = paramiko.SFTPClient.from_transport(transport)

    try:
        # Upload the file
        sftp.put(local_path, remote_path)
        print(f"File uploaded successfully to {public_ip}:{remote_path}")
    except Exception as e:
        print(f"Error uploading file: {e}")
    finally:
        # Close the SFTP and transport connections
        sftp.close()
        transport.close()

def send_command(instance_ids, command, ssm_client):
    response = ssm_client.send_command(
        InstanceIds=instance_ids,
        DocumentName="AWS-RunShellScript",
        Parameters={'commands': [command]},
    )

    command_id =  response['Command']['CommandId']
    return command_id
    


def check_command_status(command_id, instance_id, ssm_client):
    for _ in range(10):  # Try up to 10 times with a delay in between
        try:
            response = ssm_client.get_command_invocation(
                CommandId=command_id,
                InstanceId=instance_id,
            )
            print(response)
            if response['Status'] != 'InProgress':
                return response
        except ssm_client.exceptions.InvocationDoesNotExist:
            print(f"Waiting for command {command_id} to be registered in SSM...")
        time.sleep(10)  # Wait for 10 seconds before checking again

    return {"Status": "Failed", "StatusDetails": "Invocation does not exist or check exceeded retries"}