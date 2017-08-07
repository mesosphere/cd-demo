# cd-demo
A continuous delivery demo using Jenkins on DC/OS.

This demo is a Python script that, when run with the `install` command, will:

1. Installs Jenkins if it isn't already available.

Running the `pipeline` command will:

2. Sets up a Jenkins "workflow" pipeline job and the necessary credentials to demonstrate a basic continuous delivery pipeline.  Jenkins will:

    + Spin up a new Jenkins agent using the Mesos plugin. This agent runs inside a Docker container on one of our DC/OS agents.
    + Clone the git repository
    + Build a Docker container based off the [Jekyll Docker image](https://hub.docker.com/r/jekyll/jekyll/) that includes the content stored in [/site](/site) and push it to DockerHub.
    + Run the newly created container and a [Linkchecker container](https://github.com/mesosphere/docker-containers/blob/master/utils/linkchecker/Dockerfile) that runs a basic integration test against the container, checking that the webserver comes up correctly and that all links being served are valid (i.e. no 404s).
    + Manually trigger a Marathon deployment of the newly created container to the DC/OS base Marathon instance. If the application already exists, Marathon will simply upgrade it.
    + Make the application available on a public agent at port 80 using Marathon-lb.

When run with the `dynamic-agents` command, it will:

3. Creates 50 build jobs that take a random amount of time between 1 and 2 minutes. These jobs will randomly fail.
    + The Mesos plugin will spin up build agents on demand for these jobs, using as much capacity as your cluster has available.
    + When these jobs are finished, the Jenkins tasks will terminate and the resources will be relinquished back to other users of your cluster.

When run with the `uninstall` command, it will:

1. Remove any persisted credentials, build job and view configurations.
2. Uninstall Jenkins.

`bin/demo.py --help` will show you full help text and usage information.

## Basic Usage

### Prerequisites

+ GitHub account
+ Python 3
+ `pip install -r requirements.txt`

Tip: If Python 3 is not the default on your system, you may need to specifically instruct pip to install the Python 3 versions of the requirements.

### Set Up

1. Clone this repository!

    ```
    git clone https://github.com/mesosphere/cd-demo.git
    ```

2. Check out the latest stable tag, depending on DC/OS cluster version you're running against:

    DC/OS 1.10+:
    ```
    git checkout v1.8.7-2.7.2
    ```

    DC/OS 1.9 and below:
    ```
    git checkout v1.8.6-2.7.2
    ```


3. Create a branch from the latest stable tag, this is mandatory:

    ```
    git checkout -b my-demo-branch
    git push origin my-demo-branch
    ```

4. Ensure you have a DC/OS cluster available. 1 node will work but more than 1 node is preferable to demonstrate build parallelism.

5. Export the demo Docker Hub password (NOT the DC/OS cluster password) to an environment variable. You will need to replace the password here with the password for the `cddemo` user with permission to push to `mesosphere/cd-demo-app` (or your own repo, if you override the `--org` and `--username` flags later):

    ```
    export PASSWORD=mypass123
    ```

### Running Demo

1. Run the install command. This is mainly a wrapper for the `dcos package install` command but will also check to see if you're authenticated.

    ```
    python3 bin/demo.py install http://my.dcos.cluster/
    ```

    NOTE: You must use the domain name for your cluster; the IP address will fail.

2. You can now run either the pipeline demo or the dynamic agents demo. To run the pipeline demo, you will also need to specify the ELB address (`Public Agent`):

    ```
    python3 bin/demo.py pipeline  --password=$PASSWORD http://my.elb/ http://my.dcos.cluster/
    ```

3. The script will first install Marathon-lb if it looks like it isn't available. It will also update the `marathon.json` in the branch you specified to include the ELB hostname so that Marathon-lb can route to it.

4. The script will then use the Jenkins HTTP API to install jobs and necessary credentials. It will automatically trigger the initial build before finishing.

5. Navigate to the Jenkins UI to see the builds in progress. After a few seconds, you should see a build executor spinning up on Mesos. If you navigate to the job, you'll see the pipeline in progress.

6. The deploy will happen almost instantaneously. After a few seconds, you should be able to load the application by navigating to the ELB hostname you provided earlier in your browser.

![deployed-app](/img/deployed-jekyll-app.png)

7. Now let's run the dynamic agents demo. It will create 50 jobs that will randomly fail.

    ```
    python3 bin/demo.py dynamic-agents http://my.dcos.cluster/
    ```

8. Navigate back to the Jenkins and/or DC/OS UI to show build agents spinning up manually.

### Uninstalling

1. Simply run the uninstall command to remove any persisted configuration and to uninstall the DC/OS service itself. This will allow you to run multiple demos on the same cluster but you should recycle clusters if the version of the Jenkins package has changed (to ensure plugins are upgraded):

    ```
    python3 bin/demo.py uninstall http://my.dcos.cluster/
    ```

Alternatively, run the cleanup command instead to just remove jobs and to avoid having to re-install Jenkins.

## Advanced Usage

### Using a Custom Docker Hub Organisation

By default, this script assumes you will be pushing to the [mesosphere/cd-demo-app repository on Docker Hub](https://hub.docker.com/r/mesosphere/cd-demo-app/).

1. Create a public repo called `cd-demo-app` under your example organisation.
2. Create a Docker Hub user that has credentials to push to this repository.
3. Run the pipeline demo, passing in the credentials:

    ```
    python3 bin/demo.py pipeline --org=myorg --username=myuser --password=$PASSWORD http://my.elb/ http://my.dcos.cluster/
    ```

### Build on Commit

1. Run the demo to completion. The pipeline will continue to monitor your branch after the script finishes:

    ```
    python3 bin/demo.py pipeline --password=$PASSWORD http://my.elb/ http://my.dcos.cluster/
    ```

3. Create a new blog post with today's date, open it up in your text editor and make whatever changes you'd like to:

    ```
    cp site/_posts/2016-02-25-welcome-to-cd-demo.markdown site/_posts/$(date +%Y-%m-%d)-my-test-post.markdown
    nano site/_posts/$(date +%Y-%m-%d)-my-test-post.markdown
    ```

4. Commit your changes and push them up to GitHub:

    ```
    git add site/_posts/$(date +%Y-%m-%d)-my-test-post.markdown
    git commit -m "Demo change"
    git push origin my-demo-branch
    ```

5. Jenkins will pick up the change within a minute and kick off the pipeline. If you want to fail the build, simply insert a broken link into your post.

### Demonstrating Multi-tenancy

To demonstrate how you can install multiple Jenkins instances side by side on DC/OS, simply give your Jenkins instances unique names using the `--name` argument and run the demo as follows. Note that if you only have one public agent, you will not be able to deploy applications from multiple pipelines (each application requires port 80).

1. Create one instance:

    ```
    python3 bin/demo.py install --name=jenkins-1 http://my.dcos.cluster/
    ```

2. Open a new terminal tab and create a second instance and so on:

    ```
    python3 bin/demo.py install --name=jenkins-2 http://my.dcos.cluster/
    ```

3. You can uninstall these in the same way:

    ```
    python3 bin/demo.py uninstall --name=jenkins-1 http://my.dcos.cluster/
    python3 bin/demo.py uninstall --name=jenkins-2 http://my.dcos.cluster/
    ```

### Authentication

The script will check to see if your current machine has a valid `dcos_acs_token` set. If it doesn't:

1. it attempts to authenticate using the default username and password for an Enterprise DC/OS cluster. You can override these using the `--dcos-username` and `--dcos-password` arguments.

2. if this fails, it will attempt to use the `--dcos-oauth-token` arguments to authenticate against an Open DC/OS cluster.

## TODO

+ This script is currently untested on Windows.
