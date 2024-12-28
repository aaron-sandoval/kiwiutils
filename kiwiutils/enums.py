import abc
from enum import Enum
from collections import defaultdict
from typing import Iterable, Type, Any

import aenum
import pandas as pd
import numpy as np

from kiwiutils.kiwilib import IsDataclass, getAllSubclasses

class AenumABCMeta(abc.ABCMeta, aenum.EnumMeta):
    pass


class DataclassValuedEnum(abc.ABC, aenum.Enum, metaclass=AenumABCMeta):
    """
    ABC for Enum classes whose members have dataclass-like attribute access.
    Each subclass is associated with a dataclass containing the member attributes.
    However, the Enum values for each member are NOT the dataclass instances.
    Instead, these are defined in `_enum_data`.
    This is to overcome a drawback of storing complex data directly in the Enum member values.
    In this implementation, the properties of the dataclass and the member's data to be updated
    without invalidating any previous instance of that enum stored in files.
    When the enum is read from a file, its attributes will effectively be updated to the latest values in `_enum_data`.
    """
    # TODO: public method that can be called in `subclass._get_dataclass` which auto-builds a new dataclass inherited from its superclasses' dataclasses

    @staticmethod
    @abc.abstractmethod
    def _get_dataclass() -> IsDataclass:
        """
        Returns a existing dataclass or constructs and returns a new one.
        Called only once by __init_subclass__ and stored in `cls.dataclass`.
        This dataclass holds all the attributes of the outer class enum members.
        It's recommended that these dataclasses be frozen.
        """
        pass

    @classmethod
    @abc.abstractmethod
    def _enum_data(cls) -> dict[Enum, 'Type[DataclassValuedEnum]._DATACLASS']:
        """
        Instantiates dataclass members associated with each enum member.
        This method contains the data that would traditionally be located in the enum definitions.
        :param c: Will always be passed `cls._DATACLASS`. Only here so that each subclass need not make that reference.
        :return: Mapping from enum members to their data.
        """
        pass

    @staticmethod
    def _init_DVE(cls: Type['DataclassValuedEnum']):
        """
        Decorator procedure to initialize the internal dataclass and fields of a DataclassValuedEnum subclass.
        Never call this method on DataclassValuedEnum itself. Only used for its (abstract) subclasses.
        """
        cls.dataclass = cls._get_dataclass()
        cls._data = cls._enum_data()
        if cls._data is not None:
            for fld in cls.dataclass.__dataclass_fields__:
                setattr(cls, fld, property(lambda slf, f=fld: getattr(slf._data[slf], f)))
        return cls

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls = cls._init_DVE(cls)

    def __repr__(self):
        return ''.join(['<', str(self), ': ', repr(self.value), '; ', repr(self._data[self]), '>'])

    def asdict(self):
        return self._data[self].__dict__


class HierarchicalEnum(abc.ABC):
    """
    A superclass for defining a hierarchical enum-like data structure using a class hierarchy.
    Supports any hierarchical structure supported by python class inheritance.
    This is, namely, any directed acyclic graph (DAG), as long as there is a single root node in the DAG (root_class).
    """

    @classmethod
    @abc.abstractmethod
    def root_class(cls) -> type:
        """
        Return the common superclass for all nodes in the hierarchy.
        Default behavior is to return the member of the hierarchy which is a direct subclass of HierarchicalEnum.
        In the case of multiple inheritance, this will return the first superclass in the MRO which is a direct
        subclass of HierarchicalEnum.
        """
        return HierarchicalEnum

    def __repr__(self):
        if type(self) == self.root_class():
            return type(self).__name__
        else:
            # return type(self).__bases__[0]().__repr__() + '.' + type(self).__name__
            return self.root_class().__name__ + '.' + type(self).__name__
            # return type(self).__name__

    def __eq__(self, other):
        return type(self) == type(other)

    def __hash__(self):
        return hash(repr(type(self)))

    def __iter__(self):
        return iter([c() for c in getAllSubclasses(type(self))])

    def __len__(self):
        return len(getAllSubclasses(type(self)))



def enum_counts(ser: pd.Series, enumCls: type[Enum] | Iterable[type[HierarchicalEnum]]) -> pd.DataFrame:
    """
    Counts the instances of `enumCls` members in a Series of iterables.
    :param ser: Series of Iterable[Any], possibly containing members of `enumCls`.
    :param enumCls: An Enum subclass whose instances in the rows of `ser` are to be counted
    :return: A integer-valued DataFrame with columns as all the members of `enumCls`.
    Data is the count of instances of that enum member in that row in `ser`.
    """
    def make_count(lst: Iterable, enumCls1: Iterable[type]) -> list[int]:
        if len(lst) == 0:
            lst.extend([0] * len(enumCls1))
            return lst
        countDict = defaultdict(lambda: 0)
        for item in lst:
            countDict[item] += 1
        lst.clear()
        lst.extend([countDict[e] for e in enumCls1])

    enumList = list(enumCls)
    ser.apply(make_count, args=(enumList,))
    out = pd.DataFrame(np.vstack(ser.values), index=ser.index)
    # TODO: bugfix: rename goes crazy on SocialGroups
    if isinstance(enumList[0], HierarchicalEnum):
        target_names = [str(a) for a in enumList]
    else:
        target_names = [str(e) for e in list(enumList)]
    return out.rename(columns=dict(zip(range(len(enumList)), target_names)))
