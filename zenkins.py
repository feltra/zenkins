#!/bin/env python
# desc: simple tool use to monitoring and discover jenkins jobs
import os
import sys
import time
import json
import baker
import requests
from configobj import ConfigObj
from datetime import datetime as dt

try:
    config = ConfigObj('/etc/zenkins.conf')
    HOSTNAME = config.get('hostname')
    USERNAME = config.get('username')
    PASSWORD = config.get('password')
    JENKINS_URL = config.get('jenkins_url')
    PREFIX = config.get('prefix',"")
except Exception as E:
    print E
    sys.exit(1)

if PREFIX == "":
    PREFIX = ["HIGH-DTB","HIGH-BI","DISASTER-DTB","HIGH-SUPPORT"]

# used by zabbix to look up for jobs that should be monitored
def _discovery(prefix=""):
    jobs = requests.get(JENKINS_URL + '/view/All/api/json', auth=(USERNAME,PASSWORD))
    data = { 'data':[] }
    if prefix.lower() == 'all':
        for job in jobs.json().get('jobs'):
            if job.get('color') != "disabled":
                data['data'].append({'{#JOBNAME}' : job.get('name') })
    elif prefix is not None:
        for job in jobs.json().get('jobs'):
            if job.get('name').upper().startswith(prefix.upper()) and job.get('color') != "disabled" :
                data['data'].append({'{#JOBNAME}' : job.get('name') })
    return json.dumps(data)

@baker.command
def discovery(prefix=""):
     return _discovery(prefix=prefix)

# Get job data
def _rest(name="",maxtime=0): 
     r = requests.get(JENKINS_URL + '/job/' + name + '/lastBuild/api/json', auth=(USERNAME, PASSWORD),verify=False)
     if r.status_code == 200:
         try:
             job = r.json()
             if  (job.get('building') == False) and (job.get('result') == 'SUCCESS'):
                return 1
             # check if job exceeded the estimated duration
             if ( maxtime > 0 ) and (job.get('building') == True) and (job.get('result') == None):
                current = 0
                max_estimated = job.get('estimatedDuration')
                started = str(job.get('timestamp'))
                tmp = dt.fromtimestamp(float(started[:10]))
                duration = (dt.now() - tmp).seconds * 1000
                if duration > 0:
                    current = (duration*100)/max_estimated
                if current > maxtime:
                    # this is when job exceeds its estimated time
                    return -2
                else:
                    # job is running
                    return 2
         except Exception as E:
            sys.stderr.write("Failed %s" % E)
            pass
     else:
        return r.status_code
     # job failure
     return -1

# Match job name with the available prefixes
def prefilter(name,prefix=[]):
    for n in prefix:
        if name.rfind(n) == 0:
           result = n
    return result

#Get current jobs status based on its prefix and format its output so zabbix_sender can use 
def _status(name="",maxtime=0):
    if name == "all":
        for job in json.loads(_discovery('DISASTER-'))['data']:
           jobname = job.get('{#JOBNAME}')
           print HOSTNAME, "jenkins.job[" + prefilter(jobname,PREFIX) + "," + jobname + "]",int(time.time()), _rest(jobname,maxtime)
        for job in json.loads(_discovery('HIGH-'))['data']:
           jobname = job.get('{#JOBNAME}')
           print HOSTNAME, "jenkins.job[" + prefilter(jobname,PREFIX) + "," + jobname + "]",int(time.time()), _rest(jobname,maxtime)
    else:
        for job in json.loads(_discovery(name))['data']:
           jobname = job.get('{#JOBNAME}')
           print HOSTNAME, "jenkins.job[" + prefilter(jobname,PREFIX) + "," + jobname + "]",int(time.time()), _rest(jobname,maxtime)

@baker.command
def status(name="",maxtime=0):
    _status(name=name,maxtime=maxtime)

if __name__ == "__main__":
    baker.run()
