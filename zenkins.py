#!/usr/bin/env python
# desc: simple tool use to monitoring and discover jenkins jobs
import sys
import time
import json
import argparse
import requests
from configobj import ConfigObj
from datetime import datetime as dt
from pathlib import Path


SESSION = None
HOSTNAME = ""
USERNAME = ""
PASSWORD = ""
JENKINS_URL = ""
PREFIX = ""


# used by zabbix to look up for jobs that should be monitored
def _discovery(prefix=""):
    if JENKINS_URL == "":
        raise requests.URLRequired("ERROR: Url required")
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
                if job.get('name').upper() == prefix.upper() and job.get('color') != "disabled":
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


def discovery(args):
    prefix = args.name
    print(_discovery(prefix=prefix))


# Get job data
def _rest(job_name="", branch_name="", max_time=0):
    if JENKINS_URL == "":
        raise requests.URLRequired("ERROR: Url required")
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
            if (job.get('building') is True) and (job.get('result') is None):
                # job is running
                return 0

            # job failed
            return -1
        except Exception as e:
            sys.stderr.write("Failed %s" % e)
            pass
    # job failure
    return -1


def _status(name="", branch="", max_time=0):
    """ Get current jobs status based on its prefix and format its output so zabbix_sender can use """
    for job in json.loads(_discovery(name))['data']:
        job_name = job.get('{#JOBNAME}')
        branch_name = job.get('{#BRANCHNAME}', "")
        branch_name_text = ""
        if branch_name != "":
            branch_name_text = "," + branch_name
        if branch == "":
            print(HOSTNAME, "jenkins.job[" + job_name + branch_name_text + "]",
                  int(time.time()),
                  _rest(job_name,
                        branch_name,
                        max_time)
                  )
        else:
            if branch.upper() == branch_name.upper():
                print(HOSTNAME, "jenkins.job[" + job_name + branch_name_text + "]",
                      int(time.time()),
                      _rest(job_name,
                            branch_name,
                            max_time)
                      )


def status(args):
    name = args.name
    branch = args.branch
    max_time = args.max_time
    _status(name=name, branch=branch, max_time=max_time)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", "-c", default="zenkins.conf", required=False)
    sub = parser.add_subparsers()

    discover = sub.add_parser('discovery')
    discover.add_argument('name', nargs='?', default="")
    discover.set_defaults(func=discovery)

    stat = sub.add_parser('status')
    stat.add_argument('name', nargs='?', default="")
    stat.add_argument('branch', nargs='?', default="")
    stat.add_argument('max_time', nargs='?', default=0)
    stat.set_defaults(func=status)

    args = parser.parse_args()
    try:
        SESSION = requests.session()
        Path(args.config).resolve(strict=True)
        config = ConfigObj(args.config)
        HOSTNAME = config.get('hostname')
        USERNAME = config.get('username')
        PASSWORD = config.get('password')
        JENKINS_URL = config.get('jenkins_url')
        PREFIX = config.get('prefix', "")
        SESSION.auth = (USERNAME, PASSWORD)

        # Lazy validation :-)
        if HOSTNAME == "":
            raise requests.URLRequired("ERROR: Hostname Required!")
        if JENKINS_URL == "":
            raise requests.URLRequired("ERROR: Jenkins Url Required!")

        args.func(args)

    except Exception as E:
        print(E)
        sys.exit(1)
