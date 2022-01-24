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

import os
import subprocess
import glob
import shutil
import re

import createrepo_c as cr

from .keyring import KeyringManager
from .templates import Templeter
from .log import logr

logger = logr(__name__)


class Registry(object):
    """Abstract Registry class, parent of all specific Registry classes."""

    def __init__(self, conf, instance, distribution):
        self.conf = conf
        self.instance_dir = os.path.join(conf.dirs.repos, instance)
        self.distribution = distribution

    def publish(self, build):
        raise NotImplementedError


class RegistryDeb(Registry):
    """Registry for Deb format (aka. APT repository)."""

    def __init__(self, conf, instance, distribution):
        super().__init__(conf, instance, distribution)
        self.keyring = KeyringManager(conf, instance)
        self.keyring.load()

    @property
    def path(self):
        return os.path.join(self.instance_dir, 'deb')

    def publish(self, build):
        """Publish both source and binary package in APT repository."""

        logger.info("Publishing Deb packages for %s in distribution %s" \
                    % (build.name, build.distribution))

        # load reprepro distributions template
        dists_tpl_path = os.path.join(self.conf.registry.conf,
                                      'apt', 'distributions.j2')
        dists_path = os.path.join(self.path, 'conf', 'distributions')

        # create parent directory recursively, if not present
        if not os.path.exists(os.path.dirname(dists_path)):
            os.makedirs(os.path.dirname(dists_path))

        # generate reprepro distributions file
        logger.debug("Generating distribution file %s" % (dists_path))
        with open(dists_path, 'w+') as fh:
            fh.write(Templeter.frender(dists_tpl_path,
                       distributions=[build.distribution],
                       key=self.keyring.masterkey.subkey.fingerprint,
                       instance=build.source))

        # Load keyring in agent so repos are signed with new packages
        self.keyring.load_agent()

        # Check packages are not already present in this distribution of the
        # repository with this version before trying to publish them, or fail
        # when it is the case.
        logger.debug("Checking if package %s is already present in "
                     "distribution %s" % (build.name, build.distribution))
        cmd = ['reprepro', '--basedir', self.path,
               '--list-format', '${version}',
               'list', build.distribution, build.name ]
        logger.debug("run cmd: %s" % (' '.join(cmd)))
        repo_list = subprocess.run(cmd, capture_output=True)

        if repo_list.stdout.decode() == build.fullversion:
            raise RuntimeError("package %s already present in distribution %s "
                               "with version %s" \
                               % (build.name,
                                  build.distribution,
                                  build.fullversion))

        changes_glob = os.path.join(build.place, '*.changes')
        for changes_path in glob.glob(changes_glob):
            # Skip source changes, source package is published in repository as
            # part of binary changes.
            if changes_path.endswith('_source.changes'):
                continue
            logger.debug("Publishing deb changes file %s" % (changes_path))
            cmd = ['reprepro', '--verbose', '--basedir', self.path,
                   'include', build.distribution, changes_path ]
            build.runcmd(cmd, env={'GNUPGHOME': self.keyring.homedir})

    def artefacts(self):
        """Returns the list of artefacts in deb repository."""
        artefacts = []
        cmd = ['reprepro', '--basedir', self.path,
               '--list-format', '${package}|${$architecture}|${version}\n',
               'list', self.distribution ]
        repo_list_proc = subprocess.run(cmd, capture_output=True)
        lines = repo_list_proc.stdout.decode().strip().split('\n')
        for line in lines:
            (name, arch, version) = line.split('|')
            artefacts.append(RegistryArtefact(name, arch, version))
        return artefacts


class RegistryRpm(Registry):
    """Registry for Rpm format (aka. yum/dnf repository)."""

    def __init__(self, conf, instance, distribution):
        super().__init__(conf, instance, distribution)

    @property
    def path(self):
        return os.path.join(self.instance_dir, 'rpm', self.distribution)

    @property
    def pkg_dir(self):
        return os.path.join(self.path, 'Packages')

    def _mk_missing_repo_dirs(self):
        """Create pkg_dir if it does not exists, considering pkg_dir is a
           subdirectory of repo_dir."""
        if not os.path.exists(self.pkg_dir):
            logger.info("Creating missing package directory %s" \
                        % (self.pkg_dir))
            os.makedirs(self.pkg_dir)

    def publish(self, build):
        """Publish RPM (including SRPM) in yum/dnf repository."""

        logger.info("Publishing RPM packages for %s in distribution %s" \
                    % (build.name, build.distribution))

        self._mk_missing_repo_dirs()

        rpm_glob = os.path.join(build.place, '*.rpm')
        for rpm_path in glob.glob(rpm_glob):
            logger.debug("Copying RPM %s to %s" % (rpm_path, self.pkg_dir))
            shutil.copy(rpm_path, self.pkg_dir)

        logger.debug("Updating metadata of RPM repository %s" % (self.path))
        cmd = [ 'createrepo_c', '--update', self.path ]
        build.runcmd(cmd)

    def artefacts(self):
        """Returns the list of artefacts in rpm repository."""
        artefacts = []
        md = cr.Metadata()
        md.locate_and_load_xml(self.path)
        for key in md.keys():
            pkg = md.get(key)
            artefacts.append(RegistryArtefact(pkg.name, pkg.arch,
                                              pkg.version+pkg.release))
        return artefacts


class RegistryOsi(Registry):
    """Registry for Osi format (aka. OS images)."""

    CHECKSUMS_FILES =  ['SHA256SUMS', 'SHA256SUMS.gpg']

    def __init__(self, conf, instance, distribution):
        super().__init__(conf, instance, distribution)

    @property
    def path(self):
        return os.path.join(self.instance_dir, 'osi', self.distribution)

    def publish(self, build):
        """Publish OSI images."""

        logger.info("Publishing OSI images for %s" % (build.name))

        # ensure osi directory exists
        parent = os.path.dirname(self.path)
        if not os.path.exists(parent):
            logger.debug("Creating directory %s" % (parent))
            os.mkdir(parent)
            os.chmod(parent, 0o755)

        # ensure distribution directory exists
        if not os.path.exists(self.path):
            logger.debug("Creating directory %s" % (self.path))
            os.mkdir(self.path)
            os.chmod(self.path, 0o755)

        built_files = RegistryOsi.CHECKSUMS_FILES
        images_files_path = os.path.join(build.place, '*.tar.*')
        built_files.extend([os.path.basename(_path)
                            for _path in glob.glob(images_files_path)])
        logger.debug("Found files: %s" % (' '.join(built_files)))

        for _fpath in built_files:
            src = os.path.join(build.place, _fpath)
            dst = os.path.join(self.path, _fpath)
            logger.debug("Copying file %s to %s" % (src, dst))
            shutil.copyfile(src, dst)

    def artefacts(self):
        """Returns the list of artefacts in rpm repository."""
        artefacts = []
        for _path in os.listdir(self.path):
            if _path in RegistryOsi.CHECKSUMS_FILES:
                continue
            if _path.endswith('.manifest'):
                continue
            f_re = re.match(r'(?P<name>.+)_(?P<version>\d+)\.(?P<arch>.+)',
                            _path)
            if not f_re:
                logger.warning("File %s does not match OSI artefact regular "
                               "expression" % (_path))
                continue

            artefacts.append(RegistryArtefact(f_re.group('name'),
                                              f_re.group('arch'),
                                              f_re.group('version')))

        return artefacts


class RegistryArtefact:
    def __init__(self, name, architecture, version):
        self.name = name
        self.architecture = architecture
        self.version = version


class RegistryFactory():
    _formats = {
        'deb': RegistryDeb,
        'rpm': RegistryRpm,
        'osi': RegistryOsi,
    }

    @staticmethod
    def get(fmt, conf, instance, distribution):
        """Instanciate the appropriate Registry for the given format."""
        if not fmt in RegistryFactory._formats:
            raise RuntimeError("format %s unsupported by registries" % (fmt))
        return RegistryFactory._formats[fmt](conf, instance, distribution)
