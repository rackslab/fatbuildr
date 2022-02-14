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

import argparse
import sys
import os
import time

from . import FatbuildrCliRun
from ..version import __version__
from ..conf import RuntimeConfCtl
from ..images import ImagesManager
from ..keyring import KeyringManager
from ..builds.manager import ClientBuildsManager
from ..log import logr
from ..protocols import ClientFactory
from ..artefact import ArtefactDefs

logger = logr(__name__)


def progname():
    """Return the name of the program."""
    return os.path.basename(sys.argv[0])


class Fatbuildrctl(FatbuildrCliRun):
    def __init__(self):
        super().__init__()

        parser = argparse.ArgumentParser(
            description='Do something with fatbuildr.'
        )
        parser.add_argument(
            '-v',
            '--version',
            dest='version',
            action='version',
            version='%(prog)s ' + __version__,
        )
        parser.add_argument(
            '--debug',
            dest='debug',
            action='store_true',
            help="Enable debug mode",
        )
        parser.add_argument(
            '-i', '--instance', dest='instance', help="Name of the instance"
        )
        parser.add_argument(
            '--host', dest='host', help="Fatbuildr host", default='local'
        )

        subparsers = parser.add_subparsers(
            help='Action to perform', dest='action', required=True
        )

        # Parser for the images command
        parser_images = subparsers.add_parser(
            'images', help='Manage build images'
        )
        parser_images.add_argument(
            '--create', action='store_true', help='Create the images'
        )
        parser_images.add_argument(
            '--update', action='store_true', help='Update the images'
        )
        parser_images.add_argument(
            '--format',
            help='Manage image and build environment for this format',
        )
        parser_images.add_argument(
            '--force',
            action='store_true',
            help='Force creation of images even they already exist',
        )
        parser_images.add_argument(
            '--create-envs',
            action='store_true',
            help='Create the build environments in the images',
        )
        parser_images.add_argument(
            '--update-envs',
            action='store_true',
            help='Update the build environments in the images',
        )
        parser_images.set_defaults(func=self._run_images)

        # Parser for the keyring command
        parser_keyring = subparsers.add_parser(
            'keyring', help='Manage signing keyring'
        )
        parser_keyring.add_argument(
            '--create', action='store_true', help='Create keyring'
        )
        parser_keyring.add_argument(
            '--show', action='store_true', help='Show keyring information'
        )
        parser_keyring.add_argument(
            '--export', action='store_true', help='Export keyring'
        )
        parser_keyring.set_defaults(func=self._run_keyring)

        # Parser for the build command
        parser_build = subparsers.add_parser('build', help='Submit new build')
        parser_build.add_argument(
            '-a', '--artefact', help='Artefact name', required=True
        )
        parser_build.add_argument(
            '-d', '--distribution', help='Distribution name'
        )
        parser_build.add_argument(
            '-f', '--format', help='Format of the artefact'
        )
        parser_build.add_argument(
            '--derivative',
            help='Distribution derivative',
            default='main',
        )
        parser_build.add_argument(
            '-b',
            '--basedir',
            help='Artefacts definitions directory',
            required=True,
        )
        parser_build.add_argument(
            '-s', '--subdir', help='Artefact subdirectory'
        )
        parser_build.add_argument(
            '-n', '--name', help='Maintainer name', required=True
        )
        parser_build.add_argument(
            '-e', '--email', help='Maintainer email', required=True
        )
        parser_build.add_argument(
            '-m', '--msg', help='Build log message', required=True
        )
        parser_build.add_argument(
            '-w',
            '--watch',
            action='store_true',
            help='Watch build log and wait until its end',
        )
        parser_build.set_defaults(func=self._run_build)

        # Parser for the list command
        parser_list = subparsers.add_parser('list', help='List builds')
        parser_list.add_argument('-p', '--pending', help='List pending builds')
        parser_list.set_defaults(func=self._run_list)

        # Parser for the watch command
        parser_watch = subparsers.add_parser('watch', help='Watch build')
        parser_watch.add_argument('-b', '--build', help='ID of build to watch')
        parser_watch.set_defaults(func=self._run_watch)

        # Parser for the archives command
        parser_archives = subparsers.add_parser(
            'archives', help='List archives'
        )
        parser_archives.set_defaults(func=self._run_archives)

        # Parser for the registry command
        parser_registry = subparsers.add_parser(
            'registry', help='Manage artefact registries'
        )
        parser_registry.add_argument(
            '-d', '--distribution', help='Distribution name', required=True
        )
        parser_registry.set_defaults(func=self._run_registry)

        args = parser.parse_args()

        logger.setup(args.debug)

        self.conf = RuntimeConfCtl()
        self.load(args)

        # run the method corresponding to the provided action
        args.func()

    def load(self, args):
        super().load()

        self.conf.run.action = args.action
        self.conf.run.host = args.host

        # select the default instance from conf if not given in args
        if args.instance is None:
            self.instance = self.conf.run.default_instance
        else:
            self.instance = args.instance

        if args.action == 'images':
            if args.create is True:
                self.conf.run.operation = 'create'
            elif args.update is True:
                self.conf.run.operation = 'update'
            elif args.create_envs is True:
                self.conf.run.operation = 'create_envs'
            elif args.update_envs is True:
                self.conf.run.operation = 'update_envs'
            else:
                print(
                    "An operation on the images must be specified, type '%s images --help' for details"
                    % (progname())
                )
                sys.exit(1)
            if args.format:
                self.conf.run.format = args.format
            else:
                self.conf.run.format = 'all'
            self.conf.run.force = args.force

        elif args.action == 'keyring':
            if args.create is True:
                self.conf.run.operation = 'create'
            elif args.show is True:
                self.conf.run.operation = 'show'
            elif args.export is True:
                self.conf.run.operation = 'export'
            else:
                print(
                    "An operation on the keyring must be specified, type '%s keyring --help' for details"
                    % (progname())
                )
                sys.exit(1)

        elif args.action == 'build':
            self.conf.run.artefact = args.artefact
            if args.distribution:
                self.conf.run.distribution = args.distribution
            if args.format:
                self.conf.run.format = args.format
            self.conf.run.derivative = args.derivative
            self.conf.run.basedir = args.basedir
            if args.subdir:
                self.conf.run.subdir = args.subdir
            else:
                self.conf.run.subdir = self.conf.run.artefact
            self.conf.run.user_name = args.name
            self.conf.run.user_email = args.email
            self.conf.run.build_msg = args.msg
            self.conf.run.watch = args.watch

        elif args.action == 'watch':
            self.conf.run.build = args.build

        elif args.action == 'registry':
            self.conf.run.basedir = args.basedir
            self.conf.run.distribution = args.distribution

        self.conf.dump()

    def _run_images(self):
        logger.debug("running images operation: %s", self.conf.run.operation)

        mgr = ImagesManager(self.conf, self.instance)

        # check if operation is on images and run it
        if self.conf.run.operation == 'create':
            for format in mgr.selected_formats:
                mgr.create(format)
            logger.info("All images have been created")
            return
        elif self.conf.run.operation == 'update':
            for format in mgr.selected_formats:
                mgr.update(format)
            logger.info("All images have been updated")
            return

        # At this stage, the operation is on build environments

        connection = ClientFactory.get(self.conf.run.host)

        for format in mgr.selected_formats:

            distributions = connection.pipelines_format_distributions(
                self.instance, format
            )
            if not distributions:
                logger.info("No distribution defined for %s image", format)
            envs = []
            for distribution in distributions:
                env = connection.pipelines_distribution_environment(
                    self.instance, distribution
                )
                if env is not None:
                    envs.append(env)
            logger.debug(
                "Build environments found for format %s: %s", format, envs
            )

            if self.conf.run.operation == 'create_envs':
                mgr.create_envs(format, envs)
            elif self.conf.run.operation == 'update_envs':
                mgr.update_envs(format, envs)

    def _run_keyring(self):
        logger.debug(
            "running keyring operation: %s" % (self.conf.run.operation)
        )
        mgr = KeyringManager(self.conf)
        keyring = mgr.keyring(self.instance)
        if self.conf.run.operation == 'create':
            connection = ClientFactory.get(self.conf.run.host)
            instance = connection.instance(self.instance)
            keyring.create(instance.userid)
        elif self.conf.run.operation == 'show':
            keyring.show()
        elif self.conf.run.operation == 'export':
            print(keyring.export())

    def _run_build(self):
        logger.debug(
            "running build for artefact: %s instance: %s"
            % (self.conf.run.artefact, self.instance)
        )

        connection = ClientFactory.get(self.conf.run.host)

        path = os.path.join(self.conf.run.basedir, self.conf.run.subdir)
        defs = ArtefactDefs(path)

        if self.conf.run.distribution:
            fmt = connection.pipelines_distribution_format(
                self.instance, self.conf.run.distribution
            )
            # if format is also given, check it matches
            if self.conf.run.format and self.conf.run.format != fmt:
                logger.error(
                    "Specified format %s does not match the format "
                    "of the specified distribution %s"
                    % (self.conf.run.format, self.conf.run.distribution)
                )
                sys.exit(1)
            self.conf.run.format = fmt
        elif not self.conf.run.format:
            # distribution and format have not been specified, check format
            # supported by the artefact.
            fmts = defs.supported_formats
            # check if there is not more than one supported format for this
            # artefact
            if len(fmts) > 1:
                logger.error(
                    "There is more than one supported format for "
                    "artefact %s, at least the format must be "
                    "specified" % (self.conf.run.artefact)
                )
                sys.exit(1)
            if fmts:
                self.conf.run.format = fmts[0]
                logger.debug(
                    "Format %s has been selected for artefact %s"
                    % (self.conf.run.format, self.conf.run.artefact)
                )

        if not self.conf.run.format:
            logger.error(
                "Unable to define format of artefact %s, either the "
                "distribution or the format must be specified"
                % (self.conf.run.artefact)
            )
            sys.exit(1)
        elif not self.conf.run.distribution:
            dists = connection.pipelines_format_distributions(
                self.instance, self.conf.run.format
            )
            # check if there is not more than one distribution for this format
            if len(dists) > 1:
                logger.error(
                    "There is more than one distribution for the "
                    "format %s in pipelines definition, the "
                    "distribution must be specified" % (self.conf.run.format)
                )
                sys.exit(1)
            self.conf.run.distribution = dists[0]
            logger.debug(
                "Distribution %s has been selected for format %s"
                % (self.conf.run.distribution, self.conf.run.format)
            )

        # check artefact accepts this format
        if self.conf.run.format not in defs.supported_formats:
            logger.error(
                "Format %s is not accepted by artefact %s",
                self.conf.run.format,
                self.conf.run.artefact,
            )
            sys.exit(1)

        # check artefact accepts this derivative
        if self.conf.run.derivative not in defs.derivatives:
            logger.error(
                "Derivative %s is not accepted by artefact %s",
                self.conf.run.derivative,
                self.conf.run.artefact,
            )
            sys.exit(1)

        # check format is accepted for this derivative
        if self.conf.run.format not in connection.pipelines_derivative_formats(
            self.instance, self.conf.run.derivative
        ):
            logger.error(
                "Derivative %s does not accept format %s",
                self.conf.run.derivative,
                self.conf.run.format,
            )
            sys.exit(1)

        # Get the build environment corresponding to this distribution
        env = connection.pipelines_distribution_environment(
            self.instance, self.conf.run.distribution
        )
        logger.debug(
            "Build environment selected for distribution %s: %s",
            self.conf.run.distribution,
            env,
        )

        mgr = ClientBuildsManager(self.conf)

        try:
            request = mgr.request(
                self.instance,
                self.conf.run.distribution,
                self.conf.run.derivative,
                env,
                self.conf.run.format,
                self.conf.run.build_msg,
            )
            build_id = connection.submit(request)
        except RuntimeError as err:
            logger.error("Error while submitting build: %s" % (err))
            sys.exit(1)
        logger.info("Build %s submitted" % (build_id))
        if self.conf.run.watch:
            self._watch_build(build_id)

    def _run_list(self):
        logger.debug("running list")
        connection = ClientFactory.get(self.conf.run.host)
        try:
            _running = connection.running()
            if _running:
                print("Running build:")
                _running.report()
            else:
                print("No running build")

            _queue = connection.queue()
            if _queue:
                print("Pending build submissions:")
                for _build in _queue:
                    _build.report()

        except RuntimeError as err:
            logger.error("Error while listing builds: %s" % (err))
            sys.exit(1)

    def _watch_build(self, build_id):
        connection = ClientFactory.get(self.conf.run.host)
        try:
            build = connection.get(build_id)
        except RuntimeError as err:
            logger.error(err)
            sys.exit(1)

        warned_pending = False
        # if build is pending, wait
        while build.state == 'pending':
            if not warned_pending:
                logger.info(
                    "Build %s is pending, waiting for the build to start."
                    % (build.id)
                )
                warned_pending = True
            time.sleep(1)
            # poll build state again
            build = connection.get(build_id)
        try:
            for line in connection.watch(build):
                print(line, end='')
        except KeyboardInterrupt:
            # Leave gracefully after a keyboard interrupt (eg. ^c)
            logger.debug("Received keyboard interrupt, leaving.")
        except BrokenPipeError:
            # Stop if hit a broken pipe. It could happen when watch is given to
            # `head` for example.
            pass

    def _run_watch(self):
        self._watch_build(self.conf.run.build)

    def _run_archives(self):
        connection = ClientFactory.get(self.conf.run.host)
        archives = connection.archives()
        if not archives:
            print("No archive found")
            return
        print("Build archives:")
        for archive in archives:
            archive.report()

    def _run_registry(self):
        connection = ClientFactory.get(self.conf.run.host)
        _fmt = connection.pipelines_distribution_format(
            self.instance, self.conf.run.distribution
        )
        artefacts = connection.artefacts(
            self.instance, _fmt, self.conf.run.distribution
        )
        if not artefacts:
            print(
                "No artefact found in %s distribution %s"
                % (_fmt, self.conf.run.distribution)
            )
            return
        print(
            "Artefacts found for %s distribution %s:"
            % (_fmt, self.conf.run.distribution)
        )
        for artefact in artefacts:
            artefact.report()
