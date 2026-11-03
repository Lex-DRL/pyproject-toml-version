# encoding: utf-8

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Defines ``_ensure_required_overrides()``: it verifies that a subclass overrides the base class attributes."""

from typing_clean import *

_T_cls_attr_type = _U[_Type[classmethod], _Type[staticmethod], _Type[callable], _Type[object], None]

__class_static_method_set = {classmethod, staticmethod}


def _is_valid_method_override(parent_attr_type: _T_cls_attr_type, subclass_attr_type: _T_cls_attr_type) -> bool:
	if parent_attr_type is subclass_attr_type:
		return True
	if parent_attr_type in __class_static_method_set and subclass_attr_type in __class_static_method_set:
		return True
	return False


_printable_type: _Dict[_T_cls_attr_type, str] = {
	classmethod: 'classmethod',
	staticmethod: 'staticmethod',
	callable: 'regular method',
	object: 'field/attribute',
	None: 'missing',
}


def _required_type_id(attr_type: _T_cls_attr_type) -> _T_cls_attr_type:
	return classmethod if attr_type is staticmethod else attr_type


class __Mismatch(_NamedTuple):
	"""Data for a missing/wrong override."""
	name: str
	parent_type: _T_cls_attr_type
	override_type: _T_cls_attr_type

	def format(self) -> str:
		name = self.name
		parent_str = _printable_type[self.parent_type]
		subclass_str = _printable_type[self.override_type]

		is_missing = self.__is_missing_override()
		if is_missing:
			return f'{name} ({parent_str}, {subclass_str})'
		if is_missing is False:
			return f"{name} (can't exist, {subclass_str})"
		assert is_missing is None
		return f"{name} ({parent_str} expected, {subclass_str} override)"

	# def format_only_parent(self) -> str:
	# 	type_str = _printable_type[self.parent_type]
	# 	return f'{self.name} ({type_str})'
	#
	# def format_only_override(self) -> str:
	# 	type_str = _printable_type[self.override_type]
	# 	return f'{self.name} ({type_str})'

	def __is_missing_override(self) -> _O[bool]:
		"""3 states:

		- ``True``: no override while it **should be** there;
		- ``False``: attrib defined while should be **absent**;
		- ``None``: defined, but as a **wrong type** of class member.
		"""
		parent_type = self.parent_type
		override_type = self.override_type
		if _is_valid_method_override(parent_type, override_type):
			raise ValueError(f"Not a mismatch: {self!r}")
		assert parent_type is not override_type
		if override_type is None:
			return True
		if parent_type is None:
			return False
		return None

	@staticmethod
	def format_all(parent_class: type, sub_class: type, mismatches: _List['__Mismatch']) -> str:
		if not mismatches:
			return ''

		mismatch_couples = {
			(_required_type_id(m.parent_type), _required_type_id(m.override_type))
			for m in mismatches
		}
		if len(mismatch_couples) > 1:
			assert len(mismatches) > 1
			joined = ', '.join(m.format() for m in mismatches)
			return f"{sub_class!r} must override {parent_class!r} attributes: {joined}"

		assert len(mismatch_couples) == 1
		# The same type of mismatch among all
		s = 's' if len(mismatches) > 1 else ''
		names = ', '.join(m.name for m in mismatches)
		first = mismatches[0]
		is_missing = first.__is_missing_override()
		expected_what = _printable_type[first.parent_type]
		if is_missing:
			return f"{sub_class!r} must override {expected_what}{s} from {parent_class!r}: {names}"
		if is_missing is False:
			return f"{sub_class!r} is forbidden to define the following class attribute{s} (by {parent_class!r}): {names}"
		assert is_missing is None
		actual_what = _printable_type[first.override_type]
		not_what = '' if first.override_type is None else f", not {actual_what}{s}"
		return f"{sub_class!r} must override {parent_class!r} attribute{s} as {expected_what}{s}{not_what}: {names}"


class __RawClassAttr(_NamedTuple):
	"""
	We can't just use ``getattr()`` on classes: it will return bound methods,
	and we need the actual classmethod/staticmethod objects, so we need to walk the MRO.

	So this service class contains such data.
	"""
	attr_value: _A
	found_in_class: _O[type]  # The latest-in-chain class, where the current attr value actually lives
	defined_in_classes: _FrozenSet[type]  # All the MRO classes defining the same attribute

	@classmethod
	def get(cls, _cls: type, attr_name: str) -> '__RawClassAttr':
		value: _A = None
		found_in_class: _O[type] = None
		defined_in_classes: _List[type] = list()
		for mro_class in _cls.__mro__:
			if not isinstance(mro_class, type):
				raise TypeError(f"MRO for {_cls!r} isn't a class: {mro_class!r}")
			mro_vars = vars(mro_class)
			if attr_name in mro_vars:
				if found_in_class is None:
					found_in_class = mro_class
					value = mro_vars[attr_name]
				defined_in_classes.append(mro_class)
		return cls(value, found_in_class, frozenset(defined_in_classes))

	def raw_attr_type(self) -> _T_cls_attr_type:
		if self.found_in_class is None:
			return None
		attr_value = self.attr_value
		if isinstance(attr_value, classmethod):
			return classmethod
		if isinstance(attr_value, staticmethod):
			return staticmethod
		if callable(attr_value):
			return callable
		return object

	def subclass_attr_override_type(self: '__RawClassAttr', parent_attr: '__RawClassAttr') -> _T_cls_attr_type:
		found_in_class = self.found_in_class
		if found_in_class is None or found_in_class in parent_attr.defined_in_classes:
			return None
		return self.raw_attr_type()


def _ensure_required_overrides(sub_class: type, parent_class: type, required_overrides: _Iterable[str]) -> None:
	"""For each attribute name from ``required_overrides``:

	- If it's missing as class member on ``parent_class``, it must also be missing on ``sub_class``;
	- If it's defined on ``parent_class``, ``sub_class`` must override it, with the same scope
	  (regular method, static-/class-method, class-level field);

	Raise a single combined ``TypeError`` for all overrides which requirements aren't satisfied.
	"""
	if sub_class is parent_class:
		return

	mismatches: _List[__Mismatch] = []

	for name in required_overrides:
		parent_attr = __RawClassAttr.get(parent_class, name)
		parent_type = parent_attr.raw_attr_type()

		subclass_attr = __RawClassAttr.get(sub_class, name)
		subclass_type = subclass_attr.subclass_attr_override_type(parent_attr)

		if not _is_valid_method_override(parent_type, subclass_type):
			mismatches.append(__Mismatch(name, parent_type, subclass_type))

	msg = __Mismatch.format_all(parent_class, sub_class, mismatches)
	if msg:
		raise TypeError(msg)
