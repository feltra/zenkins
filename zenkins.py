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

SESSION = requests.session()
SESSION.auth = (USERNAME, PASSWORD)

# used by zabbix to look up for jobs that should be monitored
def _discovery(prefix=""):
    jobs = SESSION.get(JENKINS_URL + '/view/All/api/json')
    if jobs.status_code == requests.codes.ok:
        data = {'data': []}
        if prefix.lower() == "":
            for job in jobs.json().get('jobs'):
                if job.get('color') != "disabled":
                    r = SESSION.get(JENKINS_URL + "/job/" + job.get('name') + "/api/json")
                    if r.status_code == requests.codes.ok:
                        if r.json().get('jobs'):
                            for branch in r.json().get('jobs'):
                                result = {'{#JOBNAME}': job.get('name'), '{#BRANCHNAME}': branch.get('name')}
                                data['data'].append(result)
                        else:
                            result = {'{#JOBNAME}': job.get('name')}
                            data['data'].append(result)

        elif prefix is not None:
            for job in jobs.json().get('jobs'):
                if job.get('name').upper().startswith(prefix.upper()) and job.get('color') != "disabled":
                    r = SESSION.get(JENKINS_URL + "/job/" + job.get('name') + "/api/json")
                    if r.status_code == requests.codes.ok:
                        if r.json().get('jobs'):
                            for branch in r.json().get('jobs'):
                                result = {'{#JOBNAME}': job.get('name'), '{#BRANCHNAME}': branch.get('name')}
                                data['data'].append(result)
                        else:
                            result = {'{#JOBNAME}': job.get('name')}
                            data['data'].append(result)
        return json.dumps(data)
    else:
        jobs.raise_for_status()


@baker.command
def discovery(prefix=""):
    return _discovery(prefix=prefix)


# Get job data
def _rest(job_name="", branch_name="", max_time=0):
    url = JENKINS_URL + '/job/' + job_name
    if branch_name != "":
        url = url + "/job/" + branch_name
    url = url + '/lastBuild/api/json'

    r = SESSION.get(url, verify=False)
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
        branch_name = job.get('{#BRANCHNAME}', "")
        branch_name_text = ""
        if branch_name != "":
            branch_name_text = "," + branch_name
        print(HOSTNAME, "jenkins.job[" + job_name + branch_name_text + "]",
              int(time.time()),
              _rest(job_name,
                    branch_name,
                    max_time)
              )



@baker.command
def status(name="", max_time=0):
    _status(name=name, max_time=max_time)


if __name__ == "__main__":
    baker.run()
