"""
This module provides the SerialDevice class

Example:
    from serial_device import SerialDevice

    device = SerialDevice(port='/dev/ttyUSB0', baudrate=9600)
    device.query('HELLO') # => "Hello"

---
Nelson Darkwah Oppong, December 2017
n@darkwahoppong.com

"""

from time import time


class SerialDevice(object):
    # @port the name of serial device to connect
    # @baudrate the speed to use
    # @max_log_length maximal number of log records
    #   to keep in memory
    # @log_file if not None, must be either
    #   * a string a path to communication log file to write
    #   * or a file-like object to write the log to
    #   If None: log file is not written.
    def __init__(self, port='/dev/ttyUSB0', baudrate=115200,
                 max_log_length=100, log_file=None, **kwargs):
        from serial import serial_for_url

        self._serial = serial_for_url(port, baudrate=baudrate, **kwargs)
        self.timeout = kwargs["timeout"] if "timeout" in kwargs else None

        self._log = []
        self._max_log_length = max_log_length

        self._log_file = None
        self._log_file_path = None

        if log_file is not None:
            if isinstance(log_file, str):
                self._log_file_path = os.path.abspath(log_file)
                self._log_file = open(self._log_file_path)
            else:
                self._log_file = log_file

    def __del__(self):
        if self._log_file is not None:
            close(self._log_file)

    def _logger(self, kind, message):
        log = self._log

        # remove first entry if log is too long
        if len(log) > self._max_log_length:
            log.pop(0)

        entry = {
            'kind': kind,
            'time': time(),
            'content': message
        }

        if self._log_file is not None:
            self._log_file.write(str(entry))

        log.append(entry)

    def open(self):
        """
        Open serial connection to device.
        """
        self._serial.open()

    def close(self):
        """
        Close serial connection to device.
        """
        self._serial.close()

    def query(self, cmd):
        """
        Send command to device and immediately read response

        Args:
            cmd (bytes): Command

        Returns:
            bytes: The response from the device
        """
        self.write(cmd)
        return self.read()

    def write(self, data, line_ending=b'\n'):
        """
        Send data to device.

        Args:
            data (bytes): Data
        """
        if not self.is_open:
            self.open()

        string = data + line_ending
        self._logger('write', string)

        self._serial.write(string)

    def read(self):
        if not self.is_open:
            self.open()

        result = None
        start = time()
        while result is None:
            result = self._serial.readline()
            if (self.timeout is not None) and (time() - start > self.timeout):
                result = None
                break
        self._logger('read', result)

        return result

    @property
    def is_open(self):
        """Status of the serial connection (boolean)"""
        return self._serial.is_open

    # RETURNS: last max_log_length entries of communication log
    #   as a new-line separated text
    @property
    def dump_log(self):
        """Log entries (list)"""
        out = ""
        for rec in self._log:
            out += "%s\n" % str(rec)
        return out

    # Prints the dump_log.
    def print_dump_log(self):
        print("------- MTD415 COMMUNICATION LOG DUMP ---------")
        print(self.dump_log)
        print("--------- COMMUNICATION LOG DUMP END ----------")
