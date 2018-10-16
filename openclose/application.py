import os
from mflog import getLogger
import json
from aiohttp import web, ClientSession, BasicAuth, ClientTimeout

import aiohttp_github_helpers as h

GITHUB_USER = os.environ['GITHUB_USER']
GITHUB_PASS = os.environ['GITHUB_PASS']
GITHUB_SECRET = os.environ['GITHUB_SECRET'].encode('utf8')
LOGGER = getLogger("github_webhook_pr_labelling")
TIMEOUT = ClientTimeout(total=20)
AUTH = BasicAuth(GITHUB_USER, GITHUB_PASS)


async def handle(request):
    event = request['github_event']
    if event != 'pull_request':
        LOGGER.info("ignoring %s event" % event)
        return web.Response(text="ignoring %s event" % event)
    body = await request.read()
    decoded_body = json.loads(body.decode('utf8'))
    action = decoded_body['action']
    if action not in ["opened", "closed", "reopened"]:
        LOGGER.info("ignoring %s action" % action)
        return web.Response(text="ignoring %s action" % action)
    repo = decoded_body['repository']['name']
    owner = decoded_body['repository']['owner']['login']
    number = decoded_body['pull_request']['number']
    async with ClientSession(auth=AUTH, timeout=TIMEOUT) as session:
        if action == 'closed':
            new_status_label = "Status: Closed"
        elif action == 'opened':
            new_status_label = "Status: Pending"
        elif action == 'reopened':
            new_status_label = "Status: Review Needed"
        else:
            LOGGER.warning("unknown action: %s" % action)
            return web.Response(text="Done")
        topics = await h.github_get_repo_topics(session, owner, repo)
        if ('integration-level-2' not in topics) and \
                ('integration-level-3' not in topics) and \
                ('integration-level-4' not in topics) and \
                ('integration-level-5' not in topics):
            LOGGER.info("ignoring repo %s/%s because "
                        "of its integration level" % (owner, repo))
            return web.Response(text="Done")
        await h.github_replace_labels_with(session, owner, repo, number,
                                           "Status:*", new_status_label,
                                           True)
    return web.Response(text="Done")

check_signature_middleware = \
    h.github_check_signature_middleware_factory(GITHUB_SECRET)
app = web.Application(middlewares=[check_signature_middleware,
                                   h.github_check_github_event])
app.router.add_get('/{tail:.*}', handle)
app.router.add_post('/{tail:.*}', handle)
