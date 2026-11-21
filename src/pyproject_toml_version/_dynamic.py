# encoding: utf-8

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Dynamic-version detectors"""

from collections import OrderedDict as _OrderedDict
import errno as _errno
from os import PathLike as _PathLike, strerror as _strerror
from pathlib import Path as _Path
import re as _re
import warnings as _warnings

from typing_clean import *

from .__ensure_overrides import _ensure_required_overrides
from .__version_extractor import (
	extract_version_with_import as _extract_version_with_import,
	extract_version_with_regex as _extract_version_with_regex,
	extract_version_with_regex_by_names as _extract_version_with_regex_by_names
)


class _BaseArgs:
	"""
	Data-only class used **ONLY** internally in ``DynDetector`` to pass around
	the main/shared set of detector arguments between methods that might be used **BEFORE**
	the instance creation.
	"""

	# TODO: directly coded here for py3.6 support, to be replaced with dataclass use for 3.7+:

	__slots__ = ('toml_path', 'toml_data', 'dynamic_field')

	def __init__(self, toml_path: _U[str, _PathLike], toml_data: _Dict[str, _A], dynamic_field: str = None):
		# noinspection PyTypeChecker
		self.toml_path: _Path = toml_path
		self.toml_data: _Dict[str, _A] = toml_data
		self.dynamic_field: str = dynamic_field

		self.__post_init__()

	def __repr__(self):
		return "{nm}(toml_path={toml_path}, toml_data={toml_data}, dynamic_field={dynamic_field})".format(
			nm=self.__class__.__name__,
			toml_path=repr(self.toml_path),
			toml_data=repr(self.toml_data),
			dynamic_field=repr(self.dynamic_field),
		)

	# TODO ^

	def __post_init__(self):
		dynamic_field = self.dynamic_field
		self.dynamic_field: str = '' if dynamic_field is None else str(dynamic_field)
		self._validate_essential_args()

	def _validate_essential_args(self) -> '_BaseArgs':
		# noinspection PyTypeChecker
		toml_path: _Path = self.toml_path
		if toml_path is None:
			self.toml_path = toml_path = _Path('')
		if isinstance(toml_path, str):
			self.toml_path = toml_path = _Path(toml_path)
		if isinstance(toml_path, _PathLike) and not isinstance(toml_path, _Path):
			self.toml_path = toml_path = _Path(str(toml_path))
		if not isinstance(toml_path, _Path):
			if isinstance(toml_path, _PathLike):
				self.toml_path = toml_path = _Path(str(toml_path))
			else:
				raise TypeError(f"Invalid type for 'toml_path': {toml_path!r}")

		toml_path_str = toml_path.as_posix()
		if not toml_path_str.strip('.'):
			raise ValueError(f"No 'toml_path' was specified: {toml_path_str!r}")

		toml_data = self.toml_data
		if not toml_data:
			raise ValueError(f"Data-dict (for {toml_path_str!r}) cannot be empty: {toml_data!r}")
		if not isinstance(toml_data, _Mapping):
			raise TypeError(f"Not a data-dict (for {toml_path_str!r}): {toml_data!r}")
		if not isinstance(toml_data, (dict, _OrderedDict)):
			# Enforce the root data object to be exactly dict, not just *SOME* mapping
			self.toml_data = toml_data = {k: v for k, v in toml_data.items()}
		return self

	def _get_field_from_toml_data(
		self, field_path: str, what: str, msg_if_required: str = ''
	) -> _A:
		"""Internal: walk through the ``toml_data`` dict and extract the config's field value by a given path."""
		self._validate_essential_args()
		toml_path_str = self.toml_path.as_posix()

		if msg_if_required and not field_path:
			raise ValueError(f"{what} (for {toml_path_str!r}) is required {msg_if_required}")
		if not isinstance(field_path, str):
			raise TypeError(f"{what} (for {toml_path_str!r}) is not a string: {field_path!r}")

		value: _A = self.toml_data
		segs = field_path.split('.')
		segs_current_parent: _List[str] = []
		for seg in segs:
			if not isinstance(value, _Mapping):
				cur_path = '.'.join(segs_current_parent)
				raise TypeError(f"{what}: {cur_path!r} is not a TOML section/dict (in {toml_path_str!r}): {value!r}")
			if seg not in value:
				cur_path = '.'.join(segs_current_parent + [seg])
				raise KeyError(f"{what}: No such element (in {toml_path_str!r}): {cur_path!r}")
			value = value[seg]
			segs_current_parent.append(seg)

		return value

	def _read_dynamic_field(self, dynamic_field: str = '') -> str:
		"""
		Internal method with actual implementation of how a dynamic field is read.

		It is its own function to allow backend-specific classes intercept the dynamic field to read
		(without overriding ``dynamic_field`` arg itself).
		"""
		value = self._get_field_from_toml_data(
			dynamic_field,
			what='Dynamic field',
			msg_if_required="when version is dynamic and backend is unknown/fallback/auto"
		)
		toml_path_str = self.toml_path.as_posix()
		if not value:
			raise ValueError(f"Dynamic field ({dynamic_field!r} in {toml_path_str!r}) is empty: {value!r}")
		if not isinstance(value, str):
			raise TypeError(f"Dynamic field ({dynamic_field!r} in {toml_path_str!r}) is not a string: {value!r}")
		if not value.strip():
			raise ValueError(f"Dynamic field ({dynamic_field!r} in {toml_path_str!r}) can't contain only whitespaces: {value!r}")
		return value

	def read_dynamic_field(self) -> str:
		"""Get a value of the TOML field specified in ``dynamic_field``."""
		return self._read_dynamic_field(self.dynamic_field)

	def get_dynamic_file_path(self, strict=False) -> _Path:
		"""
		Detect the dynamic file path from the passed args and make sure it actually exists.

		:raises IsADirectoryError: Path exists, but it's not a file.
		:raises FileNotFoundError: No file at the path.
		"""
		self._validate_essential_args()
		# noinspection PyTypeChecker
		toml_path: _Path = self.toml_path
		assert isinstance(toml_path, _Path)
		proj_dir = toml_path.parent
		dynamic_field_value = self.read_dynamic_field()

		path = proj_dir / dynamic_field_value
		path = path.resolve()
		if path.is_file():
			return path
		if strict:
			# No second chances - the path must be a real filepath
			raise FileNotFoundError(_errno.ENOENT, _strerror(_errno.ENOENT), str(path))

		# Such file doesn't exist - need to check deeper

		# Just the extension missing?
		_path = _Path(str(path) + '.py')
		if _path.is_file():
			return _path

		# Not a file because a dir?
		if path.exists():
			raise IsADirectoryError(_errno.EISDIR, _strerror(_errno.EISDIR), str(path))

		# Maybe the file path was specified as an imported module path? ('module.path' instead of 'module/path.py')
		module_segs = dynamic_field_value.split('.')
		module_segs[-1] += '.py'
		file_subpath = '/'.join(module_segs)
		_path = proj_dir / file_subpath
		if _path.is_file():
			return _path

		# Again - a dir instead of file?
		if _path.exists():
			raise IsADirectoryError(_errno.EISDIR, _strerror(_errno.EISDIR), str(_path))

		# No luck
		raise FileNotFoundError(_errno.ENOENT, _strerror(_errno.ENOENT), str(path))


class DynDetector(_BaseArgs):
	"""
	Base class for all dynamic version detectors. Calling it instantiates:

	- the best detector designed for a specific backend, when the passed data matches it - even if the backend isn't specified explicitly;
	- if no specific detector matches, an instance of ``DynDetector`` itself - it might still extract the dynamic version.

	Unless you're **ABSOLUTELY** sure what backend the ``pyproject.toml`` uses,
	you should always instantiate ``DynDetector`` and not its subclasses -
	even when you expect a specific backend.
	"""

	def __post_init__(self):
		super().__post_init__()
		if type(self) is not DynDetector:
			return

		# We're actually trying to instantiate the `DynDetector` itself - ensure dynamic field is valid:
		self.read_dynamic_field()

	# region Internal stuff to auto-register all the subclasses on definition

	__specific_classes: _ClassVar[_Tuple[_Type['DynDetector'], ...]] = tuple()
	__specific_classes_set: _ClassVar[_FrozenSet[_Type['DynDetector']]] = frozenset()

	def __init_subclass__(cls: _Type['DynDetector'], **kwargs: _A) -> None:
		if super(DynDetector, cls).__new__ is not object.__new__:
			# Because in our `__new__`, we directly call `object.__new__` with no args
			# for all the subclasses:
			raise TypeError(f"{cls!r}: bases with their own __new__ (NamedTuple, tuple, ...) are not supported")

		super().__init_subclass__(**kwargs)
		_ensure_required_overrides(cls, DynDetector, DynDetector.__REQUIRED_OVERRIDES)

		all_classes = DynDetector.__specific_classes + (cls,)
		all_classes = tuple(c for c in all_classes if c is not DynDetector)
		DynDetector.__specific_classes = all_classes
		DynDetector.__specific_classes_set = frozenset(all_classes)

	@classmethod
	def _specific_classes(cls) -> _Tuple[_Type['DynDetector'], ...]:
		"""Tuple of all defined subclasses of ``DynDetector``, in the order of definition."""
		return cls.__specific_classes

	@classmethod
	def _specific_classes_set(cls) -> _FrozenSet[_Type['DynDetector']]:
		"""Frozen set of all defined subclasses of ``DynDetector``."""
		return cls.__specific_classes_set

	# endregion

	# region Required to reimplement

	__REQUIRED_OVERRIDES: _ClassVar[_Tuple[str, ...]] = ('backend_name', '_is_matching_class', 'version_str')

	@staticmethod
	def backend_name() -> str:
		"""Class method: printable unique name of this specific type of dynamic detector / its respective backend."""
		return 'Auto'

	@staticmethod
	def _is_matching_class(base_args: _BaseArgs, **kwargs) -> bool:
		"""Class method: whether this subclass matches the given init-argument values."""
		return False

	def version_str(self) -> str:
		"""The main method: extract dynamic version for this specific detector class."""
		return self.__get_fallback_version_str()

	# endregion

	def __new__(cls, *init_args, **init_kwargs) -> 'DynDetector':
		if cls is not DynDetector:
			# Completely bypass all the class-picking logic on subclasses,
			# and just do the default `__new__` instead:
			return super(DynDetector, cls).__new__(cls)
		best_class = DynDetector.__pick_best_class(*init_args, **init_kwargs)
		return super(DynDetector, best_class).__new__(best_class)

	@staticmethod
	def __pick_best_class(
		toml_path: _U[_Path, str], toml_data: _Dict[str, _A], dynamic_field: str = '',
		**kwargs
	) -> _Type['DynDetector']:
		base_args = _BaseArgs(toml_path=toml_path, toml_data=toml_data, dynamic_field=dynamic_field)
		matching_classes: _List[_Type['DynDetector']] = []
		for _cls in DynDetector._specific_classes():
			try:
				with _warnings.catch_warnings(record=True) as caught_warnings:
					_warnings.simplefilter("always")
					is_match = _cls._is_matching_class(base_args, **kwargs)
			except Exception:
				continue
			else:
				for w in caught_warnings:
					_warnings.warn_explicit(
						message=w.message,
						category=w.category,
						filename=w.filename,
						lineno=w.lineno,
						source=w.source,
					)

			if is_match:
				matching_classes.append(_cls)

		if matching_classes:
			# A more specific class found.
			first = matching_classes[0]
			if len(matching_classes) > 1:
				joined_cls_repr = ', '.join(repr(x) for x in matching_classes)
				args_dict: _OrderedDict[str, _A] = _OrderedDict(
					toml_path=toml_path, toml_data=toml_data, dynamic_field=dynamic_field, **kwargs
				)
				args_repr = ','.join(
					f'\n\t{k}={v!r}' for k, v in args_dict.items()
				)
				_warnings.warn(
					f"Multiple dynamic detectors ({joined_cls_repr}) match. Used: {first.__name__}({args_repr}\n)",
					stacklevel=3,  # 1 = here, 2 = in `__new__`, 3 = actual caller
				)
			return first

		# No specific class matches, `DynDetector` itself is our best hope.
		return DynDetector

	def __get_fallback_version_str(self, ignore_var_case=True) -> str:
		"""Last-resort automatic detection, unaware of specific backend used."""
		self._validate_essential_args()
		file_path = self.get_dynamic_file_path()
		try:
			return _extract_version_with_import(file_path, ignore_case=ignore_var_case)
		except ImportError:
			pass
		return _extract_version_with_regex_by_names(file_path, ignore_case=ignore_var_case)


T_Detector = _TypeVar('T_Detector', bound=DynDetector)


# ------------------------------------------------------------------------------


_re_hatchling = _re.compile(
	r'''^(__version__|VERSION) *= *(['"])v?(?P<version>.+?)\2''',
	flags=_re.IGNORECASE
)


class _DynDetectorHatchling(DynDetector):

	def _read_dynamic_field(self, dynamic_field: str = '') -> str:
		return super()._read_dynamic_field('tool.hatch.version.path')

	def get_dynamic_file_path(self, strict=True) -> _Path:
		return super().get_dynamic_file_path(strict=strict)

	@staticmethod
	def backend_name() -> str:
		return 'Hatchling'

	@staticmethod
	def _is_matching_class(base_args: _BaseArgs, **kwargs) -> bool:
		# noinspection PyBroadException
		try:
			backend = base_args._get_field_from_toml_data(
				'build-system.build-backend',
				what='Build-backend field',
			)
		except Exception:
			return False
		return backend == 'hatchling.build'

	def version_str(self) -> str:
		# https://hatch.pypa.io/latest/version/
		self._validate_essential_args()
		dyn_section = self.__dyn_section()
		source_map: _Dict[str, _C[[dict], str]] = {
			'regex': self.__version_str_regex,
			'code': self.__version_str_code,
			'env': self.__version_str_env,
		}

		# https://hatch.pypa.io/latest/plugins/version-source/reference/
		source = dyn_section.get('source', 'regex')
		if source is None or source == '':
			source = 'regex'
		source = self.__validate_toml_str_attr(source, 'tool.hatch.version.source')

		if source not in source_map:
			raise NotImplementedError(f"Unknown [tool.hatch.version.source] for [{self.backend_name()}]: {source!r}")
		func = source_map[source]
		return func(dyn_section)

	def __dyn_section(self) -> _Dict[str, _A]:
		dyn_section = self._get_field_from_toml_data(
			'tool.hatch.version',
			what='Dynamic-version section',
		)
		if not isinstance(dyn_section, _Mapping):
			toml_path_str = self.toml_path.as_posix()
			raise TypeError(f"[tool.hatch.version] (in {toml_path_str}) isn't a section but: {dyn_section!r}")
		if not isinstance(dyn_section, (dict, _OrderedDict)):
			dyn_section = {k: v for k, v in dyn_section.items()}
		return dyn_section

	def __validate_toml_str_attr(self, value: _A, path: str, strip = True) -> str:
		if not isinstance(value, str):
			raise TypeError(f"Not-a-string as [{path}] for [{self.backend_name()}]: {value!r}")
		if not (value.strip() if strip else value):
			raise TypeError(f"Empty [{path}] for [{self.backend_name()}]: {value!r}")
		return value

	def __version_str_regex(self, dyn_section: _Dict[str, _A]) -> str:
		# https://hatch.pypa.io/latest/plugins/version-source/regex/
		file_path = self.get_dynamic_file_path()
		regex = self.__get_regex_pattern(dyn_section)
		return _extract_version_with_regex(file_path, regex, version_gr='version')

	def __get_regex_pattern(self, dyn_section: _Dict[str, _A]) -> _Pattern:
		if 'pattern' not in dyn_section:
			return _re_hatchling
		pattern = dyn_section['pattern']
		if pattern is None or pattern == '':
			return _re_hatchling

		pattern = self.__validate_toml_str_attr(pattern, 'tool.hatch.version.pattern')
		return _re.compile(pattern)

	def __version_str_not_implemented(self, source: str) -> str:
		raise NotImplementedError(
			f"Only 'regex' is currently supported as [tool.hatch.version.source] for [{self.backend_name()}]. "
			f"Got: {source!r}"
		)

	def __version_str_code(self, dyn_section: _Dict[str, _A]) -> str:
		# https://hatch.pypa.io/latest/plugins/version-source/code/
		return self.__version_str_not_implemented('code')

	def __version_str_env(self, dyn_section: _Dict[str, _A]) -> str:
		# https://hatch.pypa.io/latest/plugins/version-source/env/
		return self.__version_str_not_implemented('env')
