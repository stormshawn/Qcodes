import time
from datetime import datetime, timedelta

import pytest

from qcodes.instrument.parameter import Parameter, _BaseParameter
from .conftest import NOT_PASSED, BetterGettableParam, SettableParam


def test_get_from_cache_does_not_trigger_real_get_if_get_if_invalid_false():
    """
    assert that calling get on the cache with get_if_invalid=False does
    not trigger a get of the parameter when parameter has expired due to max_val_age
    """
    param = BetterGettableParam(name="param", max_val_age=1)
    param.get()
    assert param._get_count == 1
    # let the cache expire
    time.sleep(2)
    param.cache.get(get_if_invalid=False)
    assert param._get_count == 1


def test_initial_set_with_without_cache():
    value = 43
    # setting the initial value triggers a set
    param1 = SettableParam(name="param", initial_value=value)
    assert param1._set_count == 1
    assert param1.cache.get(get_if_invalid=False) == value
    # setting the cache does not trigger a set
    param2 = SettableParam(name="param", initial_cache_value=value)
    assert param2._set_count == 0
    assert param2.cache.get(get_if_invalid=False) == value


def test_set_initial_and_initial_cache_raises():
    with pytest.raises(SyntaxError, match="`initial_value` and `initial_cache_value`"):
        Parameter(name="param", initial_value=1, initial_cache_value=2)


def test_get_cache():
    time_resolution = time.get_clock_info('time').resolution
    sleep_delta = 2 * time_resolution

    # Create a gettable parameter
    local_parameter = Parameter('test_param', set_cmd=None, get_cmd=None)
    before_set = datetime.now()
    time.sleep(sleep_delta)
    local_parameter.set(1)
    time.sleep(sleep_delta)
    after_set = datetime.now()

    # Check we return last set value, with the correct timestamp
    assert local_parameter.cache.get() == 1
    assert before_set < local_parameter.cache.timestamp < after_set

    # Check that updating the value updates the timestamp
    time.sleep(sleep_delta)
    local_parameter.set(2)
    assert local_parameter.cache.get() == 2
    assert local_parameter.cache.timestamp > after_set


def test_get_cache_raw_value():
    # To have a simple distinction between raw value and value of the
    # parameter lets create a parameter with an offset
    p = Parameter('p', set_cmd=None, get_cmd=None, offset=42)
    assert p.cache.timestamp is None

    # Initially, the parameter's raw value is None
    assert p.cache.raw_value is None

    # After setting the parameter to some value, the
    # raw_value attribute of the cache should return the raw_value
    p(3)
    assert p.cache.timestamp is not None
    assert p.cache.get() == 3
    assert p.cache.raw_value == 3 + 42


def test_get_cache_unknown():
    """
    Test that cache get on a parameter that has not been acquired will
    trigger a get
    """
    value = 1
    local_parameter = BetterGettableParam('test_param', set_cmd=None,
                                          get_cmd=None)
    # fake a parameter that has a value but never been get/set to mock
    # an instrument.
    local_parameter.cache._value = value
    local_parameter.cache._raw_value = value
    assert local_parameter.cache.timestamp is None
    before_get = datetime.now()
    assert local_parameter._get_count == 0
    assert local_parameter.cache.get() == value
    assert local_parameter._get_count == 1
    # calling get above will call get since TS is None
    # and the TS will therefore no longer be None
    assert local_parameter.cache.timestamp is not None
    assert local_parameter.cache.timestamp >= before_get
    # calling cache.get now will not trigger get
    assert local_parameter.cache.get() == value
    assert local_parameter._get_count == 1


def test_get_cache_known():
    """
    Test that cache.get on a parameter that has a known value will not
    trigger a get
    """
    value = 1
    local_parameter = BetterGettableParam('test_param', set_cmd=None,
                                          get_cmd=None)
    # fake a parameter that has a value acquired 10 sec ago
    start = datetime.now()
    set_time = start - timedelta(seconds=10)
    local_parameter.cache._update_with(
        value=value, raw_value=value, timestamp=set_time)
    assert local_parameter._get_count == 0
    assert local_parameter.cache.timestamp == set_time
    assert local_parameter.cache.get() == value
    # calling cache.get above will not call get since TS is set and
    # max_val_age is not
    assert local_parameter._get_count == 0
    assert local_parameter.cache.timestamp == set_time


def test_get_cache_no_get():
    """
    Test that cache.get on a parameter that does not have get is handled
    correctly.
    """
    local_parameter = Parameter('test_param', set_cmd=None, get_cmd=False)
    # The parameter does not have a get method.
    with pytest.raises(AttributeError):
        local_parameter.get()
    # get_latest will fail as get cannot be called and no cache
    # is available
    with pytest.raises(RuntimeError):
        local_parameter.cache.get()
    value = 1
    local_parameter.set(value)
    assert local_parameter.cache.get() == value

    local_parameter2 = Parameter('test_param2', set_cmd=None,
                                 get_cmd=False, initial_value=value)
    with pytest.raises(AttributeError):
        local_parameter2.get()
    assert local_parameter2.cache.get() == value


def test_set_raw_value_on_cache():
    value = 1
    scale = 10
    local_parameter = BetterGettableParam('test_param',
                                          set_cmd=None,
                                          scale=scale)
    before = datetime.now()
    local_parameter.cache._set_from_raw_value(value*scale)
    after = datetime.now()
    assert local_parameter.cache.get(get_if_invalid=False) == value
    assert local_parameter.cache.raw_value == value * scale
    assert local_parameter.cache.timestamp >= before
    assert local_parameter.cache.timestamp <= after


def test_max_val_age():
    value = 1
    start = datetime.now()
    local_parameter = BetterGettableParam('test_param',
                                          set_cmd=None,
                                          max_val_age=1,
                                          initial_value=value)
    assert local_parameter.cache.max_val_age == 1
    assert local_parameter._get_count == 0
    assert local_parameter.cache.get() == value
    assert local_parameter._get_count == 0
    # now fake the time stamp so get should be triggered
    set_time = start - timedelta(seconds=10)
    local_parameter.cache._update_with(
        value=value, raw_value=value, timestamp=set_time)
    # now that ts < max_val_age calling get_latest should update the time
    assert local_parameter.cache.timestamp == set_time
    assert local_parameter.cache.get() == value
    assert local_parameter._get_count == 1
    assert local_parameter.cache.timestamp >= start


def test_no_get_max_val_age():
    """
    Test that cache.get on a parameter with max_val_age set and
    no get cmd raises correctly.
    """
    value = 1
    with pytest.raises(SyntaxError):
        _ = Parameter('test_param', set_cmd=None,
                      get_cmd=False,
                      max_val_age=1, initial_value=value)


def test_no_get_max_val_age_runtime_error(get_if_invalid):
    """
    _BaseParameter does not have a check on creation time that
    no get_cmd is mixed with max_val_age since get_cmd could be added
    in a subclass. Here we create a subclass that does not add a get
    command and also does not implement the check for max_val_age
    """
    value = 1

    class LocalParameter(_BaseParameter):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.set_raw = lambda x: x
            self.set = self._wrap_set(self.set_raw)

    local_parameter = LocalParameter('test_param',
                                     None,
                                     max_val_age=1)
    start = datetime.now()
    set_time = start - timedelta(seconds=10)
    local_parameter.cache._update_with(
        value=value, raw_value=value, timestamp=set_time)

    if get_if_invalid is True:
        with pytest.raises(RuntimeError, match="max_val_age` is not supported"):
            local_parameter.cache.get(get_if_invalid=get_if_invalid)
    elif get_if_invalid == NOT_PASSED:
        with pytest.raises(RuntimeError, match="max_val_age` is not supported"):
            local_parameter.cache.get()
    else:
        assert local_parameter.cache.get(get_if_invalid=get_if_invalid) == 1


def test_no_get_timestamp_none_runtime_error(get_if_invalid):
    """
    Test that a parameter that has never been
    set, cannot be get and does not support
    getting raises a RuntimeError.
    """
    local_parameter = Parameter('test_param', get_cmd=False)

    if get_if_invalid is True:
        with pytest.raises(RuntimeError, match="Value of parameter test_param"):
            local_parameter.cache.get(get_if_invalid=get_if_invalid)
    elif get_if_invalid == NOT_PASSED:
        with pytest.raises(RuntimeError, match="Value of parameter test_param"):
            local_parameter.cache.get()
    else:
        assert local_parameter.cache.get(get_if_invalid=get_if_invalid) is None
