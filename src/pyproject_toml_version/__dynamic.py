# encoding: utf-8
"""Dynamic-version detectors"""

from pathlib import Path as _Path

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
		self.__require_to_reimplement('version_str')
		raise NotImplementedError('TODO')

	@classmethod
	def __require_to_reimplement(cls, method_name: str):
		if cls is DynDetector:
			return
		raise NotImplementedError(f"{cls!r} subclass must reimplement {method_name!r} method")

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
		return DynDetector


_T_Detector = _TypeVar('T_Detector', bound=DynDetector)
