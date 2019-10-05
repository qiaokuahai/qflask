from .wrappers import Request, Response
from .helpers import _endpoint_from_view_func
from ._compat import string_types, text_type
from .globals import request
from werkzeug.routing import Map, Rule, RequestRedirect, BuildError
from .globals import _test_sep_stack
from .ctx import RequestContext


class Flask(object):
    request_class = Request
    response_class = Response
    url_rule_class = Rule

    def __init__(self):
        self.url_map = Map()
        self.view_functions = {}
        self.debug = None
        self.config = {}

    def full_dispatch_request(self):
        try:
            rv = self.dispatch_request()
        except Exception as e:
            rv = self.handle_user_exception(e)
        return self.finalize_request(rv)

    def request_context(self, environ):
        return RequestContext(self, environ)

    def dispatch_request(self):
        req = _test_sep_stack.pop()
        req = req.request
        rule = req.url_rule
        # if we provide automatic options for this URL and the
        # request came with the OPTIONS method, reply automatically
        if getattr(rule, 'provide_automatic_options', False) \
           and req.method == 'OPTIONS':
            return self.make_default_options_response()
        # otherwise dispatch to the handler for that endpoint
        return self.view_functions[rule.endpoint](**req.view_args)

    def finalize_request(self, rv):
        response = self.make_response(rv)
        return response

    def wsgi_app(self, environ, start_response):
        # 暂时不考虑线程隔离
        ctx = self.request_context(environ)
        _test_sep_stack.append(ctx)
        try:
            try:
                response = self.full_dispatch_request()
            except Exception as e:
                raise
            return response(environ, start_response)
        finally:
            pass

    def route(self, rule, **options):
        def decorator(f):
            endpoint = options.pop('endpoint', None)
            self.add_url_rule(rule, endpoint, f, **options)
            return f
        return decorator

    def add_url_rule(self, rule, endpoint=None, view_func=None, **options):
        # 暂不考虑代码健壮性
        if endpoint is None:
            endpoint = _endpoint_from_view_func(view_func)
        options['endpoint'] = endpoint
        methods = options.pop('methods', None)

        rule = self.url_rule_class(rule, methods=methods, **options)

        self.url_map.add(rule)
        if view_func is not None:
            # 同一个endpoint不能重复
            old_func = self.view_functions.get(endpoint)
            if old_func is not None and old_func != view_func:
                raise AssertionError('View function mapping is overwriting an '
                                     'existing endpoint function: %s' % endpoint)
            self.view_functions[endpoint] = view_func

    def make_response(self, rv):
        status_or_headers = headers = None
        if isinstance(rv, tuple):
            rv, status_or_headers, headers = rv + (None,) * (3 - len(rv))

        if rv is None:
            raise ValueError('View function did not return a response')

        if isinstance(status_or_headers, (dict, list)):
            headers, status_or_headers = status_or_headers, None

        if not isinstance(rv, self.response_class):
            if not isinstance(rv, dict):
                raise
            rv = self.response_class(rv, headers=headers,
                                     status=status_or_headers)

        if status_or_headers is not None:
            if isinstance(status_or_headers, string_types):
                rv.status = status_or_headers
            else:
                rv.status_code = status_or_headers
        if headers:
            rv.headers.extend(headers)

        return rv

    def create_url_adapter(self, request):
        """Creates a URL adapter for the given request.  The URL adapter
        is created at a point where the request context is not yet set up
        so the request is passed explicitly.

        .. versionadded:: 0.6

        .. versionchanged:: 0.9
           This can now also be called without a request object when the
           URL adapter is created for the application context.
        """
        server_name = self.config.get("SERVER_NAME")
        if request is not None:
            return self.url_map.bind_to_environ(request.environ,
                                                server_name=server_name)
        # We need at the very least the server name to be set for this
        # to work.
        if server_name is not None:
            return self.url_map.bind(
                self.config['SERVER_NAME'],
                script_name=self.config['APPLICATION_ROOT'] or '/',
                url_scheme=self.config['PREFERRED_URL_SCHEME'])

    def run(self, host=None, port=None, debug=None, **options):
        from werkzeug.serving import run_simple
        if host is None:
            host = '127.0.0.1'
        if port is None:
            port = 5000
        if debug is not None:
            self.debug = bool(debug)
        options.setdefault('use_reloader', self.debug)
        options.setdefault('use_debugger', self.debug)
        try:
            run_simple(host, port, self, **options)
        finally:
            self._got_first_request = False

    def __call__(self, environ, start_response):
        return self.wsgi_app(environ, start_response)
