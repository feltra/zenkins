#!/usr/bin/env python
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
    config = ConfigObj('zenkins.conf')
    HOSTNAME = config.get('hostname')
    USERNAME = config.get('username')
    PASSWORD = config.get('password')
    JENKINS_URL = config.get('jenkins_url')
    PREFIX = config.get('prefix', "")
except Exception as E:
    print(E)
    sys.exit(1)


# used by zabbix to look up for jobs that should be monitored
def _discovery(prefix=""):
    jobs = requests.get(JENKINS_URL + '/view/All/api/json', auth=(USERNAME, PASSWORD))
    data = {'data': []}
    if prefix.lower() == "":
        for job in jobs.json().get('jobs'):
            if job.get('color') != "disabled":
                data['data'].append({'{#JOBNAME}': job.get('name')})
    elif prefix is not None:
        for job in jobs.json().get('jobs'):
            if job.get('name').upper().startswith(prefix.upper()) and job.get('color') != "disabled":
                data['data'].append({'{#JOBNAME}': job.get('name')})
    return json.dumps(data)


@baker.command
def discovery(prefix=""):
    return _discovery(prefix=prefix)


# Get job data
def _rest(name="", max_time=0):
    r = requests.get(JENKINS_URL + '/job/' + name + '/lastBuild/api/json', auth=(USERNAME, PASSWORD), verify=False)
    if r.status_code == 200:
        try:
            job = r.json()
            if (job.get('building') is False) and (job.get('result') == 'SUCCESS'):
                return 1
            # check if job exceeded the estimated duration
            if (max_time > 0) and (job.get('building') is True) and (job.get('result') is None):
                current = 0
                max_estimated = job.get('estimatedDuration')
                started = str(job.get('timestamp'))
                tmp = dt.fromtimestamp(float(started[:10]))
                duration = (dt.now() - tmp).seconds * 1000
                if duration > 0:
                    current = (duration * 100) / max_estimated
                if current > max_time:
                    # this is when job exceeds its estimated time
                    return -2
                else:
                    # job is running
                    return 2
        except Exception as e:
            sys.stderr.write("Failed %s" % e)
            pass
    else:
        return r.status_code
    # job failure
    return -1


def _status(name="", max_time=0):
    """ Get current jobs status based on its prefix and format its output so zabbix_sender can use """
    for job in json.loads(_discovery(name))['data']:
        job_name = job.get('{#JOBNAME}')
        print(HOSTNAME, "jenkins.job[" + job_name + "]", int(time.time()),
              _rest(job_name, max_time))


@baker.command
def status(name="", max_time=0):
    _status(name=name, max_time=max_time)


if __name__ == "__main__":
    baker.run()
