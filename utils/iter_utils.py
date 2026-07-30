import math
import itertools
import operator
from itertools import *
import collections

from icecream import ic


def flatten(iterables):
    return (elem for iterable in iterables for elem in iterable)


    # return first "True" element from iterable
    # taken from https://github.com/hynek/first/
def first_true(iterable, default=None, key=None):
    if key is None:
        for el in iterable:
            if el:
                return el
    else:
        for el in iterable:
            if key(el):
                return el

    return default


# inputs just need to be iterable, output is tuple
def add_tuple(*iterables):
#    ic(list(iterables))
    return tuple(sum(p) for p in zip(*iterables))

products = math.prod

#def multiply_tuple(a, b):
#    return tuple(aa * bb for (aa, bb) in zip(a, b))

def multiply(*iterables):
    return (products(p) for p in zip(*iterables))


# this version should allow multiplying elements of more than 2 iterables
def multiply_tuple(*iterables):
    return tuple(products(p) for p in zip(*iterables))


def multiply_scalar_tuple(a, b):
    return tuple(aa * b for aa in a)


def true_divide_scalar_tuple(a, b):
    return tuple(aa // b for aa in a)


    # let's you perform operations on all elements of a tuple
    # e.g. materials + robots * wait - robot_cost
    # other sequence of same length or scalar
    # could also handle and, or, xor, not, inversion, ordering, negation, modulo, shifting, exponent, round, floor, ceil,
    # could do another class based on array that also allows +=, -=, etc.
class arithtuple(tuple):
    def __add__(self, other):
        try:
            return arithtuple(map(operator.add, self, other))
        except TypeError as e:
            # handle case of operation on scalar
            return arithtuple(map(operator.add, self, (other,) * len(self)))

    def __sub__(self, other):
        try:
            return arithtuple(map(operator.sub, self, other))
        except TypeError as e:
            # handle case of operation on scalar
            return arithtuple(map(operator.sub, self, (other,) * len(self)))

    def __mul__(self, other):
        try:
            return arithtuple(map(operator.mul, self, other))
        except TypeError as e:
                # handle case of operation on scalar
            try:
                return arithtuple(map(operator.mul, self, (other,) * len(self)))
            except TypeError as e:
                ic(other)
                raise
    def __truediv__(self, other):
        try:
            return arithtuple(map(operator.truediv, self, other))
        except TypeError as e:
                # handle case of operation on scalar
            return arithtuple(map(operator.truediv, self, (other,) * len(self)))

    def __floordiv__(self, other):
        try:
            return arithtuple(map(operator.floordiv, self, other))
        except TypeError as e:
                # handle case of operation on scalar
            try:
                return arithtuple(map(operator.floordiv, self, (other,) * len(self)))
            except TypeError as e:
                ic(other)
                raise

    def __mod__(self, other):
        try:
            return arithtuple(map(operator.mod, self, other))
        except TypeError as e:
                # handle case of operation on scalar
            return arithtuple(map(operator.mod, self, (other,) * len(self)))

    def _replace(self, index, val):
        return arithtuple(self[0:index] + (val,) + self[index+1:])


