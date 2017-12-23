#!/usr/bin/python
# -*- coding: utf-8 -*-

import json
import traceback
import logging
from datetime import datetime
import boto3
import yaml  # pip install PyYAML
from dateutil import tz  # sudo pip install python-dateutil
import glob
import os.path
import importlib

TIME_ZONE = tz.gettz('America/Los_Angeles')


def logging_local_time_converter(secs):
    """Convert a UTC epoch time to a local timezone time for use as a logging
    Formatter

    :param secs: Time expressed in seconds since the epoch
    :return: a time.struct_time 8-tuple
    """
    from_zone = tz.gettz('UTC')
    to_zone = TIME_ZONE
    utc = datetime.fromtimestamp(secs)
    utc = utc.replace(tzinfo=from_zone)
    pst = utc.astimezone(to_zone)
    return pst.timetuple()


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if len(logging.getLogger().handlers) == 0:
    logger.addHandler(logging.StreamHandler())
logging.getLogger().setLevel(logging.INFO)
# fmt = "[%(levelname)s]   %(asctime)s.%(msecs)dZ  %(aws_request_id)s  %(message)s"
fmt = "[%(levelname)s] %(asctime)s %(message)s\n"
# datefmt = "%Y-%m-%dT%H:%M:%S"
datefmt = "%m/%d/%Y %H:%M:%S {}".format(TIME_ZONE.tzname(datetime.now()))
formatter = logging.Formatter(fmt=fmt, datefmt=datefmt)
formatter.converter = logging_local_time_converter
logging.getLogger().handlers[0].setFormatter(formatter)

# Disable boto logging
logging.getLogger('boto3').setLevel(logging.CRITICAL)
logging.getLogger('botocore').setLevel(logging.CRITICAL)
logging.getLogger('requests').setLevel(logging.CRITICAL)
logging.getLogger('urllib3').setLevel(logging.CRITICAL)


def get_event_type(event):
    """Determine where an event originated from based on it's contents

    :param event: A dictionary of metadata for an event
    :return: Either the name of the source of the event or False if no
    source can be determined
    """
    if 'source' in event and event['source'] == 'aws.events':
        # CloudWatch Scheduled Event
        return 'cloudwatch'
    elif ('Records' in event and
            type(event['Records']) == list and
            len(event['Records']) > 0 and
            type(event['Records'][0]) == dict):
        if ('eventSource' in event['Records'][0]
                and event['Records'][0]['eventSource'] == 'aws:ses'):
            # SES received email
            # Note the lower case 'eventSource'
            return 'ses'
        elif ('EventSource' in event['Records'][0]
              and event['Records'][0]['EventSource'] == 'aws:sns'):
            # SNS published message
            # Note the upper case 'EventSource'
            return 'sns'
    else:
        return False


class Alerter:
    def __init__(self, config, event, context):
        self.config = config
        self.event = event
        self.context = context

    def alert(self, message=''):
        """Publish an alert to SNS

        :param str message: The message to send in the alert
        :return: Dictionary containing the MessageId of the published SNS
        message
        """
        if 'alert_sns_topic_arn' not in self.config:
            return

        if len(message) > 0:
            message += "\n"
        logger.error('Alerting on events %s' % self.event)
        message += "\n\n"
        message += json.dumps(self.event, indent=4)
        message += "\nLog stream is : %s" % self.context.log_stream_name
        subject = 'Alert from Birch Girder'
        client = boto3.client(
            'sns', region_name=self.config['alert_sns_region'])
        client.publish(
            TopicArn=self.config['alert_sns_topic_arn'],
            Message=message,
            Subject=subject
        )


class EventHandler:
    def __init__(self, config, event, context):
        """

        :param config:
        :param event:
        :param context:
        """
        self.config = config
        self.event = event
        self.context = context
        self.alerter = Alerter(self.config, self.event, self.context)

    def process_event(self):
        """Determine event type and call the associated processor

        :return:
        """
        try:
            event_type = get_event_type(self.event)
            if event_type == 'sns':
                self.github_hook()
            else:
                logger.error("Unable to determine message type from event "
                             "%s" % self.event)
        except Exception as e:
            self.alerter.alert(
                "Uncaught exception thrown\n%s\n%s\n%s" % (
                    e.__class__,
                    e,
                    traceback.format_exc()))
            raise

    def github_hook(self):
        """

        :return:
        """

        sns_message = json.loads(self.event['Records'][0]['Sns']['Message'])

        # https://mozilla-version-control-tools.readthedocs.io/en/latest/githubwebhooks.html
        # https://github.com/mozilla-platform-ops/devservices-aws/tree/master/githubwebhooks
        # Extract the GitHub webhook from the custom 'body' wrapper added by
        # the githubwebhooks API Gateway/Lambda function
        message = sns_message['body']

        all_plugins = [
            importlib.import_module('plugins.%s' % os.path.basename(x)[:-3])
            for x in glob.glob("plugins/*.py")
            if os.path.isfile(x) and not x.endswith('__init__.py')]
        # Filter out any plugins missing the is_matching and act functions
        plugin_list = [
            x for x in all_plugins
            if hasattr(x, 'is_matching') and hasattr(x, 'act')]

        # For each plugin which matches this message, trigger the act function
        for plugin in plugin_list:
            if plugin.is_matching(self.config, message):
                plugin.act(self.config, message)


def lambda_handler(event, context):
    """Given an event determine if it's an SNS delivered GitHub webhook and
    process it.

    :param event: A dictionary of metadata for an event
    :param context: The AWS Lambda context object
    :return:
    """
    logger.debug('got event {}'.format(event))
    with open('config.yaml') as f:
        config = yaml.load(f.read())
    handler = EventHandler(config, event, context)
    handler.process_event()


def main():
    """

    :return:
    """
    event = {}
    context = type('context', (), {'log_stream_name': None})()
    lambda_handler(event, context)


if __name__ == '__main__':
    main()
