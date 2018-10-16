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
IGNORE_CONTEXT_GLOBS = ["mergify*"]


async def handle(request):
    event = request['github_event']
    if event != 'status':
        LOGGER.info("ignoring %s event" % event)
        return web.Response(text="ignoring %s event" % event)
    body = await request.read()
    decoded_body = json.loads(body.decode('utf8'))
    repo = decoded_body['repository']['name']
    owner = decoded_body['repository']['owner']['login']
    sha = decoded_body['sha']
    async with ClientSession(auth=AUTH, timeout=TIMEOUT) as session:
        topics = await h.github_get_repo_topics(session, owner, repo)
        if ('integration-level-2' not in topics) and \
                ('integration-level-3' not in topics) and \
                ('integration-level-4' not in topics) and \
                ('integration-level-5' not in topics):
            LOGGER.info("ignoring repo %s/%s because "
                        "of its integration level" % (owner, repo))
            return web.Response(text="Done")
        status = await \
            h.github_get_status(session, owner, repo, sha,
                                ignore_context_globs=IGNORE_CONTEXT_GLOBS)
        if status == 'pending':
            new_status_label = "Status: Pending"
        elif status in ('failure', 'error'):
            new_status_label = "Status: Revision Needed"
        elif status == 'success':
            new_status_label = "Status: Review Needed"
        else:
            LOGGER.warning("unknown status: %s" % status)
            return web.Response(text="Done")
        prs = await h.github_get_open_prs_by_sha(session, owner, repo, sha)
        for number in prs:
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
