# -*- coding: utf-8 -*-
"""
This module provides the MTD415TDevice class.

See https://www.thorlabs.de/thorproduct.cfm?partnumber=MTD415T for more details
on the actual temperature controller.

Example:
    from mtd415t_device import MTD415TDevice
    from time import sleep

    temp_controller = MTD415TDevice(auto_save=True)
    temp_controller.temp_setpoint = 15.025
    sleep(10)
    temp_controller.temp # => 15.020

---
Nelson Darkwah Oppong, December 2017
n@darkwahoppong.com
"""

from time import sleep, time

try:
    from .helpers import validate_is_float_or_int, validate_is_in_range
    from .serial_device import SerialDevice
except (ValueError, ImportError) as e:
    # in case we use the file by importing it as a file, not as a module
    # this is relevan if used not from installed system modules
    print("MTD415T library not installed as a system module"
          "using raw file imports to bring the things up")

    import os
    import imp

    current_source_dir = os.path.dirname(os.path.abspath(__file__))
    helpers_module = imp.load_source(
            "helpers", os.path.join(current_source_dir
                                    , "helpers.py"))
    validate_is_float_or_int = helpers_module.validate_is_float_or_int
    validate_is_in_range = helpers_module.validate_is_in_range

    serial_device_module = imp.load_source(
            "serial_device", os.path.join(current_source_dir
                                          , "serial_device.py"))
    SerialDevice = serial_device_module.SerialDevice

class MTD415TDevice(SerialDevice):
    """
    This class allows controlling and configuring the digital temperature
    controller MTD415T from Thorlabs. You need to connect the temperature
    controller to a serial port on your computer to get started.

    Args:
        port (string): Serial port, e. g. '/dev/ttyUSB0'
        auto_save (boolean, optional): Enable or disable automatic write to
            non-volatile memory after any change
    """

    # error bits, see MTD415T datasheet, p. 18
    _ERRORS = {
        0:  'not enabled',
        1:  'internal temperature too high',
        2:  'thermal latch-up',
        3:  'cycling time too small',
        4:  'no sensor',
        5:  'no tec',
        6:  'tec polarity reversed',
        13: 'value out of range',
        14: 'invalid command'
    }

    # @auto_save if set to True, the SW will ask chip to flash
    #   **EVERY** change of parameters, which basically will
    #   destroy the flash memory pretty fast, so don't use it
    #   unless you really need it.
    # @communication_log the log to use, see also: SerialDevice.__init__
    #   documentation
    # @minimal_query_interval_s minimal time since end of a query and
    #   a beginning of the next one, if query is requested earlier,
    #   then we will throttle a bit to not to overhelm the chip
    #   (otherwise it will complain on "bad command")
    def __init__(self, port, auto_save=False
                 , communication_log=None
                 , minimal_query_interval_s=0.01
                 , *args, **kwargs):
        self._auto_save = auto_save
        self.last_query_time_s = time()
        self.min_query_interval_s = 0.01
        super(MTD415TDevice, self).__init__(
                port, baudrate=115200, log_file=communication_log
                , **kwargs)

    def query(self, setting, retry=False):
        """
        Retrieve setting

        Args:
            setting (string): Setting name, generally a single character
            retry (boolean, optional): Retry failed query after 100ms,
                                       False by default

        Returns:
            string: The setting value
        """

        # NOTE: here we will slow down a bit, it looks like device
        #   can not always fit into the exchange at max speed, so
        #   we will introduce some delays between requests:
        idle_time_s = self.min_query_interval_s - (time() - self.last_query_time_s)
        if idle_time_s > 0:
            sleep(idle_time_s)

        if type(setting) == str:
            setting = setting.encode('ascii')

        cmd = setting + b'?'
        result = super(MTD415TDevice, self).query(cmd)
        self.last_query_time_s = time()

        if retry is True and (result == b'unknown command\n' or result is None):
            sleep(0.1)  # wait 100ms before retrying the same command
            return self.query(setting, retry=True)
        else:
            return result

    def write(self, data, *args, **kwargs):
        """
        Writes data

        Args:
            data (string): Data
        """
        if type(data) == str:
            data = data.encode('ascii')

        return super(MTD415TDevice, self).write(data, *args, **kwargs)

    def set(self, setting, value):
        """
        Set a setting to the given integer value

        Args:
            setting (string): Setting name, generally single character
            value (int): Set value
        """
        value = int(value)
        value_str = '{:d}'.format(value).encode('ascii')
        cmd = '{}'.format(setting).encode('ascii') + value_str
        self.write(cmd)

        # NOTE: the device answers with the set value, example, if
        #       to set TEC current limit to: 0.5 A  (500 mA units)
        #       device will respond with following exactly:
        #
        #           500
        #
        #       and if set wrong value, say TEC current limit to
        #       0.1 A it will answer with following exactly:
        #
        #           value out of range (200...2000 mA)
        confirmation = self.read().strip()
        if confirmation is None:
            self.print_dump_log()
            raise RuntimeError("Timeout for setting %s to %s"
                               %(str(setting), value_str))
        if confirmation != value_str:
            self.print_dump_log()
            raise ValueError("Device reported an error in '%s' setting to %s, error: %s"
                             % (str(setting), value_str, str(confirmation)))

        if self._auto_save:
            print("WARNING: Using auto-save mode! This warning persists.")
            self.save()

    def save(self):
        """Save settings to non-volatile memory"""
        print("WARNING: Saving config to flash memory.")
        self.write('M')

        # ensure returned data is removed from the buffer
        self.read()

    def clear_errors(self):
        """Clears error flags"""
        self.write('c')

        # ensure returned data is removed from the buffer
        self.read()

    @property
    def auto_save(self):
        """Auto save (boolean)"""
        return self._auto_save

    @auto_save.setter
    def auto_save(self, value):
        self._auto_save = (True if value is True else False)

    @property
    def idn(self):
        """Product name and version number (string)"""
        res = self.query('m', True)
        return res.decode('ascii') if res is not None else "<timeout>"

    @property
    def uid(self):
        """Unique device identifier (string)"""
        res = self.query('u', True)
        return res.decode('ascii') if res is not None else "<timeout>"

    @property
    def error_flags(self):
        """Error flags from the error register of the device (tuple, LSB
        first)"""
        val = self.query('E', True)
        if val is None:
            return "<timeout>"
        err = int(val.decode('ascii'))
        return tuple(c == '1' for c in reversed('{:016b}'.format(err)))

    @property
    def errors(self):
        """Errors from the error register of the device (tuple)"""
        flags = self.error_flags
        if isinstance(flags , str):
            return flags;
        errors = []
        for idx, err in self._ERRORS.items():
            if flags[idx] is False:
                continue

            errors.append(err)

        return tuple(errors)

    @property
    def tec_current_limit(self):
        """TEC current limit in A (float, >= 0.200 and <= 2.000)"""
        value = self.query('L', True)
        if value is None:
            return "<timeout>"
        return float(value) / 1e3

    @tec_current_limit.setter
    def tec_current_limit(self, value):
        validate_is_float_or_int(value, 'TEC current limit')

        validate_is_in_range(value, 0.2, 2, 'TEC current limit', ' A')
        value = round(value*1e3)

        self.set('L', value)

    @property
    def tec_current(self):
        """TEC current in A (float)"""
        value = self.query('A', True)
        if value is None:
            return "<timeout>"
        return float(value) / 1e3

    @property
    def tec_voltage(self):
        """TEC voltage in V (float)"""
        value = self.query('U')
        if value is None:
            return "<timeout>"
        return float(value) / 1e3

    @property
    def temp(self):
        """Current temperature in ° C (float)"""
        value = self.query('Te', True)
        if value is None:
            return "<timeout>"
        return float(value) / 1e3

    @property
    def temp_setpoint(self):
        """Temperature setpoint in ° C (float, >= 5.000 and <= 45.000)"""
        value = self.query('T', True)
        if value is None:
            return "<timeout>"
        return float(value) / 1e3

    @temp_setpoint.setter
    def temp_setpoint(self, value):
        validate_is_float_or_int(value, 'Temperature setpoint')

        validate_is_in_range(value, 5, 45, 'Temperature setpoint', '° C')
        value = round(value*1e3)

        self.set('T', value)

    @property
    def status_temp_window(self):
        """Temperature window for the status pin in K (float, >= 1e-3 and <=
        32.768)"""
        value = self.query('W', True)
        if value is None:
            return "<timeout>"
        return float(value) / 1e3

    @status_temp_window.setter
    def status_temp_window(self, value):
        validate_is_float_or_int(value, 'Status temperature window')

        validate_is_in_range(value, 1e-3, 32.768,
                             'Status temperature window', '° C')
        value = round(value*1e3)

        self.set('W', value)

    @property
    def status_delay(self):
        """Delay for changing the status pin in s (int, >=1 and <= 32768)"""
        value = self.query(b'd', True)
        if value is None:
            return "<timeout>"
        return int(value)

    @status_delay.setter
    def status_delay(self, value):
        validate_is_float_or_int(value, 'Status delay')

        value = int(value)
        validate_is_in_range(value, 1, 32768, 'Status delay', ' s')

        self.set('d', value)

    @property
    def critical_gain(self):
        """Critical gain in A/K (float, >=10e-3 and <= 100)"""
        value = self.query('G', True)
        if value is None:
            return "<timeout>"
        return float(value) / 1e3

    @critical_gain.setter
    def critical_gain(self, value):
        validate_is_float_or_int(value, 'Critical gain')

        validate_is_in_range(value, 10e-3, 100, 'Critical gain', ' A/K')
        value = round(value*1e3)

        self.set('G', value)

    @property
    def critical_period(self):
        """Critical period in s (float, >=100e-3 and <= 100.000)"""
        value = self.query('O', True)
        if value is None:
            return "<timeout>"
        return float(value) / 1e3

    @critical_period.setter
    def critical_period(self, value):
        validate_is_float_or_int(value, 'Critical period')

        validate_is_in_range(value, 100e-3, 100e3, 'Critical period', ' s')
        value = round(value*1e3)

        self.set('O', value)

    @property
    def cycling_time(self):
        """Cycling time in s (float, >= 1e-3 and <= 1.000)"""
        value = self.query('C', True)
        if value is None:
            return "<timeout>"
        return float(value) / 1e3

    @cycling_time.setter
    def cycling_time(self, value):
        validate_is_float_or_int(value, 'Cycling time')

        validate_is_in_range(value, 1e-3, 1, 'Cycling time', ' s')
        value = round(value*1e3)

        self.set('C', value)

    @property
    def p_gain(self):
        """Proportional gain in A/K (float, >=0 and <= 100.000)"""
        value = self.query('P', True)
        if value is None:
            return "<timeout>"
        return float(value) / 1e3

    @p_gain.setter
    def p_gain(self, value):
        validate_is_float_or_int(value, 'P gain')

        validate_is_in_range(value, 0, 100, 'P gain', ' A/K')
        value = round(value*1e3)

        self.set('P', value)

    @property
    def i_gain(self,):
        """Integrator gain in A/(K x s) (float, >=0 and <= 100.000)"""
        value = self.query('I', True)
        if value is None:
            return "<timeout>"
        return float(value) / 1e3

    @i_gain.setter
    def i_gain(self, value):
        validate_is_float_or_int(value, 'I gain')

        validate_is_in_range(value, 0, 100, 'I gain', ' A/(K x s)')
        value = round(value*1e3)

        self.set('I', value)

    @property
    def d_gain(self):
        """Differential gain in (A x s)/K (float, >=0 and <= 100.000)"""
        value = self.query('D', True)
        if value is None:
            return "<timeout>"
        return float(value) / 1e3

    @d_gain.setter
    def d_gain(self, value):
        validate_is_float_or_int(value, 'D gain')

        validate_is_in_range(value, 0, 100, 'D gain', ' (A x s)/K')
        value = round(value*1e3)

        self.set('D', value)
