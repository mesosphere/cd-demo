#!/usr/bin/env groovy

def variants = ['open', 'ee']
def channels = ['testing/master', 'testing/1.8.8', 'stable', 'EarlyAccess']

def cluster_request = [:]
def cluster_info = [:]
def demo = [:]
def cleanup = [:]

def get_job_name(channel, variant, build_number) {
  def channel_sanitized = channel.tr('/', '-')
  def job_name = "cd-demo-${variant}-${channel_sanitized}-${build_number}"

  return job_name
}

def get_template_url(variant, channel) {
  def template_url = ''

  if (variant.equals('ee'))   { template_url = "http://s3.amazonaws.com/downloads.mesosphere.io/dcos-enterprise/${channel}/cloudformation/ee.single-master.cloudformation.json" }
  if (variant.equals('open')) { template_url = "http://s3.amazonaws.com/downloads.dcos.io/dcos/${channel}/cloudformation/single-master.cloudformation.json" }

  return template_url
}

def get_dcos_info(job_name, section) {
  def info = sh(
    script: "./dcos-launch describe -i info-${job_name}.json | jq -r '.${section}[0].public_ip'",
    returnStdout: true
  ).trim()

  return info
}

def get_dcos_url(job_name) { return get_dcos_info(job_name, 'masters') }
def get_elb_url(job_name)  { return get_dcos_info(job_name, 'public_agents') }

node('py35') {
  wrap([$class: 'AnsiColorBuildWrapper', 'colorMapName': 'XTerm']) {

    // Install dcos-launch binary & requirements
    stage('Install dcos-launch') {
      sh "wget 'https://downloads.dcos.io/dcos/testing/master/dcos-launch' && chmod +x dcos-launch"
      sh "apt-get install -y gettext"
    }

    // Build execution phases for each matrix combination
    for (v in variants) {
      def variant = v

      for (c in channels) {
        def channel = c

        def job_name = get_job_name(channel, variant, env.BUILD_NUMBER)
 
        // Cluster acquisition
        cluster_request[variant + ':' + channel] = {
          def template_url = get_template_url(variant, channel)

          withCredentials([[
            $class: 'AmazonWebServicesCredentialsBinding',
            credentialsId: 'Teamcity AWS Development Account',
            accessKeyVariable: 'AWS_ACCESS_KEY_ID',
            secretKeyVariable: 'AWS_SECRET_ACCESS_KEY'
          ]]) {
            sh """
envsubst <<EOF > config-${job_name}.yaml
---
launch_config_version: 1
template_url: ${template_url}
deployment_name: ${job_name}
provider: aws
aws_region: eu-central-1
aws_access_key_id: ${env.AWS_ACCESS_KEY_ID}
aws_secret_access_key: ${env.AWS_SECRET_ACCESS_KEY}
template_parameters:
    KeyName: default
    AdminLocation: 0.0.0.0/0
    PublicSlaveInstanceCount: 1
    SlaveInstanceCount: 1
EOF
            """
          }

          sh "./dcos-launch create -c config-${job_name}.yaml -i info-${job_name}.json"
          sh "./dcos-launch wait -i info-${job_name}.json"

          cluster_info[variant + ':' + channel] = [:]
          cluster_info[variant + ':' + channel]['dcos_url'] = get_dcos_url(job_name)
          cluster_info[variant + ':' + channel]['elb_url'] = get_elb_url(job_name)
        }

        // Demo
        demo[variant + ':' + channel] = {
          def dcos_url = cluster_info[variant + ':' + channel]['dcos_url']
          def elb_url = cluster_info[variant + ':' + channel]['elb_url']

          node('py35') {
            // Checkout project from GitHub
            stage("${variant}:${channel} Git checkout") {
              checkout scm
            }

            // Install project requirements
            stage("${variant}:${channel} Install requirements") {
              sh "pip3 install -r requirements.txt"
              sh "pip3 install httpie"
            }

            // Prepare Git environment
            stage("${variant}:${channel} Prepare Git environment") {
              sshagent(['4ff09dce-407b-41d3-847a-9e6609dd91b8']) {
                sh "git config --global user.email 'velocity-team@mesosphere.com'"
                sh "git checkout -b ci-${job_name}"
                sh "git push origin ci-${job_name}"
               }
            }

            // Install Jenkins on acquired DC/OS cluster
            stage("${variant}:${channel} Install Jenkins") {
              withCredentials([
                string(credentialsId: 'CD_DEMO_OAUTH_TOKEN', variable: 'CD_DEMO_OAUTH_TOKEN')
              ]) {
                if (variant.equals('ee'))   { sh "python bin/demo.py install http://${dcos_url}/" }
                if (variant.equals('open')) { sh "python bin/demo.py install --dcos-oauth-token '${env.CD_DEMO_OAUTH_TOKEN}' http://${dcos_url}/" }
              }
            }

            // Run the 'pipeline' demo
            stage("${variant}:${channel} Run Jenkins pipeline demo") {
              withCredentials([
                string(credentialsId: 'CD_DEMO_OAUTH_TOKEN', variable: 'CD_DEMO_OAUTH_TOKEN'),
                string(credentialsId: 'CD_DEMO_DOCKER_PASSWORD', variable: 'CD_DEMO_DOCKER_PASSWORD')
              ]) {
                sshagent(['4ff09dce-407b-41d3-847a-9e6609dd91b8']) {
                  if (variant.equals('ee'))   { sh "python bin/demo.py pipeline --password '${env.CD_DEMO_DOCKER_PASSWORD}' http://${elb_url}/ http://${dcos_url}/" }
                  if (variant.equals('open')) { sh "python bin/demo.py pipeline --dcos-oauth-token '${env.CD_DEMO_OAUTH_TOKEN}' --password '${env.CD_DEMO_DOCKER_PASSWORD}' http://${elb_url}/ http://${dcos_url}/" }
                }
              }
            }

            // Clean up Git branch
            stage("${variant}:${channel} Clean up Git branch") {
              sshagent(['4ff09dce-407b-41d3-847a-9e6609dd91b8']) {
                sh "git push origin :ci-${job_name}"
              }
            }

            // Verify demo success
            stage("${variant}:${channel} Verify demo success") {
              timeout(30) {
                waitUntil {
                  def response = sh(
                    script: "http --check-status --ignore-stdin --timeout=2.5 HEAD 'http://${elb_url}/'",
                    returnStatus: true
                  )

                  return (response == 0)
                }
              }
            }
          }
        }

        // Clean-up DC/OS clusters
        cleanup[variant + ':' + channel] = {
          sh "./dcos-launch delete -i info-${job_name}.json"
        }
      }
    }

    // Run matrix combination phases in parallel
    try {
      stage('Acquire DC/OS clusters')  { parallel cluster_request }
      stage('Run cd-demo') { parallel demo }
    }
    finally {
      stage('Clean up') { parallel cleanup }
    }
  }
}
