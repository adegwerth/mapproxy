# This file is part of the MapProxy project.
# Copyright (C) 2010 Omniscale <http://omniscale.de>
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
# 
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
The WSGI application.
"""
from __future__ import with_statement
import re
import os
import sys

from mapproxy.request import Request
from mapproxy.response import Response
from mapproxy.config import base_config, load_base_config, abspath
from mapproxy.config.loader import load_services

def app_factory(global_options, mapproxy_conf, **local_options):
    """
    Paster app_factory.
    """
    conf = global_options.copy()
    conf.update(local_options)
    log_conf = conf.get('log_conf', None)
    reload_files = conf.get('reload_files', None)
    if reload_files is not None:
        init_paster_reload_files(reload_files)

    load_base_config(mapproxy_conf)
    
    init_logging_system(log_conf=log_conf)
    
    return make_wsgi_app(mapproxy_conf)

def init_paster_reload_files(reload_files):
    file_patterns = reload_files.split('\n')
    file_patterns.append(os.path.join(os.path.dirname(__file__), 'defaults.yaml'))
    init_paster_file_watcher(file_patterns)

def init_paster_file_watcher(file_patterns):
    from glob import glob
    for pattern in file_patterns:
        files = glob(pattern)
        _add_files_to_paster_file_watcher(files)
    
def _add_files_to_paster_file_watcher(files):
    import paste.reloader
    for file in files:
        paste.reloader.watch_file(file)
    
def init_logging_system(log_conf=None):
    import logging.config
    try:
        import cloghandler # adds CRFHandler to log handlers
        cloghandler.ConcurrentRotatingFileHandler #disable pyflakes warning
    except ImportError:
        pass
    if log_conf is None:
        log_conf = base_config().log_conf
    if log_conf:
        log_conf = abspath(log_conf)
        if not os.path.exists(log_conf):
            print >>sys.stderr, 'ERROR: log configuration %s not found.' % log_conf
            return
        logging.config.fileConfig(log_conf, dict(here=base_config().conf_base_dir))

def init_null_logging():
    import logging
    class NullHandler(logging.Handler):
        def emit(self, record):
            pass
    logging.getLogger().addHandler(NullHandler())

def make_wsgi_app(services_conf=None):
    """
    Create a ProxyApp with the given services conf. Also initializes logging.
    
    :param services_conf: the file name of the services.yaml configuration,
                          if ``None`` the default is loaded.
    """
    services = load_services(services_conf)
    return MapProxyApp(services)

class MapProxyApp(object):
    """
    The MapProxy WSGI application.
    """
    handler_path_re = re.compile('^/(\w+)')
    def __init__(self, services):
        self.handlers = {}
        for service in services.itervalues():
            for name in service.names:
                self.handlers[name] = service
    
    def __call__(self, environ, start_response):
        resp = None
        req = Request(environ)
        
        match = self.handler_path_re.match(req.path)
        if match:
            handler_name = match.group(1)
            if handler_name in self.handlers:
                try:
                    resp = self.handlers[handler_name].handle(req)
                except Exception:
                    if base_config().debug_mode:
                        raise
                    else:
                        import traceback
                        traceback.print_exc(file=environ['wsgi.errors'])
                        resp = Response('internal error', status=500)
        if resp is None:
            resp = Response('not found', mimetype='text/plain', status=404)
        return resp(environ, start_response)
