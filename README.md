# cd-demo
A continuous delivery demo using Jenkins on DCOS.

This demo is a Python script that performs the following sequence of actions when run with the `install` command:

1. Installs Jenkins if it isn't already available.
2. Sets up a series of build jobs, the necessary credentials and a [Build Pipeline](https://wiki.jenkins-ci.org/display/JENKINS/Build+Pipeline+Plugin) view to demonstrate a basic continuous delivery pipeline. Jenkins will:
    + Spin up a new Jenkins slave using the Mesos plugin. This slave runs inside a Docker container on one of our DCOS agents.
    + Clone the git repository
    + Build a Docker container based off the [Jekyll Docker image](https://hub.docker.com/r/jekyll/jekyll/) that includes the content stored in [/site](/site) and push it to DockerHub.
    + Run the newly created container and a [Linkchecker container](https://github.com/mesosphere/docker-containers/blob/master/utils/linkchecker/Dockerfile) that runs a basic integration test against the container, checking that the webserver comes up correctly and that all links being served are valid (i.e. no 404s).
    + Manually trigger a Marathon deployment of the newly created container to the DCOS base Marathon instance. If the application already exists, Marathon will simply upgrade it.
    + Make the application available on a public slave at port 80.
3. Creates 50 build jobs that take a random amount of time between 1 and 2 minutes. These jobs will randomly fail.
    + The Mesos plugin will spin up build slaves on demand for these jobs, using as much capacity as your cluster has available.
    + When these jobs are finished, the Jenkins tasks will terminate and the resources will be relinquished back to other users of your cluster.

When run with the `uninstall` command, it will:

1. Remove any persisted credentials, build job and view configurations.
2. Uninstall Jenkins.

`bin/demo.py --help` will show you full help text and usage information.

## Basic Usage

### Set Up

1. Clone this repository!

    ```
    git clone https://github.com/mesosphere/cd-demo.git
    ```
2. [Set up the DCOS CLI](https://docs.mesosphere.com/administration/introcli/cli/) locally.
3. Ensure you have a DCOS cluster available. 1 node will work but more than 1 node is preferable to demonstrate build parallelism. If you already had the CLI installed, make sure you set the new cluster URL and authenticate against it:

    ```
    dcos config set core.dcos_url http://my.dcos.cluster/
    dcos auth login
    ```

### Running Demo

1. Run the demo script. You will need to replace the password here with the password for the `cddemo` user with permission to push to `mesosphere/cd-demo-app`:

    ```
    bin/demo.py install --branch=my-demo-branch --password=mypass123 http://my.dcos.cluster/
    ```
    NOTE: Depending on your environment you may need to prepend the above command with `python` Also you must use the domain name for your cluster; the IP address will fail.
    
2. The script will install Jenkins and pause. Check that the Jenkins UI is running before hitting enter to proceed.
3. The script will now use the Jenkins HTTP API to install jobs, necessary credentials and a view. It will automatically trigger the initial build before pausing.
4. Navigate to the Jenkins UI to see the builds in progress. After a few seconds, you should see a build executor spinning up on Mesos. If you navigate to the configured view, you'll see the pipeline in progress.
5. Once the tests have completed successfully, you will need to manually deploy the build using the button in the bottom right of the "deploy" box on the view.
![deploy](/img/manual-deploy.png)
6. The deploy will happen almost instantaneously. After a few seconds, you should be able to load the application by navigating to your public slave's IP address in your browser.
![deployed-app](/img/deployed-jekyll-app.png)
7. Hit Enter to proceed to the next step of the demo. It will create 50 jobs that will randomly fail.
8. Navigate back to the Jenkins and/or DCOS UI to show build slaves spinning up manually.
9. Hit enter to complete the demo.

### Uninstalling

1. Simply run the uninstall command to remove any persisted configuration and to uninstall the DCOS service itself. This will allow you to run multiple demos on the same cluster but you should recycle clusters if the version of the Jenkins package has changed (to ensure plugins are upgraded):
    bin/demo.py uninstall http://my.dcos.cluster/

## Advanced Usage

### Using a Custom Docker Hub Organisation

By default, this script assumes you will be pushing to the [mesosphere/cd-demo-app repository on Docker Hub](https://hub.docker.com/r/mesosphere/cd-demo-app/).

1. Create a public repo called `cd-demo-app` under your example organisation.
2. Create a Docker Hub user that has credentials to push to this repository.
3. Run the demo script, passing in the credentials:

    ```
    bin/demo.py install --branch=my-demo-branch --org=myorg --username=myuser --password=mypass123 http://my.dcos.cluster/
    ```

### Build on Commit

If you'd like to demonstrate the build running automatically with every commit:

1. By default this build operates off the `demo` branch. However, it's recommended that you create your own branches for demo purposes to avoid collisions. Create a new branch in this repository and push it up to origin:

    ```
    git checkout -b my-demo-branch
    git push origin my-demo-branch
    ```
2. Run the demo to completion with the `--branch` parameter to monitor your branch. The pipeline will continue to monitor your branch after the script finishes:

    ```
    bin/demo.py install --branch=my-demo-branch --password=mypass123 http://my.dcos.cluster/
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

To demonstrate how you can install multiple Jenkins instances side by side on DCOS, simply give your Jenkins instances unique names using the `--name` argument and run the demo as follows. Note that if you only have one public slave, you will not be able to deploy applications from multiple pipelines (each application requires port 80).

1. Create one instance:

    ```
    bin/demo.py install --name=jenkins-1 --password=mypass123 http://my.dcos.cluster/
    ```
2. Open a new terminal tab and create a second instance and so on:

    ```
    bin/demo.py install --name=jenkins-2 --password=mypass123 http://my.dcos.cluster/
    ```
3. You can uninstall these in the same way:

    ```
    bin/demo.py uninstall --name=jenkins-1 http://my.dcos.cluster/
    bin/demo.py uninstall --name=jenkins-2 http://my.dcos.cluster/
    ```

### Skipping Demos

Only want to run one of the demos? Simply specify `--no-pipeline` to skip the continuous delivery demo, or `--no-dynamic-slaves` to skip the dynamic slaves demo.

## TODO

+ This script is currently untested on Windows.
