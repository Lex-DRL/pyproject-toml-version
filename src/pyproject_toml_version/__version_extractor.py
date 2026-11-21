# encoding: utf-8

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Low-level functions to actually get the version from a dynamic file in fallback mode."""

from importlib import util as _importlib_util
from pathlib import Path as _Path
import re as _re
import warnings as _warnings

from typing_clean import *
from types import ModuleType as _ModuleType


__default_var_names: _Tuple[str, ...] = ('__version__', 'VERSION')

__re_valid_var_name = _re.compile(r'^[a-z_][a-z_0-9]*$', flags=_re.IGNORECASE).match
__re_module_filename = _re.compile(
	r'^([a-z_][a-z_0-9]*)'
	r'(?:\.py[codw]?|\.so|\.dll)?'
	r'$',
	flags=_re.IGNORECASE
).match


def __module_name_from_path(file_path: _Path) -> str:
	name = file_path.name
	match = __re_module_filename(name)
	if not match:
		raise ValueError('Invalid module name')
	return match.groups()[0]


def __validate_var_names(var_names: _Iterable[str]) -> _Tuple[str, ...]:
	_names = [str(x).strip() for x in var_names if x]
	names = tuple(x for x in _names if x)
	if not names:
		names = __default_var_names

	wrong_names: _List[str] = []
	for name in names:
		if not __re_valid_var_name(name):
			wrong_names.append(name)
	if not wrong_names:
		return names

	seq = ', '. join(repr(x) for x in wrong_names)
	s = 's' if len(wrong_names) > 1 else ''
	raise ValueError(f'Invalid variable name{s} for dynamic version: {seq}')


def __keep_matching_var_names_factory(
	var_names: _Tuple[str, ...] = __default_var_names, ignore_case=True
) -> _C[[_Dict[str, _T]], _Dict[str, _T]]:
	"""
	Utility func-factory for ``extract_version_with_import()``:
	takes ``vars(module)`` and builds a new dict with only matching var-names.
	"""
	assert var_names and all(isinstance(x, str) and x and x == x.strip() for x in var_names)

	def filter_case_sensitive(module_vars: _Dict[str, _T]) -> _Dict[str, _T]:
		"""Case-sensitive func: just strictly check that the name is one of the expected ones."""
		# Do whichever is fastest - useful for huge version-name variations or module attribs:
		if len(names_tuple) < len(module_vars):
			# Less allowed names - iterate over them
			return {nm: module_vars[nm] for nm in names_tuple if nm in module_vars}
		# Less/same allowed module attribs
		return {nm: v for nm, v in module_vars.items() if nm in names_set}

	if not ignore_case:
		names_tuple = tuple(var_names)
		names_set = set(var_names)
		return filter_case_sensitive

	_names_or = '|'.join(
		_re.escape(x) for x in var_names
	)
	re_match = _re.compile(
		f'^({_names_or})$',
		flags=_re.IGNORECASE
	).match

	def filter_case_ignore(module_vars: _Dict[str, _T]) -> _Dict[str, _T]:
		"""More complex setup: we need to introduce regex match in the ignored-case case."""
		# Here, we need to check every module attr anyway:
		return {nm: v for nm, v in module_vars.items() if re_match(nm)}

	return filter_case_ignore


def __import_py_module_at_path(file_path: _Path, path_str: str) -> _Tuple[_ModuleType, str]:
	"""
	The import is very dumb - it works only on trivial modules:
	no internal relative imports resolved, no registration of the module ``sys.modules``,
	no compatibility with ``multiprocessing``, ``inspect``, dataclasses and fancy AST tricks.

	Just the simplest possible python module. But it's exactly where dynamic version should live.
	"""
	try:
		module_name = __module_name_from_path(file_path)
	except ValueError as e:
		raise ImportError(str(e), name=file_path.name, path=path_str) from e

	spec = _importlib_util.spec_from_file_location(module_name, path_str)
	if spec is None:
		raise ImportError('Unsupported file type for dynamic version', name=module_name, path=path_str)
	try:
		module = _importlib_util.module_from_spec(spec)
		spec.loader.exec_module(module)
	except (OSError, SyntaxError, ValueError) as e:
		raise ImportError(str(e), name=module_name, path=path_str) from e

	return module, module_name


def extract_version_with_import(file_path: _Path, *var_names: str, ignore_case=True, warn_on_multi=True) -> str:
	"""
	Get a version from dyn-version-module by actually trying to load it.

	No ``var_names`` = use default.

	:param warn_on_multi:
		When multiple string-type versions found - if ``True``: use the first mathing string-version
		(with respect to their order on ``var_names``) and only raise a warning.
		If ``False``, a full ``ImportError`` is thrown.
	:raises ValueError: If there's an invalid name in ``var_names``.
	:raises ImportError: If the version-extraction itself fails for any reason.
	"""
	try:
		var_names = __validate_var_names(var_names)
		path_str = str(file_path.resolve())
		module, module_name = __import_py_module_at_path(file_path, path_str)
		keep_matching_var_names = __keep_matching_var_names_factory(var_names, ignore_case)
	except Exception as e:
		tb = e.__traceback__
		if tb is not None:
			tb.tb_next = None  # re-throw the exception as raised from here
		raise

	module_vars = vars(module)
	found_versions = keep_matching_var_names(module_vars)
	if not found_versions:
		raise ImportError('No dynamic versions found in module', name=module_name, path=path_str)

	str_versions = {k: v for k, v in found_versions.items() if isinstance(v, str)}
	if len(str_versions) == 1:
		return next(iter(str_versions.values()))

	seq = ', '.join(
		f'{k}={v!r}' for k, v in found_versions.items()
	)
	if not str_versions:
		raise ImportError(
			f'No dynamic STRING versions found in module, only wrong type: {seq}',
			name=module_name, path=path_str
		)

	assert len(str_versions) > 1
	if not warn_on_multi:
		raise ImportError(
			f'Multiple dynamic versions found in module, more than one is string: {seq}',
			name=module_name, path=path_str
		)

	# Now, we need to go deeper - and detect WHICH of the allowed names passed each candidate

	seq_allowed = ', '.join(repr(x) for x in var_names)

	if not ignore_case:
		# It's easy for case-sensitive scenario:
		used_var, version = next(iter(
			(nm, str_versions[nm]) for nm in var_names if nm in str_versions
		))
		_warnings.warn(
			f'Multiple dynamic versions found ({path_str}), more than one is a string that matches name '
			f'({seq_allowed}) - using first CASE-SENSITIVE match {used_var}={version!r}; all: {seq}',
			stacklevel=2,  # 1 = here, 2 = in the actual caller
		)
		return version

	# ... but for the ignore-case, we need to redo the regex matches - now keeping track of which name allowed it:

	_matchers: _List[_C[[str], _O[_Match]]] = [
		_re.compile(f'^{escaped}$', flags=_re.IGNORECASE).match for escaped in (
			_re.escape(x) for x in var_names
		)
	]
	matchers_enum = list(enumerate(_matchers))

	def sorting_key(name: str):
		for i, matcher in matchers_enum:
			if matcher(name):
				return i, name
		raise AssertionError(f"Internal error - previously-matching name {name!r} no longer matches any: {seq_allowed}")

	matching_name_i, used_var = sorted([sorting_key(x) for x in str_versions.keys()])[0]
	version = str_versions[used_var]
	_warnings.warn(
		f'Multiple dynamic versions found ({path_str}), more than one is a string that matches name '
		f'({seq_allowed}) - using first CASE-IGNORED match {used_var}={version!r}; all: {seq}',
		stacklevel=2,  # 1 = here, 2 = in the actual caller
	)
	return version


def __build_regex_matcher(pattern: _U[str, _Pattern]) -> _Pattern:
	if not isinstance(pattern, (str, _Pattern)):
		raise TypeError(f"Not a valid regex pattern: {pattern!r}")
	if isinstance(pattern, _Pattern):
		compiled: _Pattern = pattern
	else:
		compiled: _Pattern = _re.compile(str(pattern))

	if compiled.pattern.startswith('(?i)'):
		# Compatibility with older python versions:
		skip = len('(?i)')
		compiled = _re.compile(
			compiled.pattern[skip:],
			flags=_re.IGNORECASE | compiled.flags
		)

	return compiled


def __extract_version_with_regex(
	file_path: _Path, pattern: _U[str, _Pattern], encoding='utf-8', version_gr='version'
) -> _Tuple[_O[str], _Pattern]:
	compiled = __build_regex_matcher(pattern)
	re_match = compiled.match if compiled.pattern.startswith('^') else compiled.search
	if not(version_gr and isinstance(version_gr, str) and version_gr.strip()):
		raise ValueError(f"Not a valid name for a version-group in regex: {version_gr!r}")
	with open(file_path, 'rt', encoding=encoding) as f:
		for line in f:
			match = re_match(line.rstrip())
			if not match:
				continue
			version = match.groupdict().get(version_gr)
			if version is None:
				continue
			return version, compiled
	return None, compiled


def extract_version_with_regex(
	file_path: _Path, pattern: _U[str, _Pattern], encoding='utf-8', version_gr='version'
) -> str:
	"""Get a version from dyn-version-module by trying to regex-parse with the given ``re_match`` callable."""
	version, compiled = __extract_version_with_regex(file_path, pattern, encoding=encoding, version_gr=version_gr)
	if version is not None:
		return version
	path_str = str(file_path.resolve())
	pattern_str = str(compiled.pattern)
	case_status = 'case-ignored' if (compiled.flags & _re.IGNORECASE) else 'case-sensitive'
	raise RuntimeError(f'Unable to find version (with {case_status} regex {pattern_str!r}) in: {path_str}')


def __regex_from_var_names(
	var_names: _Tuple[str, ...] = __default_var_names, ignore_case=True
) -> _Pattern:
	assert var_names and all(isinstance(x, str) and x and x == x.strip() for x in var_names)
	names_or = '|'.join(
		_re.escape(x) for x in var_names
	)
	quotes_or = '|'.join(["'''", '"""', "'", '"'])
	pattern = _re.compile(
		# hatchling-based, but accounting for more edge-cases:
		f'^({names_or})'  # verSION
		f'(?:\\s*:\\s*[a-zA-Z_][a-zA-Z_0-9\\[\\],\\.\\s\\|]*)?'  # : O[U[str, C[[...], str]]
		f'\\s*=\\s*({quotes_or})(?P<version>.+?)\\2',
		flags=_re.IGNORECASE if ignore_case else 0
	)
	# pattern.match("""verSION: O[U[str, C[[...], str]] = 'abc'""").groupdict()
	# pattern.match("""VERSION:str|None = '''1.2.3'''""").groupdict()
	# pattern.match('''version="0.1rc1"''').groupdict()
	return pattern


def extract_version_with_regex_by_names(file_path: _Path, *var_names: str, ignore_case=True, encoding='utf-8') -> str:
	"""
	Get a version from dyn-version-module by trying to regex-parse for the given ``var_names``.

	:raises ValueError: If there's an invalid name in ``var_names``.
	:raises RuntimeError: If version can't be extracted.
	"""
	try:
		var_names = __validate_var_names(var_names)
		pattern = __regex_from_var_names(var_names, ignore_case)
	except Exception as e:
		tb = e.__traceback__
		if tb is not None:
			tb.tb_next = None  # re-throw the exception as raised from here
		raise

	version, compiled = __extract_version_with_regex(file_path, pattern, encoding=encoding, version_gr='version')
	if version is not None:
		return version

	path_str = str(file_path.resolve())
	case_status = 'case-ignored' if ignore_case else 'case-sensitive'
	seq = '/'.join(var_names)
	raise RuntimeError(f'Unable to find version ({case_status} {seq}) in: {path_str}')
