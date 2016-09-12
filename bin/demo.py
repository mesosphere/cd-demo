#!/usr/bin/env python
"""demo.py

Usage:
    demo.py install [options] <dcos_url>
    demo.py pipeline [options] <elb_url> <dcos_url>
    demo.py dynamic-slaves [options] <dcos_url>
    demo.py cleanup [options] <dcos_url>
    demo.py uninstall [options] <dcos_url>

Options:
    --name <name>               Jenkins instance name to use [default: jenkins]
    --org <org>                 Docker Hub organisation [default: mesosphere]
    --username <user>           Docker Hub username [default: cddemo]
    --password <pass>           Docker Hub password
    --dcos-username <user>      DC/OS auth username [default: bootstrapuser]
    --dcos-password <pass>      DC/OS auth password [default: deleteme]
    --dcos-oauth-token <token>  DC/OS OAuth token (required for OpenDC/OS)
    --builds <n>                Number of builds to create [default: 50]

This script is used to demonstrate various features of Jenkins on the DC/OS.

Pre-requisites:
+ A running DC/OS cluster greater than version 1.7.0.
+ Python dependencies are installed (pip install -r requirements.txt)

The continuous delivery demo will create a build pipeline that will deploy a
Docker container to the DC/OS Marathon.

The dynamic slaves demo will create 50 (by default) "freestyle" Jenkins jobs.
Each of these jobs will appear as a separate Jenkins build, and will randomly
pass or fail. The duration of each job will be between 120 and 240 seconds.
"""

import dcos
import os
import random
import sys

from docopt import docopt
from subprocess import call
from urllib.parse import urlparse

from shakedown import *

def log(message):
    print("[demo]: {}".format(message))

def log_and_exit(message):
    log(message)
    exit(1)

@contextlib.contextmanager
def stdchannel_redirected(stdchannel, dest_filename):
    try:
        oldstdchannel = os.dup(stdchannel.fileno())
        dest_file = open(dest_filename, 'w')
        os.dup2(dest_file.fileno(), stdchannel.fileno())
        yield
    finally:
        if oldstdchannel is not None:
            os.dup2(oldstdchannel, stdchannel.fileno())
        if dest_file is not None:
            dest_file.close()

def needs_authentication():
    token = dcos.config.get_config_val("core.dcos_acs_token")
    if token is None:
        # need to check if token is set because the CLI code will prompt for auth otherwise
        return True
    else:
        try:
            # make a request that requires authentication
            shakedown.dcos_leader()
            return False
        except dcos.errors.DCOSException:
            return True

def authenticate_with_oauth(dcos_url, dcos_oauth_token):
    dcos_oauth_token = arguments['--dcos-oauth-token']
    url = dcos_url + 'acs/api/v1/auth/login'
    creds = { 'token' : dcos_oauth_token }
    r = http.request('post', url, json=creds)
    if r.status_code == 200:
        dcos.config.set_val('core.dcos_acs_token', r.json()['token'])
    else:
        log_and_exit('!! DC/OS authentication failed; ' +
            'invalid --dcos-oauth-token provided')

def check_and_set_token(dcos_url):
    if needs_authentication():
        try:
            dcos_username = arguments['--dcos-username']
            dcos_password = arguments['--dcos-password']
            token = shakedown.authenticate(dcos_username, dcos_password)
            dcos.config.set_val('core.dcos_acs_token', token)
        except:
            dcos_oauth_token = arguments['--dcos-oauth-token']
            if dcos_oauth_token:
                authenticate_with_oauth(dcos_url, dcos_oauth_token)
            else:
                log_and_exit('!! DC/OS authentication failed; ' +
                    'did you provide --dcos-username and --dcos-password or --dcos-oauth-token?')

def config_dcos_cli(dcos_url):
    dcos.config.set_val('core.dcos_url', dcos_url)
    dcos.config.set_val('core.ssl_verify', 'False')

def install_jenkins(jenkins_name, jenkins_url):
    log("installing Jenkins with name '{}'".format(jenkins_name))
    with open("conf/jenkins.json") as options_file:
        package_config = options_file.read().replace("JENKINS_NAME", jenkins_name)
    with open("jenkins_config.json", "w") as options_file:
        options_file.write(package_config)
    install_package('jenkins', None, jenkins_name, "jenkins_config.json")
    os.remove("jenkins_config.json")
    assert package_installed('jenkins', jenkins_name), log_and_exit('!! package failed to install')
    log("waiting for Jenkins service to come up at '{}'".format(jenkins_url))
    end_time = time.time() + 60
    while time.time() < end_time:
        if verify_jenkins(jenkins_url):
            break
        time.sleep(1)

def verify_jenkins(jenkins_url):
    try:
        r = http.get(jenkins_url)
        if r.status_code == 200 and r.headers['x-jenkins']:
            log("service is up and running, got Jenkins version '{}'".format(r.headers['x-jenkins']))
            return True
    except:
        return False

def install_marathon_lb(marathon_lb_url):
    log("installing marathon-lb")
    dcos_oauth_token = arguments['--dcos-oauth-token']
    if dcos_oauth_token:
        install_package('marathon-lb')
    else:
        install_marathon_lb_secret(marathon_lb_url)
        install_package('marathon-lb', None, None, "conf/marathon-lb.json")

def install_marathon_lb_secret(marathon_lb_url):
    with stdchannel_redirected(sys.stdout, os.devnull):
        run_dcos_command('marathon app add conf/get_sa.json')
        end_time = time.time() + 300
        while time.time() < end_time:
            if get_marathon_task('saread'):
                break
            time.sleep(1)
        log("retrieving service account JSON")
        time.sleep(30)
        satoken = run_dcos_command("task log --lines=1 saread")[0]
        run_dcos_command('marathon app remove saread')
    post_url = "{}secrets/v1/secret/default/marathon-lb".format(dcos_url)
    headers = {'Content-Type': 'application/json'}
    data = json.dumps({ 'value' : satoken })
    try:
        r = http.get(post_url)
        if r.status_code == 200:
            log("removing old marathon-lb secret key")
            http.delete(post_url)
    except:
        pass
    r = http.put(post_url, headers=headers, data=data)

def verify_marathon_lb(marathon_lb_url):
    with stdchannel_redirected(sys.stderr, os.devnull):
        try:
            r = http.get(marathon_lb_url)
            if r.status_code == 200 and r.text:
                log("marathon-lb is up and running")
                return True
        except:
            return False

def strip_to_hostname(url):
    parsed_url = urlparse(url)
    return parsed_url.netloc

def get_branch():
    branch = subprocess.check_output(['git','rev-parse', '--abbrev-ref', 'HEAD'])
    return str(branch, 'utf-8').strip()

def update_and_push_marathon_json(elb_url, branch):
    elb_hostname = strip_to_hostname(elb_url)
    with open("conf/cd-demo-app.json") as options_file:
        app_config = options_file.read().replace("ELB_HOSTNAME", elb_hostname)
    with open("marathon.json", "w") as options_file:
        options_file.write(app_config)
    if call(['git', 'add', 'marathon.json']) != 0:
        log_and_exit("!! failed to add marathon.json to git repo")
    if call(['git', 'commit', 'marathon.json', '-m', 'Update marathon.json with ELB hostname']) != 0:
        log_and_exit("!! failed to commit updated marathon.json")
    if call(['git', 'push', 'origin', branch]) != 0:
        log_and_exit("!! failed to push updated marathon.json")
    log("updated marathon.json with ELB hostname '{}'".format(elb_hostname))

def trigger_build(jenkins_url, job_name, parameter_string = None):
    log("triggering build '{}'".format(job_name))
    if parameter_string:
        post_url = "{}/job/{}/buildWithParameters?{}".format(jenkins_url, job_name, parameter_string)
    else:
        post_url = "{}/job/{}/build".format(jenkins_url, job_name)
    try:
        r = http.post(post_url)
    except:
        log("!! failed to trigger job '{}'".format(job_name))

def create_credentials(jenkins_url, credential_name, username, password):
    log("creating credentials '{}'".format(credential_name))
    credential = { 'credentials' : {
        'scope' : 'GLOBAL',
        'id' : credential_name,
        'username' : username,
        'password' : password,
        'description' : credential_name,
        '$class' : 'com.cloudbees.plugins.credentials.impl.UsernamePasswordCredentialsImpl'
    } }
    data = { 'json' : json.dumps(credential) }
    post_url = "{}/credentials/store/system/domain/_/createCredentials".format(jenkins_url)
    try:
        r = http.post(post_url, data=data)
    except:
        log("!! failed to create credentials '{}'".format(credential_name))

def create_credentials_text(jenkins_url, credential_name, text):
    log("creating credentials '{}'".format(credential_name))
    credential = { 'credentials' : {
        'scope' : 'GLOBAL',
        'id' : credential_name,
        'secret' : text,
        'description' : credential_name,
        '$class' : 'org.jenkinsci.plugins.plaincredentials.impl.StringCredentialsImpl'
    } }
    data = { 'json' : json.dumps(credential) }
    post_url = "{}/credentials/store/system/domain/_/createCredentials".format(jenkins_url)
    try:
        r = http.post(post_url, data=data)
    except:
        log("!! failed to create credentials '{}'".format(credential_name))


def delete_credentials(jenkins_url, credential_name):
    log("deleting credentials '{}'".format(credential_name))
    post_url = "{}/credentials/store/system/domain/_/credential/{}/doDelete".format(jenkins_url, credential_name)
    try:
        r = http.post(post_url)
    except:
        log("!! failed to delete credentials '{}'".format(credential_name))

def create_job(jenkins_url, job_name, job_config):
    log("creating job '{}'".format(job_name))
    post_url = "{}/createItem?name={}".format(jenkins_url, job_name)
    headers = {'Content-Type': 'application/xml'}
    try:
        r = http.post(post_url, headers=headers, data=job_config)
    except:
        log("!! failed to create job '{}'".format(job_name))

def delete_job(jenkins_url, job_name):
    log("deleting job {}".format(job_name))
    post_url = "{}/job/{}/doDelete".format(jenkins_url, job_name)
    try:
        r = http.post(post_url)
    except:
        log("!! failed to delete job '{}'".format(job_name))

def demo_pipeline(jenkins_url, elb_url, name, branch, org, username, password):
    log("creating demo pipeline (workflow)")
    create_credentials(jenkins_url, 'docker-hub-credentials', username, password)
    token = run_dcos_command("config show core.dcos_acs_token")[0].strip()
    create_credentials_text(jenkins_url, 'dcos-token', token)
    with open("jobs/pipeline-demo/config.xml") as build_job:
        job_config = build_job.read().replace("GIT_BRANCH", branch)
        job_config = job_config.replace("DOCKER_HUB_ORG", org)
        create_job(jenkins_url, "pipeline-demo", job_config)
    trigger_build(jenkins_url, "pipeline-demo")
    log("demo pipeline (workflow) created")
    log("once deployed, your application should be available at:\n\t{}".format(elb_url))

def demo_dynamic_slaves(jenkins_url, builds):
    log("creating {} freestyle Jenkins jobs".format(builds))
    random.seed()
    with open("jobs/demo-job/config.xml") as demo_job:
        job_config = demo_job.read()
        for i in range(builds):
            job_name = "demo-job-{0:02d}".format(i)
            create_job(jenkins_url, job_name, job_config)
            duration = random.randint(120, 240)
            result = random.randint(0, 1)
            parameter_string = '?DURATION={}&RESULT={}'.format(duration, result)
            trigger_build(jenkins_url, job_name, parameter_string)
    log("created {} freestyle Jenkins jobs".format(builds))

def cleanup_pipeline_jobs(jenkins_url):
    log("cleaning up demo pipeline")
    delete_credentials(jenkins_url, "docker-hub-credentials")
    delete_credentials(jenkins_url, "dcos-token")
    delete_job(jenkins_url, "pipeline-demo")

def cleanup_dynamic_slaves_jobs(jenkins_url, builds):
    log("cleaning up {} builds".format(builds))
    for i in range(builds):
        job_name = "demo-job-{0:02d}".format(i)
        delete_job(jenkins_url, job_name)

def cleanup(jenkins_url, builds):
    cleanup_pipeline_jobs(jenkins_url)
    cleanup_dynamic_slaves_jobs(jenkins_url, builds)

def uninstall(jenkins_name):
    log("uninstalling Jenkins with name '{}'".format(jenkins_name))
    uninstall_package_and_wait('jenkins', jenkins_name)
    log("Jenkins has been uninstalled")

if __name__ == "__main__":
    arguments = docopt(__doc__, version="CD Demo 0.1")

    jenkins_name = arguments['--name'].lower()
    builds = int(arguments['--builds'])
    dcos_url = arguments['<dcos_url>']
    elb_url = arguments['<elb_url>'] #TODO: FIX ME
    jenkins_url = '{}service/{}/'.format(dcos_url, jenkins_name)

    config_dcos_cli(dcos_url)
    check_and_set_token(dcos_url)

    try:
        if arguments['install']:
            if not verify_jenkins(jenkins_url):
                log("couldn't find Jenkins running at '{}'".format(jenkins_url))
                install_jenkins(jenkins_name, jenkins_url)
        elif arguments['pipeline']:
            branch = get_branch()
            if branch == 'master':
                log_and_exit("!! cannot run demo against the master branch.")
            org = arguments['--org']
            username = arguments['--username']
            password = arguments['--password']
            if not verify_marathon_lb(elb_url):
                log("couldn't find marathon-lb running at '{}'".format(elb_url))
                install_marathon_lb(elb_url)
            update_and_push_marathon_json(elb_url, branch)
            demo_pipeline(jenkins_url, elb_url, jenkins_name, branch, org, username, password)
        elif arguments['dynamic-slaves']:
            demo_dynamic_slaves(jenkins_url, builds)
        elif arguments['cleanup']:
            cleanup(jenkins_url, builds)
        elif arguments['uninstall']:
            cleanup(jenkins_url, builds)
            uninstall(jenkins_name)
    except KeyboardInterrupt:
        exit(0)
