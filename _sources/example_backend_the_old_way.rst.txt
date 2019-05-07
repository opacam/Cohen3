    .. _example_backend_the_old_way:

Writing a backend (the old way)
===============================
Here you will learn  how to write a backend from the scratch using the Cohen3
module :ref:`backend <coherence.backend>`. We will try to explain it step by
step, using as a model the classic backend LolcatsStore. You must know that
this way is not the best way to implement this kind of media server, you can
achieve the same result by using the newer tools
:ref:`models <coherence.backends.models (package)>`, but... it's recommended to
read this document, because you will get an idea of what is happening behind
the new way, using the :ref:`models <coherence.backends.models (package)>`
which, in matter fact, uses the tools from :ref:`backend <coherence.backend>`
so, it will be useful to write more complex backends and to understand the
basics of the Cohen3 Project.

Introduction (the old way)
--------------------------
This Media Backend will allow you to access the cool and cute pictures
from lolcats.com. This is mainly meant as a Sample Media Backend to learn
how to write a Media Backend using the backend tools directly. Be aware that
this could be done more easily using the modules from
:ref:`models <coherence.backends.models (package)>`.

So. You are still reading which allows me to assume that you want to learn how
to write a Media Backend for Coherence. NICE :) .

Once again: This is a SIMPLE Media Backend. It does not contain any big
requests, searches or even transcoding. The only thing we want to do in this
simple example, is to fetch a rss link on startup, parse it, save it and
restart the process one hour later again. Well, on top of this, we also want
to provide these information as a Media Server in the UPnP/DLNA
Network of course ;) .

Wow. You are still reading. You must be really interested. Then let's go...
check the source code for this backend line by line, you will see that all
the code has been commented in order to make easier to understand how to
write a backend. Let's start...

The imports (the old way)
-------------------------
We import the reactor, that allows us to specify an action to happen later::

    from twisted.internet import reactor

We import the re module to clean up quotes in some html code::

    from twisted.internet import re

Import task in order no iterate over items without blocking the application::

    from twisted.internet import task

And to parse the RSS-Data (which is XML), we use our custom function
parse_with_lxml::

    from coherence.upnp.core.utils import parse_with_lxml

The data itself is stored in BackendItems. They are also the first things we
are going to create::

    from coherence.backend import BackendItem

The entry point for each kind of Backend is a 'BackendStore'. The BackendStore
is the instance that does everything Usually. In this Example it can be
understood as the 'Server', the object retrieving and serving the data::

    from coherence.backend import BackendStore

And we will store our items into a container which will be the root for all
our items::

    from coherence.backends.models.containers import BackendContainer

To make the data 'renderable' we need to define the DIDLite-Class of the Media
we are providing. For that we have a bunch of helpers that we also want to
import::

    from coherence.upnp.core import DIDLLite

Coherence relies on the Twisted backend. I hope you are familiar with the
concept of deferreds. If not please read:

   http://twistedmatrix.com/projects/core/documentation/howto/async.html

It is a basic concept that you need to understand the following code. But why
am I talking about it? Oh, right, because we use a http-client based on the
twisted.web.client module to do our requests::

    from coherence.upnp.core.utils import getPage


The models (the old way)
------------------------
After the download and parsing of the data is done, we want to save it. In
this case, we want to fetch the images and store their URL and the title of
the image. That is the LolCatsImage class. We inherit from BackendItem as it
already contains a lot of helper methods and implementations. For this simple
example, we only have to fill the item with data::

    class LolCatsImage(BackendItem):
        '''
        The LolCatsImage server. Takes care of fetching data and creating the
        backend items.
        '''

        def __init__(self, parent_id, id, title, url):
            BackendItem.__init__(self)
            self.parentid = parent_id  # used to be able to 'go back'

            self.update_id = 0

            self.id = id  # each item has its own and unique id

            self.location = url  # the url of the picture

            self.name = title  # the title of the picture. Inside
            # coherence this is called 'name'

            # Item.item is a special thing. This is used to explain the client what
            # kind of data this is. For e.g. A VideoItem or a MusicTrack. In our
            # case, we have an image.
            self.item = DIDLLite.ImageItem(id, parent_id, self.name)

            # each Item.item has to have one or more Resource objects these hold
            # detailed information about the media data and can represent variants
            #  of it (different sizes, transcoded formats)
            res = DIDLLite.Resource(self.location, 'http-get:*:image/jpeg:*')
            res.size = None  # FIXME: we should have a size here
            #       and a resolution entry would be nice too
            self.item.res.append(res)


The server (the old way)
------------------------
The LolcatsStore is a media server. As already said before the implementation
of the server is done in an inheritance of a BackendStore. This is where the
real code happens (usually). In our case this would be: downloading the page,
parsing the content, saving it in the models and returning them on request::

    class LolcatsStore(BackendStore):
        '''
        '''

        # this *must* be set. Because the (most used) MediaServer Coherence also
        # allows other kind of Backends (like remote lights).
        implements = ['MediaServer']

        # This is only for this implementation: the http link to the lolcats rss
        # feed that we want to read and parse:
        rss_url = b"https://icanhas.cheezburger.com/lolcats/rss"

        # As we are going to build a (very small) tree with the items, we need to
        # define the first (the root) item:
        ROOT_ID = 0

        def __init__(self, server, *args, **kwargs):
            # First we initialize our heritage
            BackendStore.__init__(self, server, **kwargs)

            # When a Backend is initialized, the configuration is given as keyword
            # arguments to the initialization. We receive it here as a dictionary
            # and allow some values to be set:
            #       the name of the MediaServer as it appears in the network
            self.name = kwargs.get('name', 'LolCats')

            # timeout between updates in hours:
            self.refresh = int(kwargs.get('refresh', 1)) * (60 * 60)

            # the UPnP device that's hosting that backend, that's already done
            # in the BackendStore.__init__, just left here the sake of completeness
            self.server = server

            # internally used to have a new id for each item
            self.next_id = 1000

            # we store the last update from the rss feed so that we know
            # if we have to parse again, or not:
            self.last_updated = None

            # initialize our lolcats container (no parent, this is the root)
            self.container = BackendContainer(self.ROOT_ID, -1, self.name)

            # but as we also have to return them on 'get_by_id', we have our local
            # store of images per id:
            self.images = {}

            # we tell that if an XBox sends a request for images we'll
            # map the WMC id of that request to our local one
            self.wmc_mapping = {'16': 0}

            # and trigger an update of the data
            dfr = self.update_data()

            # So, even though the initialize is kind of done,
            # Coherence does not yet announce our Media Server.
            # Coherence does wait for signal send by us that we are ready now.
            # And we don't want that to happen as long as we don't have succeeded
            # in fetching some first data, so we delay this signaling after
            # the update is done:
            def init_completed(*args):
                # by setting the following variable to value True, the event
                # system will automatically emmit the corresponding event
                self.init_completed = True

            def init_failed(*args):
                print(f'init_failed: {args}')
                self.on_init_failed(*args, msg='Error on fetching data')

            dfr.addCallback(init_completed)
            dfr.addErrback(init_failed)

            # Now we trigger a function to update the data
            dfr.addCallback(self.queue_update)

        def get_by_id(self, id):
            print("asked for", id, type(id))
            # what ever we are asked for,
            #  we want to return the container only
            if isinstance(id, str):
                id = id.split('@', 1)[0]
            elif isinstance(id, bytes):
                id = id.decode('utf-8').split('@', 1)[0]
            if int(id) == self.ROOT_ID:
                return self.container
            return self.images.get(int(id), None)

        def upnp_init(self):
            # After the signal was triggered,
            # this method is called by coherence and
            # from now on self.server is existing and we can do the
            # necessary setup here that allows us to specify our server
            # options in more detail.

            # Here we define what kind of media content we do provide
            # mostly needed to make some naughty DLNA devices behave
            # will probably move into Coherence internals one day
            self.server.connection_manager_server.set_variable(
                0, 'SourceProtocolInfo',
                ['http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_TN;'
                 'DLNA.ORG_OP=01;DLNA.ORG_FLAGS=00f00000000000000000000000000000',
                 'http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_SM;'
                 'DLNA.ORG_OP=01;DLNA.ORG_FLAGS=00f00000000000000000000000000000',
                 'http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_MED;'
                 'DLNA.ORG_OP=01;DLNA.ORG_FLAGS=00f00000000000000000000000000000',
                 'http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_LRG;'
                 'DLNA.ORG_OP=01;DLNA.ORG_FLAGS=00f00000000000000000000000000000',
                 'http-get:*:image/jpeg:*'])

            # and as it was done after we fetched the data the first time
            # we want to take care about the server wide updates as well
            self._update_container()

        def _update_container(self, result=None):
            # we need to inform Coherence about these changes
            # again this is something that will probably move
            # into Coherence internals one day
            if self.server:
                self.server.content_directory_server.set_variable(
                    0, 'SystemUpdateID', self.update_id)
                value = (self.ROOT_ID, self.container.update_id)
                self.server.content_directory_server.set_variable(
                    0, 'ContainerUpdateIDs', value)
            return result

        def update_loop(self):
            # in the loop we want to call update_data
            dfr = self.update_data()
            # after it was done we want to take care about updating
            # the container
            dfr.addCallback(self._update_container)
            # in ANY case queue an update of the data
            dfr.addBoth(self.queue_update)

        def update_data(self):
            # trigger an update of the data

            # fetch the rss
            dfr = getPage(self.rss_url)

            # push it through our xml parser
            dfr.addCallback(parse_with_lxml)

            # then parse the data into our models
            dfr.addCallback(self.parse_data)

            return dfr

        def parse_data(self, root):
            # from there, we look for the newest update and compare it with the one
            # we have saved. If they are the same, we don't need to go on:
            pub_date = root.find('./channel/lastBuildDate').text

            if pub_date == self.last_updated:
                return

            # not the case, set this as the last update and continue
            self.last_updated = pub_date

            # and reset the children list of the container and the local storage
            self.container.children = []
            self.images = {}

            def iterate(r):
                for item in r.findall('./channel/item'):
                    lol_cat = self._parse_into_lol_cat(item)
                    if lol_cat is None:
                        continue
                    yield lol_cat

            # we go through our entries and do something specific to the
            # lolcats-rss-feed to fetch the data out of it with a task,
            # which will not block our app.
            return task.coiterate(iterate(root))

        def _parse_into_lol_cat(self, item):
            '''
            Convenient method to extract data from an item, create a LolCatsImage
            instance and append this into the LolCatsContainer

            .. versionadded:: 0.8.3
            '''
            title = item.find('title').text
            # Some titles contains non ascii quotes...we fix by replacing it
            title = re.sub("(\u2018|\u2019)", "'", title)

            # We parse the html content of the item in order to extract
            # the image link which is inside of the element parsed below
            # into form of standard html, that is why we parse again.
            try:
                img_html = item.find(
                    '{http://purl.org/rss/1.0/modules/content/}encoded').text
                img_xml = parse_with_lxml(img_html)
            except Exception as e:
                # Something happen when trying to find the link...
                # so... we skip this item by returning None.
                self.error('Error on searching lol cat image: {}'.format(e))
                self.debug('\t - parser fails on:\n{}\n'.format(img_html))
                return None

            # Now gets the image tag and extract the src property
            # from the parsed html block in the previous step.
            url = img_xml.find('img').get('src', None)
            if url is None:
                # It seems that we can find the link...so...
                # again we skip this item by returning None.
                return None

            # Create the LolCatsImage from the info we just extracted,
            # we add it into our container and we register into our
            # self.images dictionary.
            image = LolCatsImage(self.ROOT_ID, self.next_id, title, url)
            self.container.children.append(image)
            self.images[self.next_id] = image

            # increase the next_id entry every time
            self.next_id += 1

            # and increase the container update id and the system update id
            # so that the clients can refresh with the new data
            self.container.update_id += 1
            self.update_id += 1

            # Finally we return the image
            return image

        def queue_update(self, error_or_failure):
            # We use the reactor to queue another updating of our data
            print(error_or_failure)
            reactor.callLater(self.refresh, self.update_loop)

The testing (the old way)
-------------------------
Now you are ready to test your media backend, to do so you can dot it
in different ways but you can tests it directly from the backend script,
like so::

    if __name__ == '__main__':

        # First we import some modules:
        from os.path import join, dirname
        from coherence.base import Coherence
        from coherence.upnp.core.uuid import UUID

        # Generate a unique ID for our server (optional)
        # Note: this can be done by coherence directly
        new_uuid = UUID()

        # The path of the icon for our backend server (optional),
        # and notice that this should be set as a file url
        icon_url = 'file://{}'.format(
            join(dirname(__file__), 'static',
                 'images', 'coherence-icon.png'))

        # Initialize Coherence and our server by passing the keyword plugin
        # into our coherence instance with the right config:
        #     - backend: Should point to your new BackendStore class
        #     - name: Whatever the name you want to set to your new server
        #     - uuid: Unique id to identify your server
        #     - icon: The properties of your server's icon as a dict
        coherence = Coherence(
            {'logmode': 'info',
             'plugin': {'backend': 'LolcatsStore',
                        'name': 'Cohen3 LolcatsStore',
                        'proxy': 'no',
                        'uuid': new_uuid,
                        'icon': {'mimetype': 'image/png',
                                 'width': '256',
                                 'height': '256',
                                 'depth': '24',
                                 'url': icon_url}
                        }
             }
        )

        # initialize the main loop
        reactor.run()

Now you should be able to see your new server with a dlna/UPnP client, but you
can check if it is working via your web browser going to your server ip at port
8080 or use one of this (which should point to your testing machine:

     - http://127.0.0.1:8080
     - http://localhost:8080
