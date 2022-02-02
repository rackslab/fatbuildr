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
import glob

import createrepo_c as cr

from . import Registry, RegistryArtefact, ChangelogEntry
from ...log import logr

logger = logr(__name__)


class RegistryRpm(Registry):
    """Registry for Rpm format (aka. yum/dnf repository)."""

    def __init__(self, conf, instance):
        super().__init__(conf, instance)

    @property
    def distributions(self):
        return os.listdir(os.path.join(self.instance_dir, 'rpm'))

    def distribution_path(self, distribution):
        return os.path.join(self.instance_dir, 'rpm', distribution)

    def pkg_dir(self, distribution):
        return os.path.join(self.distribution_path(distribution), 'Packages')

    def _mk_missing_repo_dirs(self, distribution):
        """Create pkg_dir if it does not exists, considering pkg_dir is a
        subdirectory of repo_dir."""
        pkg_dir = self.pkg_dir(distribution)
        if not os.path.exists(pkg_dir):
            logger.info("Creating missing package directory %s" % (pkg_dir))
            os.makedirs(pkg_dir)

    def publish(self, build):
        """Publish RPM (including SRPM) in yum/dnf repository."""

        logger.info(
            "Publishing RPM packages for %s in distribution %s"
            % (build.name, build.distribution)
        )

        dist_path = self.distribution_path(distribution)
        pkg_dir = self.pkg_dir(distribution)

        self._mk_missing_repo_dirs(build.distribution)

        rpm_glob = os.path.join(build.place, '*.rpm')
        for rpm_path in glob.glob(rpm_glob):
            logger.debug("Copying RPM %s to %s" % (rpm_path, pkg_dir))
            shutil.copy(rpm_path, pkg_dir)

        logger.debug("Updating metadata of RPM repository %s" % (dist_path))
        cmd = ['createrepo_c', '--update', dist_path]
        build.runcmd(cmd)

    def artefacts(self, distribution):
        """Returns the list of artefacts in rpm repository."""
        artefacts = []
        md = cr.Metadata()
        md.locate_and_load_xml(self.distribution_path(distribution))
        for key in md.keys():
            pkg = md.get(key)
            artefacts.append(
                RegistryArtefact(
                    pkg.name, pkg.arch, pkg.version + '-' + pkg.release
                )
            )
        return artefacts

    def artefact_bins(self, distribution, src_artefact):
        """Returns the list of binary RPM generated by the given source RPM."""
        artefacts = []
        md = cr.Metadata()
        md.locate_and_load_xml(self.distribution_path(distribution))
        for key in md.keys():
            pkg = md.get(key)
            if pkg.arch == 'src':  # skip non-binary package
                continue
            # The createrepo_c library gives access to full the source RPM
            # filename, including its version and its extension. We must
            # extract the source package name out of this filename.
            source = pkg.rpm_sourcerpm.rsplit('-', 2)[0]
            if source != src_artefact:
                continue
            artefacts.append(
                RegistryArtefact(
                    pkg.name, pkg.arch, pkg.version + '-' + pkg.release
                )
            )
        return artefacts

    def artefact_src(self, distribution, bin_artefact):
        md = cr.Metadata()
        md.locate_and_load_xml(self.distribution_path(distribution))
        for key in md.keys():
            pkg = md.get(key)
            if pkg.name != bin_artefact:
                continue
            if pkg.arch == 'src':  # skip non-binary package
                continue
            # The createrepo_c library gives access to the full source RPM
            # filename, including its version and its extension. We must
            # extract the source package name out of this filename.
            srcrpm_components = pkg.rpm_sourcerpm.rsplit('-', 2)
            src_name = srcrpm_components[0]
            # For source version, extract the version and the release with
            # .src.rpm suffix removed.
            src_version = srcrpm_components[1] + '-' + srcrpm_components[2][:-8]
            return RegistryArtefact(src_name, 'src', src_version)

    def changelog(self, distribution, architecture, artefact):
        """Returns the changelog of a RPM source package."""
        md = cr.Metadata()
        md.locate_and_load_xml(self.distribution_path(distribution))
        for key in md.keys():
            pkg = md.get(key)
            if pkg.name != artefact:
                continue
            if pkg.arch != architecture:
                continue
            return RpmChangelog(pkg.changelogs).entries()


class RpmChangelog:
    def __init__(self, entries):
        self._entries = entries

    def entries(self):
        result = []
        # The createrepo_c library builds the entries list in ascending date
        # order. We prefer to list the entries to other way, so we reverse.
        for entry in reversed(self._entries):

            (author, version) = entry[cr.CHANGELOG_ENTRY_AUTHOR].rsplit(' ', 1)
            changes = [
                RpmChangelog._sanitize_entry(entry)
                for entry in entry[cr.CHANGELOG_ENTRY_CHANGELOG].split('\n')
            ]
            result.append(
                ChangelogEntry(
                    version, author, entry[cr.CHANGELOG_ENTRY_DATE], changes
                )
            )
        return result

    @staticmethod
    def _sanitize_entry(entry):
        # remove leading dash if present
        if entry.startswith('-'):
            entry = entry[1:]
        return entry.strip()
