# -*- coding: utf-8 -*-
"""Text parser plugin for Advanced Packaging Tool (APT) History log files."""

import pyparsing

from dfdatetime import time_elements as dfdatetime_time_elements

from plaso.containers import events
from plaso.lib import errors
from plaso.parsers import text_parser
from plaso.parsers.text_plugins import interface


class APTHistoryLogEventData(events.EventData):
  """APT History log event data.

  Attributes:
    command (str): command.
    command_line (str): command line.
    end_time (dfdatetime.DateTimeValues): date and time the end of the log
        entry was added.
    error (str): reported error.
    packages (str): packages that were affected.
    requester (str): user requesting the activity.
    start_time (dfdatetime.DateTimeValues): date and time the start of
        the log entry was added.
  """

  DATA_TYPE = 'linux:apt_history_log:entry'

  def __init__(self):
    """Initializes event data."""
    super(APTHistoryLogEventData, self).__init__(data_type=self.DATA_TYPE)
    self.command = None
    self.command_line = None
    self.end_time = None
    self.error = None
    self.packages = None
    self.requester = None
    self.start_time = None


class APTHistoryLogTextPlugin(interface.TextPlugin):
  """Text parser plugin for Advanced Packaging Tool (APT) History log files."""

  NAME = 'apt_history'

  DATA_FORMAT = 'Advanced Packaging Tool (APT) History log file'

  ENCODING = 'utf-8'

  # APT History log lines can be very long.
  _MAXIMUM_LINE_LENGTH = 65536

  _TWO_DIGITS = pyparsing.Word(pyparsing.nums, exact=2).setParseAction(
      text_parser.PyParseIntCast)

  _FOUR_DIGITS = pyparsing.Word(pyparsing.nums, exact=4).setParseAction(
      text_parser.PyParseIntCast)

  _APTHISTORY_DATE_TIME = pyparsing.Group(
      _FOUR_DIGITS + pyparsing.Suppress('-') +
      _TWO_DIGITS + pyparsing.Suppress('-') +
      _TWO_DIGITS +
      _TWO_DIGITS + pyparsing.Suppress(':') +
      _TWO_DIGITS + pyparsing.Suppress(':') +
      _TWO_DIGITS)

  # Start-Date: 2019-07-10  16:38:12
  _RECORD_START = (
      # APT History logs may start with empty lines
      pyparsing.ZeroOrMore(pyparsing.lineEnd()) +
      pyparsing.Literal('Start-Date:') +
      _APTHISTORY_DATE_TIME.setResultsName('start_date') +
      pyparsing.lineEnd())

  _RECORD_BODY = (
      pyparsing.MatchFirst([
          pyparsing.Literal('Commandline:'),
          pyparsing.Literal('Downgrade:'),
          pyparsing.Literal('Error:'),
          pyparsing.Literal('Install:'),
          pyparsing.Literal('Purge:'),
          pyparsing.Literal('Remove:'),
          pyparsing.Literal('Requested-By:'),
          pyparsing.Literal('Upgrade:')]) +
      pyparsing.restOfLine())

  # End-Date: 2019-07-10  16:38:10
  _RECORD_END = (
      pyparsing.Literal('End-Date:') +
      _APTHISTORY_DATE_TIME.setResultsName('end_date') +
      pyparsing.OneOrMore(pyparsing.lineEnd()))

  _LINE_STRUCTURES = [
      ('record_start', _RECORD_START),
      ('record_body', _RECORD_BODY),
      ('record_end', _RECORD_END)]

  _SUPPORTED_KEYS = frozenset([key for key, _ in _LINE_STRUCTURES])

  def __init__(self):
    """Initializes a text parser plugin."""
    super(APTHistoryLogTextPlugin, self).__init__()
    self._event_data = None

  def _ParseRecord(self, parser_mediator, key, structure):
    """Parses a pyparsing structure.

    Args:
      parser_mediator (ParserMediator): mediates interactions between parsers
          and other components, such as storage and dfVFS.
      key (str): name of the parsed structure.
      structure (pyparsing.ParseResults): tokens from a parsed log line.

    Raises:
      ParseError: when the structure type is unknown.
    """
    if key not in self._SUPPORTED_KEYS:
      raise errors.ParseError(
          'Unable to parse record, unknown structure: {0:s}'.format(key))

    if key == 'record_start':
      try:
        self._ParseRecordStart(structure)
      except errors.ParseError as exception:
        parser_mediator.ProduceExtractionWarning(
            'unable to parse record start with error: {0!s}'.format(exception))

    elif key == 'record_body':
      self._ParseRecordBody(structure)

    elif key == 'record_end':
      try:
        self._ParseRecordEnd(parser_mediator, structure)
      except errors.ParseError as exception:
        parser_mediator.ProduceExtractionWarning(
            'unable to parse record end with error: {0!s}'.format(exception))

  def _ParseRecordBody(self, structure):
    """Parses a line from the body of a log record.

    Args:
      structure (pyparsing.ParseResults): structure of tokens derived from
          a log entry.

    Raises:
      ParseError: when the date and time value is missing.
    """
    command, body = structure

    if command == 'Commandline:':
      self._event_data.command_line = body.strip()

    elif command == 'Error:':
      self._event_data.error = body.strip()

    elif command == 'Requested-By:':
      self._event_data.requester = body.strip()

    elif command in (
        'Downgrade:', 'Install:', 'Purge:', 'Remove:', 'Upgrade:'):
      self._event_data.command = command[:-1]
      self._event_data.packages = body.strip()

  def _ParseRecordEnd(self, parser_mediator, structure):
    """Parses the last line of a log record.

    Args:
      parser_mediator (ParserMediator): mediates interactions between parsers
          and other components, such as storage and dfVFS.
      structure (pyparsing.ParseResults): structure of tokens derived from
          a log entry.
    """
    time_elements_structure = self._GetValueFromStructure(structure, 'end_date')

    self._event_data.end_time = self._ParseTimeElements(time_elements_structure)

    parser_mediator.ProduceEventData(self._event_data)

    self._ResetState()

  def _ParseRecordStart(self, structure):
    """Parses the first line of a log record.

    Args:
      structure (pyparsing.ParseResults): structure of tokens derived from
          a log entry.
    """
    self._event_data = APTHistoryLogEventData()

    time_elements_structure = self._GetValueFromStructure(
        structure, 'start_date')

    self._event_data.start_time = self._ParseTimeElements(
        time_elements_structure)

  def _ParseTimeElements(self, time_elements_structure):
    """Parses date and time elements of a log line.

    Args:
      time_elements_structure (pyparsing.ParseResults): date and time elements
          of a log line.

    Returns:
      dfdatetime.TimeElements: date and time value.

    Raises:
      ParseError: if a valid date and time value cannot be derived from
          the time elements.
    """
    try:
      year, month, day_of_month, hours, minutes, seconds = (
          time_elements_structure)

      # Ensure time_elements_tuple is not a pyparsing.ParseResults otherwise
      # copy.deepcopy() of the dfDateTime object will fail on Python 3.8 with:
      # "TypeError: 'str' object is not callable" due to pyparsing.ParseResults
      # overriding __getattr__ with a function that returns an empty string
      # when named token does not exist.
      time_elements_tuple = (year, month, day_of_month, hours, minutes, seconds)
      date_time = dfdatetime_time_elements.TimeElements(
          time_elements_tuple=time_elements_tuple)

      # APT History logs store date and time values in local time.
      date_time.is_local_time = True

      return date_time

    except (TypeError, ValueError) as exception:
      raise errors.ParseError(
          'Unable to parse time elements with error: {0!s}'.format(exception))

  def _ResetState(self):
    """Resets stored values."""
    self._event_data = None

  def CheckRequiredFormat(self, parser_mediator, text_file_object):
    """Check if the log record has the minimal structure required by the plugin.

    Args:
      parser_mediator (ParserMediator): mediates interactions between parsers
          and other components, such as storage and dfVFS.
      text_file_object (dfvfs.TextFile): text file.

    Returns:
      bool: True if this is the correct parser, False otherwise.
    """
    try:
      line = self._ReadLineOfText(text_file_object)
    except UnicodeDecodeError:
      return False

    try:
      parsed_structure = self._RECORD_START.parseString(line)
    except pyparsing.ParseException:
      return False

    time_elements_structure = self._GetValueFromStructure(
        parsed_structure, 'start_date')

    try:
      self._ParseTimeElements(time_elements_structure)
    except errors.ParseError:
      return False

    self._ResetState()

    return True


text_parser.SingleLineTextParser.RegisterPlugin(APTHistoryLogTextPlugin)
