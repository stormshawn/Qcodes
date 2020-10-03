import json
import time
from collections import OrderedDict
from datetime import datetime
from unittest import TestCase

import pytest
import numpy as np

from qcodes.utils.helpers import (is_sequence, permissive_range, wait_secs,
                                  DelegateAttributes,
                                  strip_attrs, full_class,
                                  named_repr, make_sweep, is_sequence_of,
                                  compare_dictionaries, NumpyJSONEncoder,
                                  partial_with_docstring,
                                  create_on_off_val_mapping)
from qcodes.logger.logger import LogCapture
from qcodes.utils.helpers import attribute_set_to


class TestMakeSweep(TestCase):
    def test_good_calls(self):
        swp = make_sweep(1, 3, num=6)
        assert swp == [1, 1.4, 1.8, 2.2, 2.6, 3]

        swp = make_sweep(1, 3, step=0.5)
        assert swp == [1, 1.5, 2, 2.5, 3]

        # with step, test a lot of combinations with weird fractions
        # to make sure we don't fail on a rounding error
        for r in np.linspace(1, 4, 15):
            for steps in range(5, 55, 6):
                step = r / steps
                swp = make_sweep(1, 1 + r, step=step)
                assert len(swp) == steps + 1
                assert swp[0] == 1
                assert swp[-1] == 1 + r

    def test_bad_calls(self):
        with pytest.raises(AttributeError):
            make_sweep(1, 3, num=3, step=1)

        with pytest.raises(ValueError):
            make_sweep(1, 3)

        # this first one should succeed
        make_sweep(1, 3, step=1)
        # but if we change step slightly (more than the tolerance of
        # 1e-10 steps) it will fail.
        with pytest.raises(ValueError):
            make_sweep(1, 3, step=1.00000001)
        with pytest.raises(ValueError):
            make_sweep(1, 3, step=0.99999999)


class TestWaitSecs(TestCase):
    def test_bad_calls(self):
        bad_args = [None, datetime.now()]
        for arg in bad_args:
            with pytest.raises(TypeError):
                wait_secs(arg)

    def test_good_calls(self):
        for secs in [0.001, 0.003, 0.01, 0.03, 0.1, 0.3, 1]:
            finish_clock = time.perf_counter() + secs
            secs_out = wait_secs(finish_clock)
            assert secs_out > secs - 1e-4
            # add a tiny offset as this test may fail if
            # otherwise if the two calls to perf_counter are close
            # enough to return the same result as a + b - a cannot
            # in general be assumed to be <= b in floating point
            # math (here a is perf_counter() and b is the wait time
            assert secs_out <= secs+1e-14

    def test_warning(self):
        with LogCapture() as logs:
            secs_out = wait_secs(time.perf_counter() - 1)
        assert secs_out == 0

        assert logs.value.count('negative delay') == 1, logs.value


class TestDelegateAttributes(TestCase):
    def test_delegate_dict(self):
        class ToDict(DelegateAttributes):
            delegate_attr_dicts = ['d']
            apples = 'green'

        td = ToDict()
        # td.d doesn't exist yet
        with pytest.raises(AttributeError):
            td.d

        # but you can still get other attributes
        assert td.apples == 'green'

        d = {'apples': 'red', 'oranges': 'orange'}
        td.d = d

        # you can get the whole dict still
        assert td.d == d

        # class attributes override the dict
        assert td.apples == 'green'

        # instance attributes do too
        td.apples = 'rotten'
        assert td.apples == 'rotten'

        # other dict attributes come through and can be added on the fly
        assert td.oranges == 'orange'
        d['bananas'] = 'yellow'
        assert td.bananas == 'yellow'

        # missing items still raise AttributeError, not KeyError
        with pytest.raises(AttributeError):
            td.kiwis

        # all appropriate items are in dir() exactly once
        for attr in ['apples', 'oranges', 'bananas']:
            assert dir(td).count(attr) == 1

    def test_delegate_dicts(self):
        class ToDicts(DelegateAttributes):
            delegate_attr_dicts = ['d', 'e']

        td = ToDicts()
        e = {'cats': 12, 'dogs': 3}
        td.e = e

        # you can still access the second one when the first doesn't exist
        with pytest.raises(AttributeError):
            td.d
        assert td.e == e
        assert td.cats == 12

        # the first beats out the second
        td.d = {'cats': 42, 'chickens': 1000}
        assert td.cats == 42

        # but you can still access things only in the second
        assert td.dogs == 3

        # all appropriate items are in dir() exactly once
        for attr in ['cats', 'dogs', 'chickens']:
            assert dir(td).count(attr) == 1

    def test_delegate_object(self):
        class Recipient:
            black = '#000'
            white = '#fff'

        class ToObject(DelegateAttributes):
            delegate_attr_objects = ['recipient']
            gray = '#888'

        to_obj = ToObject()
        recipient = Recipient()

        # recipient not connected yet but you can look at other attributes
        with pytest.raises(AttributeError):
            to_obj.recipient
        assert to_obj.gray == '#888'

        to_obj.recipient = recipient

        # now you can access recipient through to_obj
        assert to_obj.black == '#000'

        # to_obj overrides but you can still access other recipient attributes
        to_obj.black = '#444'  # "soft" black
        assert to_obj.black == '#444'
        assert to_obj.white == '#fff'

        # all appropriate items are in dir() exactly once
        for attr in ['black', 'white', 'gray']:
            assert dir(to_obj).count(attr) == 1

    def test_delegate_objects(self):
        class R1:
            a = 1
            b = 2
            c = 3

        class R2:
            a = 4
            b = 5
            d = 6

        class ToObjects(DelegateAttributes):
            delegate_attr_objects = ['r1', 'r2']
            a = 0
            e = 7
            r1 = R1()
            r2 = R2()

        to_objs = ToObjects()

        # main object overrides recipients
        assert to_objs.a == 0
        assert to_objs.e == 7

        # first object overrides second
        assert to_objs.b == 2
        assert to_objs.c == 3

        # second object gets the rest
        assert to_objs.d == 6

        # missing attributes still raise correctly
        with pytest.raises(AttributeError):
            to_objs.f

        # all appropriate items are in dir() exactly once
        for attr in 'abcde':
            assert dir(to_objs).count(attr) == 1

    def test_delegate_both(self):
        class Recipient:
            rock = 0
            paper = 1
            scissors = 2

        my_recipient_dict = {'paper': 'Petta et al.', 'year': 2005}

        class ToBoth(DelegateAttributes):
            delegate_attr_objects = ['recipient_object']
            delegate_attr_dicts = ['recipient_dict']
            rock = 'Eiger'
            water = 'Lac Leman'
            recipient_dict = my_recipient_dict
            recipient_object = Recipient()

        tb = ToBoth()

        # main object overrides recipients
        assert tb.rock == 'Eiger'
        assert tb.water == 'Lac Leman'

        # dict overrides object
        assert tb.paper == 'Petta et al.'
        assert tb.year == 2005

        # object comes last
        assert tb.scissors == 2

        # missing attributes still raise correctly
        with pytest.raises(AttributeError):
            tb.ninja

        # all appropriate items are in dir() exactly once
        for attr in ['rock', 'paper', 'scissors', 'year', 'water']:
            assert dir(tb).count(attr) == 1


class A:
    x = 5
    y = 6


class BadKeysDict(dict):
    def keys(self):
        raise RuntimeError('you can\'t have the keys!')


class NoDelDict(dict):
    def __delitem__(self, item):
        raise KeyError('get your hands off me!')


class TestStripAttrs(TestCase):
    def test_normal(self):
        a = A()
        a.x = 15
        a.z = 25

        strip_attrs(a)

        assert a.x == 5
        assert not hasattr(a, 'z')
        assert a.y == 6

    def test_pathological(self):
        # just make sure this never errors, since it's meant to be used
        # during deletion
        a = A()
        a.__dict__ = BadKeysDict()

        a.fruit = 'mango'
        with pytest.raises(RuntimeError):
            a.__dict__.keys()

        strip_attrs(a)
        # no error, but the attribute is still there
        assert a.fruit == 'mango'

        a = A()
        a.__dict__ = NoDelDict()
        s = 'can\'t touch this!'
        a.x = s

        assert a.x == s
        # not sure how this doesn't raise, but it doesn't.
        # with self.assertRaises(KeyError):
        #     del a.x

        strip_attrs(a)
        assert a.x == s


class TestClassStrings(TestCase):
    # use a standard library object so we don't need to worry about where
    # this test is run. A little annoying to find one we can mutate though!
    def setUp(self):
        self.j = json.JSONEncoder()

    def test_full_class(self):
        assert full_class(self.j) == 'json.encoder.JSONEncoder'

    def test_named_repr(self):
        id_ = id(self.j)
        self.j.name = 'Peppa'
        assert named_repr(self.j) == \
                         f'<json.encoder.JSONEncoder: Peppa at {id_}>'


class TestIsSequenceOf(TestCase):
    def test_simple(self):
        good = [
            # empty lists pass without even checking that we provided a
            # valid type spec
            ([], None), ((), None),
            ([1, 2, 3], int),
            ((1, 2, 3), int),
            ([1, 2.0], (int, float)),
            ([{}, None], (type(None), dict)),
            # omit type (or set None) and we don't test type at all
            ([1, '2', dict],),
            ([1, '2', dict], None)
        ]
        for args in good:
            with self.subTest(args=args):
                assert is_sequence_of(*args)

        bad = [
            (1,),
            (1, int),
            ([1, 2.0], int),
            ([1, 2], float),
            ([1, 2], (float, dict))
        ]
        for args in bad:
            with self.subTest(args=args):
                assert not is_sequence_of(*args)

        # second arg, if provided, must be a type or tuple of types
        # failing this doesn't return False, it raises an error
        with pytest.raises(TypeError):
            is_sequence_of([1], 1)
        with pytest.raises(TypeError):
            is_sequence_of([1], (1, 2))

    def test_depth(self):
        good = [
            ([1, 2], int, 1),
            ([[1, 2], [3, 4]], int, 2),
            ([[1, 2.0], []], (int, float), 2),
            ([[[1]]], int, 3),
            ([[1, 2], [3, 4]], None, 2)
        ]
        for args in good:
            with self.subTest(args=args):
                assert is_sequence_of(*args)

        bad = [
            ([1], int, 2),
            ([[1]], int, 1),
            ([[1]], float, 2)
        ]
        for args in bad:
            with self.subTest(args=args):
                assert not is_sequence_of(*args)

    def test_shape(self):
        good = [
            ([1, 2], int, (2,)),
            ([[1, 2, 3], [4, 5, 6.0]], (int, float), (2, 3)),
            ([[[1]]], int, (1, 1, 1)),
            ([[1], [2]], None, (2, 1)),
            # if you didn't have `list` as a type, the shape of this one
            # would be (2, 2) - that's tested in bad below
            ([[1, 2], [3, 4]], list, (2,)),
            (((0, 1, 2), ((0, 1), (0, 1), (0, 1))), tuple, (2,)),
            (((0, 1, 2), ((0, 1), (0, 1), (0, 1))), (tuple, int), (2, 3))
        ]
        for obj, types, shape in good:
            with self.subTest(obj=obj):
                assert is_sequence_of(obj, types, shape=shape)

        bad = [
            ([1], int, (2,)),
            ([[1]], int, (1,)),
            ([[1, 2], [1]], int, (2, 2)),
            ([[1]], float, (1, 1)),
            ([[1, 2], [3, 4]], int, (2, )),
            (((0, 1, 2), ((0, 1), (0, 1))), (tuple, int), (2, 3))
        ]
        for obj, types, shape in bad:
            with self.subTest(obj=obj):
                assert not is_sequence_of(obj, types, shape=shape)

    def test_shape_depth(self):
        # there's no reason to provide both shape and depth, but
        # we allow it if they are self-consistent
        with pytest.raises(ValueError):
            is_sequence_of([], int, depth=1, shape=(2, 2))

        assert not is_sequence_of([1], int, depth=1, shape=(2,))
        assert is_sequence_of([1], int, depth=1, shape=(1,))


# tests related to JSON encoding
class TestJSONencoder(TestCase):

        def test_python_types(self):
            e = NumpyJSONEncoder()

            # test basic python types
            od = OrderedDict()
            od['a'] = 0
            od['b'] = 1
            testinput = [None, True, False, 10, float(10.), 'hello',
                         od]
            testoutput = ['null', 'true', 'false', '10', '10.0', '"hello"',
                          '{"a": 0, "b": 1}']

            for d, r in zip(testinput, testoutput):
                v = e.encode(d)
                if type(d) == dict:
                    assert v == r
                else:
                    assert v == r

        def test_complex_types(self):
            e = NumpyJSONEncoder()
            assert e.encode(complex(1, 2)) == \
                             '{"__dtype__": "complex", "re": 1.0, "im": 2.0}'
            assert e.encode(np.complex(1, 2)) == \
                             '{"__dtype__": "complex", "re": 1.0, "im": 2.0}'
            assert e.encode(np.complex64(complex(1, 2))) == \
                             '{"__dtype__": "complex", "re": 1.0, "im": 2.0}'

        def test_numpy_int_types(self):
            e = NumpyJSONEncoder()

            numpy_ints = (np.int, np.int_, np.int8, np.int16, np.int32,
                          np.int64, np.intc, np.intp,
                          np.uint, np.uint8, np.uint16, np.uint32, np.uint64,
                          np.uintc, np.uintp)

            for int_type in numpy_ints:
                assert e.encode(int_type(3)) == '3'

        def test_numpy_float_types(self):
            e = NumpyJSONEncoder()

            numpy_floats = (np.float, np.float_, np.float16, np.float32,
                            np.float64)

            for float_type in numpy_floats:
                assert e.encode(float_type(2.5)) == '2.5'

        def test_numpy_bool_type(self):
            e = NumpyJSONEncoder()

            assert e.encode(np.bool_(True)) == 'true'
            assert e.encode(np.int8(5) == 5) == 'true'
            assert e.encode(np.array([8, 5]) == 5) == '[false, true]'

        def test_numpy_array(self):
            e = NumpyJSONEncoder()

            assert e.encode(np.array([1, 0, 0])) == \
                             '[1, 0, 0]'

            assert e.encode(np.arange(1.0, 3.0, 1.0)) == \
                             '[1.0, 2.0]'

            assert e.encode(np.meshgrid((1, 2), (3, 4))) == \
                             '[[[1, 2], [1, 2]], [[3, 3], [4, 4]]]'

        def test_non_serializable(self):
            """
            Test that non-serializable objects are serialzed to their
            string representation
            """
            e = NumpyJSONEncoder()

            class Dummy:
                def __str__(self):
                    return 'i am a dummy with \\ slashes /'

            assert e.encode(Dummy()) == \
                             '"i am a dummy with \\\\ slashes /"'

        def test_object_with_serialization_method(self):
            """
            Test that objects with `_JSONEncoder` method are serialized via
            calling that method
            """
            e = NumpyJSONEncoder()

            class Dummy:
                def __init__(self):
                    self.confession = 'a_dict_addict'

                def __str__(self):
                    return 'me as a string'

                def _JSONEncoder(self):
                    return {'i_am_actually': self.confession}

            assert e.encode(Dummy()) == \
                             '{"i_am_actually": "a_dict_addict"}'


class TestCompareDictionaries(TestCase):
    def test_same(self):
        # NOTE(alexcjohnson): the numpy array and list compare equal,
        # even though a list and tuple would not. See TODO in
        # compare_dictionaries.
        a = {'a': 1, 2: [3, 4, {5: 6}], 'b': {'c': 'd'}, 'x': np.array([7, 8])}
        b = {'a': 1, 2: [3, 4, {5: 6}], 'b': {'c': 'd'}, 'x': [7, 8]}

        match, err = compare_dictionaries(a, b)
        assert match
        assert err == ''

    def test_bad_dict(self):
        # NOTE(alexcjohnson):
        # this is a valid dict, but not good JSON because the tuple key cannot
        # be converted into a string.
        # It throws an error in compare_dictionaries, which is likely what we
        # want, but we should be aware of it.
        a = {(5, 6): (7, 8)}
        with pytest.raises(TypeError):
            compare_dictionaries(a, a)

    def test_key_diff(self):
        a = {'a': 1, 'c': 4}
        b = {'b': 1, 'c': 4}

        match, err = compare_dictionaries(a, b)

        assert not match
        assert 'Key d1[a] not in d2' in err
        assert 'Key d2[b] not in d1' in err

        # try again with dict names for completeness
        match, err = compare_dictionaries(a, b, 'a', 'b')

        assert not match
        assert 'Key a[a] not in b' in err
        assert 'Key b[b] not in a' in err

    def test_val_diff_simple(self):
        a = {'a': 1}
        b = {'a': 2}

        match, err = compare_dictionaries(a, b)

        assert not match
        assert 'Value of "d1[a]" ("1", type"<class \'int\'>") not same as' in err
        assert '"d2[a]" ("2", type"<class \'int\'>")' in err

    def test_val_diff_seq(self):
        # NOTE(alexcjohnson):
        # we don't dive recursively into lists at the moment.
        # Perhaps we want to? Seems like list equality does a deep comparison,
        # so it's not necessary to get ``match`` right, but the error message
        # could be more helpful if we did.
        a = {'a': [1, {2: 3}, 4]}
        b = {'a': [1, {5: 6}, 4]}

        match, err = compare_dictionaries(a, b)

        assert not match
        assert 'Value of "d1[a]" ("[1, {2: 3}, 4]", ' \
                      'type"<class \'list\'>") not same' in err
        assert '"d2[a]" ("[1, {5: 6}, 4]", type"<class \'list\'>")' in \
                      err

    def test_nested_key_diff(self):
        a = {'a': {'b': 'c'}}
        b = {'a': {'d': 'c'}}

        match, err = compare_dictionaries(a, b)

        assert not match
        assert 'Key d1[a][b] not in d2' in err
        assert 'Key d2[a][d] not in d1' in err


class TestAttributeSetToContextManager(TestCase):
    """
    Test attribute_set_to context manager
    """

    class X:
        y = 0

    def test_attribute_set_to_value(self):
        """Test setting attribute to a value"""
        x = self.X()
        x.y = 1

        assert 1 == x.y

        with attribute_set_to(x, 'y', 2):
            assert 2 == x.y

        assert 1 == x.y

    def test_attribute_set_to_object(self):
        """Test setting attribute to an object"""
        x = self.X()
        original_object = self.X()
        x.y = original_object

        assert original_object == x.y
        assert original_object is x.y

        new_object = self.X()
        with attribute_set_to(x, 'y', new_object):
            assert new_object == x.y
            assert new_object is x.y

        assert original_object == x.y
        assert original_object is x.y


class TestPartialWithDocstring(TestCase):
    """Test the sane partial function"""
    def test_main(self):
        def f():
            pass

        docstring = "some docstring"
        g = partial_with_docstring(f, docstring)
        assert g.__doc__ == docstring


class TestCreateOnOffValMapping(TestCase):
    """Test function that creates val mapping for on/off parameters"""

    def test_values_of_mapping_are_only_the_given_two(self):
        val_mapping = create_on_off_val_mapping(on_val='666', off_val='000')
        values_set = set(list(val_mapping.values()))
        assert values_set == {'000', '666'}

    def test_its_inverse_maps_only_to_booleans(self):
        from qcodes.instrument.parameter import invert_val_mapping

        inverse = invert_val_mapping(
            create_on_off_val_mapping(on_val='666', off_val='000'))

        assert inverse == {'666': True, '000': False}


@pytest.mark.parametrize(('on_val', 'off_val'),
                         ((1, 0),
                          (1.0, 0.0),
                          ('1', '0'),
                          (True, False)
                         ))
def test_create_on_off_val_mapping_for(on_val, off_val):
    """
    Explicitly test ``create_on_off_val_mapping`` function
    by covering some of the edge cases of ``on_val`` and ``off_val``
    """
    val_mapping = create_on_off_val_mapping(on_val=on_val,
                                            off_val=off_val)

    values_list = list(set(val_mapping.values()))

    assert len(values_list) == 2
    assert on_val in values_list
    assert off_val in values_list

    assert val_mapping[1] is on_val
    assert val_mapping[True] is on_val
    assert val_mapping['1'] is on_val
    assert val_mapping['ON'] is on_val
    assert val_mapping['On'] is on_val
    assert val_mapping['on'] is on_val

    assert val_mapping[0] is off_val
    assert val_mapping[False] is off_val
    assert val_mapping['0'] is off_val
    assert val_mapping['OFF'] is off_val
    assert val_mapping['Off'] is off_val
    assert val_mapping['off'] is off_val

    from qcodes.instrument.parameter import invert_val_mapping
    inverse = invert_val_mapping(val_mapping)

    assert inverse[on_val] is True
    assert inverse[off_val] is False
