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


# Map fatbuildr normalized architectures with format native architectures.

_FORMATS_ARCH_MAP = {
    'deb': [
        ('src', 'source'),
        ('noarch', 'all'),
        ('x86_64', 'amd64'),
        ('aarch64', 'arm64'),
    ]
}

# Map fatbuildr normalized architectures with repository architectures, for
# each format.

_FORMATS_ARCH_DIR = {
    'rpm': [
        ('src', 'source'),
    ]
}


class ArchMap:
    def __init__(self, format):
        self.format = format

    def _native(self, formats_map, arch):
        if self.format not in formats_map:
            return arch
        for normalized, native in formats_map[self.format]:
            if arch == normalized:
                return native
        return arch

    def _normalized(self, formats_map, arch):
        if self.format not in formats_map:
            return arch
        for normalized, native in formats_map[self.format]:
            if arch == native:
                return normalized
        return arch

    def native(self, arch):
        return self._native(_FORMATS_ARCH_MAP, arch)

    def normalized(self, arch):
        return self._normalized(_FORMATS_ARCH_MAP, arch)

    def nativedir(self, arch):
        return self._native(_FORMATS_ARCH_DIR, arch)
