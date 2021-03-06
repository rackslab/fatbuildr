#!/usr/bin/env python3
#
# Copyright (C) 2021 Rackslab
#
# This file is part of Fatbuildr.
#
# Fatbuildr is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Fatbuildr is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Fatbuildr.  If not, see <https://www.gnu.org/licenses/>.

import threading
import logging

from .formatters import DaemonFormatter, TTYFormatter
from .filters import ThreadFilter


class Log(logging.Logger):
    def __init__(self, name):
        super().__init__(name)

    def has_debug(self):
        return self.isEnabledFor(logging.DEBUG)

    def formatter(self, debug):
        if self.name in [
            'fatbuildr.cli.fatbuildrd',
            'fatbuildr.cli.fatbuildrweb',
            'fatbuildr.wsgi',
        ]:
            return DaemonFormatter(debug)
        elif self.name == 'fatbuildr.cli.fatbuildrctl':
            return TTYFormatter(debug)
        else:
            raise RuntimeError(
                f"Unable to define log formatter for module {self.name}"
            )

    def setup(self, debug: bool, fulldebug: bool):
        if debug:
            logging_level = logging.DEBUG
        else:
            logging_level = logging.INFO

        _root_logger = logging.getLogger()
        _root_logger.setLevel(logging_level)
        _handler = logging.StreamHandler()
        _handler.setLevel(logging_level)
        _formatter = self.formatter(debug)
        _handler.setFormatter(_formatter)
        if not fulldebug:
            _filter = logging.Filter('fatbuildr')  # filter out all libs logs
            _handler.addFilter(_filter)
        _root_logger.addHandler(_handler)

    def ensure_debug(self):
        _root_logger = logging.getLogger()
        # do nothing if already at debug
        if _root_logger.isEnabledFor(logging.DEBUG):
            return
        _root_logger.setLevel(level=logging.DEBUG)
        _formatter = self.formatter(debug=True)
        # set formatter and log level for all handlers
        for handler in _root_logger.handlers:
            handler.setLevel(logging.DEBUG)
            handler.setFormatter(_formatter)

    def ensure_fulldebug(self):
        """Removes all filters in all handlers of root logger."""
        _root_logger = logging.getLogger()
        for handler in _root_logger.handlers:
            for filter in handler.filters:
                handler.removeFilter(filter)

    def add_thread_handler(self, handler):
        """Attach given handler the root logger restricted with current thread
        filter."""
        _filter = ThreadFilter(threading.current_thread().name)
        handler.addFilter(_filter)
        logging.getLogger().addHandler(handler)

    def remove_handler(self, handler):
        """Remove the given handler from the root logger."""
        logging.getLogger().removeHandler(handler)

    def mute_handler(self, handler):
        """Mute the given handler by removing it from the root logger."""
        logging.getLogger().removeHandler(handler)

    def unmute_handler(self, handler):
        """Unmute the given handler by attaching it to the root logger."""
        logging.getLogger().addHandler(handler)


def logr(name):
    """Instanciate Log by setting logging.setLoggerClass using
    logging.getLogger() so Python logging module can do all its Loggers
    registration."""
    logging.setLoggerClass(Log)
    return logging.getLogger(name)
