from __future__ import print_function
import time
import functools
from os.path import join, dirname, abspath, exists, splitext, split, basename, relpath

def formatSeconds(s):
    seconds, ms = divmod(s * 1000, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)

    if hours:
        return "%d:%02d:%02d.%03d" % (hours, minutes, seconds, ms)
    elif minutes:
        return "%d:%02d.%03d" % (minutes, seconds, ms)

    return "%d.%03d" % (seconds, ms)


    # modified from contexttimer https://github.com/brouberol/contexttimer
class Timer(object):
    """ A timer as a context manager

    Wraps around a timer. A custom timer can be passed to the constructor.

    Keyword arguments:
        output -- if True, print output after exiting context.
                  if callable, pass output to callable.
        format -- str.format string to be used for output; default "took {} seconds"
        prefix -- string to prepend (plus a space) to output
                  For convenience, if you only specify this, output defaults to True.
    """

    def __init__(self, prefix="", timer=time.time, factor=1, output=None, fmt="took {} seconds"):
        self.timer = timer
        self.factor = factor
        self.output = output
        self.fmt = fmt
        self.prefix = prefix
        self.end = None
        self.start = self()

    def __call__(self):
        """ Return the current time """
        return self.timer()

    def __enter__(self):
        """ Set the start time """
        self.start = self()
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        """ Set the end time """
        self.end = self()

        if self.prefix and self.output is None:
            self.output = True

        if self.output:
            output = " ".join([self.prefix, self.fmt.format(formatSeconds(self.elapsed))])

            if callable(self.output):
                self.output(output)
            else:
                print(output)

    def __str__(self):
        return '%.3f' % (self.elapsed)

    @property
    def elapsed(self):
        """ Return the current elapsed time since start

        If the `elapsed` property is called in the context manager scope,
        the elapsed time bewteen start and property access is returned.
        However, if it is accessed outside of the context manager scope,
        it returns the elapsed time bewteen entering and exiting the scope.

        The `elapsed` property can thus be accessed at different points within
        the context manager scope, to time different parts of the block.

        """
            # if elapsed is called out of the context manager scope, use recorded end time
        end = self() if self.end is None else self.end
        return (end - self.start) * self.factor


    # modified from contexttimer https://github.com/brouberol/contexttimer
def timefunction(f, msg=None, prefix="", logger=None, **timer_kwargs):
    """ Function decorator displaying the function execution time
    All kwargs are the arguments taken by the Timer class constructor.

    """
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        with Timer(prefix=prefix, **timer_kwargs) as t:
            out = f(*args, **kwargs)

        use_msg = (msg or f"function {f.__name__} execution time: %s") % (formatSeconds(t.elapsed))

        if "logFile" in kwargs:
            print(msg, file = kwargs["logFile"])

        if logger:
            logger.debug(use_msg)
        else:
            print(use_msg)

        return out


    # prevent double-wrapping
    if getattr(f, 'timefunction_wrapped', False):
        return f

    wrapped.timefunction_wrapped = True
    return wrapped

