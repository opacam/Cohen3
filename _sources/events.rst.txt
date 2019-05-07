    .. _the_event_system:

The events system
=================
Starting from version 0.9.0 the event system has changed from louie/dispatcher
to EventDispatcher (external dependency). Here are the most important changes:

    - The new event system is not a global dispatcher anymore.
    - All the signal/receivers are connected between them only if it is necessary.
    - We don't connect/disconnect anymore, instead you will bind/unbind.
    - The events has been renamed (this is necessary because the old event names
      contains dots in his names, and this could cause troubles with the new
      event system).

Bind the events
---------------
The event system is very similar to the one's used in
`kivy's framework <https://github.com/kivy/kivy>`_, so...if you are familiar
with the kivy's event management you will know exactly how to proceed to
connect events and properties, here is a simple example of a media observer,
made to show how to detect new devices by bind the signals emitted by the class
`Coherence <https://opacam.github.io/Cohen3/source/modules.html#coherence.base.Coherence>`_:

.. code-block:: python

        from twisted.internet import reactor
        from coherence.base import Coherence
        from coherence.upnp.core.uuid import UUID
        new_uuid = UUID()

        # called for each media server found
        def media_server_found(device):
            print(f'Media Server found: {device.get_friendly_name()}')

        # Called whenever a device is removed
        def media_server_removed(*args):
            print(f'Media Server gone: {args}')

        # Initialize Coherence with a LolCats server
        coherence = Coherence(
            {'logmode': 'info',
             'controlpoint': 'yes',
             'plugin': {'backend': 'LolcatsStore',
                        'name': 'Cohen3 LolcatsStore',
                        'uuid': new_uuid
                        }
             }
        )

        # The first parameter of the bind function is the name of the emitted
        # signal, and after the logical operator "=", we point to a function
        # that will be triggered whenever the class Coherence emits the signal.
        coherence.bind(
            coherence_device_detection_completed=media_server_found)
        coherence.bind(
            coherence_device_removed=media_server_removed)

        reactor.run()


If you want to disconnect some signal you will proceed like you use to connect,
but instead of the word **bind** you will use the word **unbind**:

.. code-block:: python

        # Unbind/disconnect the signals connected before
        coherence.unbind(
            coherence_device_detection_completed=media_server_found)
        coherence.unbind(
            coherence_device_removed=media_server_removed)

Bind the properties
-------------------
We also can bind/unbind some class properties (the same way we use
above but replacing the first parameter with the property name), but you should
be aware that we only can do that with those properties that uses the classes
from the EventDispatcher's package::

    - Property
    - ListProperty
    - DictProperty

So, similar result got above can be achieved from another perspective, using the
mentioned EventDispatcher's properties, for example:

.. code-block:: python

    from twisted.internet import reactor
    from coherence.base import Coherence
    from coherence.upnp.core.uuid import UUID
    lol_uuid = UUID()
    apple_uuid = UUID()

    # called whenever the devices property
    # of class Coherence changes
    def on_devices(coherence_instance, devices):
        print(f'Media Server devices changed: {len(devices)} found')
        for device in devices:
            print(f'\t-> {device.get_friendly_name()}')
            if device.get_friendly_name() == 'Cohen3 AppleTrailersStore':
                # Now we remove the "AppleTrailersStore" server
                coherence_instance.remove_plugin(f'uuid:{device.get_uuid()}')

    # Initialize Coherence with a LolCats server
    coherence = Coherence(
        {'logmode': 'warning',
         'controlpoint': 'yes',
         'plugin': [
             {'backend': 'LolcatsStore',
              'name': 'Cohen3 LolcatsStore',
              'uuid': lol_uuid
              },
             {'backend': 'AppleTrailersStore',
              'name': 'Cohen3 AppleTrailersStore',
              'uuid': apple_uuid
              },
         ]
         }
    )

    # The first parameter of the bind function is the name of the property.
    # Here we target the devices property (which is of kind ListProperty),
    # and after the logical operator "=", we point to a function that
    # will be triggered whenever some device is added or removed.
    coherence.bind(devices=on_devices)

    reactor.run()

If you want more information about EventDispatcher, you can take a look at the
`EventDispatcher project <https://github.com/lobocv/eventdispatcher>`_ for
extended information and examples.

.. note::
    Check the `Cohen3's Source Tree <https://opacam.github.io/Cohen3/source/coherence.html>`_
    documentation for specific class events/properties.

Supported old signals
---------------------
In order to maintain some minimal compatibility with the old event system,
the classes `Coherence <https://opacam.github.io/Cohen3/source/modules.html#coherence.base.Coherence>`_
and `ControlPoint <https://opacam.github.io/Cohen3/source/upnp/devices/control_point.html#coherence.upnp.devices.control_point.ControlPoint>`_
contains two methods: connect and disconnect which will take care to bind/unbind
some of the old signals.

The supported old signals for connect/disconnect functions for the class
`Coherence <https://opacam.github.io/Cohen3/source/modules.html#coherence.base.Coherence>`_
are:

    - Coherence.UPnP.Device.detection_completed
    - Coherence.UPnP.RootDevice.detection_completed
    - Coherence.UPnP.Device.removed
    - Coherence.UPnP.RootDevice.removed

The supported old signals for connect/disconnect functions for the class
`ControlPoint <https://opacam.github.io/Cohen3/source/upnp/devices/control_point.html#coherence.upnp.devices.control_point.ControlPoint>`_
are:

    - Coherence.UPnP.ControlPoint.MediaServer.detected
    - Coherence.UPnP.ControlPoint.MediaServer.removed
    - Coherence.UPnP.ControlPoint.MediaRenderer.detected
    - Coherence.UPnP.ControlPoint.MediaRenderer.removed
    - Coherence.UPnP.ControlPoint.InternetGatewayDevice.detected
    - Coherence.UPnP.ControlPoint.InternetGatewayDevice.removed

