import subprocess

subprocess.call(['ufw', 'allow', '1255'])
subprocess.call(['ufw', 'allow', '1900'])
subprocess.call([
    'ufw', 'allow', 'proto', 'udp', 'to', 'any', 'port', '32768:60999'
])
subprocess.call(['ufw', 'reload'])