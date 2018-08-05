__author__ = 'ilya'

from lxml import etree

ELEMENT_TYPE = type(etree.Element("Element"))

UPNP_NS = 'urn:schemas-upnp-org:metadata-1-0/upnp/'
UPNP_EVENT_NS = 'urn:schemas-upnp-org:event-1-0'
UPNP_DEVICE_NS = 'urn:schemas-upnp-org:device-1-0'
UPNP_SERVICE_NS = 'urn:schemas-upnp-org:service-1-0'

DLNA_NS = 'urn:schemas-dlna-org:metadata-1-0'
DLNA_DEVICE_NS = 'urn:schemas-dlna-org:device-1-0'

DC_NS = 'http://purl.org/dc/elements/1.1/'
PV_NS = 'http://www.pv.com/pvns/'

DIDLLITE_NS = 'urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/'

namespaces = {
    DC_NS: 'dc',
    UPNP_NS: 'upnp',
    DLNA_NS: 'dlna',
    PV_NS: 'pv',
    DLNA_DEVICE_NS: 'dev',
    UPNP_EVENT_NS: 'e',
}

for k, v in namespaces.items():
    etree.register_namespace(v, k)
