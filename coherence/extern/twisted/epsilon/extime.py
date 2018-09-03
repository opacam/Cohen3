# -*- test-case-name: epsilon.test.test_extime -*-
"""
Extended date/time formatting and miscellaneous functionality.

See the class 'Time' for details.
"""

import datetime
import re

from email.utils import formatdate, parsedate_tz

_EPOCH = datetime.datetime.utcfromtimestamp(0)


def cmp(x, y):
    """
    Replacement for built-in function cmp that was removed in Python 3

    Compare the two objects x and y and return an integer according to
    the outcome. The return value is negative if x < y, zero if x == y
    and strictly positive if x > y.
    """

    return (x > y) - (x < y)


class InvalidPrecision(Exception):
    """
    L{Time.asHumanly} was passed an invalid precision value.
    """


def sanitizeStructTime(struct):
    """
    Convert struct_time tuples with possibly invalid values to valid
    ones by substituting the closest valid value.
    """
    maxValues = (9999, 12, 31, 23, 59, 59)
    minValues = (1, 1, 1, 0, 0, 0)
    newstruct = []
    for value, maxValue, minValue in zip(struct[:6], maxValues, minValues):
        newstruct.append(max(minValue, min(value, maxValue)))
    return tuple(newstruct) + struct[6:]


def _timedeltaToSignHrMin(offset):
    """
    Return a (sign, hour, minute) triple for the offset described by timedelta.

    sign is a string, either "+" or "-". In the case of 0 offset, sign is "+".
    """
    minutes = round((offset.days * 3600000000 * 24
                     + offset.seconds * 1000000
                     + offset.microseconds)
                    / 60000000.0)
    if minutes < 0:
        sign = '-'
        minutes = -minutes
    else:
        sign = '+'
    return (sign, minutes // 60, minutes % 60)


def _timedeltaToSeconds(offset):
    """
    Convert a datetime.timedelta instance to simply a number of seconds.

    For example, you can specify purely second intervals with timedelta's
    constructor:

        >>> td = datetime.timedelta(seconds=99999999)

    but then you can't get them out again:

        >>> td.seconds
        35199

    This allows you to:

        >>> import coherence.twisted.epsilon.extime
        >>> epsilon.extime._timedeltaToSeconds(td)
        99999999.0

    @param offset: a L{datetime.timedelta} representing an interval that we
    wish to know the total number of seconds for.

    @return: a number of seconds
    @rtype: float
    """
    return ((offset.days * 60*60*24) +
            (offset.seconds) +
            (offset.microseconds * 1e-6))


class FixedOffset(datetime.tzinfo):
    _zeroOffset = datetime.timedelta()

    def __init__(self, hours, minutes):
        self.offset = datetime.timedelta(minutes = hours * 60 + minutes)

    def utcoffset(self, dt):
        return self.offset

    def tzname(self, dt):
        return _timedeltaToSignHrMin(self.offset)

    def dst(self, tz):
        return self._zeroOffset

    def __repr__(self):
        return '<%s.%s object at 0x%x offset %r>' % (
            self.__module__, type(self).__name__, id(self), self.offset)


class Time(object):
    """An object representing a well defined instant in time.

    A Time object unambiguously addresses some time, independent of timezones,
    contorted base-60 counting schemes, leap seconds, and the effects of
    general relativity. It provides methods for returning a representation of
    this time in various ways that a human or a programmer might find more
    useful in various applications.

    Every Time instance has an attribute 'resolution'. This can be ignored, or
    the instance can be considered to address a span of time. This resolution
    is determined by the value used to initalize the instance, or the
    resolution of the internal representation, whichever is greater. It is
    mostly useful when using input formats that allow the specification of
    whole days or weeks. For example, ISO 8601 allows one to state a time as,
    "2005-W03", meaning "the third week of 2005". In this case the resolution
    is set to one week. Other formats are considered to express only an instant
    in time, such as a POSIX timestamp, because the resolution of the time is
    limited only by the hardware's representation of a real number.

    Timezones are significant only for instances with a resolution greater than
    one day. When the timezone is insignificant, the result of methods like
    asISO8601TimeAndDate is the same for any given tzinfo parameter. Sort order
    is determined by the start of the period in UTC. For example, "today" sorts
    after "midnight today, central Europe", and before "midnight today, US
    Eastern". For applications that need to store a mix of timezone dependent
    and independent instances, it may be wise to store them separately, since
    the time between the start and end of today in the local timezone may not
    include the start of today in UTC, and thus not independent instances
    addressing the whole day. In other words, the desired sort order (the one
    where just "Monday" sorts before any more precise time in "Monday", and
    after any in "Sunday") of Time instances is dependant on the timezone
    context.

    Date arithmetic and boolean operations operate on instants in time, not
    periods. In this case, the start of the period is used as the value, and
    the result has a resolution of 0.

    For containment tests with the 'in' operator, the period addressed by the
    instance is used.

    The methods beginning with 'from' are constructors to create instances from
    various formats. Some of them are textual formats, and others are other
    time types commonly found in Python code.

    Likewise, methods beginning with 'as' return the represented time in
    various formats. Some of these methods should try to reflect the resolution
    of the instance. However, they don't yet.

    For formats with both a constructor and a formatter, d == fromFu(d.asFu())

    @type resolution: datetime.timedelta
    @ivar resolution: the length of the period to which this instance could
    refer. For example, "Today, 13:38" could refer to any time between 13:38
    until but not including 13:39. In this case resolution would be
    timedelta(minutes=1).
    """

    # the instance variable _time is the internal representation of time. It
    # is a naive datetime object which is always UTC. A UTC tzinfo would be
    # great, if one existed, and anyway it complicates pickling.

    class Precision(object):
        MINUTES = object() 
        SECONDS = object()

    _timeFormat = {
            Precision.MINUTES: '%I:%M %p',
            Precision.SECONDS: '%I:%M:%S %p'}

    rfc2822Weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

    rfc2822Months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug',
                     'Sep', 'Oct', 'Nov', 'Dec']

    resolution = datetime.timedelta.resolution

    #
    # Methods to create new instances
    #

    def __init__(self):
        """Return a new Time instance representing the time now.

        See also the fromFu methods to create new instances from other types of
        initializers.
        """
        self._time = datetime.datetime.utcnow()

    def _fromWeekday(klass, match, tzinfo, now):
        weekday = klass.weekdays.index(match.group('weekday').lower())
        dtnow = now.asDatetime().replace(
            hour=0, minute=0, second=0, microsecond=0)
        daysInFuture = (weekday - dtnow.weekday()) % len(klass.weekdays)
        if daysInFuture == 0:
            daysInFuture = 7
        self = klass.fromDatetime(dtnow + datetime.timedelta(days=daysInFuture))
        assert self.asDatetime().weekday() == weekday
        self.resolution = datetime.timedelta(days=1)
        return self

    def _fromTodayOrTomorrow(klass, match, tzinfo, now):
        dtnow = now.asDatetime().replace(
            hour=0, minute=0, second=0, microsecond=0)
        when = match.group(0).lower()
        if when == 'tomorrow':
            dtnow += datetime.timedelta(days=1)
        elif when == 'yesterday':
            dtnow -= datetime.timedelta(days=1)
        else:
            assert when == 'today'
        self = klass.fromDatetime(dtnow)
        self.resolution = datetime.timedelta(days=1)
        return self

    def _fromTime(klass, match, tzinfo, now):
        minute = int(match.group('minute'))
        hour = int(match.group('hour'))
        ampm = (match.group('ampm') or '').lower()
        if ampm:
            if not 1 <= hour <= 12:
                raise ValueError('hour %i is not in 1..12' % (hour,))
            if hour == 12 and ampm == 'am':
                hour = 0
            elif ampm == 'pm':
                hour += 12
        if not 0 <= hour <= 23:
            raise ValueError('hour %i is not in 0..23' % (hour,))

        dtnow = now.asDatetime(tzinfo).replace(second=0, microsecond=0)
        dtthen = dtnow.replace(hour=hour, minute=minute)
        if dtthen < dtnow:
            dtthen += datetime.timedelta(days=1)

        self = klass.fromDatetime(dtthen)
        self.resolution = datetime.timedelta(minutes=1)
        return self

    def _fromNoonOrMidnight(klass, match, tzinfo, now):
        when = match.group(0).lower()
        if when == 'noon':
            hour = 12
        else:
            assert when == 'midnight'
            hour = 0
        dtnow = now.asDatetime(tzinfo).replace(
            minute=0, second=0, microsecond=0)
        dtthen = dtnow.replace(hour=hour)
        if dtthen < dtnow:
            dtthen += datetime.timedelta(days=1)

        self = klass.fromDatetime(dtthen)
        self.resolution = datetime.timedelta(minutes=1)
        return self

    def _fromNow(klass, match, tzinfo, now):
        # coerce our 'now' argument to an instant
        return now + datetime.timedelta(0)

    weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday',
                'saturday', 'sunday']

    humanlyPatterns = [
        (re.compile(r"""
            \b
            ((next|this)\s+)?
            (?P<weekday>
                monday
                | tuesday
                | wednesday
                | thursday
                | friday
                | saturday
                | sunday
            )
            \b
            """, re.IGNORECASE | re.VERBOSE),
            _fromWeekday),
        (re.compile(r"\b(today|tomorrow|yesterday)\b", re.IGNORECASE),
            _fromTodayOrTomorrow),
        (re.compile(r"""
            \b
            (?P<hour>\d{1,2}):(?P<minute>\d{2})
            (\s*(?P<ampm>am|pm))?
            \b
            """, re.IGNORECASE | re.VERBOSE),
            _fromTime),
        (re.compile(r"\b(noon|midnight)\b", re.IGNORECASE),
            _fromNoonOrMidnight),
        (re.compile(r"\b(now)\b", re.IGNORECASE),
            _fromNow),
    ]

    _fromWeekday = classmethod(_fromWeekday)
    _fromTodayOrTomorrow = classmethod(_fromTodayOrTomorrow)
    _fromTime = classmethod(_fromTime)
    _fromNoonOrMidnight = classmethod(_fromNoonOrMidnight)
    _fromNow = classmethod(_fromNow)

    def fromHumanly(klass, humanStr, tzinfo=None, now=None):
        """Return a new Time instance from a string a human might type.

        @param humanStr: the string to be parsed.

        @param tzinfo: A tzinfo instance indicating the timezone to assume if
        none is specified in humanStr. If None, assume UTC.

        @param now: A Time instance to be considered "now" for when
        interpreting relative dates like "tomorrow". If None, use the real now.

        Total crap now, it just supports weekdays, "today" and "tomorrow" for
        now. This is pretty insufficient and useless, but good enough for some
        demo functionality, or something.
        """
        humanStr = humanStr.strip()
        if now is None:
            now = Time()
        if tzinfo is None:
            tzinfo = FixedOffset(0, 0)

        for pattern, creator in klass.humanlyPatterns:
            match = pattern.match(humanStr)
            if not match \
            or match.span()[1] != len(humanStr):
                continue
            try:
                return creator(klass, match, tzinfo, now)
            except ValueError:
                continue
        raise ValueError('could not parse date: %r' % (humanStr,))

    fromHumanly = classmethod(fromHumanly)

    iso8601pattern = re.compile(r"""
        ^ (?P<year> \d{4})
        (
            # a year may optionally be followed by one of:
            # - a month
            # - a week
            # - a specific day, and an optional time
            #     a specific day is one of:
            #     - a month and day
            #     - week and weekday
            #     - a day of the year
            (
                -? (?P<month1> \d{2})
                |
                -? W (?P<week1> \d{2})
                |
                (
                    -? (?P<month2> \d{2})
                    -? (?P<day> \d{2})
                    |
                    -? W (?P<week2> \d{2})
                    -? (?P<weekday> \d)
                    |
                    -? (?P<dayofyear> \d{3})
                )
                (
                    T (?P<hour> \d{2})
                    (
                        :? (?P<minute> \d{2})
                        (
                            :? (?P<second> \d{2})
                            (
                                [\.,] (?P<fractionalsec> \d+)
                            )?
                        )?
                    )?
                    (
                        (?P<zulu> Z)
                        |
                        (?P<tzhour> [+\-]\d{2})
                        (
                            :? (?P<tzmin> \d{2})
                        )?
                    )?
                )?
            )?
        )? $""", re.VERBOSE)

    def fromISO8601TimeAndDate(klass, iso8601string, tzinfo=None):
        """Return a new Time instance from a string formated as in ISO 8601.

        If the given string contains no timezone, it is assumed to be in the
        timezone specified by the parameter `tzinfo`, or UTC if tzinfo is None.
        An input string with an explicit timezone will always override tzinfo.

        If the given iso8601string does not contain all parts of the time, they
        will default to 0 in the timezone given by `tzinfo`.

        WARNING: this function is incomplete. ISO is dumb and their standards
        are not free. Only a subset of all valid ISO 8601 dates are parsed,
        because I can't find a formal description of the format. However,
        common ones should work.
        """

        def calculateTimezone():
            if groups['zulu'] == 'Z':
                return FixedOffset(0, 0)
            else:
                tzhour = groups.pop('tzhour')
                tzmin = groups.pop('tzmin')
                if tzhour is not None:
                    return FixedOffset(int(tzhour), int(tzmin or 0))
            return tzinfo or FixedOffset(0, 0)

        def coerceGroups():
            groups['month'] = groups['month1'] or groups['month2']
            groups['week'] = groups['week1'] or groups['week2']
            # don't include fractional seconds, because it's not an integer.
            defaultTo0 = ['hour', 'minute', 'second']
            defaultTo1 = ['month', 'day', 'week', 'weekday', 'dayofyear']
            if groups['fractionalsec'] is None:
                groups['fractionalsec'] = '0'
            for key in defaultTo0:
                if groups[key] is None:
                    groups[key] = 0
            for key in defaultTo1:
                if groups[key] is None:
                    groups[key] = 1
            groups['fractionalsec'] = float('.'+groups['fractionalsec'])
            for key in defaultTo0 + defaultTo1 + ['year']:
                groups[key] = int(groups[key])

            for group, min, max in [
                # some years have only 52 weeks
                ('week', 1, 53),
                ('weekday', 1, 7),
                ('month', 1, 12),
                ('day', 1, 31),
                ('hour', 0, 24),
                ('minute', 0, 59),

                # Sometime in the 22nd century AD, two leap seconds will be
                # required every year.  In the 25th century AD, four every
                # year.  We'll ignore that for now though because it would be
                # tricky to get right and we certainly don't need it for our
                # target applications.  In other words, post-singularity
                # Martian users, please do not rely on this code for
                # compatibility with Greater Galactic Protectorate of Earth
                # date/time formatting!  Apologies, but no library I know of in
                # Python is sufficient for processing their dates and times
                # without ADA bindings to get the radiation-safety zone counter
                # correct. -glyph

                ('second', 0, 61),
                # don't forget leap years
                ('dayofyear', 1, 366)]:
                if not min <= groups[group] <= max:
                    raise ValueError('%s must be in %i..%i' % (group, min, max))

        def determineResolution():
            if match.group('fractionalsec') is not None:
                return max(datetime.timedelta.resolution,
                    datetime.timedelta(
                        microseconds=1 * 10 ** -len(
                            match.group('fractionalsec')) * 1000000))

            for testGroup, resolution in [
            ('second', datetime.timedelta(seconds=1)),
            ('minute', datetime.timedelta(minutes=1)),
            ('hour', datetime.timedelta(hours=1)),
            ('weekday', datetime.timedelta(days=1)),
            ('dayofyear', datetime.timedelta(days=1)),
            ('day', datetime.timedelta(days=1)),
            ('week1', datetime.timedelta(weeks=1)),
            ('week2', datetime.timedelta(weeks=1))]:
                if match.group(testGroup) is not None:
                    return resolution

            if match.group('month1') is not None \
            or match.group('month2') is not None:
                if self._time.month == 12:
                    return datetime.timedelta(days=31)
                nextMonth = self._time.replace(month=self._time.month+1)
                return nextMonth - self._time
            else:
                nextYear = self._time.replace(year=self._time.year+1)
                return nextYear - self._time

        def calculateDtime(tzinfo):
            """Calculate a datetime for the start of the addressed period."""

            if match.group('week1') is not None \
            or match.group('week2') is not None:
                if not 0 < groups['week'] <= 53:
                    raise ValueError(
                        'week must be in 1..53 (was %i)' % (groups['week'],))
                dtime = datetime.datetime(
                    groups['year'],
                    1,
                    4,
                    groups['hour'],
                    groups['minute'],
                    groups['second'],
                    int(round(groups['fractionalsec'] * 1000000)),
                    tzinfo=tzinfo
                )
                dtime -= datetime.timedelta(days = dtime.weekday())
                dtime += datetime.timedelta(
                    days = (groups['week']-1) * 7 + groups['weekday'] - 1)
                if dtime.isocalendar() != (
                    groups['year'], groups['week'], groups['weekday']):
                    # actually the problem could be an error in my logic, but
                    # nothing should cause this but requesting week 53 of a
                    # year with 52 weeks.
                    raise ValueError('year %04i has no week %02i' %
                                     (groups['year'], groups['week']))
                return dtime

            if match.group('dayofyear') is not None:
                dtime = datetime.datetime(
                    groups['year'],
                    1,
                    1,
                    groups['hour'],
                    groups['minute'],
                    groups['second'],
                    int(round(groups['fractionalsec'] * 1000000)),
                    tzinfo=tzinfo
                )
                dtime += datetime.timedelta(days=groups['dayofyear']-1)
                if dtime.year != groups['year']:
                    raise ValueError(
                        'year %04i has no day of year %03i' %
                        (groups['year'], groups['dayofyear']))
                return dtime

            else:
                return datetime.datetime(
                    groups['year'],
                    groups['month'],
                    groups['day'],
                    groups['hour'],
                    groups['minute'],
                    groups['second'],
                    int(round(groups['fractionalsec'] * 1000000)),
                    tzinfo=tzinfo
                )


        match = klass.iso8601pattern.match(iso8601string)
        if match is None:
            raise ValueError(
                '%r could not be parsed as an ISO 8601 date and time' %
                (iso8601string,))

        groups = match.groupdict()
        coerceGroups()
        if match.group('hour') is not None:
            timezone = calculateTimezone()
        else:
            timezone = None
        self = klass.fromDatetime(calculateDtime(timezone))
        self.resolution = determineResolution()
        return self

    fromISO8601TimeAndDate = classmethod(fromISO8601TimeAndDate)

    def fromStructTime(klass, structTime, tzinfo=None):
        """Return a new Time instance from a time.struct_time.

        If tzinfo is None, structTime is in UTC. Otherwise, tzinfo is a
        datetime.tzinfo instance coresponding to the timezone in which
        structTime is.

        Many of the functions in the standard time module return these things.
        This will also work with a plain 9-tuple, for parity with the time
        module. The last three elements, or tm_wday, tm_yday, and tm_isdst are
        ignored.
        """
        dtime = datetime.datetime(tzinfo=tzinfo, *structTime[:6])
        self = klass.fromDatetime(dtime)
        self.resolution = datetime.timedelta(seconds=1)
        return self

    fromStructTime = classmethod(fromStructTime)

    def fromDatetime(klass, dtime):
        """Return a new Time instance from a datetime.datetime instance.

        If the datetime instance does not have an associated timezone, it is
        assumed to be UTC.
        """
        self = klass.__new__(klass)
        if dtime.tzinfo is not None:
            self._time = dtime.astimezone(FixedOffset(0, 0)).replace(tzinfo=None)
        else:
            self._time = dtime
        self.resolution = datetime.timedelta.resolution
        return self

    fromDatetime = classmethod(fromDatetime)

    def fromPOSIXTimestamp(klass, secs):
        """Return a new Time instance from seconds since the POSIX epoch.

        The POSIX epoch is midnight Jan 1, 1970 UTC. According to POSIX, leap
        seconds don't exist, so one UTC day is exactly 86400 seconds, even if
        it wasn't.

        @param secs: a number of seconds, represented as an integer, long or
        float.
        """
        self = klass.fromDatetime(_EPOCH + datetime.timedelta(seconds=secs))
        self.resolution = datetime.timedelta()
        return self

    fromPOSIXTimestamp = classmethod(fromPOSIXTimestamp)

    def fromRFC2822(klass, rfc822string):
        """
        Return a new Time instance from a string formated as described in RFC 2822.

        @type rfc822string: str

        @raise ValueError: if the timestamp is not formatted properly (or if
        certain obsoleted elements of the specification are used).

        @return: a new L{Time}
        """

        # parsedate_tz is going to give us a "struct_time plus", a 10-tuple
        # containing the 9 values a struct_time would, i.e.: (tm_year, tm_mon,
        # tm_day, tm_hour, tm_min, tm_sec, tm_wday, tm_yday, tm_isdst), plus a
        # bonus "offset", which is an offset (in _seconds_, of all things).

        maybeStructTimePlus = parsedate_tz(rfc822string)

        if maybeStructTimePlus is None:
            raise ValueError('could not parse RFC 2822 date %r' % (rfc822string,))
        structTimePlus = sanitizeStructTime(maybeStructTimePlus)
        offsetInSeconds = structTimePlus[-1]
        if offsetInSeconds is None:
            offsetInSeconds = 0
        self = klass.fromStructTime(
            structTimePlus,
            FixedOffset(
                hours=0,
                minutes=offsetInSeconds // 60))
        self.resolution = datetime.timedelta(seconds=1)
        return self

    fromRFC2822 = classmethod(fromRFC2822)

    #
    # Methods to produce various formats
    #

    def asPOSIXTimestamp(self):
        """Return this time as a timestamp as specified by POSIX.

        This timestamp is the count of the number of seconds since Midnight,
        Jan 1 1970 UTC, ignoring leap seconds.
        """
        mytimedelta = self._time - _EPOCH
        return _timedeltaToSeconds(mytimedelta)

    def asDatetime(self, tzinfo=None):
        """Return this time as an aware datetime.datetime instance.

        The returned datetime object has the specified tzinfo, or a tzinfo
        describing UTC if the tzinfo parameter is None.
        """
        if tzinfo is None:
            tzinfo = FixedOffset(0, 0)

        if not self.isTimezoneDependent():
            return self._time.replace(tzinfo=tzinfo)
        else:
            return self._time.replace(tzinfo=FixedOffset(0, 0)).astimezone(tzinfo)

    def asNaiveDatetime(self, tzinfo=None):
        """Return this time as a naive datetime.datetime instance.

        The returned datetime object has its tzinfo set to None, but is in the
        timezone given by the tzinfo parameter, or UTC if the parameter is
        None.
        """
        return self.asDatetime(tzinfo).replace(tzinfo=None)

    def asRFC2822(self, tzinfo=None, includeDayOfWeek=True):
        """Return this Time formatted as specified in RFC 2822.

        RFC 2822 specifies the format of email messages.

        RFC 2822 says times in email addresses should reflect the local
        timezone. If tzinfo is a datetime.tzinfo instance, the returned
        formatted string will reflect that timezone. Otherwise, the timezone
        will be '-0000', which RFC 2822 defines as UTC, but with an unknown
        local timezone.

        RFC 2822 states that the weekday is optional. The parameter
        includeDayOfWeek indicates whether or not to include it.
        """
        dtime = self.asDatetime(tzinfo)

        if tzinfo is None:
            rfcoffset = '-0000'
        else:
            rfcoffset = '%s%02i%02i' % _timedeltaToSignHrMin(dtime.utcoffset())

        rfcstring = ''
        if includeDayOfWeek:
            rfcstring += self.rfc2822Weekdays[dtime.weekday()] + ', '

        rfcstring += '%i %s %4i %02i:%02i:%02i %s' % (
            dtime.day,
            self.rfc2822Months[dtime.month - 1],
            dtime.year,
            dtime.hour,
            dtime.minute,
            dtime.second,
            rfcoffset)

        return rfcstring

    def asRFC1123(self):
        """
        Return the time formatted as specified in RFC 1123.

        Useful when setting the max-age value of an HTTP cookie, which
        requires the timezone be represented as the string 'GMT',
        rather than an offset, e.g., '-0000'
        """
        return formatdate(self.asPOSIXTimestamp(), False, True)

    def asISO8601TimeAndDate(self, includeDelimiters=True, tzinfo=None,
                             includeTimezone=True):
        """Return this time formatted as specified by ISO 8861.

        ISO 8601 allows optional dashes to delimit dates and colons to delimit
        times. The parameter includeDelimiters (default True) defines the
        inclusion of these delimiters in the output.

        If tzinfo is a datetime.tzinfo instance, the output time will be in the
        timezone given. If it is None (the default), then the timezone string
        will not be included in the output, and the time will be in UTC.

        The includeTimezone parameter coresponds to the inclusion of an
        explicit timezone. The default is True.
        """
        if not self.isTimezoneDependent():
            tzinfo = None
        dtime = self.asDatetime(tzinfo)

        if includeDelimiters:
            dateSep = '-'
            timeSep = ':'
        else:
            dateSep = timeSep = ''

        if includeTimezone:
            if tzinfo is None:
                timezone = '+00%s00' % (timeSep,)
            else:
                sign, hour, min = _timedeltaToSignHrMin(dtime.utcoffset())
                timezone = '%s%02i%s%02i' % (sign, hour, timeSep, min)
        else:
            timezone = ''

        microsecond = ('%06i' % (dtime.microsecond,)).rstrip('0')
        if microsecond:
            microsecond = '.' + microsecond

        parts = [
            ('%04i' % (dtime.year,), datetime.timedelta(days=366)),
            ('%s%02i' % (dateSep, dtime.month), datetime.timedelta(days=31)),
            ('%s%02i' % (dateSep, dtime.day), datetime.timedelta(days=1)),
            ('T', datetime.timedelta(hours=1)),
            ('%02i' % (dtime.hour,), datetime.timedelta(hours=1)),
            ('%s%02i' % (timeSep, dtime.minute), datetime.timedelta(minutes=1)),
            ('%s%02i' % (timeSep, dtime.second), datetime.timedelta(seconds=1)),
            (microsecond, datetime.timedelta(microseconds=1)),
            (timezone, datetime.timedelta(hours=1))
        ]

        formatted = ''
        for part, minResolution in parts:
            if self.resolution <= minResolution:
                formatted += part

        return formatted

    def asStructTime(self, tzinfo=None):
        """Return this time represented as a time.struct_time.

        tzinfo is a datetime.tzinfo instance coresponding to the desired
        timezone of the output. If is is the default None, UTC is assumed.
        """
        dtime = self.asDatetime(tzinfo)
        if tzinfo is None:
            return dtime.utctimetuple()
        else:
            return dtime.timetuple()

    def asHumanly(self, tzinfo=None, now=None, precision=Precision.MINUTES):
        """Return this time as a short string, tailored to the current time.

        Parts of the date that can be assumed are omitted. Consequently, the
        output string depends on the current time. This is the format used for
        displaying dates in most user visible places in the quotient web UI.

        By default, the current time is determined by the system clock. The
        current time used for formatting the time can be changed by providing a
        Time instance as the parameter 'now'.

        @param precision: The smallest unit of time that will be represented
        in the returned string.  Valid values are L{Time.Precision.MINUTES} and
        L{Time.Precision.SECONDS}.

        @raise InvalidPrecision: if the specified precision is not either
        L{Time.Precision.MINUTES} or L{Time.Precision.SECONDS}.
        """
        try:
            timeFormat = Time._timeFormat[precision]
        except KeyError:
            raise InvalidPrecision(
                    'Use Time.Precision.MINUTES or Time.Precision.SECONDS')

        if now is None:
            now = Time().asDatetime(tzinfo)
        else:
            now = now.asDatetime(tzinfo)
        dtime = self.asDatetime(tzinfo)

        # Same day?
        if dtime.date() == now.date():
            if self.isAllDay():
                return 'all day'
            return dtime.strftime(timeFormat).lower()
        else:
            res = str(dtime.date().day) + dtime.strftime(' %b')  # day + month
            # Different year?
            if not dtime.date().year == now.date().year:
                res += dtime.strftime(' %Y')
            if not self.isAllDay():
                res += dtime.strftime(', %s' % (timeFormat,)).lower()
            return res

    #
    # methods to return related times
    #

    def getBounds(self, tzinfo=None):
        """
        Return a pair describing the bounds of self.

        This returns a pair (min, max) of Time instances. It is not quite the
        same as (self, self + self.resolution). This is because timezones are
        insignificant for instances with a resolution greater or equal to 1
        day.

        To illustrate the problem, consider a Time instance::

            T = Time.fromHumanly('today', tzinfo=anything)

        This will return an equivalent instance independent of the tzinfo used.
        The hour, minute, and second of this instance are 0, and its resolution
        is one day.

        Now say we have a sorted list of times, and we want to get all times
        for 'today', where whoever said 'today' is in a timezone that's 5 hours
        ahead of UTC. The start of 'today' in this timezone is UTC 05:00. The
        example instance T above is before this, but obviously it is today.

        The min and max times this returns are such that all potentially
        matching instances are within this range. However, this range might
        contain unmatching instances.

        As an example of this, if 'today' is April first 2005, then
        Time.fromISO8601TimeAndDate('2005-04-01T00:00:00') sorts in the same
        place as T from above, but is not in the UTC+5 'today'.

        TIME IS FUN!
        """
        if self.resolution >= datetime.timedelta(days=1) \
        and tzinfo is not None:
            time = self._time.replace(tzinfo=tzinfo)
        else:
            time = self._time

        return (
            min(self.fromDatetime(time), self.fromDatetime(self._time)),
            max(self.fromDatetime(time + self.resolution),
                self.fromDatetime(self._time + self.resolution))
        )

    def oneDay(self):
        """Return a Time instance representing the day of the start of self.

        The returned new instance will be set to midnight of the day containing
        the first instant of self in the specified timezone, and have a
        resolution of datetime.timedelta(days=1).
        """
        day = self.__class__.fromDatetime(self.asDatetime().replace(
                hour=0, minute=0, second=0, microsecond=0))
        day.resolution = datetime.timedelta(days=1)
        return day

    #
    # useful predicates
    #

    def isAllDay(self):
        """Return True iff this instance represents exactly all day."""
        return self.resolution == datetime.timedelta(days=1)

    def isTimezoneDependent(self):
        """Return True iff timezone is relevant for this instance.

        Timezone is only relevent for instances with a resolution better than
        one day.
        """
        return self.resolution < datetime.timedelta(days=1)

    #
    # other magic methods
    #

    def __cmp__(self, other):
        if not isinstance(other, Time):
            raise TypeError("Cannot meaningfully compare %r with %r" % (self, other))
        return cmp(self._time, other._time)

    def __eq__(self, other):
        if isinstance(other, Time):
            return cmp(self._time, other._time) == 0
        return False

    def __ne__(self, other):
        return not (self == other)

    def __repr__(self):
        return 'extime.Time.fromDatetime(%r)' % (self._time,)

    __str__ = asISO8601TimeAndDate

    def __contains__(self, other):
        """Test if another Time instance is entirely within the period addressed by this one."""
        if not isinstance(other, Time):
            raise TypeError(
                '%r is not a Time instance; can not test for containment'
                % (other,))
        if other._time < self._time:
            return False
        if self._time + self.resolution < other._time + other.resolution:
            return False
        return True

    def __add__(self, addend):
        if not isinstance(addend, datetime.timedelta):
            raise TypeError('expected a datetime.timedelta instance')
        return Time.fromDatetime(self._time + addend)

    def __sub__(self, subtrahend):
        """
        Implement subtraction of an interval or another time from this one.

        @type subtrahend: L{datetime.timedelta} or L{Time}

        @param subtrahend: The object to be subtracted from this one.

        @rtype: L{datetime.timedelta} or L{Time}

        @return: If C{subtrahend} is a L{datetime.timedelta}, the result is
        a L{Time} instance which is offset from this one by that amount.  If
        C{subtrahend} is a L{Time}, the result is a L{datetime.timedelta}
        instance which gives the difference between it and this L{Time}
        instance.
        """
        if isinstance(subtrahend, datetime.timedelta):
            return Time.fromDatetime(self._time - subtrahend)

        if isinstance(subtrahend, Time):
            return self.asDatetime() - subtrahend.asDatetime()

        return NotImplemented
