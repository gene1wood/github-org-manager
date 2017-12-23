#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import agithub.GitHub  # pip install agithub


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def is_matching(config, message):
    """

    :param config:
    :param message:
    :return:
    """

    plugin_enabled = True
    if not plugin_enabled:
        return False
    if ('action' in message and message['action'] == 'added'
            and 'repository' in message):
        # MemberEvent
        # https://developer.github.com/v3/activity/events/types/#memberevent
        if ('member' in message and 'sender' in message
                and message['member']['login'] == message['sender']['login']):
            # The user added themselves as a collaborator to a repository
            # This could either be a repository transfer of a user's personal
            # repo into the org, or it could be an org owner adding themselves
            # as a collaborator to a repo

            # Normally an org owner adding themselves as a collaborator to a
            # repo would grant them `write` permission to that repo in addition
            # to the `admin` rights that they inherit from being an org owner.

            # An org owner might do this in advance of demoting themselves from
            # org owner to org member so as to retain `write` access to a given
            # repo.

            # This plugin will automatically elevate them from having `write`
            # access to the repo to `admin` access to the repo.

            # Since GitHub doesn't permit a user that has `admin` access to a
            # repo to demote themselves to having only `read` or `write`, if
            # that ex-org-owner wanted to retain *only* `write` or `read`
            # access to a repo and not `admin`, they would need a different
            # repo admin or org owner to subsequently demote them from being a
            # repo admin to a repo writer or reader.

            # Until GitHub creates a webhook indicating a repo transfer has
            # occurred, this corner case will be a problem due to this plugin.
            logger.info(
                "Detected a GitHub MemberEvent webhook with a sender and "
                "member login of '{login}' indicating either that {repo} is a "
                "repo, newly transferred into the organization, or an org "
                "owner has added themselves as a collaborator to the existing"
                "organization repo {repo}".format(
                    login=message['member']['login'],
                    repo=message['repository']['full_name']))
            return True
    return False


def act(config, message):
    """Given a GitHub webhook event of a newly transferred repo, grant the user
    that transferred the repo in admin rights on that repo

    :param config:
    :param message:
    :return:
    """
    repo_full_name = message['repository']['full_name']
    owner = message['repository']['owner']['login']
    repo = message['repository']['name']
    user = message['member']['login']

    ag = agithub.GitHub.GitHub(token=config['github_token'])
    status, data = ag.repos[owner][repo].collaborators[user].permission.get()
    if status < 200 or status >= 300:
        logger.error("Unexpected error %s : %s" % (status, data))
        return
    old_permission = data['permission']
    if old_permission == 'admin':
        logger.error("User %s already has %s permission in the repo %s. No "
                     "action taken" %
                     (user, old_permission, repo_full_name))
        return

    # https://developer.github.com/v3/repos/collaborators/#add-user-as-a-collaborator
    ag.repos[owner][repo].collaborators[user].put(body={'permission': 'admin'})
    status, data = ag.repos[owner][repo].collaborators[user].permission.get()
    logger.info("User %s permissions in the repo %s have been changed from %s "
                "to %s" % (user, repo_full_name, old_permission,
                           data['permission']))
