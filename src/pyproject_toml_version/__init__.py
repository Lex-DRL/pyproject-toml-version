# encoding: utf-8

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
Get version from 'pyproject.toml' - static or dynamic, regardless of backend.

Usage::

	from pyproject_toml_version import pyproject_version
	# or, since the module exports only this ^ function:
	from pyproject_toml_version import *

	version: str = pyproject_version('pyproject.toml')
"""

import tomli as _tomli
from typing_clean import *

from .__dynamic import *
from .__dynamic import _T_Detector


def __read_whole_toml(toml_path: str = 'pyproject.toml') -> _Dict[str, _A]:
	with open(toml_path, 'rb') as f:  # tomli.load needs a binary file since v1.2
		toml_data = _tomli.load(f)
	if not isinstance(toml_data, dict):
		raise TypeError(f"Internal error - 'tomli.load' returned not-a-dict (for {toml_path!r}): {toml_data!r}")
	return toml_data


def __extract_toml_section(toml_path: str, toml_data: _Dict[str, _A], section: str = 'project') -> _Dict[str, _A]:
	try:
		sec_data: _O[_Dict[str, _A]] = toml_data[section]
	except KeyError:
		raise ValueError(f"Missing/empty {section!r} section in {toml_path!r}")
	if sec_data is None:
		raise ValueError(f"Empty {section!r} section in {toml_path!r}")
	if not isinstance(sec_data, dict):
		raise TypeError(f"Internal error - {section!r} section (in {toml_path!r}) isn't a dict: {sec_data!r}")
	return sec_data


def __is_version_in_dynamic_list(
	section: str, section_data: _Dict[str, _A], field: str = 'dynamic', version_name: str = 'version'
) -> bool:
	dynamic = section_data.get(field)
	if dynamic is None:
		dynamic = []
	if isinstance(dynamic, str):
		dynamic = dynamic.split()

	ok = True
	if not isinstance(dynamic, (list, tuple, set, _Iterable)):
		try:
			dynamic = iter(dynamic)
		except Exception:
			ok = False
	if not ok:
		field_path = f'{section}.{field}'
		raise TypeError(f"Invalid type for {field_path!r} field (list expected): {dynamic!r}")
	dynamic_set: _Set[str] = set(dynamic)
	return version_name in dynamic_set


def __validate_ver_str(version, toml_path: str, what: str = 'version', at: str = 'in') -> str:
	what_first = '' if not what else what[0].upper() + what[1:]
	if version is None:
		raise ValueError(f"No {what} found {at} {toml_path!r}")
	if not version:
		raise ValueError(f"Empty {what} ({at} {toml_path!r}): {version!r}")
	if not isinstance(version, str):
		raise TypeError(f"{what_first} ({at} {toml_path!r}) isn't a string: {version!r}")
	if not version.strip():
		raise ValueError(f"{what_first} ({at} {toml_path!r}) contains nothing but whitespace characters: {version!r}")
	return version


def pyproject_version(toml_path: str = 'pyproject.toml', dynamic_field: str = '') -> str:
	"""Get version from 'pyproject.toml' - static or dynamic, regardless of backend."""
	toml_data = __read_whole_toml(toml_path)
	project = __extract_toml_section(toml_path, toml_data, section='project')

	is_static = 'version' in project
	is_dynamic = __is_version_in_dynamic_list('project', section_data=project)
	if is_static == is_dynamic:
		what = 'version is both static and dynamic' if is_static else 'neither static nor dynamic version is present'
		raise ValueError(f"Invalid project file - {what}: {toml_path!r}")

	if is_static:
		# Simple case: static version
		version = project['version']
		return __validate_ver_str(version, toml_path, what='version', at='in')

	assert is_dynamic and not is_static
	# Using `build` is fragile, need to reimplement for each popular build-backend
	detector = DynDetector(toml_path=toml_path, toml_data=toml_data, dynamic_field=dynamic_field)
	version = detector.version_str()
	backend_name = detector.backend_name()
	return __validate_ver_str(version, toml_path, what=f'dynamic [{backend_name}] version', at='for')
