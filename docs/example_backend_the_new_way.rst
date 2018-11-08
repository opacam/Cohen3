    .. _example_backend_the_new_way:

Writing a backend (the new way)
===============================
Here you will learn  how to write a backend from the scratch using the Cohen3
tools :ref:`models <coherence.backends.models (package)>`. We will try to
explain it step by step, using as a model the classic backend LolcatsStore.
This same example is also explained using the module
:ref:`backend <coherence.backend>` and you will get the same result using one
method or another, but with this newer method you will have less lines in your
code and will be more maintainable...so...let's begin...

Introduction (the new way)
--------------------------
This is a Media Backend that allows you to access the cool and cute pictures
from lolcats.com, explained from scratch using the tools from
:ref:`models <coherence.backends.models (package)>`.

The imports (the new way)
-------------------------
We import the re module to clean up quotes in some html code::

    import re

We import the reactor, that allows us to specify an action to happen later::

    from twisted.internet import reactor

And to parse the RSS-Data (which is XML), we use our custom function
parse_with_lxml::

    from coherence.upnp.core.utils import parse_with_lxml

The data itself is stored in BackendItems. They are also the first things we
are going to create::

    from coherence.backends.models.items import BackendImageItem

The entry point for each kind of Backend is a 'BackendStore'. The BackendStore
is the instance that does everything Usually. In this Example it can be
understood as the 'Server', the object retrieving and serving the data::

    from coherence.backends.models.stores import BackendImageStore


To make the data 'renderable' we need to define the DIDLite-Class of the Media
we are providing. For that we have a bunch of helpers that we also want to
import::

    from coherence.upnp.core import DIDLLite

Coherence relies on the Twisted backend. I hope you are familiar with the
concept of deferreds. If not please read:

   http://twistedmatrix.com/projects/core/documentation/howto/async.html

It is a basic concept that you need to understand the following code. But why
am I talking about it? Oh, right, because we use a http-client based on the
twisted.web.client module to do our requests.

The models (the new way)
------------------------
After the download and parsing of the data is done, we want to save it. In
this case, we want to fetch the images and store their URL and the title of
the image. That is the LolCatsImage class::

    class LolCatsImage(BackendImageItem):
        '''
        We inherit from BackendImageItem as it already contains a lot of
        helper methods and implementations. For this simple example,
        we only have to fill the item with data, first we define the mimetype
        of our image, you could change that when initializing your LolCatsImage
        by passing the kwarg `mimetype`.
        '''
        mimetype = 'image/jpeg'

        def __init__(self, parent_id, item_id, urlbase, **kwargs):
            super(LolCatsImage, self).__init__(
                parent_id, item_id, urlbase, **kwargs)

            # each Item.item has to have one or more Resource objects these hold
            # detailed information about the media data and can represent variants
            #  of it (different sizes, transcoded formats)
            res = DIDLLite.Resource(self.location, 'http-get:*:image/jpeg:*')
            res.size = None  # FIXME: we should have a size here
            self.item.res.append(res)

The server (the new way)
------------------------
The LolcatsStore is a media server. As already said before the implementation
of the server is done in an inheritance of a BackendImageStore. This is where the
real code happens (usually). In our case this would be: downloading the page,
parsing the content, saving it in the models and returning them on request. Most
of the work will be done by the base class
:class:`~coherence.backends.models.stores.BackendBaseStore`, but still we must
override some base functions
(:meth:`~coherence.backends.models.stores.BackendBaseStore.parse_data` and
:meth:`~coherence.backends.models.stores.BackendBaseStore.parse_item`) which
will be specific for your media server. Here is an example of how to proceed::

    class LolcatsStore(BackendImageStore):
        '''
        The media server for Lolcats.com.
        '''
        logCategory = 'lolcats'
        implements = ['MediaServer']

        # Here we define what kind of media content we do provide
        # mostly needed to make some naughty DLNA devices behave
        # will probably move into Coherence internals one day
        upnp_protocols = [
            'http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_TN;'
            'DLNA.ORG_OP=01;DLNA.ORG_FLAGS=00f00000000000000000000000000000',
            'http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_SM;'
            'DLNA.ORG_OP=01;DLNA.ORG_FLAGS=00f00000000000000000000000000000',
            'http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_MED;'
            'DLNA.ORG_OP=01;DLNA.ORG_FLAGS=00f00000000000000000000000000000',
            'http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_LRG;'
            'DLNA.ORG_OP=01;DLNA.ORG_FLAGS=00f00000000000000000000000000000',
            'http-get:*:image/jpeg:*']

        # This is only for this implementation: the http link to the lolcats rss
        # feed that we want to read and parse:
        root_url = b"https://icanhas.cheezburger.com/lolcats/rss"
        # The root_find_items defines the tag pointing to the item for our parsed xml
        root_find_items = './channel/item'
        # As we are going to build a (very small) tree with the items, we need to
        # define the first (the root) item:
        root_id = 0

        # The class that defines our Media Server items, this will be used by
        # the LolcatsStore to generate our items
        item_cls = LolCatsImage

        last_updated = ''

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
            self.items = {}

            # we go through our entries and do something specific to the
            # lolcats-rss-feed to fetch the data out of it in a non-blocking
            # way. This operation will could be done be calling the base class,
            # or you could implement your own way. The BackendBaseStore's method
            # meets our needs so...
            return super(LolcatsStore, self).parse_data(root)

        def parse_item(self, item):
            title = item.find('title').text
            # Some titles contains non ascii quotes...
            # we fix it with the help of the re module
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
                # so... we skip this item by returning None
                # and log the failed item.
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

            # Create a dictionary with the data we want into our item,
            # this item will be created automatically by the base class
            # of LolcatsStore using this data.
            data = {
                'title': title,
                'url': url,
            }
            return data

The testing (the new way)
-------------------------
Now you are ready to test your media backend, to do so you can do it
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
8080 or use one of this (which should point to your testing machine):

     - http://127.0.0.1:8080
     - http://localhost:8080

