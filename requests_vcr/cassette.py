import io
import json
import mimetools
from requests.models import PreparedRequest, Response
from requests.structures import CaseInsensitiveDict
from requests.packages.urllib3 import HTTPResponse


def serialize_prepared_request(request, method):
    return {
        'body': request.body,
        'headers': dict(request.headers),
        'method': request.method,
        'url': request.url,
    }


def deserialize_prepared_request(serialized):
    p = PreparedRequest()
    p.body = serialized['body']
    p.headers = CaseInsensitiveDict(serialized['headers'])
    p.method = serialized['method']
    p.url = serialized['url']
    return p


def serialize_response(response, method):
    return {
        'content': response.content,
        'encoding': response.encoding,
        'headers': dict(response.headers),
        'status_code': response.status_code,
        'url': response.url,
    }


def deserialize_response(serialized):
    r = Response()
    r.encoding = serialized['encoding']
    r.headers = CaseInsensitiveDict(serialized['headers'])
    r.url = serialized['url']
    r.status_code = serialized['status_code']
    add_urllib3_response(serialized, r)
    return r


def add_urllib3_response(serialized, response):
    body = io.StringIO(serialized['content'])
    h = HTTPResponse(
        body,
        status=response.status_code,
        headers=response.headers,
        preload_content=False,
        original_response=MockHTTPResponse(response.headers)
    )
    response.raw = h


class Cassette(object):

    """The Cassette object abstracts how requests are saved.

    Example usage::

        c = Cassette('vcr/cassettes/httpbin.json', 'json', 'w+b')
        r = requests.get('https://httpbin.org/get')
        c.save(r)

    """

    def __init__(self, cassette_name, serialize, mode='rb'):
        self.cassette_name = cassette_name
        self.serialize_format = serialize
        self.recorded_response = None
        self.fd = open(cassette_name, mode)
        self.serialized = {}

    def as_response(self):
        if not self.recorded_response:
            self.load_serialized_data()
            self.recorded_response = self.deserialize(self.serialized)
        return self.recorded_response

    def deserialize(self, serialized_data):
        r = deserialize_response(serialized_data['response'])
        r.request = deserialize_prepared_request(serialized_data['request'])
        return r

    def is_empty(self):
        try:
            self.as_response()
        except ValueError:
            return True
        else:
            return False

    def load_serialized_data(self):
        if not self.serialized:
            self.serialized = json.load(self.fd)

    def match(self, request, match_options):
        if not isinstance(match_options, list):
            raise ValueError('match_requests_on must be a list of strings')

        def _map_match(opt):
            match_map = {'uri': 'url'}
            return match_map.get(opt, opt)

        self.load_serialized_data()
        serialized_request = self.serialized['request']
        for opt in match_options:
            opt = _map_match(opt)
            if not serialized_request[opt] == getattr(request, opt):
                return False

        return True

    def save(self, response):
        self.recorded_response = response
        serialized = self.serialize(response)
        json.dump(serialized, self.fd)
        # Flush the file so that people can inspect files immediately (if they
        # so please)
        self.fd.flush()

    def serialize(self, response):
        return {
            'request': serialize_prepared_request(response.request,
                                                  self.serialize_format),
            'response': serialize_response(response, self.serialize_format),
        }


class MockHTTPResponse(object):
    def __init__(self, headers):
        h = ["%s: %s" % (k, v) for (k, v) in headers.items()]
        h = io.StringIO('\r\n'.join(h) or None)
        self.msg = mimetools.Message(h)

    def isclosed(self):
        return False