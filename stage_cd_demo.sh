#!/bin/bash
# Script for setting up the CI/CD demo in DC/OS
#

# Requirements:
#   - DC/OS cluster with 1 public slave and 5 private slaves with
#       or without superuser set
#   - DCOS CLI installed on localhost
#   - DCOS_EE set to true or false
#   - DCOS_URL set to DCOS master URL
#
# If no user credentials are supplied, the following will be used:
#   Enterprise:
#     - AWS default bootstrapuser/deleteme
#     - Override with DCOS_USER & DCOS_PW
#   OSS:
#     - The token hard-coded below for mesosphere.user@gmail.com
#         password: unicornsarereal
#     - Override with DCOS_AUTH_TOKEN
set -o errexit

if [ -z ${DCOS_EE+x} ]; then DCOS_EE=true; fi
if [ -z ${DCOS_URL+x} ]; then
#strip http(s) from Master IP url
mip_clean=${1#*//}
#strip trailing slash from Master IP url
DCOS_URL=https://${mip_clean%/}/
fi

if [ -z ${DCOS_PUB_ELB+x} ]; then
# strip http(s) from ELB url
elb_clean=${2#*//}
# strip trailing slash from ELB url
DCOS_PUB_ELB=https://${elb_clean%/}/
fi

#Run CI Script in infrastructure mode
for i in `dcos cluster list | awk ' FNR > 1 { print $1 }' | sed 's/\*//'`; do dcos cluster remove $i; done

DCOS_AUTH_TOKEN=${DCOS_AUTH_TOKEN:=$ci_auth_token}
DCOS_USER=${DCOS_USER:='bootstrapuser'}
DCOS_PW=${DCOS_PW:='deleteme'}

log_msg() {
    echo `date -u +'%D %T'`: $1
}

cmd_eval() {
        log_msg "Executing: $1"
        eval $1
}


ee_login() {
cat <<EOF | expect -
spawn dcos cluster setup "$DCOS_URL" --no-check
expect "username:"
send "$DCOS_USER\n"
expect "password:"
send "$DCOS_PW\n"
expect eof
EOF
}

sudo pip3 install -r requirements.txt

cmd_eval ee_login
dcos package install --yes dcos-enterprise-cli

echo $DCOS_URL

if [ -e "password.txt" ]
then
  docker_password=`cat password.txt`
fi

if [ -z "$docker_password" ]
then
        echo -n "Enter docker repo password and press [ENTER]: "
        read -s docker_password
fi

python3 bin/demo.py install $DCOS_URL

read -p "SETUP Complete, Press Any Key to Continue"

python3 bin/demo.py pipeline  --password=$docker_password $DCOS_PUB_ELB $DCOS_URL
counter=1
read -p "Press any key to commit a new post"

cp site/_posts/2016-02-25-welcome-to-cd-demo.markdown site/_posts/`date +'%Y-%m-%d'`-new-post.markdown
git add site/_posts/*
git commit -m 'New Post'
git push
counter=$((counter+1))

read -p "PIPELINE Demo complete, Press Any Key to Continue"

python3 bin/demo.py dynamic-agents $DCOS_URL

read -p "Dynamic Agents Demo complete, Press Any Key to Continue"

python3 bin/demo.py uninstall $DCOS_URL
dcos package uninstall --yes marathon-lb
git reset --hard HEAD~$counter
git push -f
dcos security secrets delete marathon-lb
