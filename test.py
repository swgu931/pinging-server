import os
import subprocess


response = 1
hostname = "google.com" #example
ping_command = "ping -c 1 " +  hostname
print("ping_command : ", ping_command)
#response = os.system("ping -c 1 " + hostname)
#out = subprocess.check_output("ping -c 1 $hostname", shell=True)
out = subprocess.check_output(ping_command, shell=True)

print("out : ", out)


#and then check the response...
if response == 0:
  print( hostname, 'is up!')
else:
  print( hostname, 'is down!')
