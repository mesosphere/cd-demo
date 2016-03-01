#!/usr/bin/python
"""demo.py

Usage:
    demo.py install [--name=<name>] (--no-pipeline | [--branch=<branch>] [--org=<org>] [--username=<user>] --password=<pass>) [--no-dynamic-slaves] [--builds=<n>] <dcos_url>
    demo.py uninstall [--name=<name>] [--builds=<n>] <dcos_url>

Options:
    --name=<name>          Jenkins instance name to use [default: jenkins].
    --no-pipeline          Don't run continuous delivery demo.
    --branch=<branch>      Git branch for continuous delivery demo [default: demo].
    --org=<org>            Docker Hub organisation where repo lives [default: mesosphere].
    --username=<user>      Docker Hub username to push image with [default: cddemo].
    --password=<pass>      Docker Hub password to push image with.
    --no-dynamic-slaves    Don't run dynamic slaves demo.
    --builds=<n>           Number of builds to create [default: 50].

This script is used to demonstrate various features of Jenkins on the DCOS.

Pre-requisites:
+ A DCOS CLI is configured and available on the PATH of the host system
+ A running DCOS cluster greater than version 1.4. It currently does not
work with clusters that have authentication enabled.
+ Python dependencies are installed (pip install -r requirements.txt)

The continuous delivery demo will create a build pipeline that will deploy a Docker
container to the DCOS Marathon.

The dynamic slaves demo will create 50 (by default) "freestyle" Jenkins jobs.
Each of these jobs will appear as a separate Jenkins build, and will randomly
pass or fail. The duration of each job will be between 120 and 240 seconds.
"""

from docopt import docopt
import json
import os
import random
import requests
import shutil
from subprocess import call

def log(message):
    print "[demo] {}".format(message)

def config_dcos_cli(dcos_url):
    if call (["dcos", "config", "set", "core.dcos_url", dcos_url],stdout=open(os.devnull, 'wb')) == 1:
        log("Unable to configure DCOS CLI.")
        exit(1)

def make_temp_dir():
    remove_temp_dir()
    os.mkdir("tmp")

def rename(path, jenkins_name):
    with open(path, 'r+') as f:
        config = json.load(f)
        config['jenkins']['framework-name'] = jenkins_name
        f.seek(0)
        json.dump(config, f, indent=4)

def install(dcos_url, jenkins_name, jenkins_url):
    log ("Installing Jenkins with name {}".format(jenkins_name))
    shutil.copyfile("conf/jenkins.json", "tmp/jenkins.json")
    rename("tmp/jenkins.json", jenkins_name)
    command = "dcos package install --yes --options=tmp/jenkins.json jenkins"
    print ("\n> " + command)
    if call (['dcos', 'package', 'install', '--yes', '--options=tmp/jenkins.json', 'jenkins']) != 0:
        log ("Failed to install Jenkins")
        exit(1)
    print("\n[demo] Jenkins has been installed! Wait for it to come up before proceeding at: {}".format(jenkins_url))
    raw_input("[demo] Press [Enter] to continue, or ^C to cancel...")

def verify(jenkins_url):
    r = requests.get(jenkins_url)
    if r.status_code != 200:
        log ("Couldn't find a Jenkins instance running at {}".format(jenkins_url))
        return False
    log ("Jenkins is up and running! Got Jenkins version {}".format(r.headers['x-jenkins']))
    return True

def create_credentials(jenkins_url, id, username, password):
    credential = { 'credentials' : { 'scope' : 'GLOBAL', 'id' : id, 'username' : username, 'password' : password, 'description' : id, '$class' : 'com.cloudbees.plugins.credentials.impl.UsernamePasswordCredentialsImpl'} }
    data = {'json' : json.dumps(credential) }
    post_url = "{}/credential-store/domain/_/createCredentials".format(jenkins_url)
    r = requests.post(post_url, data=data)

def create_job(jenkins_url, job_name, job_config):
    log ("Creating job")
    headers = {'Content-Type' : 'application/xml' }
    post_url = "{}/createItem?name={}".format(jenkins_url, job_name)
    r = requests.post(post_url, headers=headers, data=job_config)
    if r.status_code != 200:
        log ("Failed to create job {} at {}".format(job_name, jenkins_url))
        exit(1)
    log ("Job {} created successfully".format(job_name))

def create_view(jenkins_url, view_name, view_config):
    log ("Creating view")
    headers = {'Content-Type' : 'text/xml' }
    post_url = "{}/createView?name={}".format(jenkins_url, view_name)
    r = requests.post(post_url, headers=headers, data=view_config)

def trigger_build(jenkins_url, job_name, parameter_string = None):
    log ("Triggering build {}".format(job_name))
    if parameter_string:
        post_url = "{}/job/{}/buildWithParameters?{}".format(jenkins_url, job_name, parameter_string)
    else:
        post_url = "{}/job/{}/build".format(jenkins_url, job_name)
    r = requests.post(post_url)

def delete_credentials(jenkins_url, credential_name):
    log ("Deleting credentials {}".format(credential_name))
    post_url = "{}/credential-store/domain/_/credential/{}/doDelete".format(jenkins_url, credential_name)
    r = requests.post(post_url)

def delete_job(jenkins_url, job_name):
    log ("Deleting job {}".format(job_name))
    post_url = "{}/job/{}/doDelete".format(jenkins_url, job_name)
    r = requests.post(post_url)

def delete_view(jenkins_url, view_name):
    log ("Deleting view {}".format(view_name))
    post_url = "{}/view/{}/doDelete".format(jenkins_url, view_name)
    r = requests.post(post_url)

def remove_temp_dir():
    shutil.rmtree("tmp", ignore_errors=True)

def demo_pipeline(jenkins_url, dcos_url, name, branch, org, username, password):
    log ("Creating demo pipeline")
    create_credentials(jenkins_url, 'docker-hub-credentials', username, password)
    with open("jobs/build-cd-demo/config.xml") as build_job:
        job_config = build_job.read().replace("GIT_BRANCH", branch)
        job_config = job_config.replace("DOCKER_HUB_ORG", org)
        create_job(jenkins_url, "build-cd-demo", job_config)
    with open("jobs/test-cd-demo/config.xml") as test_job:
        job_config = test_job.read().replace("GIT_BRANCH", branch)
        create_job(jenkins_url, "test-cd-demo", job_config)
    with open("jobs/deploy-cd-demo/config.xml") as deploy_job:
        job_config = deploy_job.read().replace("GIT_BRANCH", branch)
        job_config = job_config.replace("DCOS_URL", dcos_url)
        job_config = job_config.replace("JENKINS_NAME", name)
        create_job(jenkins_url, "deploy-cd-demo", job_config)
    with open("views/cd-demo-pipeline.xml") as pipeline_view:
        view_config = pipeline_view.read()
        create_view(jenkins_url, "cd-demo-pipeline", view_config)
    trigger_build(jenkins_url, "build-cd-demo")
    log ("Created demo pipeline")
    raw_input("[demo] Press [Enter] to continue, or ^C to cancel...")

def demo_dynamic_slaves(jenkins_url, builds):
    log ("Creating {} freestyle Jenkins jobs".format(builds))
    random.seed()
    with open("jobs/demo-job/config.xml") as demo_job:
        job_config = demo_job.read()
        for i in range(1, builds):
            job_name = "demo-job-{0:02d}".format(i)
            create_job(jenkins_url, job_name, job_config)
            duration = random.randint(120, 240)
            result = random.randint(0, 1)
            parameter_string = '?DURATION={}&RESULT={}'.format(duration, result)
            trigger_build(jenkins_url, job_name, parameter_string)
            log ("Job {} created successfully. Duration: {}. Result: {}. Triggering build.".format(job_name, duration, result))
    log ("Created {} freestyle Jenkins jobs".format(builds))
    raw_input("[demo] Press [Enter] to continue, or ^C to cancel...")

def cleanup_pipeline_jobs (jenkins_url):
    log ("Cleaning up demo pipeline")
    delete_credentials(jenkins_url, "docker-hub-credentials")
    delete_view(jenkins_url, "cd-demo-pipeline")
    delete_job(jenkins_url, "deploy-cd-demo")
    delete_job(jenkins_url, "test-cd-demo")
    delete_job(jenkins_url, "build-cd-demo")

def cleanup_dynamic_slaves_jobs(jenkins_url, builds):
    log ("Cleaning up {} builds".format(builds))
    for i in range(1, builds):
        job_name = "demo-job-{0:02d}".format(i)
        delete_job(jenkins_url, job_name)
    log ("Cleaned up {} builds".format(builds))

def cleanup(jenkins_url, builds):
    log ("Cleaning up Jenkins")
    cleanup_pipeline_jobs(jenkins_url)
    cleanup_dynamic_slaves_jobs(jenkins_url, builds)

def uninstall(dcos_url, jenkins_name):
    log ("Uninstalling Jenkins with name {}".format(jenkins_name))
    command = "dcos package uninstall --app-id={} jenkins".format(jenkins_name)
    print (command)
    if call (['dcos','package','uninstall','--app-id={}'.format(jenkins_name), 'jenkins']) != 0:
        log ("Failed to uninstall Jenkins")
        exit(1)
    print("[demo] Jenkins has been uninstalled!")

if __name__ == "__main__":
    arguments = docopt(__doc__, version="CD Demo 0.1")

    jenkins_name = arguments['--name']
    builds = int(arguments['--builds'])
    dcos_url = arguments['<dcos_url>']
    jenkins_url = '{}service/{}/'.format(dcos_url, jenkins_name)

    config_dcos_cli(dcos_url)

    try:
        if arguments['install']:
            make_temp_dir()
            if not verify(jenkins_url):
                install(dcos_url, jenkins_name, jenkins_url)
            if not arguments['--no-pipeline']:
                branch = arguments['--branch']
                org = arguments['--org']
                username = arguments['--username']
                password = arguments['--password']
                demo_pipeline(jenkins_url, dcos_url, jenkins_name, branch, org, username, password)
            if not arguments['--no-dynamic-slaves']:
                demo_dynamic_slaves(jenkins_url, builds)
            remove_temp_dir()
        elif arguments['uninstall']:
            cleanup(jenkins_url, builds)
            uninstall(dcos_url, jenkins_name)
    except KeyboardInterrupt:
        exit(0)
