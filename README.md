An AWS Lambda function to manage a GitHub Organization

# Overview

`github-org-manager` is a lightweight framework to execute arbitrary actions
in response to GitHub webhook events. Specifically, it's meant to trigger off of
SNS notifications created by the [mozilla-platform-ops githubwebhooks tool](https://github.com/mozilla-platform-ops/devservices-aws/tree/master/githubwebhooks)
which generates notifications for the github.com/mozilla organization.

`github-org-manager` passes the GitHub webhook event to all plugins in the
`plugins/` directory, allowing each plugin to test if the event should trigger
that plugin by calling that plugin's `is_matching` function.

Each plugin that determines that the GitHub webhook event should trigger an
action has its `act` function called which can take an action in response to
that GitHub webhook event

# One time setup

* Provision a [GitHub personal token](https://github.com/settings/tokens) with
  `repo` scope permissions. The scopes needed depend entirely on what plugins
  you plan to run.
* Create a `config.yaml` with GitHub personal token. The file would look like
  this:

      github_token: 0123456789abcdef0123456789abcdef01234567

* Zip up github-org-manager, it's dependencies and the `config.yaml`

      tmpdir=`mktemp -d`
      pip install agithub PyYAML python-dateutil --target "$tmpdir"
      cwd=`pwd`
      pushd "$tmpdir"
      zip -r "${cwd}/github_org_manager.zip" *
      popd
      rm -rf "$tmpdir"
      zip --junk-paths github_org_manager.zip github_org_manager/__init__.py
      chmod 644 github_org_manager/config.yaml;zip --junk-paths github_org_manager.zip github_org_manager/config.yaml;chmod 600 github_org_manager/config.yaml
      cd github_org_manager
      zip ../github_org_manager.zip plugins/*

        
* Create an AWS IAM role to be used by a AWS Lambda function with `LambdaBasicExecution`

      echo '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":["lambda.amazonaws.com"]},"Action":["sts:AssumeRole"]}]}' | aws iam create-role --role-name github-org-manager --assume-role-policy-document file:///dev/stdin
      aws iam attach-role-policy --role-name github-org-manager --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

  * If you enable the alert SNS alert feature, you'll need to also grant the Lambda function rights to publish to that SNS topic

* Deploy the zip artifact to Lambda

      role_arn="`aws iam get-role --role-name github-org-manager --output text --query 'Role.Arn'`"
      lambda_arn="`aws lambda create-function --function-name github-org-manager --runtime python2.7 --timeout 30 --role $role_arn --handler __init__.lambda_handler --zip-file fileb://github_org_manager.zip --query 'FunctionArn' --output text`"
      echo "Created Lambda function $lambda_arn"

  * Later you can update the lambda function if you add or changea plugin by running

        aws lambda update-function-code --function-name github-org-manager --zip-file fileb://github_org_manager.zip

* Determine the SNS topic ARN of the SNS topic containing the GitHub webhook events

      topic_arn="arn:aws:sns:us-west-2:699292812394:github-webhooks-all"

* Update Lambda function resource policy to grant SNS rights to invoke it

      aws lambda add-permission --function-name github-org-manager --statement-id GiveSNSPermissionToInvokeFunction --action lambda:InvokeFunction --principal sns.amazonaws.com --source-arn $topic_arn

* Subscribe the Lambda function to the SNS topic

      aws sns subscribe --topic-arn $topic_arn --protocol lambda --notification-endpoint $lambda_arn

# Plugins

To creat a plugin, add a python module to the `plugins/` directory. The new
module must contain at least two functions, `is_matching` and `act`

Each function must accept two arguments
* `config` : A dictionary containing the `config.yaml` contents
* `message` : A dictionary containing the [GitHub webhook payload](https://developer.github.com/webhooks/#payloads)

The `is_matching` function's return value is used to determine whether or not
the `act` function is called. if `is_matching` returns a [truthy](https://docs.python.org/2/library/stdtypes.html#truth-value-testing)
value then `act` will be called.

The `act` function need not return anything

A minimal plugin would be a file called `plugins/example.py` and would look like

```python
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def is_matching(config, message):
    return ('action' in message and message['action'] == 'added')

def act(config, message):
    logger.info("Hello world")
```