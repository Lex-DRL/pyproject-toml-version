# encoding: utf-8

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Test actual config files."""

from itertools import chain as _chain
from pathlib import Path as _Path
import re as _re
import warnings as _warnings

from typing_clean import *
import pytest

from pyproject_toml_version import pyproject_version


CONFIGS_ROOT_DIR = _Path(__file__).parent / "data"

__re_version_comment_match = _re.compile(
	(
		r'^#+\s*(?:'
		r'"([^"]+)"|'  # "version", or...
		r"'([^']+)'"  # 'version'
		r')\s*(?:'
		r'#.*'  # optional extra comment after
		r')?$'
	), flags=_re.IGNORECASE
).match
__re_dyn_field_comment_match = _re.compile(
	(
		r'^#+\s*'
		r'\[\s*([^\[\]]+)\s*\]'  # [field.path]
		r'\s*(?:'
		r'#.*'  # optional extra comment after
		r')?$'
	), flags=_re.IGNORECASE
).match


def __parse_group_from_comment_line(
	stripped_line: str,
	matcher: _C[[str], _O[_Match[str]]],
	what: str = 'version'
) -> _O[str]:
	match = matcher(stripped_line)
	if not match:
		return None
	valid_groups = [g for g in match.groups() if g]
	if not valid_groups:
		return None
	assert len(valid_groups) == 1, (
		f"Internal error - somehow multiple groups are regex-parsed from {what} comment: "
		f"{stripped_line!r} -> {valid_groups!r}"
	)
	extracted = valid_groups[0]
	return extracted if extracted else None


def _parse_version_from_comment_line(stripped_line: str = "# '0.0.2-b3' # comment") -> _O[str]:
	return __parse_group_from_comment_line(stripped_line, matcher=__re_version_comment_match, what='version')


def _parse_dyn_field_from_comment_line(stripped_line: str = "# [field.path] # comment") -> _O[str]:
	return __parse_group_from_comment_line(stripped_line, matcher=__re_dyn_field_comment_match, what='dyn-field')


def _to_path_obj(value: _U[str, _Path]) -> _Path:
	if isinstance(value, _Path):
		return value
	return _Path(str(value))


class Case(_NamedTuple):
	path: _U[_Path, str]
	expected: _O[str]
	dynamic_field: str = ''
	parsing_error: _U[str, BaseException, None] = None
	parsing_warning: _O[str] = None

	@staticmethod
	def __extract_from_opening_file_comments(path: _Path) -> _Tuple[_O[str], _O[str]]:
		"""
		- ``None``: can't extract
		- ``''``: extracted, empty string
		"""
		assert isinstance(path, _Path)

		expected: _O[str] = None
		dynamic_field: _O[str] = None
		with path.open('rt', encoding='utf-8') as f:
			while expected is None or dynamic_field is None:
				line = f.readline()
				line = line.rstrip('\r\n').strip()

				if not line:
					continue
				if not line.startswith('#'):
					break

				if expected is None:
					expected = _parse_version_from_comment_line(line)
				elif dynamic_field is None:
					dynamic_field = _parse_dyn_field_from_comment_line(line)
				else:
					break
		return expected, dynamic_field

	@staticmethod
	def from_file(path: _U[_Path, str]) -> _O['Case']:
		path = _to_path_obj(path)
		assert isinstance(path, _Path)
		if not path.is_file():
			return Case(path, None, parsing_warning=f"Not a file, skipped: {path!s}")

		try:
			expected, dynamic_field = Case.__extract_from_opening_file_comments(path)
		except Exception as e:
			return Case(path, None, parsing_error=e)
		if not dynamic_field:
			dynamic_field = ''
		assert isinstance(dynamic_field, str)

		if not expected:
			return Case(
				path, expected, dynamic_field=dynamic_field,
				parsing_error=f"File skipped, version isn't parsed: {path!s}"
			)

		assert expected and isinstance(expected, str)
		return Case(path, expected, dynamic_field=dynamic_field)


def __cases_to_path_and_str(cases: _Iterable[Case]) -> _Generator[Case, _A, None]:
	for case in cases:
		if case.parsing_error:
			yield case
			continue
		path = case.path
		expected = case.expected
		dynamic_field = case.dynamic_field
		yield Case(_Path(path), expected, dynamic_field=dynamic_field, parsing_warning=case.parsing_warning)
		yield Case(str(path), expected, dynamic_field=dynamic_field)


def _config_cases(
	parent_dir: _U[str, _Path] = CONFIGS_ROOT_DIR,
	file_pattern: str = '*.toml',
	explicit_paths: _Iterable[_U[str, _Path]] = (),
):
	"""Decorator factory: scan the parent directory -> parametrize a func with one test per found config."""
	_explicit_paths = [_to_path_obj(x) for x in explicit_paths]
	_parent_dir = _to_path_obj(parent_dir)
	file_pattern = str(file_pattern)
	all_matching_paths = _chain(
		_parent_dir.rglob(file_pattern),
		_explicit_paths
	)

	cases: _List[Case] = sorted(
		case for case in (
			Case.from_file(path) for path in all_matching_paths
		) if case is not None
	)
	return pytest.mark.parametrize(
		['path', 'expected', 'dynamic_field', 'parsing_error', 'parsing_warning'],
		list(__cases_to_path_and_str(cases))
	)


@_config_cases()
def test_configs_auto(
	path: _U[_Path, str], expected: _O[str], dynamic_field: str,
	parsing_error: _U[str, BaseException, None], parsing_warning: _O[str]
):
	if parsing_warning:
		_warnings.warn(parsing_warning)

	if isinstance(parsing_error, BaseException):
		raise parsing_error
	if parsing_error:
		raise RuntimeError(f"Parsing error for {path!r}: {parsing_error}")
	if expected is None:
		return

	assert pyproject_version(path, dynamic_field=dynamic_field) == expected
