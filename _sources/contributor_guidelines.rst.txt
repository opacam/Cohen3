 
Contributor Guidelines
----------------------

Pull Request Guidelines
~~~~~~~~~~~~~~~~~~~~~~~

Before you submit a pull request, check that it meets these guidelines:

1. The pull request should include tests.
2. If the pull request adds functionality, the docs should be updated. Put
   your new functionality into a function with a docstring.
3. The pull request should work for Python 3.6 and 3.7, and Travis CI.
4. Check https://travis-ci.com/opacam/Cohen3/pull_requests to ensure the tests
   pass for all supported Python versions and platforms.

Coding Standards
~~~~~~~~~~~~~~~~

* PEP8
* Write new code in Python 3.

Docstrings
~~~~~~~~~~

Every module/class/method/function needs a docstring, so use the following
keywords when relevant:

- ``.. versionadded::`` to mark the version in which the feature was added.
- ``.. versionchanged::`` to mark the version in which the behaviour of the
  feature was changed.
- ``.. note::`` to add additional info about how to use the feature or related
  feature.
- ``.. warning::`` to indicate a potential issue the user might run into using
  the feature.

Examples::

    def my_new_feature(self, arg):
        """
        New feature is awesome

        .. versionadded:: 0.8.3

        .. note:: This new feature will likely blow your mind

        .. warning:: Please take a seat before trying this feature
        """

Will result in:

    def my_new_feature(self, arg):
        New feature is awesome

        .. versionadded:: 0.8.3

        .. note:: This new feature will likely blow your mind

        .. warning:: Please take a seat before trying this feature


When referring to other parts of the api use:

- ``:mod:`~coherence.module``` to refer to a module
- ``:class:`~coherence.module.Class``` to refer to a class
- ``:attr:`~coherence.module.Class.attribute``` to refer to a attibute
- ``:meth:`~coherence.module.Class.method``` to refer to a method

Obviously replacing `module`, `Class`, `attribute` and `method` with their
real name, and using using '.' to separate modules referring to imbricated
modules, e.g::

    :mod:`~coherence.upnp.core.device`
    :class:`~coherence.upnp.core.device.Device`
    :attr:`~coherence.upnp.core.device.Device.services`
    :meth:`~coherence.upnp.core.device.Device.parse_device`

Will result in:

    :mod:`~coherence.upnp.core.device`
    :class:`~coherence.upnp.core.device.Device`
    :attr:`~coherence.upnp.core.device.Device.services`
    :meth:`~coherence.upnp.core.device.Device.parse_device`

To build your documentation, enter into docs folder and run::

    $ make html

If you updated your Cohen3 install, and have some trouble compiling docs, run::

    $ make clean
    $ make html

The docs will be generated in ``docs/_build/html``. For more information on
docstring formatting, please refer to the official
`Sphinx Documentation <http://sphinx-doc.org/>`_.
