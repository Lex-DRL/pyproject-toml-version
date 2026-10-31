# encoding: utf-8
"""Dynamic-version detectors"""

from pathlib import Path as _Path
import warnings as _warnings

from typing_clean import *


class _BaseArgs:
	"""
	Data-only class used **ONLY** internally in ``DynDetector`` to pass around
	the main/shared set of detector arguments between methods that run **BEFORE**
	the instance creation.
	"""
	__slots__ = ('toml_path', 'toml_data', 'dynamic_field')

	# TODO: directly coded here for py3.6 support, to be replaced with dataclass use for 3.7+:

	def __init__(self, toml_path: _U[_Path, str], toml_data: _Dict[str, _A], dynamic_field: str = ''):
		self.toml_path: _U[_Path, str] = toml_path
		self.toml_data: _Dict[str, _A] = toml_data
		self.dynamic_field: str = dynamic_field

	def __repr__(self):
		return "{nm}(toml_path={toml_path}, toml_data={toml_data}, dynamic_field={dynamic_field})".format(
			nm=self.__class__.__name__,
			toml_path=repr(self.toml_path),
			toml_data=repr(self.toml_data),
			dynamic_field=repr(self.dynamic_field),
		)


class DynDetector(_BaseArgs):
	"""
	Base class for all dynamic version detectors. Calling it instantiates:

	- the best detector designed for a specific backend, when the passed data matches it - even if the backend isn't specified explicitly;
	- if no specific detector matches, an instance of ``DynDetector`` itself - it might still extract the dynamic version.

	Unless you're **ABSOLUTELY** sure what backend the ``pyproject.toml`` uses,
	you should always instantiate ``DynDetector`` and not its subclasses -
	even when you expect a specific backend.
	"""

	# region Internal stuff to auto-register all the subclasses on definition

	__specific_classes: _ClassVar[_Tuple[_Type['DynDetector'], ...]] = tuple()
	__specific_classes_set: _ClassVar[_FrozenSet[_Type['DynDetector']]] = frozenset()

	def __init_subclass__(cls: _Type['DynDetector'], **kwargs: _A) -> None:
		if super(DynDetector, cls).__new__ is not object.__new__:
			# Because in our `__new__`, we directly call `object.__new__` with no args
			# for all the subclasses:
			raise TypeError(f"{cls!r}: bases with their own __new__ (NamedTuple, tuple, ...) are not supported")

		super().__init_subclass__(**kwargs)

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

	@classmethod
	def _is_matching_class(cls, base_args: _BaseArgs, **kwargs) -> bool:
		"""Class method: whether this subclass matches given init-argument values."""
		cls.__require_to_reimplement('_is_matching_class')
		return False

	@classmethod
	def backend_name(cls) -> str:
		"""Class method: printable name of this specific type of dynamic detector / its respective backend."""
		cls.__require_to_reimplement('backend_name')
		return 'Auto'

	def version_str(self) -> str:
		"""The main method: extract dynamic version for this specific detector class."""
		self.__require_to_reimplement('version_str', class_='')
		return self.__get_fallback_version_str()

	@classmethod
	def __require_to_reimplement(cls, method_name: str, class_='class-'):
		if cls is DynDetector:
			return
		raise NotImplementedError(f"{cls!r} subclass must reimplement {method_name!r} {class_}method")

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

	def __get_fallback_version_str(self) -> str:
		raise NotImplementedError('TODO')

	def __validate_essential_args(self) -> None:
		toml_path: _Path = self.toml_path
		if toml_path is None:
			self.toml_path = toml_path = _Path('')
		if isinstance(toml_path, str):
			self.toml_path = toml_path = _Path(toml_path)
		if not isinstance(toml_path, _Path):
			raise TypeError(f"Invalid type for 'toml_path': {toml_path!r}")

		toml_path_str = str(toml_path)
		if not toml_path_str.strip('.'):
			raise ValueError(f"No 'toml_path' was specified: {toml_path_str!r}")

		toml_data = self.toml_data
		if not toml_data:
			raise ValueError(f"Data-dict (for {toml_path_str!r}) cannot be empty: {toml_data!r}")
		if not isinstance(toml_data, _Mapping):
			raise TypeError(f"Not a data-dict (for {toml_path_str!r}): {toml_data!r}")

	def _get_field_from_toml_data(
		self, field_path: str, what: str, msg_if_required: str = ''
	) -> _A:
		"""Internal: walk through the ``toml_data`` dict and extract the config's field value by a given path."""
		self.__validate_essential_args()
		toml_path_str = str(self.toml_path)

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

	def read_dynamic_field(self) -> str:
		"""Get a value of the TOML field specified in ``dynamic_field``."""
		dynamic_field = self.dynamic_field
		value = self._get_field_from_toml_data(
			dynamic_field,
			what='Dynamic field',
			msg_if_required="when version is dynamic and backend is unknown/fallback/auto"
		)
		toml_path_str = str(self.toml_path)
		if not isinstance(value, str):
			raise TypeError(f"Dynamic field ({dynamic_field!r} in {toml_path_str!r}) is not a string: {value!r}")
		if not value:
			raise ValueError(f"Dynamic field ({dynamic_field!r} in {toml_path_str!r}) is empty")
		if not value.strip():
			raise ValueError(f"Dynamic field ({dynamic_field!r} in {toml_path_str!r}) can't contain only whitespaces: {value!r}")
		return value

	def __post_init__(self):
		self.__validate_essential_args()
		if type(self) is not DynDetector:
			return

		# We're actually trying to instantiate the `DynDetector` itself - ensure dynamic field is valid:
		self.read_dynamic_field()

	# TODO: directly coded here for py3.6 support, to be replaced with dataclass use for 3.7+:

	def __init__(self, *args, **kwargs):
		super(DynDetector, self).__init__(*args, **kwargs)
		self.__post_init__()


_T_Detector = _TypeVar('T_Detector', bound=DynDetector)
