from functools import lru_cache
from typing import Callable
import abc
import copy

from kiwiutils.kiwilib import getAllSubclasses
from kiwiutils.enums import HierarchicalEnum, DataclassValuedEnum, AenumABCMeta


class Aliasable(abc.ABC):
    def alias(self, locale: str = None):
        if locale is None:
            # locale = self.aliasFuncs()[self.defaultLocale]
            locale = self._defaultLocale
        return self._aliasFuncs[locale](self)

    @classmethod
    @abc.abstractmethod
    def aliasFuncs(cls) -> dict[str, Callable[['Aliasable'], str]]:
        """
        Defines a map between locale strings, e.g., 'en_US', and Callables returning the localization of an instance.
        Callables must match the API of no-arg methods in a class, taking only a single `self` arg.
        """
        return {}  # Essentially this defines abstract static class data

    @classmethod
    def defaultLocale(cls) -> str:
        # if not hasattr(cls, '_defaultLocale'):
        #     cls._defaultLocale: str = next(iter(cls.aliasFuncs().keys()))
        return cls._defaultLocale

    @classmethod
    def setDefaultLocale(cls, locale: str):
        cls._defaultLocale = locale

    @staticmethod
    def initAliasable(cls_: type):
        cls_._aliasFuncs = cls_.aliasFuncs()
        cls_._defaultLocale = next(iter(cls_._aliasFuncs.keys()))

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if "__isabstractmethod__" not in cls.aliasFuncs.__dict__ or not cls.aliasFuncs.__isabstractmethod__:
            # Only for subclasses which have implemented `aliasFuncs`
            cls.initAliasable(cls)
        # if not any([hasattr(base, '_subclasses') and cls._subclasses == base._subclasses for base in cls.__bases__]):
        #     cls._subclasses: List[Type['Aliasable']] = []
        #     for c in cls.__bases__:  # Register subclasses since Aliasable.__subclasses__() doesn't seem to do so reliably
        #         if issubclass(c, Aliasable):
        #             c._subclasses.append(cls)

    # @classmethod
    # def subclasses(cls):
    #     return cls._subclasses


class AliasableEnum(Aliasable, DataclassValuedEnum, metaclass=AenumABCMeta):
    @classmethod
    @lru_cache
    def aliases_to_members_deep(
            cls,
            alias_func: Callable[['AliasableEnum', str], str] = lambda x, loc: x.alias(loc)
    ) -> dict[str, 'AliasableEnum']:
        """
        Returns a mapping from aliases to enum members for the members of all subclasses of `cls`.
        Warning: In the case of duplicate keys among multiple subclasses,
        the function behavior is undefined for which enum member is returned in the value.
        """
            # return {sub: {a.alias(locale): a for a in sub} for sub in getAllSubclasses(cls, includeSelf=True)}
        return {alias_func(a): a for sub in getAllSubclasses(cls, includeSelf=True) for a in sub}


class AliasableHierEnum(Aliasable, HierarchicalEnum):
    @classmethod
    def root_class(cls) -> type:
        """
        Return the common superclass for all nodes in the hierarchy.
        Default behavior is to return the member of the hierarchy which is a direct subclass of HierarchicalEnum.
        In the case of multiple inheritance, this will return the first superclass in the MRO which is a direct
        subclass of HierarchicalEnum.
        """
        if cls._ROOT_CLASS is not None:
            return cls._ROOT_CLASS
        elif cls == AliasableHierEnum:
            return cls
        elif AliasableHierEnum in cls.__bases__:
            cls._ROOT_CLASS = cls
            return cls
        else:
            return cls.__bases__[0].root_class()

    @classmethod
    @lru_cache
    def aliases_to_members(
            cls,
            alias_func: Callable[['AliasableHierEnum', str], str] = lambda x, loc: x.alias(loc)
    ) -> dict[str, 'AliasableHierEnum']:
        """
        Returns a mapping from aliases to enum members for the members of all subclasses of `cls`.
        Warning: In the case of duplicate keys in the subclass DAG,
        the function behavior is undefined for which enum member is returned in the value.
        :param alias_func: Alias function. Defaults to standard alias, but others might be wanted, like `builtins._e`.
        """
        out = {alias_func(sub()): sub for sub in getAllSubclasses(cls)}
        if len(out) < len(getAllSubclasses(cls)):
            subs: dict[type, str] = {c: c().alias(locale) for c in getAllSubclasses(cls)}
            for sub, alias in copy.copy(subs).items():
                if alias in out:
                    subs.pop(sub)
                    out.pop(alias)
            raise ValueError(f'The subclass DAG of {cls} contains duplicate localizations: {subs.keys()}')
        return out