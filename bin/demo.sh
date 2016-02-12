#!/bin/bash
set -e

function usage {
    cat <<END
Usage: $0 <create-many|cleanup-many|create-cd> <http://dcos.url>

This script is used to demonstrate various features of Jenkins on the DCOS.

The create-many command will create 50 "freestyle" Jenkins jobs. Each of these jobs
will appear as a separate Jenkins build, and will randomly pass or fail. The
duration of each job will be between 120 and 240 seconds.

The create-cd command will create a build pipeline that will deploy a Docker
container to the DCOS Marathon.

This script will demonstrate how the Mesos plugin can automatically create and
destroy Jenkins build slaves as demand increases or decreases, as well as create
continuous delivery pipelines on the Mesosphere DCOS.
END
    return 1
}


function create_job {
    local jenkins_url=$1
    local xml_path=$2
    local job_name=$3

    curl -fH 'Content-Type: application/xml' --data-binary @${xml_path} \
        "${jenkins_url}/createItem?name=${job_name}"

    if [[ $? == 0 ]]; then
        echo "Job '${job_name}' created successfully."
    else
        echo "There was a problem creating the Jenkins job '${job_name}'."
        return 1
    fi
}

function trigger_build {
    local jenkins_url=$1
    local job_name=$2
    # if [ -n $3 ]; then
    #     local parameters=$3
    #     curl -fX POST "${jenkins_url}/job/${job_name}/buildWithParameters?$parameters"
    # else
    curl -fX POST "${jenkins_url}/job/${job_name}/build"
    # fi
}

function create_view {
    local jenkins_url=$1
    local xml_path=$2
    local view_name=$3
    curl -fH 'Content-Type: text/xml' -X POST --data-binary @${xml_path} \
        ${jenkins_url}/createView\?name\=${view_name}
}

function update_dcos_cli {
    local dcos_url=$1
    dcos config set core.dcos_url ${dcos_url}
}

function install_jenkins {
    dcos config unset package.sources
    dcos config prepend package.sources 'https://github.com/mesosphere/universe/archive/configurable-slave-container.zip'
    dcos package update
    # TODO: rename stuff
    #mkdir -p tmp/conf
    #cat conf/jenkins.json | jq '.jenkins."framework-name" = "jenkins-$(jenkins_name)"' > tmp/jenkins-$(jenkins_name).json
    dcos package install --yes --options=conf/jenkins.json jenkins
    echo "Info: Jenkins has been installed! Wait for it to come up before proceeding."
    read -p "Press [Enter] to continue, or ^C to cancel..."
}

function verify_jenkins {
    local jenkins_url=$1

    if jenkins_version=`curl -sI $jenkins_url | grep 'X-Jenkins:' | awk -F': ' '{print $2}' | tr -d '\r'`; then
        echo "Info: Jenkins is up and running! Got Jenkins version ${jenkins_version}."
        echo
    else
        echo "Error: didn't find a Jenkins instance running at ${jenkins_url}."
        return 1
    fi
}

function create {
    local jenkins_url=$1
    local job_basename=$2
    local count=$3

    cat << END
This script will create 50 "freestyle" Jenkins jobs. Each of these jobs will
appear as a separate Jenkins build, and will randomly pass or fail. The
duration of each job will be between 120 and 240 seconds.

About to create ${count} jobs that start with ${job_basename} on the Jenkins
instance located at:

  ${jenkins_url}

END

    read -p "Press [Enter] to continue, or ^C to cancel..."

    for i in `seq -f "%02g" 1 $count`; do
        duration=$(((RANDOM % 120) + 120))
        result=$((RANDOM % 2))
        demo_job_name="${job_basename}-${i}"

        curl -fH 'Content-Type: application/xml' --data-binary @jobs/demo-job.xml \
            "${jenkins_url}/createItem?name=${demo_job_name}"

        if [[ $? == 0 ]]; then
            echo "Job '${demo_job_name}' created successfully. Duration: ${duration}. Result: ${result}. Triggering build."
            curl -fX POST "${jenkins_url}/job/${demo_job_name}/buildWithParameters?DURATION=${duration}&RESULT=${result}"
        else
            echo "There was a problem creating the Jenkins job '${demo_job_name}'."
            return 1
        fi
    done
}

function cleanup {
    local jenkins_url=$1
    local job_basename=$2
    local count=$3

    for i in `seq -f "%02g" 1 $count`; do
        demo_job_name="${job_basename}-${i}"
        echo "Deleting job '${demo_job_name}'"
        curl -fX POST "${jenkins_url}/job/${demo_job_name}/doDelete"
    done
}


function create_cd_jobs {
    local jenkins_url=$1
    local dcos_url=$2
    create_job ${jenkins_url} "jobs/build-cd-demo/config.xml" build-cd-demo
    mkdir -p tmp/deploy-cd-demo
    cat jobs/deploy-cd-demo/config.xml | sed "s#DCOS_URL#$dcos_url#g" > tmp/deploy-cd-demo/config.xml
    create_job ${jenkins_url} "tmp/deploy-cd-demo/config.xml" deploy-cd-demo
    create_view ${jenkins_url} "views/cd-demo-pipeline.xml" cd-demo-pipeline
    trigger_build ${jenkins_url} build-cd-demo
}


function main {

    if ! command -v curl > /dev/null; then
        echo "Error: cURL not found in $PATH"
        return 1
    fi

    if [[ ! $# != 4 ]]; then
        usage
    else
        local operation="$1"
        local dcos_url="$2"
    fi

    update_dcos_cli $dcos_url

    local jenkins_url=$dcos_url/service/jenkins-demo
    local demo_job_name="demo-job"
    local demo_job_count=50

    case $operation in
        create-many)
            verify_jenkins $jenkins_url
            create $jenkins_url $demo_job_name $demo_job_count
            ;;
        cleanup-many)
            cleanup $jenkins_url $demo_job_name $demo_job_count
            ;;
        create-cd)
            install_jenkins
            verify_jenkins $jenkins_url
            create_cd_jobs $jenkins_url $dcos_url
            ;;
        *)
            echo -e "Unknown operation: ${operation}\n"
            usage
            ;;
    esac
}

main $@
